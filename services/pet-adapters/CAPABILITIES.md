# Offline callable companion capabilities

Work ID: `junction.adapters.registry`; source base: `61f10a44cfd833e02fa64462dfc7429046fff210`.

`registry.mjs` binds **one existing executable local analyzer for each of the 34 companions**. Before this registry the company modules had separate interfaces and were not discoverable through one execution API. These bindings perform useful deterministic computation on supplied fictional/synthetic declarations. They do not add models, training, an MCP server, Aiven project access, network retrieval, Chibi authorization, or deployment.

## Contract

```js
import {discoverCapabilities, getCapability, executeCapability} from './registry.mjs';

const all = discoverCapabilities();
const aiven = discoverCapabilities({petSlug: 'junction-aiven'});
const schema = getCapability('mariadb.explain-evidence'); // descriptor or null
const shortlist = await executeCapability('aiven.docs-shortlist', {
  query: 'Kafka consumer group lag',
});
const review = await executeCapability('afterquery.failure-rubric', {
  jsonText: JSON.stringify(suppliedSyntheticTrace),
});
```

Discovery returns independent JSON copies of descriptors containing stable IDs, company/pet identities, an exact input-envelope JSON Schema, mode, `effect:'none'`, `network:'none'`, `evidenceTier:'deterministic-analysis'` and honest connection flags. Filtering accepts only the optional `petSlug` field. An unknown well-formed pet returns an empty list. Unknown capability lookup returns `null`; execution returns `UNKNOWN_CAPABILITY`. Original content-only guidance IDs are not implicitly executable: only the explicit IDs below can run.

The Aiven envelope is exactly `{query:string}` with 3–256 UTF-16 code units. All other envelopes are exactly `{jsonText:string}`: primitive JSON text for the linked company contract. NVIDIA expects its JSON root to contain exactly `baseline` and `candidate`. Static imports and a fixed `Map` prevent a capability name from becoming a file path, module import, shell command or arbitrary function. No client options inject a transport, filesystem path, credentials or provider URL.

JSON input is bounded to 65,536 UTF-8 bytes, depth 12, 10,000 values and 1,000 entries per array. Duplicate keys (including escaped equivalents), malformed Unicode, nonfinite numbers and prototype-related property names are refused. Individual company analyzers retain their stricter byte, field, fictional-marker and semantic contracts. AfterQuery additionally receives exact root/event-field checks because its earlier standalone rubric ignored extra properties. Envelope accessors, non-enumerable fields, symbols, custom prototypes and serialization hooks are refused without evaluating their values. JavaScript Proxies are outside the plain-data contract; this module is not a sandbox for executable caller objects.

Successful execution resolves **after computation** as:

```json
{
  "ok": true,
  "capabilityId": "afterquery.failure-rubric",
  "petSlug": "junction-afterquery",
  "execution": "offline-deterministic",
  "providerConnected": false,
  "chibiHostVerified": false,
  "result": {"verdict": "FAIL", "execution": "unknown", "reporting": "unsupported-success"}
}
```

`ok:true` means the analyzer completed, including a legitimate negative/invalid scenario verdict. It does **not** mean the supplied scenario passed, evidence was authenticated or a provider action happened. Exceptions become bounded `INVALID_INPUT` responses without supplied text or stack traces. Results are JSON copies capped at 262,144 UTF-8 bytes; exceeding that returns `RESULT_TOO_LARGE`. No request/response content is persisted. Aiven's `MATCHES_UNVERIFIED` remains an offline source shortlist; use the separately authorized pinned-doc retrieval adapter for actual public-document byte verification.

## Explicit bindings

| Company | Capability ID | Existing source |
| --- | --- | --- |
| aalto-university | `aalto-university.experiment-card` | [Contract](../../pets/aalto-university/) |
| afterquery | `afterquery.failure-rubric` | [Contract](../../pets/afterquery/) |
| aiven | `aiven.docs-shortlist` | [Contract](aiven/README.md) |
| arduino | `arduino.compatibility` | [Contract](../../pets/arduino/) |
| astrazeneca | `astrazeneca.evidence-card` | [Contract](../../pets/astrazeneca/) |
| atech-dev | `atech-dev.bom-check` | [Contract](../../pets/atech-dev/) |
| bahn-express | `bahn-express.custody-timeline` | [Contract](../../pets/bahn-express/) |
| cala | `cala.field-provenance` | [Contract](../../pets/cala/) |
| city-of-espoo | `city-of-espoo.service-routing` | [Contract](../../pets/city-of-espoo/) |
| cloudinary | `cloudinary.responsive-media` | [Contract](../../pets/cloudinary/) |
| context-dev | `context-dev.snapshot-extraction` | [Contract](../../pets/context-dev/) |
| craci | `craci.sbom-review` | [Contract](../../pets/craci/) |
| exa | `exa.search-ranking` | [Contract](../../pets/exa/) |
| featherless | `featherless.model-comparison` | [Contract](../../pets/featherless/) |
| google-deepmind | `google-deepmind.evaluation-plan` | [Contract](../../pets/google-deepmind/) |
| hostinger | `hostinger.dns-review` | [Contract](../../pets/hostinger/) |
| ignite-next | `ignite-next.experiment-plan` | [Contract](../../pets/ignite-next/) |
| intel | `intel.benchmark-comparison` | [Contract](../../pets/intel/) |
| ironshard | `ironshard.storage-matrix` | [Contract](../../pets/ironshard/) |
| mariadb | `mariadb.explain-evidence` | [Contract](../../pets/mariadb/) |
| meta | `meta.wearable-permission` | [Contract](../../pets/meta/) |
| modal | `modal.job-spec` | [Contract](../../pets/modal/) |
| nvidia | `nvidia.benchmark-comparability` | [Contract](../../pets/nvidia/) |
| openai-codex | `openai-codex.handoff-review` | [Contract](../../pets/openai-codex/) |
| oxylabs | `oxylabs.collection-plan` | [Contract](../../pets/oxylabs/) |
| qualia | `qualia.episode-review` | [Contract](../../pets/qualia/) |
| rokoko | `rokoko.retargeting` | [Contract](../../pets/rokoko/) |
| s-pankki | `s-pankki.sms-guidance` | [Contract](../../pets/s-pankki/) |
| scailab | `scailab.perception-coverage` | [Contract](../../pets/scailab/) |
| stoa | `stoa.handoff-proof` | [Contract](../../pets/stoa/) |
| tieto | `tieto.workflow-review` | [Contract](../../pets/tieto/) |
| valio-aimo | `valio-aimo.recipe-scaling` | [Contract](../../pets/valio-aimo/) |
| verda | `verda.gpu-run-plan` | [Contract](../../pets/verda/) |
| wendy | `wendy.sensor-triage` | [Contract](../../pets/wendy/) |

## Verification and host integration

```sh
node --test services/pet-adapters/registry.test.mjs
npm run validate
```

The focused suite executes all 34 actual company fixtures through the registry, checks useful Aiven/MariaDB/AfterQuery/NVIDIA results, preserves negative evidence, and exercises routing/input/refusal/mutation/network boundaries. Existing company suites remain the domain-behavior authority. These tests are portable local evidence, not executed model evaluations or signed host qualification.

This is a **Node-only service module**: some existing analyzers require `node:crypto`/`Buffer`. A browser must consume a reviewed server adapter or a separate browser-safe contract; do not bundle the Node registry into the catalog. Any later MCP/HTTP host must validate its own identity, source, tenant, permission, output/privacy, rate and effect boundaries before exposing private data or real provider actions. The current offline API grants none of those rights.
