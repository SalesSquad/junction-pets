// Implemented localhost contract. No sponsor API or authentication claim.
export const endpoints = Object.freeze({ session: '/api/demo/session', catalog: '/api/catalog', policy: '/api/policy', quotes: '/api/quotes', reviews: '/api/reviews', orders: '/api/orders', audit: '/api/audit', reprice: '/api/demo/reprice' });
export const metadata = Object.freeze({ mode: 'SYNTHETIC_NONCOMMERCIAL', supplier_id: 'supplier-demo', openapi: '/openapi.json', endpoints,
  approval: 'UNAUTHENTICATED_SYNTHETIC_HUMAN_DECISION', session: 'EPHEMERAL_DEMO_CAPABILITY_NOT_REAL_IDENTITY',
  quoteBody: 'UNSIGNED_kattely.procurement.quote.v1', families: ['dairy-milk', 'oat-drink'], fixtureDeliveryDate: '2026-11-16' });
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
  openapi: '3.1.0', info: { title: 'Trusted Trade — implemented SYNTHETIC localhost API', version: '0.3.0', description: 'All parties, stock, prices, approvals and orders invented. No commercial effects. Demo capabilities are not verified identities.' },
  servers: [{ url: '/' }], paths: {
    '/.well-known/trusted-trade': { get: operation('Discover synthetic capabilities') },
    [endpoints.session]: { post: operation('Issue an ephemeral demo buyer capability (not login)', object({ buyerId: str }), '201') },
    [endpoints.catalog]: { get: operation('Read current synthetic product prices, stock and versions') },
    [endpoints.policy]: { get: operation('Read server-owned demo budget and approval threshold') },
    [endpoints.quotes]: { post: operation('Fix price and check availability; no reservation', ref('QuoteRequest'), '201', true) },
    [endpoints.reviews]: { post: operation('Diagnose and propose a fixed quote from one coherent synthetic source snapshot; creates no approval', ref('QuoteRequest'), '201', true) },
    '/api/reviews/{id}/decision': { parameters: [parameter('id')], post: operation('Decide the exact displayed quote/snapshot; any budget exception applies only to that quote', ref('ReviewDecision'), '200', true) },
    '/api/quotes/{id}': { parameters: [parameter('id')], get: operation('Read original quote terms') },
    '/api/quotes/{id}/approval': { parameters: [parameter('id')], post: operation('Explicit unauthenticated synthetic human decision', object({ buyerId: str, decision: { enum: ['approve', 'reject'] }, approver: str }, ['buyerId', 'decision']), '200', true) },
    '/api/quotes/{id}/body': { parameters: [parameter('id')], get: operation('Export UNSIGNED Kättely-compatible quote BODY, not a signed receipt') },
    [endpoints.orders]: { post: operation('Revalidate and commit exactly one simulated order', object({ quoteId: str, buyerId: str, idempotencyKey: { type: 'string', pattern: '^[A-Za-z0-9_-]{10,80}$' } }), '201', true) },
    '/api/orders/{id}': { parameters: [parameter('id')], get: operation('Read simulated receipt') },
    '/api/orders/{id}/cancel': { parameters: [parameter('id')], post: operation('Cancel and restock once', object({ buyerId: str }), '200', true) },
    [endpoints.audit]: { get: operation('Read append-only in-memory demo events') },
    [endpoints.reprice]: { post: operation('Demo-only mutation; invalidates old source versions', object({ sku: str, priceCents: { ...int, maximum: 100000 } }), '200', true) },
  }, components: { securitySchemes: { demoCapability: { type: 'http', scheme: 'bearer', description: 'Synthetic session capability only; NOT OAuth or real buyer identity.' } }, schemas: {
    UnsignedQuoteBody: object({ version: { const: 'kattely.procurement.quote.v1' }, quote_id: str,
      supplier_id: { const: 'supplier-demo' }, buyer_id: str, audience: { const: 'https://supplier-demo.invalid' },
      currency: { const: 'EUR' }, issued_at: { type: 'integer' }, expires_at: { type: 'integer' },
      lines: { type: 'array', minItems: 1, items: object({ sku: str, quantity: int, unit: { const: 'L' }, unit_price_cents: int, stock_version: int }) },
      total_cents: { ...int, description: 'Sum of quantity * unit_price_cents; all values synthetic net cents.' } }),
    Product: { type: 'object', required: ['sku', 'family', 'lactoseFree', 'unitsAvailable', 'priceCents', 'version', 'deliverBy'], properties: {
      sku: str, family: { enum: ['dairy-milk', 'oat-drink'] }, lactoseFree: { type: 'boolean' }, unitsAvailable: { type: 'integer', minimum: 0 }, priceCents: int, version: int, deliverBy: { type: 'string', format: 'date' } } },
    Quote: { type: 'object', required: ['id', 'buyerId', 'lines', 'totalCents', 'approvalRequired', 'status', 'createdAtMs', 'expiresAtMs', 'explanation'], properties: {
      id: str, buyerId: str, totalCents: int, approvalRequired: { type: 'boolean' }, status: str, createdAtMs: { type: 'integer' }, expiresAtMs: { type: 'integer' }, explanation: str,
      lines: { type: 'array', items: object({ sku: str, name: str, quantityLitres: int, unitPriceCents: int, totalCents: int, stockVersion: int, certification: str, deliverBy: str }) } } },
    Order: { type: 'object', required: ['id', 'buyerId', 'quoteId', 'status', 'totalCents', 'commitment'], properties: {
      id: str, buyerId: str, quoteId: str, status: { enum: ['SIMULATED_COMMITTED', 'SIMULATED_CANCELLED'] }, totalCents: int, commitment: { const: 'SIMULATION_ONLY_NO_REAL_PURCHASE' }, idempotentReplay: { type: 'boolean' } } },
    BuyingNeed: object({ family: { enum: ['dairy-milk', 'oat-drink'] }, quantityLitres: { ...int, maximum: 10000 }, lactoseFree: { type: 'boolean' }, deliverBy: { const: '2026-11-16' } }),
    ReviewDecision: object({ buyerId: str, decision: { enum: ['approve', 'reject'] }, snapshotId: str, quoteId: str }),
    SourceSnapshot: object({ id: str, observedAtMs: { type: 'integer' }, mode: { const: 'INVENTED_FIXTURE' },
      stockReserved: { const: false }, products: { type: 'array', items: ref('Product') },
      policy: { type: 'object' }, constraints: ref('BuyingNeed') }),
    ProcurementReview: object({ id: str, buyerId: str, snapshotId: str, sourceSnapshot: ref('SourceSnapshot'),
      requested: ref('BuyingNeed'), originalBudgetCents: int, diagnosis: { type: 'object',
        required: ['outcome', 'minimumCostCents', 'additionalBudgetCents', 'missingLitres', 'sourceVersions'],
        properties: { outcome: { enum: ['FEASIBLE_AT_SNAPSHOT', 'BUDGET_REVIEW_NEEDED', 'POLICY_LIMIT_EXCEEDED', 'STOCK_SHORTFALL'] } } },
      quoteId: { type: ['string', 'null'] }, status: str, expiresAtMs: { type: 'integer' } }),
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
for (const [path, method] of [[endpoints.orders, 'post'], ['/api/orders/{id}', 'get'], ['/api/orders/{id}/cancel', 'post']]) successSchema(path, method, object({ order: ref('Order') }));
successSchema('/api/quotes/{id}/body', 'get', object({ mode: { const: 'SYNTHETIC' }, signature: { const: 'UNSIGNED' }, body: ref('UnsignedQuoteBody') }));

Object.assign(openapi.components.schemas.Quote.properties, {
  snapshotId: str, sourceSnapshot: ref('SourceSnapshot'), reviewId: { type: ['string', 'null'] },
  budgetCents: int, budgetException: { oneOf: [{ type: 'null' }, object({
    originalBudgetCents: int, proposedBudgetCents: int, additionalCents: int, scope: { const: 'THIS_QUOTE_ONLY' },
  })] },
});
openapi.components.schemas.Quote.required.push('snapshotId', 'sourceSnapshot', 'reviewId', 'budgetCents', 'budgetException');
for (const [path, method] of [[endpoints.reviews, 'post'], ['/api/reviews/{id}/decision', 'post']]) {
  successSchema(path, method, object({ review: ref('ProcurementReview'),
    quote: { oneOf: [ref('Quote'), { type: 'null' }] } }));
}
