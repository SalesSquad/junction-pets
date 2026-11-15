/** Verification only; the private host owns identity, grants and explicit consent. */
import { createLocalJWKSet, decodeProtectedHeader, importJWK, jwtVerify } from 'jose';

export class JwtHostVerificationError extends Error {
  constructor(code) { super(code); this.code = code; }
}
const refuse = code => { throw new JwtHostVerificationError(code); };
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const text = (value, max = 512) => typeof value === 'string' && value.length > 0 && value.length <= max;
const algorithmsAllowed = new Set(['RS256','ES256','EdDSA']);
const fields = new Set(['issuer','accessAudience','decisionAudience','jwks','accessTyp','decisionTyp',
  'algorithms','maxAccessAgeSeconds','maxDecisionAgeSeconds','clock']);
const b64 = (value, minimum, maximum) => {
  if (!text(value, Math.ceil(maximum * 4 / 3)) || !/^[A-Za-z0-9_-]+$/.test(value)) return false;
  const bytes = Buffer.from(value, 'base64url');
  return bytes.length >= minimum && bytes.length <= maximum && bytes.toString('base64url') === value;
};
function boundedClaims(value, depth = 0, budget = { nodes: 0 }) {
  if (++budget.nodes > 512 || depth > 8) return false;
  if (value === null || typeof value === 'boolean') return true;
  if (typeof value === 'number') return Number.isFinite(value);
  if (typeof value === 'string') return value.length <= 4096;
  if (Array.isArray(value)) return value.length <= 64 && value.every(v => boundedClaims(v, depth + 1, budget));
  return object(value) && Object.keys(value).length <= 128 && Object.entries(value).every(([key,v]) =>
    key.length <= 128 && !['__proto__','prototype','constructor'].includes(key) && boundedClaims(v, depth + 1, budget));
}
function publicKey(key, algorithms) {
  if (!object(key) || !text(key.kid,100) || !/^[A-Za-z0-9_.-]+$/.test(key.kid) ||
      !algorithms.includes(key.alg) || (key.use !== undefined && key.use !== 'sig') ||
      (key.key_ops !== undefined && (!Array.isArray(key.key_ops) || key.key_ops.length !== 1 || key.key_ops[0] !== 'verify'))) return false;
  const common = ['kty','kid','alg','use','key_ops'];
  let allowed, shape;
  if (key.kty === 'RSA' && key.alg === 'RS256') {
    allowed = [...common,'n','e']; shape = b64(key.n,256,1024) && b64(key.e,1,8);
  } else if (key.kty === 'EC' && key.alg === 'ES256') {
    allowed = [...common,'crv','x','y']; shape = key.crv === 'P-256' && b64(key.x,32,32) && b64(key.y,32,32);
  } else if (key.kty === 'OKP' && key.alg === 'EdDSA') {
    allowed = [...common,'crv','x']; shape = key.crv === 'Ed25519' && b64(key.x,32,32);
  } else return false;
  return shape && Object.keys(key).every(name => allowed.includes(name));
}

export async function createJwtHostVerifier(config = {}) {
  let keys, issuer, accessAudience, decisionAudience, algorithms, clock, accessAge, decisionAge;
  try {
    if (!object(config) || Object.keys(config).some(key => !fields.has(key))) throw Error();
    const url = new URL(config.issuer);
    if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash ||
        !text(config.issuer,2048)) throw Error();
    issuer = config.issuer; accessAudience = config.accessAudience; decisionAudience = config.decisionAudience;
    if (!text(accessAudience) || !text(decisionAudience) || accessAudience === decisionAudience ||
        (config.accessTyp !== undefined && config.accessTyp !== 'at+jwt') ||
        (config.decisionTyp !== undefined && config.decisionTyp !== 'buyer-decision+jwt')) throw Error();
    algorithms = config.algorithms ?? ['RS256','ES256','EdDSA'];
    if (!Array.isArray(algorithms) || algorithms.length < 1 || algorithms.length > 3 ||
        new Set(algorithms).size !== algorithms.length || algorithms.some(alg => !algorithmsAllowed.has(alg))) throw Error();
    accessAge = config.maxAccessAgeSeconds ?? 900; decisionAge = config.maxDecisionAgeSeconds ?? 300;
    if (!Number.isSafeInteger(accessAge) || accessAge < 1 || accessAge > 900 ||
        !Number.isSafeInteger(decisionAge) || decisionAge < 1 || decisionAge > 300) throw Error();
    clock = config.clock ?? (() => new Date());
    if (typeof clock !== 'function') throw Error();
    const now = clock(); if (!(now instanceof Date) || !Number.isFinite(now.getTime())) throw Error();
    if (!object(config.jwks) || Object.keys(config.jwks).some(key => key !== 'keys') ||
        !Array.isArray(config.jwks.keys) || config.jwks.keys.length < 1 || config.jwks.keys.length > 16 ||
        Buffer.byteLength(JSON.stringify(config.jwks)) > 65536) throw Error();
    keys = structuredClone(config.jwks);
    if (keys.keys.some(key => !publicKey(key,algorithms)) || new Set(keys.keys.map(key => key.kid)).size !== keys.keys.length) throw Error();
    await Promise.all(keys.keys.map(key => importJWK(key,key.alg)));
  } catch { refuse('HOST_IDENTITY_CONFIG_INVALID'); }
  const resolver = createLocalJWKSet(keys);
  const verify = async (token,audience,typ,maximumAge) => {
    try {
      if (!text(token,16384) || Buffer.byteLength(token) > 16384 || token.split('.').length !== 3) throw Error();
      const header = decodeProtectedHeader(token);
      if (!object(header) || Object.keys(header).some(name => !['alg','kid','typ'].includes(name)) ||
          header.typ !== typ || !algorithms.includes(header.alg) ||
          !keys.keys.some(key => key.kid === header.kid && key.alg === header.alg)) throw Error();
      const now = clock(); if (!(now instanceof Date) || !Number.isFinite(now.getTime())) throw Error();
      const { payload } = await jwtVerify(token,resolver,{
        issuer,audience,typ,algorithms,currentDate:now,clockTolerance:0,
        requiredClaims:['iss','aud','sub','iat','exp'],maxTokenAge:maximumAge,
      });
      const seconds = Math.floor(now.getTime()/1000);
      if (!text(payload.sub) || !Number.isSafeInteger(payload.iat) || !Number.isSafeInteger(payload.exp) ||
          payload.iat < 0 || payload.exp <= payload.iat || payload.exp-payload.iat > maximumAge ||
          payload.iat > seconds || payload.exp <= seconds ||
          (payload.nbf !== undefined && (!Number.isSafeInteger(payload.nbf) || payload.nbf > seconds)) ||
          payload.aud !== audience || !boundedClaims(payload)) throw Error();
      return structuredClone(payload);
    } catch { refuse('HOST_IDENTITY_INVALID'); }
  };
  return Object.freeze({
    verifyAccessToken: token => verify(token,accessAudience,'at+jwt',accessAge),
    verifyDecisionProof: token => verify(token,decisionAudience,'buyer-decision+jwt',decisionAge),
    configurationStatus: () => ({configured:true,verification:'PINNED_PUBLIC_JWKS',
      accessTyp:'at+jwt',decisionTyp:'buyer-decision+jwt',keyCount:keys.keys.length,
      algorithms:[...algorithms],maxAccessAgeSeconds:accessAge,maxDecisionAgeSeconds:decisionAge,
      identityAndConsentAuthority:'EXTERNAL_HOST_ONLY'}),
  });
}
