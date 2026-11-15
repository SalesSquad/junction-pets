# Cala host-only evidence provider milestone

Work `J26-PF-CALA-M350-M3-20261114`, base
`3e2aeaf69cb7a54c79ba3a35c06dfd9ade89d3e1`. **Maturity remains 2/6.**
No authenticated Cala execution, sponsor qualification or live source claim.
This new subtree leaves the existing product, stub, browser and source manifest
unchanged. It reuses `core.mjs` goal validation and its evidence rules; it does
not feed arbitrary provider payloads into the browser fixture ranker.

## Offline use (Node 22+, no dependencies)

From `solutions/cala-founder-opportunity-graph`:

```sh
node provider/cli.mjs lead
node provider/cli.mjs lead --human-reviewed
node provider/cli.mjs duplicates
node provider/cli.mjs forged-source
node --test provider/provider.test.mjs
```

CLI uses only `SYNTHETIC_PROVIDER_REPLAY`, never credentials or network. Every
identity, source, public-rights verification and lead assertion is fictional,
including the verified-sounding issuer announcement at `example.invalid`.
`--human-reviewed` is an explicit local review assertion after inspecting the
preview, not an authenticated reviewer attestation. Without it the result is a
preview requiring human review. Negative cases are listed by the CLI usage.
No server, daemon, persistence, outreach, contact details or private raw response
export exists. Redirect stdout only to an owner-approved destination if desired.

## Host bridge contract (not Cala wire documentation)

`preview({host, query, approvedEntityId, goal, clock, identity, limits?})`
accepts **already authorized injected capabilities**, never an API key or URL.
The future trusted host alone owns the documented `https://api.cala.ai/mcp/`
transport and `X-API-KEY`, schema translation, streaming byte cap, cancellation,
public-source rights, identity authentication, consent and revocation. This
module cannot make an untrusted injected implementation trustworthy.

- `identity`: bounded nonempty `actorRef`, `tenantRef`, `approvalRef`, kept out of
  output except a request-context hash. These are context, never self-issued grants.
- `clock`: explicit ISO `now` and matching `asOf` date. Host must supply actual
  trusted time. The replay fixes both; no wall-clock freshness claim is implied.
- `query`: at most 160 characters; fixed existing founder goal validation.
  No fuzzy selection: caller must provide a user-approved exact UUID **before**
  the walk. Search must return exactly one resolved, public match to that UUID.
- `host.tools`: exactly `entity_search`, `entity_introspection`,
  `entity_retrieval`, each `{name, capability:'read', readOnly:true}`.
  Lookup is not needed for this search implementation; all other tools refuse.
- `host.authorize({identity, clock, approvedEntityId, goal, name, signal})` must
  return exactly `true` before each tool operation, checking the already-granted
  authority, exact entity approval, data rights and current revocation.
- `host.callTool({name, arguments, signal, maxResponseBytes})` returns UTF-8 JSON
  bytes/string. Host must cap streaming bytes **before buffering**, honor abort,
  disallow background continuation and translate to the actual discovered MCP
  tool argument/output schema. No particular Cala tool argument schema is assumed.
  This module checks bytes again before parsing. In-process callbacks must not
  block the event loop; an arbitrary blocking/misbehaving callback cannot be
  preempted by JavaScript timers.

The narrow bridge returns these envelopes, translated by the trusted host:

1. Search: `{entities:[{id, identity:'resolved', public:true}]}`. At most 25.
2. Introspection: `{entityId, fields:[{key, semantic}]}`. At most 40 descriptors.
   `key` is the actually observed provider field name; `semantic` is an
   **explicit host-verified interpretation**, not model inference or a default
   naming convention. Exactly one unique mapping is required for each of
   `investorId`, `issuerId`, `economicRoundId`, `kind`, `role`, `lead`, `eventDate`,
   `stage`, `sector`, `geography`, `source`. Missing/ambiguous mapping refuses;
   unknown enums must remain unknown, never mapped by guesswork. Replay uses
   arbitrary `observed_N` keys to exercise this path.
