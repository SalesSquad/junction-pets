/**
 * Kättely research lane: a real Ed25519 cryptographic proof over SYNTHETIC
 * quote and buying mandate data. The buyer's private key stays in the
 * independent buyer process or browser; the supplier holds only its own key.
 * Ephemeral self-attested demo keys are NOT verified legal identities,
 * real delegated authority, AP2 conformance or payments.
 * No external signature, payment or commercial service is contacted.
 */
import { createHash, createPrivateKey, createPublicKey, generateKeyPairSync, sign, verify } from 'node:crypto';

export class TrustFault extends Error {
  constructor(code, message) { super(message); this.code = code; }
}


/** Private local-state codec helpers, never a public authorization input. */
export const invalidPrivateState = () => {
  throw new TrustFault('INVALID_COMPONENT_STATE', 'Private demo component state is malformed, incomplete or unsupported.');
};
export function restorePrivateComponent(value, kind, fields) {
  if (value === undefined) return null;
  const expected = ['kind', 'version', ...fields];
  if (!value || typeof value !== 'object' || Array.isArray(value) ||
      value.kind !== kind || value.version !== 1 ||
      Object.keys(value).length !== expected.length || expected.some((key) => !Object.hasOwn(value, key))) invalidPrivateState();
  const ancestors = new Set();
  let count = 0;
  const inspect = (item, depth = 0) => {
    if (++count > 1000000 || depth > 100) invalidPrivateState();
    if (item === null || typeof item === 'string' || typeof item === 'boolean') return;
    if (typeof item === 'number' && Number.isFinite(item)) return;
    if (!item || typeof item !== 'object' || ancestors.has(item) ||
        (!Array.isArray(item) && Object.getPrototypeOf(item) !== Object.prototype) ||
        Reflect.ownKeys(item).some((key) => typeof key !== 'string')) invalidPrivateState();
    ancestors.add(item);
    for (const entry of Object.values(item)) inspect(entry, depth + 1);
    ancestors.delete(item);
  };
  inspect(value);
  return structuredClone(value);
}
export function restorePrivateEntries(entries, validValue = () => true) {
  if (!Array.isArray(entries) || entries.length > 100000) invalidPrivateState();
  const map = new Map();
  for (const entry of entries) {
    if (!Array.isArray(entry) || entry.length !== 2 || typeof entry[0] !== 'string' ||
        !entry[0] || entry[0].length > 1000 || map.has(entry[0]) || !validValue(entry[1], entry[0])) invalidPrivateState();
    map.set(entry[0], entry[1]);
  }
  return map;
}

export function canonical(value) {
  if (value === null || typeof value === 'boolean' || typeof value === 'string') return JSON.stringify(value);
  if (typeof value === 'number') {
    if (!Number.isSafeInteger(value)) throw new TrustFault('INVALID_SIGNING_PAYLOAD', 'Only safe integer numbers can be signed.');
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object' && Object.getPrototypeOf(value) === Object.prototype) {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}`;
  }
  throw new TrustFault('INVALID_SIGNING_PAYLOAD', 'Only plain JSON fields are eligible for signatures.');
}

export const digest = (value) => createHash('sha256').update(canonical(value)).digest('base64url');
export const protectedHeader = (kid) => ({ typ: 'kattely.demo.procurement-envelope.v1', alg: 'EdDSA', kid });

/** Can be called by an independent process with its own private signing key. */
export function signDemoEnvelope(privateKey, kid, payload) {
  const header = protectedHeader(kid);
  const signature = sign(null, Buffer.from(`${canonical(header)}.${canonical(payload)}`), privateKey).toString('base64url');
  return { protected: header, payload, signature };
}

export function makeDemoMandatePayload({ quote, signedOffer, now, nonce }) {
  return { kind: 'SYNTHETIC_BUYER_MANDATE', quoteId: quote.id,
    buyerId: quote.buyerId, audience: 'https://supplier-demo.invalid',
    issuedAtMs: now, expiresAtMs: quote.expiresAtMs,
    allowedAction: 'CREATE_ONE_SIMULATED_ORDER', maxTotalCents: quote.totalCents,
    approval: quote.approvalRequired ? 'SYNTHETIC_RECORDED_REVIEW' : 'WITHIN_DEMO_POLICY',
    signedOfferDigest: digest(signedOffer), nonce };
}

const makeSigner = (role) => {
  const { privateKey, publicKey } = generateKeyPairSync('ed25519');
  const jwk = publicKey.export({ format: 'jwk' });
  const kid = `demo-${role}-${createHash('sha256').update(jwk.x).digest('hex').slice(0, 16)}`;
  return { privateKey, publicKey, jwk: { ...jwk, kid, use: 'sig', alg: 'EdDSA' }, kid };
};

