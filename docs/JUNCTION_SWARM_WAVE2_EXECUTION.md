# Junction Swarm Wave 2 — execution and integration plan

**Work ID:** `JUNCTION-SWARM-W2` (this plan: `JUNCTION-SWARM-W2-CLAUDE`)
**Baseline:** PR4 `4099d930d0cc60b4caf54416317ea84c82f3f4c9`, stacked on PR3 `e102f15504a6cf428edff5b27be2fb581a95e15a`.
**Audience:** coordinator and worker agents. This is a plan, not evidence. Nothing here is provisioned, running or verified unless the Fact table says so.

## 0. Fact vs target

Every row marked **FACT** was read from this repo at the baseline SHA (source in the last column). Everything marked **TARGET** is work this plan schedules; no TARGET may be reported as done without a receipt (section 9).

| Item | Status | Value | Source |
| --- | --- | --- | --- |
| Company pet packages | FACT | 34, each with `AGENTS.md`, `pet.json`, `STORY.md`, `evals.json` | `pets/`, `docs/DEVELOPMENT_SYSTEM.md` |
| Roster roles | FACT | 18 challenge, 13 technology, 2 main (Arduino, Verda), 1 collaborator (Google DeepMind); only those 3 have `roleVerified: true` | `evidence/company-roster.json` |
| Desired per-pet Codex Cloud environment manifests | FACT | 34 files in `ops/environments/`, all `state: unprovisioned`, `environmentId: null` | `ops/environments/mariadb.json` (representative) |
| Ready Codex Cloud environments | FACT | **0**. Existing `chibi-marketplace-cloud` is `Unpublished`, not a Junction env | `docs/DEVELOPMENT_SYSTEM.md` (12 Nov observation) |
| Private Plugin Creator registrations | FACT | 34, `USER_PRIVATE`, provider-reported, source-byte-matched | `ops/plugin-registrations/` |
| Chibi host installation of those plugins | FACT | **Installation unverified**; registration alone gives no evidence | `docs/DEVELOPMENT_SYSTEM.md` |
| Authored behavior eval cases | FACT | 204 (6 per pet), **0 live runs**, 0 provider-verified | `docs/BEHAVIOR_EVALS.md` |
| 4-pet Council demo (OpenAI Codex, MariaDB, NVIDIA, Meta) | FACT | Deterministic synthetic; `hostAuthorization:false`; **not live** | `docs/INTER_PET_COLLABORATION.md`, `lib/pet-collaboration.mjs` |
| Leases | FACT | Filesystem-only (`dist/ops-claims`), single workspace; not distributed | `ops/README.md` |
| PostgreSQL, Chibi host, browser, adoption, provider gates | FACT | Marked absent until independently evidenced | `ops/AGENTS.md` |
| Collaboration contract v1 | TARGET / in progress | W3 is drafting `contracts/pet-collaboration/v1/` in this wave; this path did not exist at the PR4 baseline | W3 task `JUNCTION-SWARM-W2-CONTRACTS` |
| Public submission repo | FACT | `junction-pets` only; repo is currently private; no Chibi source, `ops/` or receipts in submission | `docs/JUNCTION_SUBMISSION.md` |
| Junction challenge brief / eligibility | **UNKNOWN** | Not in repo. Do not invent; check the Junction platform | `docs/JUNCTION_SUBMISSION.md` |
| Reuse sources (MIT, per work order) | TARGET to verify | `carabaestlein/aiven-prototype-agent@8531f3cfb364121314c014e8ec8a72d84c82388e`, `Aiven-Labs/aiven-runtime-langgraph@fcb5ef8bf731b72fd557f3c326adbc58f18da8f7`. The MIT claim comes from the task order; W1 reads `LICENSE` at each pinned SHA before copying anything | work order |

## 1. Architecture (target)