3. Retrieval: `{entityId, rows:[{[observedKey]:value,...}]}`. Requests only those
   inspected keys, bounded to 100 rows. Both entity bindings must match exact UUID.
   Source values are host-normalized `{id, originId, url, publishedAt,
   credibility:'primary'}`; these asserted fields alone do **not** verify origin.

`host.verifySource({identity, clock, approvedEntityId, goal, source, claim,
claimDigest, signal})` is a separate host-owned provenance and disclosure check.
It must validate the original public issuer source and its explicit investor,
lead, economic round and date assertion against the **whole exact claim**, not
merely echo provider data or check URL syntax. It returns `{claimDigest, url,
originId, issuerId, primary:true, public:true, verifiedAt:clock.now}` only on
success. Source/claim objects are bounded copies; no automatic URL fetch exists.
A forged digest, origin, issuer, URL, stale verification time or nonpublic source
is withheld. Real host qualification must include malicious-source cases.

## Decisions, bounds and integrity

Read sequence is search → introspection → retrieval; no pagination or retries.
Defaults: per-call 5 seconds, whole walk 15 seconds, 256 KiB per tool response,
25 entities, 100 rows and 106 asynchronous operations (including authorization
and source checks). Overrides only lower bounds. Each pending capability races
a timer and receives an aborted signal when complete/expired; no later result
is consumed. The host remains responsible for actual transport cancellation.

Unknown roles, lead status, event kind or economic identity abstain. `ISSUER`
is never an investor. Dedup uses explicit `(issuer UUID, economic round ID)`;
filings never establish or multiply a round. Conflicting lead/date claims block
that round. Goal-window and preceding-365-day checks exclude stale rounds.
Every accepted funding claim requires separately verified primary provenance.
No amount is interpreted or summed; missing remains `UNKNOWN`, never zero.
The result exposes UUIDs, dates, deduplicated citation references and reason
codes; no provider free text, response bodies, actor/tenant references or host
exceptions are exported. The host must authorize final disclosure as well.

`reviewPreview(result,{approved:true,evidenceDigest})` requires the exact preview
hash and returns a human-reviewed **evidence-only** shortlist. It is a local
assertion helper, not an authorization or anti-forgery boundary; a caller can
construct JSON and hashes. Host must authenticate actual review/disclosure.
HOLD means no supported evidence/review; REFUSE means invalid input, identity,
authority, schema, bounds or failed capability. Other supported rounds can
survive a withheld round; exclusions remain visible.

Returned objects are recursively frozen. The SHA256 JSON chain binds the hashed
request context and exact observed bridge response bytes and verified claims.
Each entry hashes `{index,stage,digest,previous}` using JS JSON serialization;
initial previous is 64 zeroes. `evidenceDigest` hashes the serialized evidence.
It is labeled **INTEGRITY NOT AUTHENTICITY**: no signature, trusted timestamp,
append-only storage, provider attestation or resistance to recomputing the whole
chain is claimed. Replay determinism holds for identical inputs/bytes/config.

## Source and remaining gate

Read Cala/M350 in `docs/challenge-research/current-source-catalog.json` snapshot
2026-11-14, latest clarification before older guidance, and existing product
core, contract, fixture and README. Source instructions: search/lookup →
introspection → retrieval; missing ≠ zero; ISSUER ≠ INVESTOR; filings can duplicate
economic rounds. No saved Knowledge OS reference was reused; that tool family
was not available in this runtime.

Remaining dependency: a separately authorized trusted host implementing actual
MCP discovery/schema translation, account/key storage, source rights and public
origin verification, followed by held-out authenticated Cala qualification.
There is no browser wiring, live call, automatic maturity increase, sponsor
claim or deployment in this milestone. Coordinator owns commit/PR; this worker
only writes `provider/**` and runs its offline tests.

The host bridge must serialize compact canonical JSON with unique keys. Duplicate or ambiguous object members fail closed before any claim is consumed. Raw provider formatting must be normalized by the trusted host without silently discarding conflicting values.
