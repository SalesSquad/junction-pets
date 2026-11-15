/** Independent read-only diagnostic client. No supplier/core import or POST. */
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { diagnoseProcurement, DiagnosticError } from './procurement-diagnostics.mjs';

const refuse = (code, message) => { throw new DiagnosticError(code, message); };

export function parseDiagnosticArgs(args) {
  const values = {};
  for (const arg of args) {
    const match = arg.match(/^--(milk-litres|oat-litres|budget-cents)=(0|[1-9]\d*)$/);
    if (!match || Object.hasOwn(values, match[1])) {
      refuse('INVALID_ARGUMENT', 'Use unique --milk-litres=N, --oat-litres=N and --budget-cents=N whole-number options.');
    }
    const value = Number(match[2]);
    const max = match[1] === 'budget-cents' ? 5_000_000 : 10_000;
    if (!Number.isSafeInteger(value) || value > max || (match[1] === 'budget-cents' && !value)) {
      refuse('INVALID_ARGUMENT', 'Litres must be 0–10000 and the optional budget 1–5000000 integer cents.');
    }
    values[match[1]] = value;
  }
  const milk = values['milk-litres'] ?? (values['oat-litres'] === undefined ? 1000 : 0);
  const oat = values['oat-litres'] ?? 0;
  if (!milk && !oat) refuse('INVALID_ARGUMENT', 'At least one positive product quantity is required.');
  return { milk, oat, budgetCents: values['budget-cents'] };
}

export async function runDiagnostics({ args = [], supplierUrl = 'http://127.0.0.1:4177' } = {}) {
  const quantities = parseDiagnosticArgs(args);
  const base = new URL(supplierUrl);
  if (base.protocol !== 'http:' || !['127.0.0.1', 'localhost', '[::1]'].includes(base.hostname) ||
      base.username || base.password || base.pathname !== '/' || base.search || base.hash) {
    refuse('LOCALHOST_ONLY', 'Use a plain localhost HTTP origin for this invented-catalog diagnostic.');
  }
  const requests = [];
  const read = async (path) => {
    if (typeof path !== 'string' || !path.startsWith('/') || path.startsWith('//')) {
      refuse('DISCOVERY_REFUSED', 'Discovery must name origin-relative public read endpoints.');
    }
    const url = new URL(path, base);
    if (url.origin !== base.origin || url.username || url.password || url.search || url.hash) {
      refuse('DISCOVERY_REFUSED', 'Discovery cannot select another origin, credentials or hidden query terms.');
    }
    const response = await fetch(url, { method: 'GET', redirect: 'error', signal: AbortSignal.timeout(5000) });
    requests.push({ method: 'GET', path: url.pathname, status: response.status });
    if (!response.ok) refuse('SUPPLIER_READ_FAILED', 'The public synthetic supplier read failed.');
    const chunks = [];
    let size = 0;
    for await (const chunk of response.body) {
      size += chunk.length;
      if (size > 1_048_576) refuse('RESPONSE_TOO_LARGE', 'Synthetic read exceeded the bounded diagnostic response size.');
      chunks.push(chunk);
    }
    return JSON.parse(Buffer.concat(chunks).toString('utf8'));
  };
  const discovery = await read('/.well-known/trusted-trade');
  if (discovery.mode !== 'SYNTHETIC_NONCOMMERCIAL' || discovery.fixtureDeliveryDate !== '2026-11-16') {
    refuse('SUPPLIER_MODE_REFUSED', 'Only the explicitly invented local fixture contract is supported.');
  }
  const spec = await read(discovery.openapi);
  const routes = discovery.endpoints;
  for (const capability of ['catalog', 'policy']) {
    if (routes?.[capability] !== '/api/' + capability || !spec.paths?.[routes[capability]]?.get) {
      refuse('DISCOVERY_REFUSED', 'Require documented public catalog and policy GET capabilities.');
    }
  }
  const policy = await read(routes.policy);
  const catalog = await read(routes.catalog);
  if (catalog.mode !== 'INVENTED_FIXTURE') refuse('SUPPLIER_MODE_REFUSED', 'Catalog must be explicitly invented fixture data.');
  const requirements = [];
  for (const [family, quantityLitres] of [['dairy-milk', quantities.milk], ['oat-drink', quantities.oat]]) {
    if (quantityLitres) requirements.push({ family, quantityLitres, lactoseFree: true, deliverBy: discovery.fixtureDeliveryDate });
  }
  return {
    ...diagnoseProcurement({ catalog: catalog.products, requirements,
      budgetCents: quantities.budgetCents ?? policy.perOrderBudgetCents,
      policyBudgetCents: policy.perOrderBudgetCents, deliveryFeeCents: policy.deliveryFeeCents, taxBps: policy.taxBps }),
    observedAt: new Date().toISOString(),
    readConsistency: 'Separate public reads, not an atomic or reserved inventory snapshot.',
    requests,
  };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const result = await runDiagnostics({ args: process.argv.slice(2), supplierUrl: process.env.SUPPLIER_URL });
    process.stdout.write(JSON.stringify(result, null, 2) + '\n');
  } catch (error) {
    process.stderr.write(JSON.stringify({ error: { code: error.code ?? 'DIAGNOSTIC_FAILED', message: error.message } }) + '\n');
    process.exitCode = 1;
  }
}
