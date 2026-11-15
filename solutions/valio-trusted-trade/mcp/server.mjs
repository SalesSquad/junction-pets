/** Optional official MCP v2 stdio adapter. Never a sponsor/production endpoint. */
import { McpServer, acceptedContent, inputRequired, CLIENT_CAPABILITIES_META_KEY } from '@modelcontextprotocol/server';
import { serveStdio } from '@modelcontextprotocol/server/stdio';
import * as z from 'zod/v4';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { BridgeError, createTradeClient, privateHostCredentialFile } from './trade-client.mjs';

const identifier = z.string().regex(/^[A-Za-z0-9_-]{1,100}$/);
const commandKey = z.string().regex(/^[A-Za-z0-9_-]{10,80}$/);
const need = z.object({ family: z.enum(['dairy-milk', 'oat-drink']), lactoseFree: z.boolean(),
  quantityLitres: z.number().int().min(1).max(10000), deliverBy: z.string().regex(/^\d{4}-\d{2}-\d{2}$/) }).strict();
const runInput = z.object({ runId: identifier }).strict();
const actionInput = z.object({ runId: identifier, commandKey }).strict();
const formSchema = z.object({ decision: z.enum(['approve', 'reject']) }).strict();
const outputSchema = z.object({ mode: z.literal('SYNTHETIC'),
  lifetime: z.enum(['MEMORY_NON_RESUMABLE', 'PRIVATE_LOCAL_SQLITE']), ok: z.boolean(),
  data: z.record(z.string(), z.unknown()),
  error: z.object({ code: z.string(), retryable: z.boolean(), nextActions: z.array(z.string()) }).strict().optional() }).strict();

function compact(result) {
  const run = result.run;
  const q = result.quote;
  const out = { ...(run ? { run: Object.fromEntries(['id', 'quoteId', 'reviewId', 'planId', 'orderId', 'status'].map(k => [k, run[k] ?? null])) } : {}),
    nextActions: [...new Set((result.nextActions ?? []).map(action => ({
      request_human_approval: 'review_purchase', reject: 'review_purchase',
      verify_signed_mandate: 'commit_purchase', commit_purchase: 'commit_purchase',
      request_separate_payment_approval: 'settle_purchase', settle_payment: 'settle_purchase',
      cancel_refund: 'cancel_purchase', prepare_new_purchase: 'prepare_purchase', view_receipt: 'purchase_status',
    })[action] ?? 'purchase_status'))] };
  if (q) out.quote = { id: q.id, snapshotId: q.snapshotId, totalCents: q.totalCents, currency: 'EUR',
    status: q.status, expiresAtMs: q.expiresAtMs, approvalRequired: q.approvalRequired,
    budgetException: q.budgetException ?? null, costBreakdown: q.costBreakdown,
    lines: q.lines?.map(line => ({ sku: line.sku, quantityLitres: line.quantityLitres, packs: line.packs,
      packLitres: line.packLitres, totalCents: line.totalCents })) };
  if (result.review) out.review = { id: result.review.id, status: result.review.status,
    diagnosis: result.review.diagnosis?.outcome, minimumCostCents: result.review.diagnosis?.minimumCostCents,
    additionalBudgetCents: result.review.diagnosis?.additionalBudgetCents, missingLitres: result.review.diagnosis?.missingLitres };
  if (result.order) out.order = { id: result.order.id, status: result.order.status, totalCents: result.order.totalCents };
  if (result.payment) out.payment = { status: result.payment.transfer?.status ?? null,
    amountCents: result.payment.proposal?.amountCents ?? null };
  return out;
}

