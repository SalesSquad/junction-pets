# Buyer identity and host consent

Implemented in the existing local synthetic trade service. This is a verified-host integration boundary, not a new identity provider, organization directory, login service or claim of legal identity. Real supplier orders and funds remain disabled.

## Trust and activation

An approved private host owns login, membership/delegation, access-token issuance and the UI that issues exact signed human decisions. No verified issuer, real buyer mandate or hosted consent service is configured by this source change. Existing personal GitHub/ChatGPT/Valio web sessions do not establish that procurement identity grant.

Install the optional verifier with `npm --prefix identity ci --ignore-scripts`. An operator provisions an owner-held 0600 JSON file outside source and iCloud, then sets `VALIO_IDENTITY_CONFIG=/absolute/private/path.json` and a **new** `VALIO_STATE_FILE` before `npm start`. Host mode requires the persistent runtime; VALIO_EPHEMERAL=1 refuses instead of losing single-use consent/replay state. No secrets are requested through tool/model arguments or a token-paste form. A bad config, missing dependency, changed issuer profile or incompatible state refuses startup; there is no anonymous fallback.

Configuration fields:

- `profileId`: stable opaque identifier of this approved host/buyer deployment.
- `issuer`: exact HTTPS issuer; `accessAudience` and `decisionAudience` must differ.
- `jwks`: operator-verified **public-only** signature JWKS. Algorithms are explicitly limited to RS256, ES256 and/or EdDSA; no token-supplied key URL or discovery.
- `grants`: at most 256 private mappings, each with `subject`, `buyerId`, `ownerScope`, `principalType` (HUMAN/AGENT), `active`, integer `revision`, `actions` and `maxOrderCents` (1..250000, additionally bounded by domain policy).
- Actions: `read`, `prepare`, `commit`, `cancel`, `relay_decision`, `approve`, `pay`, `audit`, `inventory`. AGENT cannot hold approve/pay. Explicitly assigning the same ownerScope delegates shared workflow access; buyerId alone never joins unrelated scopes. Audit/ledger history requires the separate audit grant.

Only the current single synthetic buyer is served. The adapter is not a multitenant commerce system. Subject mappings remain in the private operator file; state, API output and audit use pseudonymous actor/owner hashes. The same subject/owner scope survives access-token rotation. The state file pins host versus demo mode, profile and issuer; existing anonymous workflows cannot be adopted into host ownership.

Grant activation/revocation and revision changes are reread from the private file on each authorization check, including immediately before cached-success replay and after awaited I/O. Verifier settings/public keys require an explicit restart when changed; operator must preserve the intended profile identity through a legitimate key rotation.

## Exact human decisions

Every host request authenticates a short-lived `at+jwt`. The access role, an amr/acr field, a synthetic MCP form or a model's approve argument is **not** consent. A decision requires a separate `buyer-decision+jwt`, signed by the approved host for the separate decision audience, sent privately as `X-Buyer-Decision-Proof`.

Required signed decision claims, in addition to iss/aud/sub/iat/exp:

- `profileId`, `buyerId`, opaque `ownerRef`, `reviewerGrantRevision`; sub must currently map to an active HUMAN with approve/pay authority in that same owner scope.
- `action`: QUOTE_DECISION or PAYMENT_DECISION; `decision`: approve/reject.
- Exact `quoteId`, `snapshotId`, `quoteBodyDigest` (existing canonical SHA256 base64url), `totalCents`.
- Unique bounded `jti`, lifetime at most 300 seconds. Current time and grants are rechecked inside the state transaction.
- Payment additionally requires exact `orderId` and `paymentProposalDigest`; purchase consent never grants payment consent.

An actor needs the relevant decision action or explicit relay_decision authority to submit already signed human evidence. Host state-changing commands require stable Idempotency-Key headers. Nonce, command scope, evidence digest, actor reference and domain decision are recorded in one SQLite transaction. A nonce cannot authorize a different command; a cached response still requires current access and current reviewer authority. Expired evidence can be reconciled by reading status; it is never extended by a retry. Domain quote-only budget exceptions, source freshness and signed buyer mandate remain independently enforced.

`GET /api/identity/decision-context?quoteId=...&action=QUOTE_DECISION` returns the exact owned context for a trusted host UI/signer, without consent. PAYMENT_DECISION additionally takes orderId. The private host must bind the displayed terms to the human interaction before issuing proof; this repository cannot prove physical human presence or the host's honesty.

## Clients and data

`/api/identity/configuration` is public configuration-only; `/api/identity/me` exposes sanitized current grants. Private quotes, bodies, proofs, orders, runs and history are protected in host mode. Audit remains private and separately privileged. Authentication is performed before replay lookup, and network verification never holds the SQLite write lock.

MCP accepts trusted executor callbacks (or private owner-held token/proof files); credentials and consent proofs are absent from tool arguments and persisted client state. The client pins workflow restore to profile/owner. Native local demo browser pages explicitly pause in host mode and do not mint a replacement demo session, accept pasted external tokens or infer a login. A host's authenticated browser session/CSRF/login integration must be supplied by that host; none was configured or deployed here.

No raw external token, proof JWT, subject/email or host signing key is stored in trade state, audit or tools. Synthetic supplier/buyer keys in the existing private local database retain their documented prototype custody boundary.

## Qualification

- `node --test tests/buyer-identity.test.mjs tests/persistent-http.test.mjs tests/valio-order-connection.test.mjs`: injected-verifier HTTP/policy/persistence checks, including revoked cache replay, unrelated scope, exact proof/nonce, restart and state-mode refusal. This suite does not claim signature verification.
- `npm --prefix identity run check`: 67 real JOSE crypto assertions across RS256/ES256/EdDSA and invalid assertions/configs.
- `npm --prefix identity run check:http`: real signed host access and independent human proof through persistent HTTP, synthetic order/settlement/refund, rotation/restart and non-sendable supplier handoff.
- `node mcp/checks/host-identity.mjs`: official MCP SDK with injected host HTTP server and private executor callbacks; no real person/provider.
- `node tests/browser-resume.browser.mjs`: existing recovery plus explicit host-mode refusal to fall back to anonymous identity.

Exact source, executed outcomes and independent risk-review dispositions are recorded in the delivery PR. No real issuer/account, human identity, Valio order credential, hosted deployment or external order was qualified.

See [identity verifier API and primary references](identity/README.md), [MCP host integration](mcp/README.md) and [Valio order connection](VALIO_ORDER_CONNECTION.md).

The additional `npm --prefix identity run check:mcp` joins the official SDK, private host credential files, real JOSE signatures and persistent HTTP in one executable synthetic end-to-end check (separate quote/payment proof, commit, settlement, refund, no external calls). The real HTTP check also activates the private configuration loader and verifies live grant revocation/revision without restarting.

Recorded human consent is revalidated again before quote commitment and before settlement: its current reviewer grant/revision, exact source/body/amount, approval decision and expiry must still match. An earlier approval does not survive revocation before the effect. Expired nonce replay markers are pruned; the bounded per-quote consent/effect audit remains private provenance, not a credential or login session.

Host proof providers can relay a signed approve or reject decision. A signed payment rejection records refusal and never dispatches settlement. After a successful approval/rejection ACK the client drops matching raw proof from its memory cache; a lost ACK retains the exact proof only until its bounded signed expiry for acknowledgement recovery.