export function createDemoTrustRegistry({ clock = () => Date.now(), initialState } = {}) {
  const restored = restorePrivateComponent(initialState, 'demo-trust-registry',
    ['supplierPrivateKey', 'supplierKid', 'registeredKeys', 'buyersBySession', 'offers', 'byQuote', 'usedNonces']);
  let supplier;
  if (restored) {
    try {
      if (typeof restored.supplierPrivateKey !== 'string' || !/^[A-Za-z0-9+/]+={0,2}$/.test(restored.supplierPrivateKey)) invalidPrivateState();
      const privateKey = createPrivateKey({ key: Buffer.from(restored.supplierPrivateKey, 'base64'), type: 'pkcs8', format: 'der' });
      if (privateKey.asymmetricKeyType !== 'ed25519') invalidPrivateState();
      const publicKey = createPublicKey(privateKey);
      const jwk = publicKey.export({ format: 'jwk' });
      const kid = 'demo-supplier-' + createHash('sha256').update(jwk.x).digest('hex').slice(0, 16);
      if (kid !== restored.supplierKid) invalidPrivateState();
      supplier = { privateKey, publicKey, kid, jwk: { ...jwk, kid, use: 'sig', alg: 'EdDSA' } };
    } catch { invalidPrivateState(); }
  } else supplier = makeSigner('supplier');
  const registeredKeys = restored ? restorePrivateEntries(restored.registeredKeys, (jwk, kid) =>
    jwk && jwk.kid === kid && jwk.kty === 'OKP' && jwk.crv === 'Ed25519' &&
    typeof jwk.x === 'string' && /^[A-Za-z0-9_-]{43}$/.test(jwk.x) &&
    jwk.use === 'sig' && jwk.alg === 'EdDSA' && Object.keys(jwk).every((key) => ['kty', 'crv', 'x', 'kid', 'use', 'alg'].includes(key))) : new Map([[supplier.kid, supplier.jwk]]);
  if (restored && JSON.stringify(registeredKeys.get(supplier.kid)) !== JSON.stringify(supplier.jwk)) invalidPrivateState();
  const knownKeys = new Map();
  try { for (const [kid, jwk] of registeredKeys) knownKeys.set(kid, createPublicKey({ key: jwk, format: 'jwk' })); }
  catch { invalidPrivateState(); }
  const buyersBySession = restored ? restorePrivateEntries(restored.buyersBySession, (entry) => entry &&
    typeof entry.kid === 'string' && entry.kid.startsWith('demo-buyer-') &&
    JSON.stringify(registeredKeys.get(entry.kid)) === JSON.stringify(entry.jwk)) : new Map();
  const offers = restored ? restorePrivateEntries(restored.offers, (entry, id) => entry?.payload?.quoteId === id) : new Map();
  const byQuote = restored ? restorePrivateEntries(restored.byQuote, (entry, id) => entry?.signedOffer?.payload?.quoteId === id && entry?.signedMandate?.payload?.quoteId === id) : new Map();
  if (restored && (!Array.isArray(restored.usedNonces) || restored.usedNonces.some((nonce) => typeof nonce !== 'string' || !/^[0-9a-f-]{36}$/.test(nonce)) ||
      new Set(restored.usedNonces).size !== restored.usedNonces.length)) invalidPrivateState();
  const usedNonces = new Set(restored?.usedNonces ?? []);

  const registerBuyerKey = (sessionToken, publicJwk) => {
    if (typeof sessionToken !== 'string' || !publicJwk || typeof publicJwk !== 'object' ||
        Array.isArray(publicJwk) || publicJwk.kty !== 'OKP' || publicJwk.crv !== 'Ed25519' ||
        typeof publicJwk.x !== 'string' || !/^[A-Za-z0-9_-]{43}$/.test(publicJwk.x) ||
        Object.keys(publicJwk).some((key) => !['kty', 'crv', 'x'].includes(key))) {
      throw new TrustFault('INVALID_BUYER_KEY', 'Register a public-only Ed25519 OKP JWK for this demo session.');
    }
    const previous = buyersBySession.get(sessionToken);
    if (previous) {
      if (previous.jwk.x !== publicJwk.x) throw new TrustFault('BUYER_KEY_LOCKED', 'A session cannot silently switch its demo buyer signing key.');
      return { kid: previous.kid, mode: 'UNVERIFIED_SELF_ATTESTED_BUYER_KEY' };
    }
    let publicKey;
    try { publicKey = createPublicKey({ key: publicJwk, format: 'jwk' }); }
    catch { throw new TrustFault('INVALID_BUYER_KEY', 'Provided buyer key is not a valid public Ed25519 point.'); }
    const kid = `demo-buyer-${createHash('sha256').update(publicJwk.x).digest('hex').slice(0, 16)}`;
    const jwk = { kty: 'OKP', crv: 'Ed25519', x: publicJwk.x, kid, use: 'sig', alg: 'EdDSA' };
    buyersBySession.set(sessionToken, { kid, jwk });
    knownKeys.set(kid, publicKey);
    registeredKeys.set(kid, jwk);
    return { kid, mode: 'UNVERIFIED_SELF_ATTESTED_BUYER_KEY' };
  };
  const verifySeal = (envelope, expectedKid) => {
    if (!envelope || !envelope.protected || envelope.protected.alg !== 'EdDSA' ||
        envelope.protected.typ !== 'kattely.demo.procurement-envelope.v1' ||
        envelope.protected.kid !== expectedKid || !knownKeys.has(expectedKid) ||
        typeof envelope.signature !== 'string') throw new TrustFault('TRUST_HEADER_INVALID', 'Unrecognized proof header or local demo key.');
    const valid = verify(null,
      Buffer.from(`${canonical(envelope.protected)}.${canonical(envelope.payload)}`),
      knownKeys.get(expectedKid), Buffer.from(envelope.signature, 'base64url'));
    if (!valid) throw new TrustFault('SIGNATURE_INVALID', 'The signed evidence was modified or the signature is invalid.');
    return envelope.payload;
  };

  const verifyHandshake = (proof, originalQuote, expectedQuoteBody) => {
    if (!proof || !originalQuote || !expectedQuoteBody) throw new TrustFault('HANDSHAKE_INVALID', 'Quote and both proof envelopes are required.');
    const offer = verifySeal(proof.signedOffer, supplier.kid);
    const mandateKid = proof.signedMandate?.protected?.kid;
    const mandate = verifySeal(proof.signedMandate, mandateKid);
    if (offer.kind !== 'SYNTHETIC_SUPPLIER_QUOTE' || mandate.kind !== 'SYNTHETIC_BUYER_MANDATE' ||
        offer.quoteId !== originalQuote.id || mandate.quoteId !== originalQuote.id ||
        offer.buyerId !== originalQuote.buyerId || mandate.buyerId !== originalQuote.buyerId ||
        offer.quoteBodyDigest !== digest(expectedQuoteBody) || mandate.signedOfferDigest !== digest(proof.signedOffer) ||
        offer.totalCents !== originalQuote.totalCents || mandate.maxTotalCents !== originalQuote.totalCents ||
        mandate.allowedAction !== 'CREATE_ONE_SIMULATED_ORDER' ||
        mandate.approval !== (originalQuote.approvalRequired ? 'SYNTHETIC_RECORDED_REVIEW' : 'WITHIN_DEMO_POLICY') ||
        typeof mandate.nonce !== 'string' || !/^[0-9a-f-]{36}$/.test(mandate.nonce) ||
        offer.audience !== 'https://supplier-demo.invalid' ||
        mandate.audience !== 'https://supplier-demo.invalid') {
      throw new TrustFault('PROOF_BINDING_INVALID', 'Mandate must bind to exactly these buyer, supplier, quote and financial terms.');
    }
    const now = clock();
    if (![now, originalQuote.createdAtMs, originalQuote.expiresAtMs, offer.issuedAtMs,
        offer.expiresAtMs, mandate.issuedAtMs, mandate.expiresAtMs].every((value) => Number.isSafeInteger(value) && value >= 0) ||
        originalQuote.createdAtMs >= originalQuote.expiresAtMs ||
        offer.issuedAtMs >= offer.expiresAtMs || mandate.issuedAtMs >= mandate.expiresAtMs ||
        offer.issuedAtMs < originalQuote.createdAtMs || mandate.issuedAtMs < offer.issuedAtMs ||
        mandate.expiresAtMs > offer.expiresAtMs) {
      throw new TrustFault('PROOF_TIME_INVALID', 'All proof times must be ordered integer epoch timestamps within the original quote.');
    }
    if (now >= originalQuote.expiresAtMs || now >= offer.expiresAtMs || now >= mandate.expiresAtMs ||
        offer.expiresAtMs > originalQuote.expiresAtMs || mandate.expiresAtMs > originalQuote.expiresAtMs ||
        offer.issuedAtMs > now || mandate.issuedAtMs > now) {
      throw new TrustFault('PROOF_EXPIRED', 'Trust proof has expired; a new quote and mandate are required.');
    }
    return { valid: true, quoteId: originalQuote.id, buyerId: originalQuote.buyerId,
      signedOfferDigest: digest(proof.signedOffer), signedMandateDigest: digest(proof.signedMandate),
      quoteBodyDigest: digest(expectedQuoteBody), simulatedIdentity: true, signedBy: [supplier.kid, mandateKid] };
  };

  const signOffer = (quote, quoteBody) => {
    if (quote.status !== 'APPROVED' && quote.status !== 'AUTO_COMMIT_ELIGIBLE') {
      throw new TrustFault('APPROVAL_REQUIRED', 'Quote must pass the existing buyer policy and decision gate first.');
    }
    const issuedAtMs = clock();
    if (issuedAtMs >= quote.expiresAtMs) throw new TrustFault('PROOF_EXPIRED', 'Quote expired before handshake.');
    if (offers.has(quote.id)) return structuredClone(offers.get(quote.id));
    const signedOffer = signDemoEnvelope(supplier.privateKey, supplier.kid, { kind: 'SYNTHETIC_SUPPLIER_QUOTE', quoteId: quote.id,
      buyerId: quote.buyerId, audience: quoteBody.audience, issuedAtMs, expiresAtMs: quote.expiresAtMs,
      quoteBodyDigest: digest(quoteBody), totalCents: quote.totalCents });
    offers.set(quote.id, signedOffer);
    return structuredClone(signedOffer);
  };

  const issueHandshake = (quote, quoteBody, signedMandate, sessionToken) => {
    if (quote.status !== 'APPROVED' && quote.status !== 'AUTO_COMMIT_ELIGIBLE') {
      throw new TrustFault('APPROVAL_REQUIRED', 'A real buyer-policy decision must precede synthetic proof issuance.');
    }
    if (byQuote.has(quote.id)) throw new TrustFault('MANDATE_REPLAY', 'This quote already has one synthetic mandate.');
    const registered = buyersBySession.get(sessionToken);
    if (!registered) throw new TrustFault('BUYER_KEY_REQUIRED', 'The independent buyer process must register its own public signing key.');
    const signedOffer = offers.get(quote.id);
    if (!signedOffer) throw new TrustFault('SIGNED_OFFER_REQUIRED', 'Request the supplier-signed offer before issuing a buyer mandate.');
    if (!signedMandate || signedMandate.protected?.kid !== registered.kid) {
      throw new TrustFault('BUYER_KEY_MISMATCH', 'Mandate signature does not belong to this demo session.');
    }
    const proof = { mode: 'SELF_ATTESTED_EPHEMERAL_DEMO_KEYS', proofType: 'NOT_A_PRODUCTION_KATTELY_OR_AP2_RECEIPT',
      signedOffer, signedMandate, verification: null };
    proof.verification = verifyHandshake(proof, quote, quoteBody);
    if (usedNonces.has(signedMandate.payload.nonce)) throw new TrustFault('MANDATE_REPLAY', 'A signed buyer nonce may never be reused.');
    usedNonces.add(signedMandate.payload.nonce);
    byQuote.set(quote.id, proof);
    return structuredClone(proof);
  };

  if (restored) {
    try {
      for (const offer of offers.values()) verifySeal(offer, supplier.kid);
      for (const [quoteId, proof] of byQuote) {
        verifySeal(proof.signedOffer, supplier.kid);
        verifySeal(proof.signedMandate, proof.signedMandate.protected.kid);
        if (digest(proof.signedOffer) !== digest(offers.get(quoteId)) ||
            !usedNonces.has(proof.signedMandate.payload.nonce) ||
            proof.signedMandate.payload.signedOfferDigest !== digest(proof.signedOffer)) invalidPrivateState();
      }
    } catch { invalidPrivateState(); }
  }
  return Object.freeze({
    // This contains a SYNTHETIC supplier private key. Only the private local store may consume it.
    exportState: () => structuredClone({ kind: 'demo-trust-registry', version: 1,
      supplierPrivateKey: supplier.privateKey.export({ type: 'pkcs8', format: 'der' }).toString('base64'), supplierKid: supplier.kid,
      registeredKeys: [...registeredKeys], buyersBySession: [...buyersBySession], offers: [...offers], byQuote: [...byQuote], usedNonces: [...usedNonces] }),
    registerBuyerKey,
    signOffer,
    issueHandshake,
    verifyHandshake,
    findHandshake: (quoteId) => structuredClone(byQuote.get(quoteId) ?? null),
    publicKeys: () => ({ mode: 'EPHEMERAL_SYNTHETIC_SELF_ATTESTED', keys: [...registeredKeys.values()] }),
  });
}
