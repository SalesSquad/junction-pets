// Implemented localhost contract. No sponsor API or authentication claim.
export const endpoints = Object.freeze({ session: '/api/demo/session', catalog: '/api/catalog', productsSearch: '/api/products/search', scanResolve: '/api/scan/resolve', scanOcr: '/api/scan/ocr', policy: '/api/policy', quotes: '/api/quotes', reviews: '/api/reviews', orders: '/api/orders', audit: '/api/audit', auditVerify: '/api/audit/verify', reprice: '/api/demo/reprice', plans: '/api/plans', shock: '/api/demo/shock', jwks: '/.well-known/trusted-trade/jwks.json', buyerKey: '/api/trust/buyer-key', wallet: '/api/demo/wallet', ledger: '/api/demo/ledger', ledgerVerify: '/api/demo/ledger/verify' });
export const metadata = Object.freeze({ mode: 'SYNTHETIC_NONCOMMERCIAL', supplier_id: 'supplier-demo', openapi: '/openapi.json', endpoints,
  approval: 'UNAUTHENTICATED_SYNTHETIC_HUMAN_DECISION', session: 'EPHEMERAL_DEMO_CAPABILITY_NOT_REAL_IDENTITY',
  quoteBody: 'UNSIGNED_kattely.procurement.quote.v3', tradeProof: 'Ed25519_SIGNED_LOCAL_DEMO_KEYS_NOT_REAL_KATTELY_OR_AP2',
  portfolio: 'DETERMINISTIC_MULTI_PRODUCT_OPTIONS_WITH_SYNTHETIC_METRICS', recovery: 'STOCK_SHOCK_REPLANS_WITH_FRESH_APPROVAL',
  settlement: 'DOUBLE_ENTRY_SYNTHETIC_WALLET_REQUIRES_SEPARATE_DEMO_PAYMENT_APPROVAL_NO_PSP',
  retrieval: 'FIXTURE_LEXICAL_READ_ONLY; OPTIONAL_SCOPED_PGVECTOR_SQL_ADAPTER_REQUIRES_EXTERNAL_DB_AND_REAL_EMBEDDINGS',
  families: ['dairy-milk', 'oat-drink'], fixtureDeliveryDate: '2026-11-16',
  scanning: 'EXACT_SYNTHETIC_GTIN_AND_OPTIONAL_TRANSIENT_SERVER_OCR_UNTRUSTED; NO_META_DEVICE_OR_PHYSICAL_DELIVERY_ATTESTATION' });
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
  openapi: '3.1.0', info: { title: 'Trusted Trade — implemented SYNTHETIC localhost API', version: '0.7.0', description: 'All parties, stock, prices, approvals, emission factors, orders, scan GTINs and EUR wallet balances invented. Default product discovery is lexical, NOT pgvector. Optional pgvector adapter requires a real separate database and embedding provider. No banking, brokerage or commercial effects. Scanner observations are not physical receipt attestation. Independent Ed25519 proof-of-possession demo keys are self-attested, not verified identities, Kättely or AP2 certification.' },
  servers: [{ url: '/' }], paths: {
    '/.well-known/trusted-trade': { get: operation('Discover synthetic capabilities') },
    [endpoints.jwks]: { get: operation('Publish ephemeral self-attested demo verification keys, NOT a trusted identity registry') },
    [endpoints.session]: { post: operation('Issue an ephemeral demo buyer capability (not login)', object({ buyerId: str }), '201') },
    [endpoints.catalog]: { get: operation('Read current synthetic product prices, stock and versions') },
    [endpoints.productsSearch]: { get: { summary: 'Read-only buyer-scoped product candidate discovery (fixture lexical by default; optional PostgreSQL/pgvector provider)',
      security: [{ demoCapability: [] }],
      parameters: [{ name: 'q', in: 'query', required: true, schema: { type: 'string', minLength: 2, maxLength: 160 } }],
      responses: { '200': { description: 'Advisory candidates with source digests; never commercial truth' }, '400': { description: 'Invalid query' }, '403': { description: 'Demo session required' }, '503': { description: 'Configured search backend unavailable' } } } },
    [endpoints.scanResolve]: { get: { summary: 'Resolve a checksum-valid barcode by exact synthetic GTIN; never semantic identity',
      parameters: [{ name: 'gtin', in: 'query', required: true, schema: str }],
      responses: { '200': { description: 'Exact synthetic product identity, never authority' }, '400': { description: 'Invalid barcode or checksum' }, '404': { description: 'Unknown barcode' } } } },
    [endpoints.scanOcr]: { post: { summary: 'OPTIONAL demo-server Tesseract image OCR. No image storage; text is untrusted until user confirms.',
      security: [{ demoCapability: [] }],
      requestBody: { required: true, content: { 'image/png': { schema: { type: 'string', format: 'binary' } }, 'image/jpeg': { schema: { type: 'string', format: 'binary' } } } },
      responses: { '200': { description: 'OCR text and advisory typed recipe candidates; never an order or approval' }, '403': { description: 'Session required' }, '413': { description: 'Image too large' }, '503': { description: 'Local OCR unavailable or busy' } } } },
    [endpoints.buyerKey]: { post: operation('Register independent buyer agent PUBLIC Ed25519 key in its demo session', object({ buyerId: str, publicJwk: object({ kty: { const: 'OKP' }, crv: { const: 'Ed25519' }, x: str }) }), '201', true) },
    [endpoints.policy]: { get: operation('Read server-owned demo budget and approval threshold') },
    [endpoints.wallet]: { get: operation('Read fictional buyer and supplier wallet balances; demo session required', null, '200', true) },
    [endpoints.ledger]: { get: operation('Inspect in-memory fictional double-entry EUR journal', null, '200', true) },
    [endpoints.ledgerVerify]: { get: operation('Verify balanced postings and local hash-linked settlement receipts', null, '200', true) },
    [endpoints.quotes]: { post: operation('Fix price and check availability; no reservation', ref('QuoteRequest'), '201', true) },
    [endpoints.reviews]: { post: operation('Diagnose and propose a fixed quote from one coherent synthetic source snapshot; creates no approval', ref('QuoteRequest'), '201', true) },
    '/api/reviews/{id}/decision': { parameters: [parameter('id')], post: operation('Decide the exact displayed quote/snapshot; any budget exception applies only to that quote', ref('ReviewDecision'), '200', true) },
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
    '/api/orders/{id}/scan': { parameters: [parameter('id')], post: operation('Record exactly one self-attested GTIN match to an existing signed synthetic order; not physical delivery proof', object({ buyerId: str, gtin: str, idempotencyKey: { type: 'string', pattern: '^[A-Za-z0-9_-]{10,80}$' } }), '201', true) },
    [endpoints.audit]: { get: operation('Read append-only in-memory demo events') },
    [endpoints.auditVerify]: { get: operation('Verify the in-memory SHA-256 receipt hash chain; no external anchoring') },
    [endpoints.reprice]: { post: operation('Demo-only mutation; invalidates old source versions', object({ sku: str, priceCents: { ...int, maximum: 100000 } }), '200', true) },
    [endpoints.shock]: { post: operation('Synthetic stock outage; triggers a safe recovery flow', object({ sku: str, unitsAvailable: { type: 'integer', minimum: 0, maximum: 1000000 } }), '200', true) },
  }, components: { securitySchemes: { demoCapability: { type: 'http', scheme: 'bearer', description: 'Synthetic session capability only; NOT OAuth or real buyer identity.' } }, schemas: {
    UnsignedQuoteBody: object({ version: { const: 'kattely.procurement.quote.v3' }, quote_id: str,
      supplier_id: { const: 'supplier-demo' }, buyer_id: str, audience: { const: 'https://supplier-demo.invalid' },
      currency: { const: 'EUR' }, issued_at: { type: 'integer' }, expires_at: { type: 'integer' },
      lines: { type: 'array', minItems: 1, items: object({ sku: str, quantity: int, unit: { const: 'L' }, unit_price_cents: int, stock_version: int, supplier_id: str, pack_litres: int, pack_count: int, min_order_packs: int }) },
      total_cents: { ...int, description: 'Product subtotal plus synthetic delivery fee and tax, rounded to integer cents.' } }),
    Product: { type: 'object', required: ['sku', 'family', 'lactoseFree', 'unitsAvailable', 'priceCents', 'version', 'deliverBy'], properties: {
      sku: str, gtin: str, family: { enum: ['dairy-milk', 'oat-drink'] }, lactoseFree: { type: 'boolean' }, unitsAvailable: { type: 'integer', minimum: 0 }, priceCents: int, version: int, deliverBy: { type: 'string', format: 'date' } } },
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
    ReviewDecision: object({ buyerId: str, decision: { enum: ['approve', 'reject'] }, snapshotId: str, quoteId: str }),
    SourceSnapshot: object({ id: str, observedAtMs: { type: 'integer' }, mode: { const: 'INVENTED_FIXTURE' },
      stockReserved: { const: false }, products: { type: 'array', items: ref('Product') },
      policy: { type: 'object' }, constraints: ref('BuyingNeed') }),
    ProcurementReview: object({ id: str, buyerId: str, snapshotId: str, sourceSnapshot: ref('SourceSnapshot'),
      requested: ref('BuyingNeed'), originalBudgetCents: int, diagnosis: { type: 'object',
        required: ['outcome', 'minimumCostCents', 'additionalBudgetCents', 'missingLitres', 'sourceVersions'],
        properties: { outcome: { enum: ['FEASIBLE_AT_SNAPSHOT', 'BUDGET_REVIEW_NEEDED', 'POLICY_LIMIT_EXCEEDED', 'STOCK_SHORTFALL', 'PACKING_CONSTRAINT'] } } },
      quoteId: { type: ['string', 'null'] }, status: str, expiresAtMs: { type: 'integer' } }),
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
successSchema(endpoints.productsSearch, 'get', object({
  query: str, mode: { enum: ['FIXTURE_LEXICAL_NO_EMBEDDINGS', 'PGVECTOR_HYBRID_RRF'] },
  candidates: { type: 'array', items: { type: 'object', required: ['sku', 'name', 'provenance', 'requiresTradeCoreValidation'], properties: {
    sku: str, name: str, family: str, lexicalScore: { type: 'number' }, rrfScore: { type: 'number' },
    provenance: { type: 'object', required: ['sourceKind', 'sourceRef', 'sourceVersion', 'sourceSha256'], properties: {
      sourceKind: str, sourceRef: str, sourceVersion: { type: ['string', 'integer'] }, sourceSha256: str, observedAt: { type: ['string', 'null'], format: 'date-time' },
    } }, requiresTradeCoreValidation: { const: true },
  } } },
  reason: { enum: ['RANKED_ADVISORY_CANDIDATES', 'NO_SUPPORTED_MATCH', 'EXACT_GTIN_ROUTE_REQUIRED', 'UNVERIFIED_DIETARY_CONSTRAINT', 'LOW_CONFIDENCE_ABSTAINED'] },
  requiresTradeCoreValidation: { const: true },
}));
successSchema(endpoints.scanResolve, 'get', object({ product: object({
  gtin: str, sku: str, name: str, family: str, unitsAvailable: { type: 'integer', minimum: 0 },
  priceCents: int, stockVersion: int, mode: { const: 'INVENTED_FIXTURE_EXACT_GTIN' },
  observation: { const: 'CHECK_DIGIT_AND_EXACT_CATALOG_MATCH_ONLY' }, authority: { const: 'NONE_SCAN_CANNOT_AUTHORIZE_TRADE' },
}) }));
successSchema(endpoints.scanOcr, 'post', object({
  text: str, candidates: { type: 'array', items: object({ family: str, quantityLitres: int, lactoseFree: { type: 'boolean' }, sourceLine: str, requiresHumanReview: { const: true } }) },
  duplicateFamilies: { type: 'array', items: str }, rawExcerpt: str,
  evidence: { const: 'OCR_TEXT_UNTRUSTED_REQUIRES_USER_REVIEW' }, warning: str,
  mode: { const: 'LOCAL_TESSERACT_OCR_UNTRUSTED' }, persistence: { const: 'IMAGE_NOT_STORED' }, requiresHumanConfirmation: { const: true },
}));
successSchema('/api/orders/{id}/scan', 'post', object({ observation: object({
  orderId: str, sku: str, gtin: str, observedCount: int, orderedCount: int, packLitres: int, observedLitres: int, orderedLitres: int, receiptId: str,
  matchedSignedOrder: { const: true }, evidenceLevel: { const: 'SELF_ATTESTED_SCAN_NOT_PROOF_OF_DELIVERY' },
  idempotentReplay: { type: 'boolean' },
}) }));
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

const zeroInt = { type: 'integer', minimum: 0 };
openapi.components.schemas.PricingBreakdown = object({
  subtotalCents: zeroInt, deliveryFeeCents: zeroInt, taxCents: zeroInt, taxBps: zeroInt,
});
Object.assign(openapi.components.schemas.Product.properties, { packLitres: int, minOrderPacks: int });
openapi.components.schemas.Product.required.push('packLitres', 'minOrderPacks');
Object.assign(openapi.components.schemas.QuoteLine.properties, { packLitres: int, minOrderPacks: int, packs: int });
Object.assign(openapi.components.schemas.Quote.properties, { costBreakdown: ref('PricingBreakdown') });
openapi.components.schemas.Quote.required.push('costBreakdown');
openapi.components.schemas.SourceSnapshot.properties.constraints = {
  oneOf: [ref('BuyingNeed'), object({ requirements: { type: 'array', items: ref('BuyingNeed') }, mode: { const: 'TYPED_PORTFOLIO' } })],
};
Object.assign(openapi.components.schemas.UnsignedQuoteBody.properties, {
  source_snapshot_id: str,
  cost_breakdown: object({ subtotal_cents: zeroInt, delivery_fee_cents: zeroInt, tax_cents: zeroInt, tax_bps: zeroInt }),
});
openapi.components.schemas.UnsignedQuoteBody.required.push('source_snapshot_id', 'cost_breakdown');

openapi.components.schemas.QuoteLine.required.push('packLitres', 'minOrderPacks', 'packs');
