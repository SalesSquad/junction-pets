// Implemented localhost contract. No sponsor API or authentication claim.
export const endpoints = Object.freeze({ session: '/api/demo/session', catalog: '/api/catalog', policy: '/api/policy', quotes: '/api/quotes', orders: '/api/orders', audit: '/api/audit', auditVerify: '/api/audit/verify', reprice: '/api/demo/reprice', plans: '/api/plans', shock: '/api/demo/shock', jwks: '/.well-known/trusted-trade/jwks.json', buyerKey: '/api/trust/buyer-key', wallet: '/api/demo/wallet', ledger: '/api/demo/ledger', ledgerVerify: '/api/demo/ledger/verify' });
export const metadata = Object.freeze({ mode: 'SYNTHETIC_NONCOMMERCIAL', supplier_id: 'supplier-demo', openapi: '/openapi.json', endpoints,
  approval: 'UNAUTHENTICATED_SYNTHETIC_HUMAN_DECISION', session: 'EPHEMERAL_DEMO_CAPABILITY_NOT_REAL_IDENTITY',
  quoteBody: 'UNSIGNED_kattely.procurement.quote.v2', tradeProof: 'Ed25519_SIGNED_LOCAL_DEMO_KEYS_NOT_REAL_KATTELY_OR_AP2',
  portfolio: 'DETERMINISTIC_MULTI_PRODUCT_OPTIONS_WITH_SYNTHETIC_METRICS', recovery: 'STOCK_SHOCK_REPLANS_WITH_FRESH_APPROVAL',
  settlement: 'DOUBLE_ENTRY_SYNTHETIC_WALLET_REQUIRES_SEPARATE_DEMO_PAYMENT_APPROVAL_NO_PSP',
  families: ['dairy-milk', 'oat-drink'], fixtureDeliveryDate: '2026-11-16' });
const json = (schema) => ({ 'application/json': { schema } });
const ref = (name) => ({ $ref: `#/components/schemas/${name}` });
const object = (properties, required = Object.keys(properties)) => ({ type: 'object', additionalProperties: false, required, properties });
const str = { type: 'string' };
const int = { type: 'integer', minimum: 1 };
const operation = (summary, schema, status = '200', secured = false) => ({ summary,
  ...(secured ? { security: [{ demoCapability: [] }] } : {}),
  ...(schema ? { requestBody: { required: true, content: json(schema) } } : {}),
  responses: { [status]: { description: 'Synthetic result only' }, '400': { description: 'Invalid terms' }, '403': { description: 'Buyer capability or approval refused' }, '409': { description: 'Budget, stock, expiry, state or replay conflict' } } });