```
PUBLIC junction-pets (submitted)            PRIVATE SalesSquad/chibi (never submitted)
 pets/*  contracts/*  services/*             Rust host: identity, tenant, Cedar PEP,
 council (LangGraph) + adapters  ───IPC───►  grants/revocation, model/tool execution,
 dispatch-ledger client, eval-runner          signed receipts, budget, consent
        │                                            │
        └── PostgreSQL (leases, fencing, checkpoints) ┘  (ledger schema is public;
                                                          the instance is private)
 Mission Control (owner-only, live) reads ledger + receipts; never in the public bundle
```

Decisions (made, not open):

1. **Council graph = LangGraph.** Nodes: `plan → authorize → dispatch → await-receipt → verify → merge-or-fail → human-gate`. State checkpointed to PostgreSQL after every node.
2. **Authorization = host Rust/Cedar.** The Council holds no authority; it submits a `PetCollaborationRequest` with an `authorityRef` and obeys the host decision. `syntheticGrant` from `lib/pet-collaboration.mjs` stays test-only and is rejected when `mode != "synthetic"`.
3. **State = PostgreSQL.** Durable ledger writes (claim, checkpoint, receipt, completion) require a monotonically increasing **fencing token** and reject stale tokens. GitHub pushes use independent expected-HEAD/compare-and-swap checks; GitHub does not understand ledger fencing tokens. Filesystem leases remain for local dev only and are labelled so.
4. **Model/tool calls produce verifiable receipts.** Each receipt binds: request ID, grant/decision ref, provider request ID, model ID, input/output SHA-256, tool name + args digest, cost, source SHA. The host signs; the Council only stores and verifies.
5. **Grants and revocation live in Chibi.** Revocation must take effect before dispatch (recheck) and during a run (next tool call fails closed).
6. **Public/private split.** The submission contains contracts, schemas, Council, adapters, evals, synthetic fixtures. It contains no Chibi code, no `ops/`, no receipts, no secrets (`docs/JUNCTION_SUBMISSION.md`).
7. **Reuse with notices.** From the two Aiven sources, copy only what the Council needs (graph scaffolding, checkpointer wiring, tool-call shape). Each copied file keeps its header; add `THIRD_PARTY_NOTICES` entries with repo, pinned SHA, MIT text and the list of copied paths. The existing `scripts/build-notices.mjs` is the generation route; do not hand-edit generated notices. Aiven/other companies are not endorsing anything.
8. **No GitHub Actions** by default. Checks run in Codex Cloud (when an env is ready), an authorized local machine, or the integrator's host; receipts name where.

## 2. Execution lanes and model routing

| Role | Default | Use for |
| --- | --- | --- |
| Coding | **Codex Cloud** (per-pet env once ready; until then local isolated worktree, stated in the receipt) | All implementation, mechanical tests |
| Meaningful coding / review | **Claude Sonnet (medium)** | Council graph, fencing logic, authz-adjacent code, independent review of diffs |
| Bounded regression | **Claude Haiku (low)** | Re-run a fixed checklist on a frozen diff, short triage; verify its answers |
| Architectural escalation | **Fable**, one-off, bounded question and output | Only for a proven reasoning gap (e.g. fencing/crash-resume invariants, host IPC trust boundary) |

Do not switch Codex Pro/Plus profiles to evade limits. Do not fan out blanket review swarms.

### Owner and external agent surfaces (target; not live)

- **Dot / ChatGPT Work:** owner-only command surface over a read-only Mission Control MCP tool. Dot may propose or enqueue a bounded job using an authenticated control-plane API, but cannot write completion receipts, forge environment readiness, or inherit Chibi grants. Verify the actual Dot-to-plugin binding before claiming integration.
- **OpenAI Agents SDK:** may be used inside an individual pet model adapter for tracing, structured tools and evaluation. Do not create a second independent handoff scheduler: LangGraph coordinates cross-pet workflow and Chibi authorizes every tool call. SDK trace IDs may be attached to host receipts; avoid sending sensitive traces to external destinations without consent.
- **MCP / WebMCP / A2A:** expose versioned capabilities at an explicit gateway boundary, not direct credential sharing between pets. A2A is an optional later interop adapter; first-party inter-pet calls use the v1 typed contract.
- **Aiven:** PostgreSQL/checkpoint and optional observability are preferred sponsor-facing pilots where an existing authorized project is available. The demo must continue in synthetic/offline mode without Aiven credentials, labelled accurately.

