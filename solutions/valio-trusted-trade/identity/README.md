# Optional host identity verifier

This package verifies assertions issued by an **already trusted private host**. It creates no accounts, OAuth clients, grants, credentials, human identities, supplier connection or purchase authority. Core trade and settlement remain synthetic. The embedding server must map the verified issuer/subject to its current operator-held buyer/workspace grants and independently validate all decision scopes.

Install and check from the solution directory:

```sh
npm --prefix identity ci --ignore-scripts
npm --prefix identity run check
```

The package pins `jose@6.2.17` (npm registry observed 15 November 2026), uses local public JWKS only and has no authorization/discovery/network request path. It supports Node >=22.16. The dedicated check is outside `tests/*.test.mjs`, so the existing dependency-free synthetic suite does not require installing this optional package.

## API

```js
import { createJwtHostVerifier } from './identity/jwt-host.mjs';

const verifier = await createJwtHostVerifier({
  issuer: 'https://approved-host.example.invalid/',
  accessAudience: 'urn:example:trade-api',
  decisionAudience: 'urn:example:trade-decisions',
  jwks: approvedPublicJwks,
  algorithms: ['ES256'],
  accessTyp: 'at+jwt',
  decisionTyp: 'buyer-decision+jwt',
  maxAccessAgeSeconds: 900,
  maxDecisionAgeSeconds: 300,
});
const identityClaims = await verifier.verifyAccessToken(accessToken);
const decisionClaims = await verifier.verifyDecisionProof(hostSignedDecision);
const configurationOnly = verifier.configurationStatus();
```

Both verify methods return a detached plain payload only after JOSE signature, explicit protected header, issuer, exact audience, required claims and time validation. Identity and decision audiences **must differ**. Access tokens cannot substitute for a decision proof, including an access token carrying `role`, `amr` or `acr`. A decision proof still needs the embedding server's exact quote, snapshot, amount, action, decision, expiry and replay/nonce checks. This library does not infer consent from a role or from successful JWT authentication.

The constructor accepts only the fields shown above plus optional `clock: () => Date` for controlled checks. Issuer matching is exact; HTTPS is required. Tokens need integer `iat`, `exp`, nonempty `sub`, and the pinned `iss`/`aud`. Future issuance/not-before, expiration, excessive lifetime/age and multi-audience tokens are refused with zero clock tolerance. Limits are 16 KiB per token, 16 keys / 64 KiB per JWKS, and bounded payload depth/node/string/array sizes.

Every configured JWK requires a distinct `kid`, matching `alg`, and public signature shape. Supported profiles are RSA/RS256, P-256/ES256 and Ed25519/EdDSA; optional `use` must be `sig`, and optional `key_ops` must be exactly `['verify']`. Private/symmetric key material, certificates and arbitrary JWK metadata are refused. A token header may contain only `alg`, `kid`, `typ`: embedded `jwk`, remote `jku`/`x5u`, `x5c`, custom critical headers and unencoded payload options are never consumed.

Public keys must come from the operator-approved host, bound to the fixed issuer through a separate verified configuration process. A syntactically valid JWKS does not establish that trust. Rotation is explicit: replace the public config and construct/restart a verifier; this module never downloads replacement keys or extends an assertion's expiry. The caller must recheck current grants/revocation and time **inside each privileged transaction and before replay lookup**, not reuse a cached authorization result.

Failures expose only `HOST_IDENTITY_CONFIG_INVALID` or `HOST_IDENTITY_INVALID`. Raw tokens, signing material, subjects and JOSE internals are not included in errors, status or logs. Do not put real assertions, identity mappings or private keys in this public source package.

## Evidence and limits

The executable check signs ephemeral synthetic RS256, ES256 and EdDSA tokens with real JOSE crypto, then exercises valid access/separate decisions, forged signatures, wrong issuer/audience/type, access/decision substitution, missing claims, expiry/future/lifetime limits, header key injection, malformed and oversized inputs, public-key/configuration constraints and detached results. It makes zero provider calls and verifies zero real people; passing it is not a hosted login, tenant isolation or genuine human-presence receipt.

Primary API/security documentation:
- [JOSE JWT verification options](https://github.com/panva/jose/blob/main/docs/jwt/verify/interfaces/JWTVerifyOptions.md)
- [JOSE local public JWKS](https://github.com/panva/jose/blob/main/docs/jwks/local/functions/createLocalJWKSet.md)
- [JOSE security policy](https://github.com/panva/jose/security)
- [JWT best current practices, RFC 8725](https://www.rfc-editor.org/rfc/rfc8725.html)