const parameter = (name) => ({ name, in: 'path', required: true, schema: str });
export const openapi = {
  openapi: '3.1.0', info: { title: 'Trusted Trade — implemented SYNTHETIC localhost API', version: '0.4.0', description: 'All parties, stock, prices, approvals, emission factors, orders and EUR wallet balances invented. No banking, brokerage or commercial effects. Independent Ed25519 proof-of-possession demo keys are self-attested, not verified identities, Kättely or AP2 certification.' },
  servers: [{ url: '/' }], paths: {
    '/.well-known/trusted-trade': { get: operation('Discover synthetic capabilities') },
    [endpoints.jwks]: { get: operation('Publish ephemeral self-attested demo verification keys, NOT a trusted identity registry') },
    [endpoints.session]: { post: operation('Issue an ephemeral demo buyer capability (not login)', object({ buyerId: str }), '201') },
    [endpoints.catalog]: { get: operation('Read current synthetic product prices, stock and versions') },
    [endpoints.buyerKey]: { post: operation('Register independent buyer agent PUBLIC Ed25519 key in its demo session', object({ buyerId: str, publicJwk: object({ kty: { const: 'OKP' }, crv: { const: 'Ed25519' }, x: str }) }), '201', true) },
    [endpoints.policy]: { get: operation('Read server-owned demo budget and approval threshold') },
    [endpoints.wallet]: { get: operation('Read fictional buyer and supplier wallet balances; demo session required', null, '200', true) },
    [endpoints.ledger]: { get: operation('Inspect in-memory fictional double-entry EUR journal', null, '200', true) },
    [endpoints.ledgerVerify]: { get: operation('Verify balanced postings and local hash-linked settlement receipts', null, '200', true) },
    [endpoints.quotes]: { post: operation('Fix price and check availability; no reservation', ref('QuoteRequest'), '201', true) },
    [endpoints.plans]: { post: operation('Compare deterministic multi-item portfolio plans, no commitment', ref('PortfolioPlanRequest'), '201', true) },
    '/api/plans/{id}/quotes': { parameters: [parameter('id')], post: operation('Fix a server-held option to an immutable synthetic quote', object({ buyerId: str, optionId: { enum: ['cost', 'resilience', 'footprint'] } }), '201', true) },
    '/api/plans/{id}/recover': { parameters: [parameter('id')], post: operation('Replan after disruption; NEVER reuse original quote approval', object({ buyerId: str }), '201', true) },
    '/api/quotes/{id}': { parameters: [parameter('id')], get: operation('Read original quote terms') },
    '/api/quotes/{id}/approval': { parameters: [parameter('id')], post: operation('Explicit unauthenticated synthetic human decision', object({ buyerId: str, decision: { enum: ['approve', 'reject'] }, approver: str }, ['buyerId', 'decision']), '200', true) },
    '/api/quotes/{id}/body': { parameters: [parameter('id')], get: operation('Export UNSIGNED Kättely-compatible quote BODY, not a signed receipt') },
    '/api/quotes/{id}/offer': { parameters: [parameter('id')], post: operation('Supplier signs exact quote using its own ephemeral demo Ed25519 key', object({ buyerId: str }), '201', true) },
    '/api/quotes/{id}/handshake': { parameters: [parameter('id')], post: operation('Verify buyer-process-signed mandate against supplier-signed offer and session public key', object({ buyerId: str, signedMandate: ref('SignedEnvelope') }), '201', true) },
    [endpoints.orders]: { post: operation('Revalidate and commit exactly one simulated order', object({ quoteId: str, buyerId: str, idempotencyKey: { type: 'string', pattern: '^[A-Za-z0-9_-]{10,80}$' } }), '201', true) },
    '/api/orders/{id}': { parameters: [parameter('id')], get: operation('Read simulated receipt') },
    '/api/orders/{id}/cancel': { parameters: [parameter('id')], post: operation('Cancel and restock once', object({ buyerId: str }), '200', true) },
    '/api/orders/{id}/payment': { parameters: [parameter('id')], get: operation('Read owner-session synthetic payment approval, transfer and balances', null, '200', true) },
    '/api/orders/{id}/payment-approval': { parameters: [parameter('id')], post: operation('New fictional human click bound to server-owned supplier payout proposal digest; signed portfolio trade required', object({ buyerId: str, decision: { enum: ['approve', 'reject'] }, proposalDigest: str }), '200', true) },
    '/api/orders/{id}/settlement': { parameters: [parameter('id')], post: operation('Transfer invented EUR from buyer fixture wallet to order-derived fictional suppliers exactly once', object({ buyerId: str, idempotencyKey: { type: 'string', pattern: '^[A-Za-z0-9_-]{10,80}$' } }), '201', true) },
    [endpoints.audit]: { get: operation('Read append-only in-memory demo events') },
    [endpoints.auditVerify]: { get: operation('Verify the in-memory SHA-256 receipt hash chain; no external anchoring') },
    [endpoints.reprice]: { post: operation('Demo-only mutation; invalidates old source versions', object({ sku: str, priceCents: { ...int, maximum: 100000 } }), '200', true) },
    [endpoints.shock]: { post: operation('Synthetic stock outage; triggers a safe recovery flow', object({ sku: str, unitsAvailable: { type: 'integer', minimum: 0, maximum: 1000000 } }), '200', true) },
  }, components: { securitySchemes: { demoCapability: { type: 'http', scheme: 'bearer', description: 'Synthetic session capability only; NOT OAuth or real buyer identity.' } }, schemas: {
    UnsignedQuoteBody: object({ version: { const: 'kattely.procurement.quote.v2' }, quote_id: str,
      supplier_id: { const: 'supplier-demo' }, buyer_id: str, audience: { const: 'https://supplier-demo.invalid' },
      currency: { const: 'EUR' }, issued_at: { type: 'integer' }, expires_at: { type: 'integer' },
      lines: { type: 'array', minItems: 1, items: object({ sku: str, quantity: int, unit: { const: 'L' }, unit_price_cents: int, stock_version: int, supplier_id: str }) },
      total_cents: { ...int, description: 'Sum of quantity * unit_price_cents; all values synthetic net cents.' } }),
    Product: { type: 'object', required: ['sku', 'family', 'lactoseFree', 'unitsAvailable', 'priceCents', 'version', 'deliverBy'], properties: {
      sku: str, family: { enum: ['dairy-milk', 'oat-drink'] }, lactoseFree: { type: 'boolean' }, unitsAvailable: { type: 'integer', minimum: 0 }, priceCents: int, version: int, deliverBy: { type: 'string', format: 'date' } } },
    Quote: { type: 'object', required: ['id', 'buyerId', 'lines', 'totalCents', 'approvalRequired', 'status', 'createdAtMs', 'expiresAtMs', 'explanation'], properties: {
      id: str, buyerId: str, totalCents: int, approvalRequired: { type: 'boolean' }, status: str, createdAtMs: { type: 'integer' }, expiresAtMs: { type: 'integer' }, explanation: str,
      lines: { type: 'array', items: ref('QuoteLine') } } },
    Order: { type: 'object', required: ['id', 'buyerId', 'quoteId', 'status', 'totalCents', 'commitment'], properties: {
      id: str, buyerId: str, quoteId: str, status: { enum: ['SIMULATED_COMMITTED', 'SIMULATED_CANCELLED'] }, totalCents: int, commitment: { const: 'SIMULATION_ONLY_NO_REAL_PURCHASE' }, idempotentReplay: { type: 'boolean' },
      paymentEligible: { type: 'boolean' }, verifiedQuoteBodyDigest: { type: ['string', 'null'] } } },
    SyntheticWallet: { type: 'object', required: ['mode', 'currency', 'buyerBalanceCents', 'suppliers'], properties: {
      mode: { const: 'SYNTHETIC_IN_MEMORY_NO_BANK_TRANSFER' }, currency: { const: 'EUR' },
      buyerBalanceCents: { type: 'integer', minimum: 0 }, initialBuyerFundsCents: int,
      suppliers: { type: 'array', items: object({ account: str, balanceCents: { type: 'integer', minimum: 0 } }) } } },
    SyntheticPayment: { type: 'object', required: ['proposal', 'approval', 'transfer', 'wallet'], properties: {
      proposal: { type: 'object', required: ['orderId', 'amountCents', 'allocations', 'digest'], properties: {
        orderId: str, amountCents: int, digest: str, signedQuoteBodyDigest: str,
        currency: { const: 'EUR' }, rail: { const: 'IN_MEMORY_NO_BANK_OR_PSP' },
        allocations: { type: 'array', items: object({ supplierId: str, amountCents: int }) } } },
      approval: { type: ['object', 'null'] }, transfer: { type: ['object', 'null'] }, wallet: ref('SyntheticWallet'),
      idempotentReplay: { type: 'boolean' } } },
    BuyingNeed: object({ family: { enum: ['dairy-milk', 'oat-drink'] }, quantityLitres: { ...int, maximum: 10000 }, lactoseFree: { type: 'boolean' }, deliverBy: { const: '2026-11-16' } }),
    PortfolioPlanRequest: object({ buyerId: str, requirements: { type: 'array', minItems: 2, maxItems: 2, items: ref('BuyingNeed') }, budgetCents: { ...int, maximum: 250000 } }),
    QuoteLine: object({ sku: str, name: str, quantityLitres: int, unitPriceCents: int, totalCents: int,
      stockVersion: int, certification: str, deliverBy: str, family: str, supplierId: str,
      reliabilityBps: int, emissionsGramsPerL: int },
      ['sku', 'name', 'quantityLitres', 'unitPriceCents', 'totalCents', 'stockVersion', 'certification', 'deliverBy']),
    PortfolioOption: { type: 'object', required: ['id', 'totalCents', 'lines', 'withinBudget', 'carbonKgEstimate', 'riskScorePct'], properties: {
      id: { enum: ['cost', 'resilience', 'footprint'] }, title: str, explanation: str, totalCents: int, equivalentTo: { type: ['string', 'null'] },
      lines: { type: 'array', items: ref('QuoteLine') }, withinBudget: { type: 'boolean' },
      carbonKgEstimate: { type: 'number', description: 'Fictional kg-equivalent estimate; not certified environmental information' },
      riskScorePct: { type: 'number', description: 'Synthetic heuristic; not probability of real supplier failure' },
      largestSupplierExposurePct: { type: 'number' }, supplierCount: int } },
    PortfolioPlan: { type: 'object', required: ['id', 'buyerId', 'requirements', 'options', 'recommendedOptionId', 'expiresAtMs'], properties: {
      id: str, buyerId: str, requirements: { type: 'array', items: ref('BuyingNeed') },
      options: { type: 'array', items: ref('PortfolioOption') }, recommendedOptionId: str,
      expiresAtMs: { type: 'integer' }, recoveredFrom: str, humanApprovalCarriedOver: { type: 'boolean' } } },
    SignedEnvelope: object({ protected: object({ typ: { const: 'kattely.demo.procurement-envelope.v1' }, alg: { const: 'EdDSA' }, kid: str }),
      payload: { type: 'object' }, signature: str }),
    TradeProof: { type: 'object', required: ['mode', 'signedOffer', 'signedMandate', 'verification'], properties: {
      mode: { const: 'SELF_ATTESTED_EPHEMERAL_DEMO_KEYS' }, proofType: str,
      signedOffer: ref('SignedEnvelope'), signedMandate: ref('SignedEnvelope'), verification: { type: 'object' } } },
    QuoteRequest: { ...object({ buyerId: str, need: ref('BuyingNeed'), requestText: str, budgetCents: { ...int, maximum: 250000 } }, ['buyerId']), oneOf: [{ required: ['need'], not: { required: ['requestText'] } }, { required: ['requestText'], not: { required: ['need'] } }] },
  } },
};