**Sizing derivation:** the 5 core workers write disjoint trees; 34 pets are shallow uniform items but each needs its own gated environment, and **0 are ready**. So: core W1–W8 first (≤8), then 2 pet lanes (6 workers), widening only as environments become verified and capacity allows (concurrency depends on verified executor capacity and exclusive-write leases; start with the smallest wave that yields evidence).

## 3. Core workers W1–W8

Workers never commit to shared branches or merge; they write only owned paths and return the handoff record from `ops/AGENTS.md`. The integrator pushes the one task branch per stack layer.

| ID / Work ID | Owns (disjoint) | Delivers | Depends on |
| --- | --- | --- | --- |
| **W3** `JUNCTION-SWARM-W2-CONTRACTS` | `contracts/pet-collaboration/v1/**` | v1 additions: `revocation`, `checkpoint`, `tool-receipt` schemas; fixtures valid/invalid; version bump rules | – (first) |
| **W4** `JUNCTION-SWARM-W2-LEDGER` | `services/dispatch-ledger/**` | PostgreSQL migrations (leases, fencing token, checkpoints, receipts, idempotency keys), client library, expected-HEAD check helper | W3 |
| **W1** `JUNCTION-SWARM-W2-COUNCIL` | `services/council/**` only; W8 owns notices/exports | LangGraph Council, host IPC client interface, delegation policy (depth, fan-out, cycle, budget), resume-from-checkpoint | W3, W4 |
| **W2** `JUNCTION-SWARM-W2-FLEET` | `services/fleet-control/**` | Current slice: fail-closed read-only provider/CI/eval/grant status projection. TARGET later: capacity-bounded scheduler, per-pet lease, retries and env readiness gate. | W4 |
| **W5** `JUNCTION-SWARM-W2-EVAL` | `services/eval-runner/**` | Runner that calls the host/model adapter and emits `behavior-eval` submissions; follows `docs/BEHAVIOR_EVALS.md`; separate adjudication step | W3 |
| **W6** `JUNCTION-SWARM-W2-HOST` | **Private `SalesSquad/chibi` repo only** (not this repo) | Rust/Cedar policies for delegation, grant issue/revoke, signed receipts, IPC server. Public side gets only an interface doc + fixtures via W3 | W3 |
| **W7** `JUNCTION-SWARM-W2-MC` | `apps/mission-control/**` (existing UX owner path) | Owner-only live view over ledger/receipts: lease owner, fencing token, last checkpoint, per-pet tier, stale/blocked. Not hosted publicly | W4 |
| **W8** `JUNCTION-SWARM-W2-INTEGRATOR` | `docs/**` (except this plan's author lane), `scripts/**`, `lib/**`, `schemas/`, `package*.json`, `ops/**`, generated exports | Merge order, lockfile, `npm test` glob (see 5), public-export allowlist + leak check, notices, receipts, PRs | all |

Shared files (`package.json`, lockfile, `ops/registry.mjs`, exporter) have **one** owner: W8. Workers request changes in their handoff.

## 4. Pet swimlanes (34), grouped by specialization

The grouping is a TARGET planning choice made from each pet's tagline; the roster role (challenge/technology/…) is a FACT from `evidence/company-roster.json` and is shown as C / T / M / X (collaborator). Roles are archived observations; only Arduino, Verda and Google DeepMind are verified.

| Lane group | Pets (role) | Why grouped |
| --- | --- | --- |
| **G1 Coding, evaluation, supply chain** | openai-codex (T), afterquery (C), craci (T), featherless (T) | Coordinator/reviewer pets; first delegation sources |
| **G2 Data and storage** | mariadb (C), aiven (T), cala (C), ironshard (T) | Read-only data analysis; first delegation target is MariaDB |
| **G3 Web, research, knowledge** | exa (C), context-dev (C), oxylabs (T), aalto-university (C), astrazeneca (C) | Source-backed retrieval, public data |
| **G4 Compute and infrastructure** | nvidia (T), modal (T), verda (M), intel (C), hostinger (C) | Compute/benchmark planning |
| **G5 Physical, 3D, robotics, hardware** | arduino (M), atech-dev (T), wendy (T), qualia (T), rokoko (C), scailab (T) | Hardware, mocap, perception data |
| **G6 Multimodal, wearable, voice, media** | meta (C), google-deepmind (X), cloudinary (T) | Voice/wearable/media paths |
| **G7 Civic, finance, logistics, enterprise** | city-of-espoo (C), s-pankki (C), valio-aimo (C), bahn-express (C), stoa (C), tieto (C), ignite-next (C) | Domain workflows; lowest delegation priority |

Count check: 4+4+5+5+6+3+7 = 34.

### Per-pet workers: 34 × 3 = 102 (TARGET)

Each pet `<slug>` gets three worker roles with disjoint paths and the work IDs `junction.<slug>.code|test|review`:

| Role | Owns | Does | Model |
| --- | --- | --- | --- |
| `code` | `pets/<slug>/` (only if assigned) and `services/pet-adapters/<slug>/` | Adapter exposing the pet's declared, non-connection capabilities to the Council; capability metadata stays in `pet.json` | Codex Cloud; Sonnet for authz-adjacent pets |
| `test` | `tests/pet-<slug>.test.mjs` (per-pet test ownership, discovered by `node --test`) | Contract fixtures, capability/deny cases, no network | Codex Cloud; Haiku for fixed regression reruns |
| `review` | none (read-only) | Independent diff review, returns findings; integrator persists the receipt | Sonnet medium |

A pet lane is **admitted** only when: its env manifest is `ready` with a real ID (else it runs in a stated local worktree and its receipts cannot count as "cloud"), its prior lane is merged or recorded-blocked, and no other writer holds its lease. 102 workers never run at once; the Fleet scheduler admits by capacity.

## 5. Work order, dependencies, handoffs

| Wave | Content | Gate (acceptance test) |
| --- | --- | --- |
| **W0 Freeze** | Record baseline `4099d93`, run `npm ci --ignore-scripts`, `npm run validate`, `npm test`, `npm run build`, `npm run plugins:check`, `npm run eval:prepare` once; save receipts | Receipts exist bound to the SHA; Fact table in section 0 still true |
| **Wave 1 Contracts + ledger** | W3 → W4 (parallel start after W3 schemas freeze), W6 starts host policies | Schema fixtures validate with Ajv; ledger migration applies to an ephemeral PostgreSQL; stale fencing token write is rejected (test) |
| **Wave 2 First real delegation** | W1 Council + W6 host, pets: `openai-codex` → `mariadb` read-only | See 6.1–6.3 |
| **Wave 3 Fleet + evals** | W2, W5, W7; human provisions Codex Cloud envs (UI action, section 8) | Fleet refuses `environmentId:null`; eval-runner produces ≥1 provider-attested run for the 2 pets; MC shows tier correctly |
| **Wave 4 Pet breadth** | G1–G3 pets by tier (section 10), then G4–G7 | Per pet: validate+tests+build green on its head; its 6 evals executed and adjudicated, or labelled not run |
| **Wave 5 Rich connectors** | NVIDIA 3D, Meta voice | Start only after each connector is verified (6.4) |
| **Wave 6 Submission** | W8 public export allowlist, leak scan, notices, dry run | Section 11 |

**Handoff schema/IPC rule:** workers hand off through schema'd artifacts only. Council ↔ host is one local IPC/HTTP boundary carrying `request.schema.json` in and `receipt.schema.json` out, plus W3's new revocation and tool-receipt schemas. Changing a v1 schema after Wave 1 freeze is a W3+W8 decision and bumps the schema version; consumers pin `pet-collaboration.v1`.

**Test discovery updated in Wave 2:** W8 changed `npm test` to `node --test`, which discovers nested service and contract `.test.mjs` files; `npm run test:wave2` targets the new Node suites explicitly. The Python LangGraph Council suite is separate: `PYTHONPATH=services/council python -m pytest -q services/council/tests`. Neither local test suite is hosted Cloud CI or signed-provider evidence.

## 6. Priority scenarios (acceptance tests)

Each needs a real authenticated Chibi user/tenant, the real host, and receipts. A synthetic run proves nothing here and must be labelled `mode: synthetic`.

### 6.1 OpenAI Codex → MariaDB read-only delegation (first live milestone)

1. User asks the `openai-codex` pet a database question; its plan delegates `query-review` to `mariadb` (capability exists in `pets/mariadb/pet.json` with `requiresConnection:false`) with `requestedEffect: "read"` and redacted/fixture context only.
2. Host issues a decision and a read-only grant; Council dispatches; MariaDB pet runs through a real model call.
3. Pass criteria: host-signed receipt with provider request ID and model ID; response matches the schema; `externalEffects:false`; no SQL executed against a live DB (a real MariaDB connection is a **separate, later** connector gate; "read-only" here means read-effect delegation).
4. A write-effect request to MariaDB is denied by the host and the deny is receipted.

### 6.2 Revoke-grant test

Same flow; the owner revokes the grant (a) before dispatch → request denied, no model call, receipt `denied`; (b) mid-run → next tool/model step fails closed, status `failed` with revocation reason, no result merged. Replaying the old `authorityRef` after revocation is denied.

### 6.3 Crash/resume

Kill the Council process (i) after dispatch before receipt, (ii) after receipt before merge, (iii) while holding the lease. Pass: restart resumes from the last PostgreSQL checkpoint using only ledger + receipts (no chat); the idempotency key prevents a second model call; the dead worker's fencing token is rejected if it wakes; exactly one terminal receipt per request.

### 6.4 NVIDIA 3D and Meta voice (after the above)

Gated on verified connectors: NVIDIA 3D needs a verified 3D/GPU connector and a real or explicitly disclosed benchmark; Meta voice needs consent-verified transcript chunks, a `turnId`, device/speaker permission and cancellation per `docs/INTER_PET_COLLABORATION.md`. Until a connector is verified, these remain `synthetic` and the UI says so. No microphone/camera rights are granted to other pets.

## 7. Failover and issue recovery

| Failure | Detection | Recovery |
| --- | --- | --- |
| Worker crash / lost cloud task | Lease TTL expires in PostgreSQL | Scheduler checks branch, receipts and surviving work first, then reassigns with a new lease and higher fencing token; old writer is fenced out |
| Two writers on one pet | Lease conflict, or remote expected-HEAD mismatch on push | Later writer stops; records blocker; no force-push |
| Cloud env missing/unpublished | Manifest `environmentId:null` or provider readback fails | Pet marked `unprovisioned`/`blocked`; runs only in an explicitly stated local worktree; other pets continue |
| Host or provider outage | Host health check / receipt `failed` | Council returns a `failed` receipt; bounded retry with backoff and the same idempotency key; no silent substitution of provider or account |
| Authz denial | Host decision `denied` | Terminal; surfaces reason; never retried with a different authority |
| Stale evidence | Receipt SHA ≠ requested HEAD or pet digest differs | Displayed `stale`, never green |
| Lock file stuck (local dev) | `owner.json` | Use `reclaim-stale-lock` per `ops/README.md`; never steal blindly |

Every failure ends with a ledger line: work ID, source SHA, blocker, owner, next action. A blocked pet never blocks independent pets.

## 8. Cloud environments (target, verified Codex UI provisioning)

Per pet, a named Codex Cloud dev environment `junction-<slug>` is the **desired** target (already declared in `ops/environments/<slug>.json`). FACT: zero are ready. Verified on the Mini: Codex CLI `0.166.0` supports Cloud `exec`, `status`, `list`, `apply`, `diff`, but **no create/publish command**. OpenAI's [Cloud environments documentation](https://learn.chatgpt.com/docs/environments/cloud-environments) directs creation and publishing through **Work in → Cloud → Select environment → Create environment** or **Settings → Codex Cloud → Environments** in the signed-in web/desktop UI. An authorized owner or agent with verified UI control may operate that workflow; if the provider requires confirmation, honor it. After publishing, a PR records the real ID, UTC time, pinned source and provider evidence in the manifest (W8 owns edits); a separate Cloud task proves execution. Never invent IDs. Pilot `junction-aiven` first, then the `junction-openai-codex`/`junction-mariadb` live-demo pair. These are reusable configurations, **not permanent always-on VMs**. Mac Mini `codex-plus` can dispatch only to an already-published environment using `--env REAL_ID`, with separate Plus identity and no quota rotation.

## 9. PR stack constraints and daily evidence

**Stack:** PR3 `e102f15` → PR4 `4099d93` (this baseline) → new PRs. Rules:

- Start from the exact baseline SHA; do not rebase or squash PR3/PR4. If either changes, W8 re-verifies and rebases new layers explicitly.
- Layers (one branch + draft PR each, `codex/junction-swarm-w2-<layer>`): L1 contracts+ledger, L2 council+host-interface fixtures, L3 fleet+eval+MC, L4 per-group pet lanes, L5 connectors, L6 submission export. A layer merges only after its predecessor.
- Never push to default branch, force-push, or bypass protections. Each layer PR names its parent SHA. Workers do not push.
- The private Chibi work (W6) lands in its own repo and PR; the public stack only references it by commit SHA in receipts.

**Daily evidence (bound to source SHA):** at a fixed time each day, W8 produces `ops/receipts/daily/<YYYY-MM-DD>.json` (private, not exported) containing: stack HEAD SHA, per-layer PR head, `validate`/`test`/`build` results with where they ran, per-pet tier and lease owner, evals executed/attested/passed (not "authored"), env readiness count, open blockers. Any entry whose SHA is not the current HEAD is `stale`. No secrets or private data inside. Receipts follow the existing schema in `ops/README.md` (name = work ID + first 12 chars of head).

## 10. Partial-delivery semantics

Each pet has a tier; the platform and submission use whatever is reached, and a lower tier never blocks a higher-tier pet.

| Tier | Meaning | Required evidence |
| --- | --- | --- |
| T0 `content-ready` | Valid package (34 authored today; W0 must re-run `validate` to confirm) | Source SHA + schema pass |
| T1 `adapter-tested` | Adapter + fixture tests pass on its head | Test receipt at SHA |
| T2 `delegable` | Host-granted, real-model delegation succeeded and a denial case failed closed | Host-signed receipts |
| T3 `eval-attested` | Its 6 evals executed with provider-attested invocations and adjudication | Eval receipts |
| T4 `connector-live` | A verified real connector (e.g. MariaDB read, NVIDIA 3D, Meta voice) | Connector-specific receipt |

Submission claims count only pets at the tier actually evidenced; the Council works with any subset of available pets and must report unavailable ones, not simulate them. The minimum credible submission is the T2 pair `openai-codex`+`mariadb` with 6.1–6.3 receipts; everything else is additive.

## 11. Submission gate (Wave 6)

- Public export is an allowlist tree: `pets/`, `contracts/`, `services/` (public parts), `apps/catalog`, fixtures, tests, notices. Excluded: `ops/`, `apps/mission-control`, `dist/ops-claims`, receipts, registrations, Chibi code, secrets. W8 adds a leak-scan test that fails on any excluded path or secret pattern.
- Disclose pre-existing work (Chibi runtime, marketplace, earlier companions) per `docs/JUNCTION_SUBMISSION.md`; show the new, demonstrable work only.
- Owner decisions still required: repo visibility, license grant, challenge eligibility, submission itself. This plan authorizes none of them.

## 12. Do-not list

No fake environment IDs; no claim that registered plugins are installed; no 204-case "pass" without executed, attested runs; no use of `syntheticGrant` as authority; no copying Chibi private code, Cedar policy source or keys into this repo; no GitHub Actions workflows or paid executors by default; no inventing Junction briefs, sponsor endorsements or deadlines; no direct push to `main`.
