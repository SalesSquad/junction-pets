/** Real JOSE verification with ephemeral synthetic signing keys, never provider access. */
import assert from 'node:assert/strict';
import { SignJWT, exportJWK, generateKeyPair } from 'jose';
import { createJwtHostVerifier } from '../jwt-host.mjs';

const instant = Date.UTC(2026,10,15,6);
const seconds = Math.floor(instant/1000);
const issuer = 'https://identity.example.invalid/';
const configBase = {issuer,accessAudience:'urn:synthetic:trade-api',
  decisionAudience:'urn:synthetic:trade-decision',clock:()=>new Date(instant)};
let checks = 0;
const refused = async (value,code='HOST_IDENTITY_INVALID') => {
  await assert.rejects(value,error => error.code === code && error.message === code);
  checks++;
};
const pairs = new Map();
const keys = [];
for (const alg of ['RS256','ES256','EdDSA']) {
  const pair = await generateKeyPair(alg,{extractable:true});
  pairs.set(alg,pair);
  keys.push({...await exportJWK(pair.publicKey),kid:'host-'+alg,alg,use:'sig',key_ops:['verify']});
}
const config = {...configBase,jwks:{keys}};
const verifier = await createJwtHostVerifier(config);
const payload = () => ({iss:issuer,aud:config.accessAudience,sub:'synthetic-agent',
  iat:seconds-10,exp:seconds+60});
const sign = (claims=payload(),header={},alg='EdDSA',key=pairs.get(alg).privateKey) =>
  new SignJWT(claims).setProtectedHeader({alg,kid:'host-'+alg,typ:'at+jwt',...header}).sign(key);
for (const alg of pairs.keys()) {
  const claims = payload();
  const verified = await verifier.verifyAccessToken(await sign(claims,{},alg));
  assert.deepEqual(verified,claims); checks++;
  verified.sub='mutated-detached-copy';
  assert.equal((await verifier.verifyAccessToken(await sign(claims,{},alg))).sub,'synthetic-agent'); checks++;
}
const decision = {...payload(),aud:config.decisionAudience,sub:'synthetic-human',quoteId:'Q-1',
  snapshotId:'S-1',decision:'approve',jti:'synthetic-decision-1'};
assert.deepEqual(await verifier.verifyDecisionProof(await sign(decision,{typ:'buyer-decision+jwt'})),decision);checks++;
await refused(verifier.verifyAccessToken(await sign(decision,{typ:'buyer-decision+jwt'})));
await refused(verifier.verifyDecisionProof(await sign()));
await refused(verifier.verifyAccessToken(await sign({...payload(),iss:'https://untrusted.example.invalid/'})));
await refused(verifier.verifyAccessToken(await sign({...payload(),aud:'urn:elsewhere'})));
await refused(verifier.verifyAccessToken(await sign({...payload(),aud:[config.accessAudience,'urn:elsewhere']})));
await refused(verifier.verifyAccessToken(await sign(payload(),{typ:'JWT'})));
await refused(verifier.verifyAccessToken(await sign(payload(),{kid:'unknown'})));
for (const field of ['iss','aud','sub','iat','exp']) {
  const claims=payload();delete claims[field];await refused(verifier.verifyAccessToken(await sign(claims)));
}
for (const claims of [{...payload(),exp:seconds},{...payload(),iat:seconds+1},
  {...payload(),nbf:seconds+1},{...payload(),exp:seconds+901},{...payload(),exp:seconds-10},
  {...payload(),iat:seconds-901,exp:seconds+1},{...payload(),iat:seconds-0.5},
  {...payload(),sub:''},{...payload(),nested:{data:'x'.repeat(4097)}},
  {...payload(),array:Array(65).fill(0)},{...payload(),nested:JSON.parse('{"__proto__":{"admin":true}}')}]) {
  await refused(verifier.verifyAccessToken(await sign(claims)));
}
await refused(verifier.verifyDecisionProof(await sign({...decision,iat:seconds-10,exp:seconds+291},{typ:'buyer-decision+jwt'})));
const forged = await generateKeyPair('EdDSA');
await refused(verifier.verifyAccessToken(await sign(payload(),{},'EdDSA',forged.privateKey)));
const good = await sign();
const parts=good.split('.');parts[2]=(parts[2][0]==='A'?'B':'A')+parts[2].slice(1);
await refused(verifier.verifyAccessToken(parts.join('.')));
const unsigned = Buffer.from(JSON.stringify({alg:'none',typ:'at+jwt',kid:'host-EdDSA'})).toString('base64url')+
  '.'+Buffer.from(JSON.stringify(payload())).toString('base64url')+'.';
