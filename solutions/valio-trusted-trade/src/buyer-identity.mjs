/** Host-owned identity/consent boundary. Commerce remains SYNTHETIC. */
import { createHash } from 'node:crypto';
import { TradeError, unsignedQuoteBody } from './core.mjs';
import { digest } from './trust-envelope.mjs';

const sha = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
const refuse = (code, message, status = 403) => { throw new TradeError(code, message, status); };
const safe = value => typeof value === 'string' && /^[A-Za-z0-9_-]{1,100}$/.test(value);
const actions = new Set(['read','prepare','commit','cancel','relay_decision','approve','pay','audit','inventory']);
const object = value => value && typeof value === 'object' && !Array.isArray(value);
const publicPaths = new Set(['/api/health','/api/identity/configuration']);

export function bindIdentityProfile(context, service, identity) {
  const profile = identity ? { mode: 'HOST_AUTHENTICATED', profileId: identity.profileId, issuerDigest: identity.issuerDigest } :
    { mode: 'SYNTHETIC', profileId: 'synthetic-demo-v1' };
  const saved = context.identityState.get('profile');
  if (saved && JSON.stringify(saved) !== JSON.stringify(profile)) refuse('IDENTITY_STATE_PROFILE_MISMATCH', 'Use a separate state file for another identity mode or issuer profile.', 503);
  if (!saved && identity && (context.sessions.size || context.quoteOwners.size || context.orderOwners.size ||
      context.reviewOwners.size || context.agentRuns.size || service.exportState().quotes.length)) {
    refuse('IDENTITY_STATE_PROFILE_MISMATCH', 'Existing anonymous workflows are preserved and cannot become authenticated ownership.', 503);
  }
  context.identityState.set('profile', profile);
}