// Response schemas expose the actual local wire data, especially the unsigned interop body.
const successSchema = (path, method, schema) => {
  const responses = openapi.paths[path][method].responses;
  const code = responses['201'] ? '201' : '200';
  responses[code].content = json(schema);
};
successSchema(endpoints.session, 'post', object({ token: str, buyerId: str, mode: { const: 'SYNTHETIC_NOT_AUTHENTICATED' } }));
successSchema(endpoints.catalog, 'get', object({ mode: { const: 'INVENTED_FIXTURE' }, products: { type: 'array', items: ref('Product') } }));
for (const [path, method] of [[endpoints.quotes, 'post'], ['/api/quotes/{id}', 'get'], ['/api/quotes/{id}/approval', 'post']]) successSchema(path, method, object({ quote: ref('Quote') }));
successSchema(endpoints.plans, 'post', object({ plan: ref('PortfolioPlan') }));
successSchema('/api/plans/{id}/recover', 'post', object({ plan: ref('PortfolioPlan') }));
successSchema('/api/plans/{id}/quotes', 'post', object({ quote: ref('Quote') }));
successSchema('/api/quotes/{id}/offer', 'post', object({ signedOffer: ref('SignedEnvelope') }));
successSchema('/api/quotes/{id}/handshake', 'post', object({ proof: ref('TradeProof') }));
for (const [path, method] of [[endpoints.orders, 'post'], ['/api/orders/{id}', 'get'], ['/api/orders/{id}/cancel', 'post']]) successSchema(path, method, object({ order: ref('Order') }));
successSchema(endpoints.wallet, 'get', object({ wallet: ref('SyntheticWallet') }));
for (const [path, method] of [['/api/orders/{id}/payment', 'get'], ['/api/orders/{id}/payment-approval', 'post'], ['/api/orders/{id}/settlement', 'post']]) successSchema(path, method, ref('SyntheticPayment'));
successSchema('/api/quotes/{id}/body', 'get', object({ mode: { const: 'SYNTHETIC' }, signature: { const: 'UNSIGNED' }, body: ref('UnsignedQuoteBody') }));