await refused(verifier.verifyAccessToken(unsigned));
const noAlg = Buffer.from(JSON.stringify({typ:'at+jwt',kid:'host-EdDSA'})).toString('base64url')+'.'+good.split('.')[1]+'.'+good.split('.')[2];
await refused(verifier.verifyAccessToken(noAlg));
const hs = await new SignJWT(payload()).setProtectedHeader({alg:'HS256',kid:'host-EdDSA',typ:'at+jwt'}).sign(new Uint8Array(32).fill(1));
await refused(verifier.verifyAccessToken(hs));
for (const forbidden of ['jwk','jku','x5u','x5c','crit','b64']) {
  // Inspecting the header must reject before any embedded key or URL could be consumed.
  const header={alg:'EdDSA',kid:'host-EdDSA',typ:'at+jwt',[forbidden]:forbidden==='crit'?['unknown']:'untrusted'};
  const token=Buffer.from(JSON.stringify(header)).toString('base64url')+'.'+good.split('.')[1]+'.'+good.split('.')[2];
  await refused(verifier.verifyAccessToken(token));
}
for (const token of ['',null,{},'x'.repeat(16385),'a.b','a.b.c.d']) await refused(verifier.verifyAccessToken(token));
for (const invalid of [{...config,issuer:'http://host.invalid/'},{...config,issuer:'https://host.invalid/?x=y'},
  {...config,accessAudience:config.decisionAudience},{...config,accessTyp:'JWT'},{...config,decisionTyp:'JWT'},
  {...config,algorithms:['HS256']},{...config,maxAccessAgeSeconds:901},{...config,maxDecisionAgeSeconds:301},
  {...config,jwks:{keys:[]}},{...config,jwks:{keys:[...keys,keys[0]]}},
  {...config,jwks:{keys:[{...keys[2],d:'private-key-must-never-be-accepted'}]}},
  {...config,jwks:{keys:[{kty:'oct',kid:'secret',alg:'HS256',k:'secret'}]}},
  {...config,jwks:{keys:[{...keys[2],x5c:['unvalidated-certificate']}]}},
  {...config,jwks:{keys:[{...keys[2],x:'malformed'}]}},
  {...config,clock:()=>new Date(NaN)},{...config,unknown:true}]) {
  await refused(createJwtHostVerifier(invalid),'HOST_IDENTITY_CONFIG_INVALID');
}
const noSlash = await createJwtHostVerifier({...config,issuer:issuer.slice(0,-1)});
assert.equal((await noSlash.verifyAccessToken(await sign({...payload(),iss:issuer.slice(0,-1)}))).iss,issuer.slice(0,-1));checks++;
config.jwks.keys.length=0;
assert.deepEqual(await verifier.verifyAccessToken(good),payload());checks++;
assert.deepEqual(verifier.configurationStatus(),{configured:true,verification:'PINNED_PUBLIC_JWKS',
  accessTyp:'at+jwt',decisionTyp:'buyer-decision+jwt',keyCount:3,algorithms:['RS256','ES256','EdDSA'],
  maxAccessAgeSeconds:900,maxDecisionAgeSeconds:300,identityAndConsentAuthority:'EXTERNAL_HOST_ONLY'});checks++;
console.log(JSON.stringify({check:'pinned-jose-host-access-and-separate-decision-verification',outcome:'PASS',
  assertions:checks,algorithms:['RS256','ES256','EdDSA'],providerCalls:0,realIdentities:0}));