export function createBuyerIdentity({ profileId, issuer, verifier, grants, clock = () => Date.now() } = {}) {
  if (!safe(profileId) || typeof issuer !== 'string' || !issuer.startsWith('https://') ||
      typeof verifier?.verifyAccessToken !== 'function' || typeof verifier?.verifyDecisionProof !== 'function' ||
      !(Array.isArray(grants) || typeof grants === 'function')) throw new TypeError('Invalid host identity configuration');
  const issuerDigest = sha(issuer);
  const list = () => {
    const value = typeof grants === 'function' ? grants() : grants;
    if (!Array.isArray(value) || !value.length || value.length > 256) refuse('IDENTITY_CONFIG_INVALID', 'The operator identity grant source is unavailable.', 503);
    const subjects = new Set();
    for (const grant of value) {
      if (!object(grant) || typeof grant.subject !== 'string' || !grant.subject || grant.subject.length > 200 ||
          subjects.has(grant.subject) || !safe(grant.buyerId) || !safe(grant.ownerScope) ||
          !['HUMAN','AGENT'].includes(grant.principalType) || typeof grant.active !== 'boolean' ||
          !Number.isSafeInteger(grant.revision) || grant.revision < 1 || !Array.isArray(grant.actions) ||
          !grant.actions.length || new Set(grant.actions).size !== grant.actions.length ||
          grant.actions.some(action => !actions.has(action)) || !Number.isSafeInteger(grant.maxOrderCents) ||
          grant.maxOrderCents < 1 || grant.maxOrderCents > 250000 ||
          (grant.principalType !== 'HUMAN' && grant.actions.some(action => ['approve','pay'].includes(action)))) {
        refuse('IDENTITY_CONFIG_INVALID', 'Operator grants are malformed; authority is not inferred.', 503);
      }
      subjects.add(grant.subject);
    }
    return value;
  };
  list();
  const resolve = subject => {
    const grant = list().find(value => value.subject === subject);
    if (!grant?.active) refuse('IDENTITY_REVOKED', 'No active operator grant exists for this host identity.');
    return { grant, actorRef: 'actor-' + sha([profileId, issuer, subject]),
      ownerRef: 'owner-' + sha([profileId, issuer, grant.buyerId, grant.ownerScope]) };
  };
  const time = payload => {
    const now = Math.floor(clock() / 1000);
    if (payload?.iss !== issuer || typeof payload.sub !== 'string' || !payload.sub ||
        !Number.isSafeInteger(payload.iat) || !Number.isSafeInteger(payload.exp) ||
        payload.iat > now || payload.exp <= now || payload.exp <= payload.iat ||
        (payload.nbf !== undefined && (!Number.isSafeInteger(payload.nbf) || payload.nbf > now))) {
      refuse('IDENTITY_EXPIRED', 'The verified host assertion is no longer current.', 401);
    }
  };
  const current = identity => {
    time(identity.claims);
    const value = resolve(identity.claims.sub);
    if (value.ownerRef !== identity.ownerRef || value.actorRef !== identity.actorRef ||
        value.grant.revision !== identity.grantRevision) refuse('IDENTITY_REVOKED', 'The host grant changed; authenticate again.');
    return value.grant;
  };
  const authenticate = async request => {
    const raw = request.headers.authorization?.match(/^Bearer ([^\s]{1,16384})$/)?.[1];
    if (!raw) refuse('HOST_IDENTITY_REQUIRED', 'Connect through the configured identity host; anonymous demo sessions are disabled.', 401);
    let claims, proofClaims = null;
    try {
      claims = await verifier.verifyAccessToken(raw);
      if (request.headers['x-buyer-decision-proof']) proofClaims = await verifier.verifyDecisionProof(request.headers['x-buyer-decision-proof']);
    } catch { refuse('HOST_ASSERTION_INVALID', 'The host access assertion or decision proof could not be verified.', 401); }
    time(claims);
    const { grant, actorRef, ownerRef } = resolve(claims.sub);
    return { claims, proofClaims, proofDigest: proofClaims ? sha(request.headers['x-buyer-decision-proof']) : null,
      actorRef, ownerRef, buyerId: grant.buyerId, principalType: grant.principalType, grantRevision: grant.revision };
  };
  const operation = (method, path) => {
    if (method === 'GET') return /^\/api\/(?:audit|demo\/ledger)(?:\/|$)/.test(path) ? 'audit' : 'read';
    if (path === '/api/suppliers/valio-mock/observe' || path === '/api/scan/ocr') return 'read';
    if (path === '/api/demo/session') refuse('DEMO_IDENTITY_DISABLED', 'Anonymous demo capability minting is disabled.', 401);
    if (/^\/api\/demo\/(reprice|shock)$/.test(path)) return 'inventory';
    if (/\/(?:approval|decision|payment-approval)$/.test(path)) return 'decision';
    if (/\/(?:cancel)$/.test(path)) return 'cancel';
    if (path === '/api/orders' || /\/(?:commit|offer|handshake|settlement)$/.test(path) || path === '/api/trust/buyer-key') return 'commit';
    return 'prepare';
  };
  const ownReads = (path, owner, context) => {
    const quote = path.match(/^\/api\/quotes\/([^/]+)(?:\/|$)/)?.[1];
    const order = path.match(/^\/api\/orders\/([^/]+)(?:\/|$)/)?.[1];
    const plan = path.match(/^\/api\/plans\/([^/]+)(?:\/|$)/)?.[1];
    const run = path.match(/^\/api\/agent\/runs\/([^/]+)(?:\/|$)/)?.[1];
    if ((quote && context.quoteOwners.get(quote) !== owner) || (order && context.orderOwners.get(order) !== owner) ||
        (plan && context.planOwners.get(plan) !== owner) || (run && context.agentRuns.get(run)?.owner !== owner)) {
      refuse('BUYER_MISMATCH', 'This host scope does not own the requested workflow.');
    }
  };
  const scopeQuote = (path, payload, service, context) => {
    const run = path.match(/^\/api\/agent\/runs\/([^/]+)(?:\/|$)/)?.[1];
    const orderId = path.match(/^\/api\/orders\/([^/]+)(?:\/|$)/)?.[1];
    const quoteId = path.match(/^\/api\/quotes\/([^/]+)(?:\/|$)/)?.[1] ??
      (run ? context.agentRuns.get(run)?.quoteId : undefined) ?? payload.quoteId ??
      (orderId ? service.order(orderId).quoteId : undefined);
    return quoteId ? service.quote(quoteId) : null;
  };
  return Object.freeze({
    profileId, issuerDigest, authenticate,
    isPublic: path => publicPaths.has(path),
    describe: () => ({ mode: 'HOST_AUTHENTICATED', credentialSource: 'PRIVATE_HOST', commerce: 'SYNTHETIC',
      login: 'HOST_OWNS_LOGIN', exactDecisionProofRequired: true, anonymousSessionMinting: false }),
    me(identity) {
      const grant = current(identity);
      return { mode: 'HOST_AUTHENTICATED', buyerId: grant.buyerId, actorRef: identity.actorRef,
        ownerRef: identity.ownerRef, profileId, principalType: grant.principalType,
        actions: [...grant.actions], grantRevision: grant.revision, commerce: 'SYNTHETIC' };
    },
    authorize({ identity, method, path, payload = {}, context, service, commandFingerprint }) {
      const grant = current(identity), action = operation(method, path), owner = identity.ownerRef;
      if (grant.buyerId !== service.policy().buyerId) refuse('BUYER_MISMATCH', 'This executor does not serve the host buyer mapping.');
      if (payload.buyerId !== undefined && payload.buyerId !== grant.buyerId) refuse('BUYER_MISMATCH', 'Caller buyer fields cannot change the host grant.');
      if (action !== 'decision' && !grant.actions.includes(action)) refuse('IDENTITY_ACTION_DENIED', 'The current host grant does not allow this operation.');
      ownReads(path, owner, context);
      const quote = scopeQuote(path, payload, service, context);
      if ((quote && quote.totalCents > grant.maxOrderCents) ||
          (payload.budgetCents !== undefined && payload.budgetCents > grant.maxOrderCents)) {
        refuse('IDENTITY_BUDGET_DENIED', 'This operation exceeds the current host procurement grant.');
      }
      if (method === 'GET') return null;
      if (action !== 'decision') return { actorRef: identity.actorRef, grantRevision: grant.revision, action,
        ownerRef: owner, mode: 'HOST_AUTHENTICATED', consent: null };
      const payment = path.endsWith('/payment-approval');
      const neededRole = payment ? 'pay' : 'approve';
      if (!grant.actions.includes(neededRole) && !grant.actions.includes('relay_decision')) refuse('IDENTITY_ACTION_DENIED', 'The current host grant cannot submit decisions.');
      const proof = identity.proofClaims;
      if (!proof) refuse('HOST_DECISION_REQUIRED', 'An independently signed, exact host decision is required; a model boolean or access role grants no consent.');
      time(proof);
      const reviewer = resolve(proof.sub), reviewerGrant = reviewer.grant;
      if (reviewerGrant.principalType !== 'HUMAN' || !reviewerGrant.actions.includes(neededRole) ||
          reviewer.ownerRef !== owner || !quote || quote.totalCents > reviewerGrant.maxOrderCents ||
          proof.buyerId !== grant.buyerId || proof.ownerRef !== owner ||
          proof.profileId !== profileId || proof.reviewerGrantRevision !== reviewerGrant.revision ||
          proof.action !== (payment ? 'PAYMENT_DECISION' : 'QUOTE_DECISION') ||
          proof.decision !== payload.decision || !['approve','reject'].includes(proof.decision) ||
          proof.quoteId !== quote.id || proof.snapshotId !== quote.snapshotId ||
          proof.totalCents !== quote.totalCents || proof.quoteBodyDigest !== digest(unsignedQuoteBody(quote)) ||
          !safe(proof.jti) || proof.exp - proof.iat > 300) {
        refuse('HOST_DECISION_SCOPE_MISMATCH', 'The signed human decision does not match the exact current workflow.');
      }
      if (context.quoteOwners.get(quote.id) !== owner) refuse('BUYER_MISMATCH', 'The decision is outside this host-owned workflow.');
      if (!payment) service.assertQuoteFresh(quote.id);
      else {
        const orderId = path.match(/^\/api\/orders\/([^/]+)\/payment-approval$/)?.[1];
        const proposal = service.payment(orderId, grant.buyerId).proposal;
        if (proof.orderId !== orderId || proof.paymentProposalDigest !== proposal.digest ||
            payload.proposalDigest !== proposal.digest) refuse('HOST_DECISION_SCOPE_MISMATCH', 'Payment requires its own exact proposal-bound host decision.');
      }
      const nonceKey = 'nonce:' + sha([issuer, proof.sub, proof.jti]);
      const prior = context.identityState.get(nonceKey);
      if (prior && (prior.commandFingerprint !== commandFingerprint || prior.proofDigest !== identity.proofDigest)) {
        refuse('HOST_DECISION_REPLAY', 'This host decision nonce was already used for another command.');
      }
      return { mode: 'HOST_AUTHENTICATED', actorRef: identity.actorRef, ownerRef: owner,
        grantRevision: grant.revision, action, consent: { kind: payment ? 'PAYMENT_DECISION' : 'QUOTE_DECISION',
          reviewerRef: reviewer.actorRef, reviewerGrantRevision: reviewerGrant.revision,
          quoteId: quote.id, snapshotId: quote.snapshotId, totalCents: quote.totalCents,
          proofDigest: identity.proofDigest, expiresAtMs: proof.exp * 1000, nonceKey, commandFingerprint } };
    },
    record(context, service, authorization) {
      if (!authorization) return;
      if (authorization.consent) {
        if (context.identityState.size >= 10000) refuse('IDENTITY_CAPACITY', 'The bounded identity receipt store is full.', 429);
        context.identityState.set(authorization.consent.nonceKey, structuredClone(authorization.consent));
        context.identityState.set('consent:' + authorization.consent.kind + ':' + authorization.consent.quoteId, structuredClone(authorization.consent));
      }
      service.recordIdentityAuthorization(authorization);
    },
  });
}
