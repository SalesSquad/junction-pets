# Challenge knowledge and agent composition

The 34 independently versioned agents are specialists that can collaborate through one authorized host. They are not34 unrelated chatbots or34 permanently running workers. Each package now contains its exact current challenge/technology sources, bounded role, expected proof and preferred peer proposals in runtime AGENTS.md. The existing plugin producer embeds that same public guidance into the 34 generated skills. Developer research remains in CHALLENGE_RESEARCH.md and the shared source index.

## Chibi Agent Mesh — implementation sequence (14 November 2026)

**Product decision:** A pet is one continuing Chibi companion, not a duplicate per
challenge. Junction adds a *view* of the 34 existing company specialists; a
solution may reference several pets and the same pet may serve several solutions.
Golfer, Sailor and other existing Chibi companions keep their original Chibi
identity, passport, art and skills. They may join a solution when relevant, but
must not be copied into `pets/` or renamed as company sponsors.

| Layer | Existing owner / source | Next addition, without parallel infrastructure |
| --- | --- | --- |
| Identity and art | 34 `pets/*/pet.json` with unique `artIndex`; original 6×6 atlas in `apps/catalog/public/assets/company-mascots.png`; Chibi Pet Passport | Reuse art and stable IDs in Council trace. The private host remains the identity and avatar authority for adopted pets. |
| Solution membership | Junction solution workspace successor [PR #82](https://github.com/SalesSquad/junction-pets/pull/82), `agentIds[]` and `capabilityUses[]` | Join solution, pet and declared capability in the workspace. Do not create a second product-to-agent registry. |
| Peer selection | `ops/agent-composition-20261113.json` proposals; `services/pet-adapters/` declared capabilities; Council contract v1 | Rank eligible recipients by declared skill, context fit and evidence. Proposals never confer authority. |
| Request and decision | `contracts/pet-collaboration/v1/`; private Chibi `pet_collaboration.rs`, Cedar and HostPolicy | Send a bounded, source-bound help request **only after** the host maps its scope to a known Cedar action and authorizes the recipient. Admission is currently not dispatch. |
| Execution and receipts | Chibi PetExecutor, artifact store, revocation, receipts; Council replay | Record actual host call, source, model/tool/effect, cost and recipient result with a host-signed receipt. No public trace includes private payloads. |
| Marketplace display | Chibi Junction bundle refresh [PR #109](https://github.com/SalesSquad/chibi/pull/109) | Project the verified membership and sanitized receipts into Chibi, with labels for simulated/proposed/host-verified work. Do not replace the existing catalog. |

### Milestones and acceptance

1. **Visible slice — this branch:** augment the already functioning
   `apps/collaboration-demo/` trace with each participant's canonical atlas
   index. Render existing avatar art in team, scenario and handoff timeline,
   with initials if the local atlas fails to load. The deterministic fixture and
   SHA-256 trace integrity remain unchanged except for the newly included field.
2. **Challenge-specific teams:** after the existing solution workspace source
   is accepted, show one selected solution and its related specialists, not all
   122 proposed edges. Render proposal vs actual handoff as different states.
3. **Host-gated `request_peer_help`:** use Chibi's existing per-tenant
   admission seam, skill intersection, Cedar action mapping, scoped context
   capsule, nonce/expiry and budget. Preserve cycle/depth limits, deny unknown
   skills, revocations, unapproved effects and cross-tenant delegation.
4. **Intelligent routing (opt-in):** evaluate Proofmatch/capability matching,
   Jev/Typesafe evidence, OpenAI Responses/Decisions and other provider
   proposals against a deterministic policy baseline. Model-generated choices
   remain suggestions until a Chibi host decision and verified receipt.
5. **Real product reuse:** prove one authorized peer-help flow; then compose
   existing Golfer/Sailor, Meta, NVIDIA, Aimo or Rokoko companions into the
   relevant challenge solutions without cloning accounts, art or execution
   engines. Prefer one useful end-to-end interaction to a large unverified graph.

**Evidence labels:** `SYNTHETIC` = fixture replay, `PROPOSED` = unexecuted
capability match, `HOST_VERIFIED` = actual private host receipt. Public
visualizations must never infer the third state from a graph edge, GitHub PR,
manifest or checksum. No new provider spending, identity scopes, host grants,
merges or deployment are part of the visible slice.

## One source map, one execution authority

- [Fresh19 main and19 technical briefs](challenge-research/README.md) own challenge facts and captured material links.
- [34-agent composition graph](../ops/agent-composition-20261113.json) owns proposed peer edges and the first recipe. A graph edge is not a grant or installed tool.
- The pet manifest owns declared capabilities/version; AGENTS.md owns packaged model guidance. Its content hash binds the actual public knowledge text.
- The existing Chibi host owns identity, consent, capability discovery, policy, execution, source admission, durable receipts and private memory. Continue through HostPolicy.decide, PetExecutor.invoke and HostArtifactStore. No second coordinator or secret-sharing system is introduced.
- [PR56](https://github.com/SalesSquad/junction-pets/pull/56) supplies an explicitly offline34-operation registry and finite Aiven workflow. A local declaration checker is not drawing QA, live procurement or a bank connection.

Private videos, Discord member dumps, raw portfolio context, account credentials and unapproved peer histories are not inserted into public runtime instructions. Forward a narrow approved task capsule and return an attributed result. Raw provider outputs belong in the private host artifact store, not public envelopes or graph checkpoints.

## First vertical slice: Stoa asks NVIDIA

The source recipe is at services/stoa-nvidia/index.mjs. prepareStoaDrawingTask creates a fixed source-bound task; runStoaNvidiaDrawing invokes the NVIDIA runDrawingObservation operation and checks the returned source/page/region bindings before presenting a candidate or abstention.

1. Stoa identifies the drawing revision, question and cleared regions. The input binds source ID/SHA256, page, region IDs, normalized bounds and actual image hashes.
2. The host admits the exact Stoa→NVIDIA drawing-observation request. In production it rechecks actor, tenant/user, recipient, source, context, effect, fence, expiry and budget. The developer CLI is a separate bounded source harness.
3. NVIDIA uses the exact Nemotron 3.5 Super VL model to return region-cited observations and uncertainty. The drawing task has no invented benchmark rows and does not call benchmark comparison merely to satisfy another workflow.
4. Stoa verifies the returned source/artifact and region evidence, then formats an attributed candidate or abstains. Formatting that result is not a third privileged model node.
5. Drawing interpretation is unverified visual evidence until checked against the authoritative geometry and held-out answers. It does not certify quantities, structural safety, clinical claims or company systems.

The model's own verification pass is not an independent factual proof. In production, wrap every provider call in the existing host's current policy/fence/budget checks; a one-time recipe-start decision is insufficient. Parent consumption must be attested through the host's own artifact store.

## Data and result contract

| Stage | Minimum input | Returned evidence | Failure behavior |
| --- | --- | --- | --- |
| Stoa preparation | Question, source revision/page, cleared image regions and hashes | Exact parent task/input digest, actor and recipient IDs | Reject malformed or inconsistent source/regions |
| NVIDIA drawing observation | Bounded prepared request and approved provider connection | Source and region citations, candidate/uncertainty, actual model/call metadata | Abstain or fail on unknown model, invalid output, unsupported region or provider failure |
| Stoa readback | Original task plus returned NVIDIA result | Attributed candidate tied to the same source/artifact | Reject substituted result or missing/mismatched source binding |
| Production host | Current policy, artifact-read authority and immutable producer output | Durable host-bound execution/consumption receipts | Deny expired, revoked, cross-tenant or stale-fence requests |

Only the fixed developer drawing recipe is newly connected in source. Other graph edges are planning/guidance proposals, and must pass the existing host admission and actual adapter qualification before being called. Preserve LIVE, REPLAYED, SYNTHETIC and OFFLINE_DETERMINISTIC labels. Source code, an injected transport test, a zero-network plan and a live provider response are different evidence.

## Agent-specific composition map

| Agent | Exact current brief or support scope | Preferred peer tasks |
| --- | --- | --- |
| aalto-university | Aaltonomous Humanoid, Beyond the Clinic | nvidia / integration-design, verda / integration-design, intel / challenge-design, qualia / support-design, google-deepmind / integration-design |
| afterquery | Break the Agent | openai-codex / integration-design, verda / integration-design, google-deepmind / integration-design, featherless / support-design, qualia / support-design |
| aiven | Best Use of Aiven | mariadb / challenge-design, afterquery / challenge-design, craci / integration-design |
| arduino | The Green European Renaissance, Best use of Arduino Uno Q | scailab / support-design, wendy / support-design, nvidia / integration-design, qualia / support-design |
| astrazeneca | Equal Care Across Finland | exa / challenge-design, mariadb / challenge-design, google-deepmind / integration-design |
| atech-dev | Atech Real World Challenge | arduino / challenge-design, wendy / support-design, qualia / support-design |
| bahn-express | Spread | afterquery / challenge-design, aiven / integration-design, modal / integration-design |
| cala | Make Unicorns Real | exa / challenge-design, context-dev / challenge-design, aiven / integration-design |
| city-of-espoo | Rethinking Recruitment | cala / challenge-design, exa / challenge-design, afterquery / challenge-design |
| cloudinary | Best Use of Cloudinary | modal / integration-design, nvidia / integration-design, qualia / support-design |
| context-dev | The Web Is Your Real-Time Database, Best Use of Context.dev: Fully Structured Web | exa / challenge-design, oxylabs / integration-design, aiven / integration-design |
| craci | Best use of CRACI | tieto / challenge-design, openai-codex / integration-design, afterquery / challenge-design |
| exa | The Internet Butler / Your Personal Assistant | context-dev / challenge-design, oxylabs / integration-design, aiven / integration-design |
| featherless | Supporting role; no matching prize brief | afterquery / challenge-design, google-deepmind / integration-design, nvidia / integration-design |
| google-deepmind | Best Use of Gemini API, Best Use of Gemma | nvidia / integration-design, verda / integration-design, afterquery / challenge-design |
| hostinger | Decode the Noise | context-dev / challenge-design, aiven / integration-design, oxylabs / integration-design, exa / challenge-design, afterquery / challenge-design |
| ignite-next | Stop Simulating, Start Moving: See It. Detect It. Act on It. The Intel Physical AI Challenge | intel / challenge-design, nvidia / integration-design, scailab / support-design, verda / integration-design, qualia / support-design, wendy / support-design |
| intel | Stop Simulating, Start Moving: See It. Detect It. Act on It. The Intel Physical AI Challenge | ignite-next / challenge-design, nvidia / integration-design, scailab / support-design, qualia / support-design |
| ironshard | Supporting role; no matching prize brief | aiven / integration-design, modal / integration-design, qualia / support-design |
| mariadb | Wikipedia Through Time. | google-deepmind / integration-design, exa / challenge-design, afterquery / challenge-design |
| meta | AI Glasses for Everyone, Everyday | nvidia / integration-design, qualia / support-design, wendy / support-design, cloudinary / integration-design |
| modal | Best use of Modal | verda / integration-design, nvidia / integration-design, ironshard / support-design |
| nvidia | Best Use of Nemotron | modal / integration-design, verda / integration-design, intel / challenge-design, scailab / support-design, qualia / support-design |
| openai-codex | Best Use of Codex | tieto / challenge-design, craci / integration-design, afterquery / challenge-design |
| oxylabs | Best agentic usecase of Oxylabs Web API | context-dev / challenge-design, exa / challenge-design, aiven / integration-design |
| qualia | Supporting role; no matching prize brief | scailab / support-design, rokoko / challenge-design, afterquery / challenge-design |
| rokoko | The Robot Teleoperation Challenge | nvidia / integration-design, qualia / support-design, verda / integration-design, wendy / support-design |
| s-pankki | Personal Economic Trainer | mariadb / challenge-design, aiven / integration-design, afterquery / challenge-design, exa / challenge-design |
| scailab | Supporting role; no matching prize brief | nvidia / integration-design, intel / challenge-design, qualia / support-design |
| stoa | Make Blueprints Talk | nvidia / drawing-observation, mariadb / challenge-design, cloudinary / integration-design, modal / integration-design, exa / challenge-design |
| tieto | Earned Trust in AI Code | openai-codex / integration-design, craci / integration-design, afterquery / challenge-design |
| valio-aimo | Trusted Trade Agents | aiven / integration-design, afterquery / challenge-design, tieto / challenge-design, context-dev / challenge-design |
| verda | Verda Compute Track | nvidia / integration-design, modal / integration-design, afterquery / challenge-design, google-deepmind / integration-design |
| wendy | Supporting role; no matching prize brief | arduino / challenge-design, intel / challenge-design, qualia / support-design |

## Checks and current limits

Run npm run agents:check, npm run plugins:check, npm run validate, npm test, npm run build and npm run demo:stoa-nvidia. The default demo is zero-network. The explicit execute path requires the clean pinned source and a host-managed NVIDIA key; a missing key must cause zero provider calls.

Current author verification and exact source receipt are in the task PR. Real-provider vision accuracy, hosted Chibi adoption/authorization, live peer routing, hardware performance and publication remain separate acceptance gates. Existing historical Fable/model responses remain tied to their previous package bytes; regenerated knowledge does not inherit those scores.

The six additional MLH technology challenges remain in the shared19-technology source index without fabricated company agents. Aalto's two independent briefs and Intel/Ignite's shared challenge keep separate identifiers. No automatic dispatch, provider fallback, new grant, resource provisioning or public submission is authorized by this graph.