export function createBridgeServer(client, requestContext = { era: 'modern' }) {
  const server = new McpServer({ name: 'valio-synthetic-trade', version: '0.1.0' },
    { capabilities: { tools: {} } });
  let queue = Promise.resolve();
  const result = data => {
    const structuredContent = { mode: 'SYNTHETIC', lifetime: client.lifetime, ok: true, data };
    return { content: [{ type: 'text', text: JSON.stringify(structuredContent) }], structuredContent };
  };
  const failure = (error, toolName) => {
    const code = typeof error?.code === 'string' && /^[A-Z0-9_]{1,80}$/.test(error.code) ? error.code : 'BRIDGE_REFUSED';
    const structuredContent = { mode: 'SYNTHETIC', lifetime: client.lifetime, ok: false, data: {},
      error: { code, retryable: error?.retryable === true,
        nextActions: code === 'HOST_DECISION_REQUIRED' ?
          ['A trusted host must obtain and sign this exact human decision outside model arguments. A synthetic MCP form or approval role is insufficient.'] :
          code === 'INTEGRATION_NOT_CONFIGURED' ?
          ['An operator must configure the server-side sponsor mock integration. Never submit a vendor key, customer ID or URL to this tool.'] :
          toolName === 'lookup_valio_mock' ? [error?.retryable ?
            'Retry lookup_valio_mock with the same narrowed product IDs and date after the server delay.' :
            'Review the product/date input or ask the operator to inspect sponsor schema. Missing data is never zero stock or authority.'] :
          error?.retryable ? ['Inspect purchase_status; retry the identical command key.'] :
          ['Inspect purchase_status or revise the request; no authority was inferred.'] } };
    return { isError: true, content: [{ type: 'text', text: JSON.stringify(structuredContent) }], structuredContent };
  };
  const register = (name, schema, description, annotations, handler) => {
    server.registerTool(name, { description, inputSchema: schema, outputSchema, annotations },
      (args, context) => {
        const execute = async () => { try { return await handler(args, context); } catch (error) { return failure(error, name); } };
        const pending = queue.then(execute, execute); queue = pending.then(() => undefined, () => undefined);
        return pending;
      });
  };
  const hints = (readOnlyHint, destructiveHint) => ({ readOnlyHint, destructiveHint, idempotentHint: true, openWorldHint: false });
  const confirm = async (ctx, challenge, key) => {
    if (challenge.authorization) return challenge.authorization.decision;
    const capabilities = requestContext.era === 'legacy' ? server.server.getClientCapabilities() :
      ctx.mcpReq.envelope?.[CLIENT_CAPABILITIES_META_KEY];
    if (!capabilities?.elicitation?.form) throw new BridgeError('HUMAN_CONFIRMATION_UNAVAILABLE');
    let content;
    if (requestContext.era === 'legacy') {
      try {
        const response = await ctx.mcpReq.elicitInput({ mode: 'form', message: challenge.message,
          requestedSchema: { type: 'object', properties: { decision: { type: 'string', title: 'Explicit fictional human decision',
            enum: ['approve', 'reject'] } }, required: ['decision'], additionalProperties: false } });
        if (response.action !== 'accept') return null;
        content = formSchema.parse(response.content);
      } catch { throw new BridgeError('HUMAN_CONFIRMATION_UNAVAILABLE'); }
    } else {
      const token = ctx.mcpReq.requestState();
      if (!token) return inputRequired({ requestState: challenge.token, inputRequests: {
        confirmation: inputRequired.elicit({ message: challenge.message,
          requestedSchema: { type: 'object', properties: { decision: { type: 'string',
            title: 'Explicit fictional human decision', enum: ['approve', 'reject'] } },
            required: ['decision'], additionalProperties: false } }) } });
      client.checkChallenge(key, token, challenge.binding);
      content = acceptedContent(ctx.mcpReq.inputResponses, 'confirmation', formSchema);
      if (!content) return null;
    }
    client.authorizeChallenge(key, challenge.token, challenge.binding, content.decision);
    return content.decision;
  };
  register('search_products', z.object({ query: z.string().min(2).max(160),
    limit: z.number().int().min(1).max(10).default(5) }).strict(),
  'Read a small, advisory candidate set from the invented local catalog. Never proves allergens, stock or purchase authority.',
  hints(true, false), async ({ query, limit }) => {
    const value = await client.search(query, limit);
    return result({ mode: value.mode, reason: value.reason, candidates: value.candidates?.map(c => ({
      sku: c.sku, name: c.name, family: c.family, provenance: c.provenance, requiresTradeCoreValidation: true })) ?? [] });
  });
  register('lookup_valio_mock', z.object({
    products: z.array(z.string().regex(/^[0-9]{1,12}$/)).min(1).max(20)
      .refine(values => new Set(values).size === values.length, 'Product IDs must be distinct.'),
    requestedDate: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).refine(value =>
      Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value, 'Use a valid ISO date.'),
  }).strict(),
  'Read only the requested sponsor MOCK product/date observations through the configured local server. Units, prices and sentinel stock remain unqualified source facts; no order authority or fixture promotion. Accepts numeric catalog product IDs only (1–12 digits); never submit personal identifiers, credentials, customer or URL.',
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true }, async input => {
    const observed = await client.lookupValioMock(input);
    if (observed.mode !== 'SPONSOR_MOCK_READ_ONLY' || observed.requiresTradeCoreValidation !== true ||
        observed.provenance?.provider !== 'VALIO_JUNCTION_MOCK_API' || observed.provenance?.origin !== 'https://junction26.valioaimo.fi' ||
        !Array.isArray(observed.classifications) || observed.classifications.length > input.products.length ||
        observed.classifications.some(item => !input.products.includes(item.productId)) ||
        new Set(observed.classifications.map(item => item.productId)).size !== observed.classifications.length) {
      throw new BridgeError('INVALID_SPONSOR_RESPONSE');
    }
    const priceById = new Map((observed.prices?.products ?? []).map(item => [item.productId, item]));
    const sourceNumber = value => typeof value === 'number' && Number.isFinite(value) ? value : 'UNMAPPED';
    const priceSummary = id => {
      const price = priceById.get(id);
      return { currency: /^[A-Z]{3}$/.test(observed.prices?.currency ?? '') ? observed.prices.currency : 'UNMAPPED',
        catalogValue: sourceNumber(price?.catalogPrice?.value),
        catalogValueWithTax: sourceNumber(price?.catalogPrice?.valueWithTax),
        netPriceFound: typeof price?.netPriceFound === 'boolean' ? price.netPriceFound : 'UNMAPPED',
        error: typeof price?.error === 'boolean' ? price.error : 'UNMAPPED',
        interpretation: 'OPAQUE_SOURCE_ONLY_NOT_NET_OFFER' };
    };
    return result({ mode: observed.mode, requiresTradeCoreValidation: true,
      missingProductIds: input.products.filter(id => !observed.classifications.some(item => item.productId === id)),
      products: observed.classifications.map(item => ({
        productId: item.productId, purchasingAuthority: 'NONE', availability: item.availability,
        cutoff: item.cutoff, netPrice: item.netPrice, observedPrice: priceSummary(item.productId),
        scheduleLineCount: item.scheduleFacts?.length ?? 0,
        scheduleFacts: (item.scheduleFacts ?? []).slice(0, 5).map(line => ({
          salesBlocked: line.salesBlocked, stock: line.stock, sourceAmount: line.sourceAmount,
          sourceUnit: line.sourceUnit, unitInterpretation: 'UNMAPPED',
        })), scheduleFactsTruncated: (item.scheduleFacts?.length ?? 0) > 5,
      })), provenance: {
        provider: observed.provenance.provider, origin: observed.provenance.origin,
        observedAt: observed.provenance.observedAt, requestedDate: observed.provenance.requestedDate,
        availability: { endpoint: observed.provenance.availability?.endpoint,
          sha256: observed.provenance.availability?.sha256, providerTime: observed.provenance.availability?.providerTime },
        prices: { endpoint: observed.provenance.prices?.endpoint,
          sha256: observed.provenance.prices?.sha256, pricingDate: observed.provenance.prices?.pricingDate },
        interpretation: observed.provenance.interpretation,
        limitations: observed.provenance.limitations?.filter(value => typeof value === 'string').slice(0, 20),
      }, cache: { hit: observed.cache?.hit, ageMs: observed.cache?.ageMs, ttlMs: observed.cache?.ttlMs },
      nextActions: ['Treat these as source observations only; a separate validated trade-core quote is required.'] });
  });
  register('prepare_purchase', z.object({ commandKey, budgetCents: z.number().int().min(1).max(250000),
    requirements: z.array(need).min(1).max(2).refine(list => new Set(list.map(n => n.family)).size === list.length,
      'Each product family must appear once.') }).strict(),
  'Prepare exact whole-pack requirements and a fixed synthetic quote. Use one stable commandKey on retries; this grants no approval, order or payment.',
  hints(false, false), async args => result(compact(await client.prepare(args))));
  register('purchase_status', runInput,
    'Read the latest owner-session workflow status and next actions. Reconcile this after timeout before retrying an identical command.',
    hints(true, false), async ({ runId }) => result(compact(await client.status(runId))));
  register('review_purchase', actionInput,
    'Request an actual host interaction for the displayed synthetic quote only. Model arguments cannot grant approval or raise a future budget. No real approver identity is claimed.',
    hints(false, true), async ({ runId, commandKey: key }, ctx) => {
      const context = await client.reviewContext(runId);
      if ((client.hostAuthenticated && context.q.status === 'AWAITING_HUMAN_APPROVAL') ||
          (context.q.status === 'APPROVED' && !context.callerScopeAccepted)) {
        return result(compact(await client.decide(runId, key, 'approve', context.binding)));
      }
      if (['APPROVED', 'AUTO_COMMIT_ELIGIBLE', 'REJECTED', 'SIMULATED_COMMITTED', 'SIMULATED_CANCELLED'].includes(context.q.status)) {
        return result(compact(context.full));
      }
      const delta = context.q.budgetException?.additionalCents ?? 0;
      const challenge = client.challenge(key, 'review', runId, context.binding,
        'SYNTHETIC ONLY: approve quote ' + context.q.id + ' / source ' + context.q.snapshotId +
        ' for ' + context.q.totalCents + ' EUR cents? Quote-only extra budget: ' + delta +
        ' cents. Exact original product/diet/quantity/date requirements remain mandatory; no real supplier is connected.');
      const decision = await confirm(ctx, challenge, key);
      if (decision && typeof decision === 'object') return decision;
      if (!decision) return result({ ...compact(context.full), approval: 'NOT_GRANTED' });
      return result(compact(await client.decide(runId, key, decision, context.binding)));
    });
  register('commit_purchase', actionInput,
    'Commit exactly one already-approved synthetic quote with an independently held buyer key. Verifies original caller intent, packs, budget, prices and signed body; never self-approves or pays.',
    hints(false, true), async ({ runId, commandKey: key }) => result(compact(await client.commit(runId, key))));
  register('cancel_purchase', actionInput,
    'Cancel the owned synthetic order and reverse any fictional payment once. No external supplier or bank is contacted.',
    hints(false, true), async ({ runId, commandKey: key }) => result(compact(await client.cancel(runId, key))));
  register('settle_purchase', actionInput,
    'Request separate host confirmation for the exact synthetic payment proposal, then settle once. Purchase approval is not payment approval; never moves real funds.',
    hints(false, true), async ({ runId, commandKey: key }, ctx) => {
      const context = await client.paymentContext(runId);
      if (context.pay.transfer) return result(compact(await client.status(runId)));
      if (client.hostAuthenticated) return result(compact(await client.settle(runId, key, context.binding, context.pay.proposal.digest)));
      const challenge = client.challenge(key, 'payment', runId, context.binding, context.message,
        { proposalDigest: context.pay.proposal.digest });
      const decision = await confirm(ctx, challenge, key);
      if (decision && typeof decision === 'object') return decision;
      if (decision !== 'approve') return result({ ...compact(await client.status(runId)), paymentApproval: 'NOT_GRANTED', nextActions: ['A rejected command key stays rejected. Use a new commandKey only for a deliberate new payment decision.'] });
      return result(compact(await client.settle(runId, key, context.binding, context.pay.proposal.digest)));
    });
  return server;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const hostFile = process.env.VALIO_HOST_ACCESS_TOKEN_FILE;
    const proofFile = process.env.VALIO_HOST_DECISION_PROOF_FILE;
    if (proofFile !== undefined && hostFile === undefined) throw new BridgeError('HOST_PROVIDER_CONFIG_INVALID');
    const client = await createTradeClient({ baseUrl: process.env.SUPPLIER_URL ?? 'http://127.0.0.1:4177',
      stateFile: process.env.VALIO_AGENT_STATE_FILE,
      ...(hostFile === undefined ? {} : { hostAccessToken: privateHostCredentialFile(hostFile) }),
      ...(proofFile === undefined ? {} : { hostDecisionProof: privateHostCredentialFile(proofFile) }) });
    const handle = serveStdio(context => createBridgeServer(client, context),
      { onerror: () => process.stderr.write('Synthetic MCP protocol operation refused.\n') });
    const close = () => { client.close(); void handle.close(); };
    process.once('SIGTERM', close); process.once('SIGINT', close); process.stdin.once('end', () => client.close());
  } catch (error) {
    process.stderr.write('Synthetic MCP startup refused: ' +
      (typeof error?.code === 'string' && /^[A-Z0-9_]{1,80}$/.test(error.code) ? error.code : 'BRIDGE_INITIALIZATION_FAILED') + '\n');
    process.exitCode = 1;
  }
}
