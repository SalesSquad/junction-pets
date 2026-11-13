# Junction Pets — development operating system

**Work ID:** `JUNCTION-ORCHESTRATION-20261112`
**Canonical source:** `SalesSquad/junction-pets`
**Host boundary:** `SalesSquad/chibi` is a separate, private runtime and marketplace.

This repository is the source of **34 independent company-specific agent packages** and their development evidence. It is not a copy of Chibi.pet. The same codebase can be built and tested in an isolated cloud task without access to the owner's Macs.

**Current work register (13 November):** [`DEVELOPMENT_QUEUE.md`](DEVELOPMENT_QUEUE.md) and [`ops/development-queue-20261113.json`](../ops/development-queue-20261113.json) preserve the 34-company next-task queue with one reviewed/merged Aiven source slice, two observed Cloud tasks (MariaDB and AfterQuery) and 31 unstarted proposals. These records are planning and handoff inputs, not an autonomous dispatcher, an always-running fleet or a new paid executor.

## One pet, one development owner, one desired cloud environment

Each `pets/<company>/` has a runtime-facing `AGENTS.md`, `pet.json`, `STORY.md`, and `evals.json`. These describe a companion for a user, *not* instructions for an autonomous developer. `ops/AGENTS.md` and `ops/environments/<company>.json` describe a separate developer agent and its desired **Codex Cloud** environment. A manifest is a request for an environment, **not proof that one has been created**. Never invent environment IDs or reuse a disconnected session as current proof.

The authoritative records are, in order:

1. GitHub branch and exact commit SHA for the contents of a pet.
2. An authenticated Codex Cloud environment identifier and observed setup state, if one exists.
3. Receipt for a test, model evaluation, PR, deployment, or Chibi integration **bound to that exact source SHA**.
4. Generated Mission Control status, a **snapshot** derived from the records above. Chat summaries and old pages are handoffs, not evidence.

The controller may handle many pets, but it must limit concurrent jobs to available execution capacity. Every agent owns only one active write lease for a pet at a time; a pet's runtime data and privileges are never shared by virtue of a common monorepo.

## Workspace and ownership

| Path | Owner | Contents |
| --- | --- | --- |
| `pets/<company>/` | One company-content writer | Versioned agent behavior, source evidence, example tasks and eval definitions |
| `ops/environments/` | Orchestration integrator | One desired cloud environment and developer agent identity per pet |
| `ops/receipts/` | Evidence integrator | Only authenticated, source-bound execution receipts; no unverified green status |
| `ops/work/` | Work coordinator | Work requests, claim/lease/retry state; no credentials or user data |
| `scripts/ops-*.mjs`, `tests/ops-*.test.mjs` | Orchestration integrator | Portable control-plane generation, validation and safety tests |
| `apps/mission-control/` | UX owner | Internal status viewer, independent of public catalog |
| `apps/catalog/` | Catalog UX owner | Public-facing discovery and preview; never internal work or secrets |
| `schemas/`, package/lock files, `lib/` and generated exports | Root integrator | Cross-pet contracts, release and integration outputs |

The already existing [package contract](../catalog-contract.md), [Chibi adapter](CHIBI_INTEGRATION.md), and [host readiness guide](EVENT_GUIDE.md) remain authoritative. Workers must not modify them implicitly.

## Daily agent loop

1. **Discover.** Read repository `AGENTS.md`, this file, `catalog-contract.md`, and the assigned pet's four files. Record the exact upstream commit and check the current PRs.
2. **Claim.** Use the work registry's atomic claim/lease rules. Stop if another active writer owns the same pet or exact files. Expired lease is eligible for reassignment only after checking surviving work, branches and receipts.
3. **Develop.** Use an isolated cloud workspace based on a published, authorized environment. Limit changes to the assigned pet or an explicitly disjoint shared module. Do not move private Chibi code into this repository or between cloud providers.
4. **Verify.** Run repository validation, Node tests and catalog build. Where a model is actually invoked, run the pet's behavioral evals and record the model/version, exact input, evaluator method and outcomes. Merely **defining** six cases per pet is not an executed model evaluation.
5. **Publish evidence, not claims.** Commit to a task-owned branch, open/update a draft PR, capture its current HEAD and matching CI proof. Receipts for older commits must show stale, not green.
6. **Handoff.** Report work ID, paths, source SHA, branch/PR, checks with links/log IDs, exact blocker and one actionable next step. Release the lease. Do not push direct to main or merge/deploy without authorization.

## Cloud environment provisioning

Codex Cloud reuses **published** environments. A new task starts in its own workspace; multiple tasks can use the same published configuration, but the requested per-pet setup is represented by a distinct environment manifest and should receive a **distinct published environment ID** when created and verified. Configure it with the repository and pet-specific start instructions. Prefer portable Node/Rust checks and synthetic fixtures. Keep Apple build/signing on an authorized Apple executor, without blocking this codebase on a Mac.

Creation and publication are available in Codex Cloud's web/desktop environment management. The source-only command-line planner has **no authenticated create/list/publish or execution authority**, and its manifest is not a live provider readback. Never infer `ready` from a desired name or old receipt; independently recheck the provider/account, selected repo and task admission. Do not substitute unrelated pay-per-use Agents API sandboxes, rotate ChatGPT accounts, or silently copy private code to another provider.

**W8 provisioning update, 13 November 2026:** all 34 Pro/Legacy environments now have actual provider IDs, individual settings readbacks and prior source-bound Cloud task evidence in [the private provisioning record](../ops/cloud-provisioning-20261113.json). The manifests permit dry-run planning; a fresh account/provider/source check and bounded work ownership remain required for each task. This does not qualify Chibi runtime, model evaluations or an autonomous Fleet adapter.

**Next Cloud UI observation, 13 November:** the owner's existing authenticated Pro interface actually launched the [Aiven source developer task](https://chatgpt.com/local/6af6b453-cd8c-8191-92f7-a8559f0350d3) using `chibi-marketplace-cloud`, which contained the private Junction repo. The 34 historical **Legacy** environment IDs were not selectable in that new-Cloud picker and are not substituted for the selected executor. The subsequent [Aiven PR #11](https://github.com/SalesSquad/junction-pets/pull/11) passed 252/252 full Node checks and 23/23 focused checks on author HEAD `48db6f84` and was reviewed/merged at `f1bbd3b7`; this does not execute model evaluations or activate Chibi. New owner-observed [MariaDB](https://chatgpt.com/local/6af6b88c-3af4-8191-a1f3-84bb3805b0e3) and [AfterQuery](https://chatgpt.com/local/6af6b96a-4ed0-8191-9f36-61dcf4ac70cf) Cloud developer tasks are running in separate workspaces; MariaDB's source was verified, AfterQuery's was still in preflight at the observation. The other **31** proposals have no task URLs. The existing Junction Mission Control hourly automation has a source-completion check, **not** a 34-job dispatcher; a separate new recurring task was blocked by the scheduler's 20-active-task cap.

**Historical 12 November provider observation:** the signed-in Pro environment settings showed 43 environment entries, 15 explicitly `Unpublished`. At **that** checkpoint, `chibi-marketplace-cloud` exposed `Continue setup` and no ready Junction execution was proven; the Pro Work composer displayed exhausted Codex/Work usage. This older observation is **superseded for the Aiven task by the actual 13 November execution above**, not generalized to 34 live company jobs.

An explicitly selected, separately authenticated Mac Mini `codex-plus` CLI v0.166.0 also supports `codex-plus cloud exec --env <verified ID> --branch <task branch> <prompt>`. It does **not** expose a create-environment subcommand. `scripts/ops-cloud-dispatch.mjs` only creates an inspectable **dry-run plan** after a source SHA, profile and authenticated environment receipt have been supplied. It never starts a task, swaps accounts or extracts credentials. The Mac is optional, not an execution prerequisite for this portable monorepo.

## Honest status language

| Status | Meaning | Evidence required |
| --- | --- | --- |
| `content-ready` | An authored, valid company package | Exact source commit + schema checks |
| `unprovisioned` | Desired cloud manifest exists but no environment ID | Manifest only; **not** an execution result |
| `ready` | Cloud environment available to start tasks | Authenticated provider environment ID and time |
| `running` | Current task is executing | Task/job ID, live state and unexpired lease |
| `blocked` | A named gate prevents a next step | Explicit blocker, owner and recovery action |
| `stale` | Last evidence is older than requested HEAD/time | Previous SHA/time retained, no green display |
| `verified` | An exact commit and gate passed | Test scope, immutable receipt, matching SHA |
| `published` | Release is actually available to an external user | Chibi release and recipient-journey proof |

Internal Mission Control reads the generated `status.json` as a timestamped snapshot. It must display unknowns and missing data explicitly. Its HTML is intentionally separate from `dist/site` and any Chibi Maker export, so private development state never becomes a public pet artifact.

There is already a [Junction Mission Control Site](https://junction-mission-control-mikael.ervamaamikael.chatgpt.site) (observed active v4, 12 November). Its MCP tools currently provide event/status guidance, **not** a writer or feed for the 34-pet source registry. Site access includes an external visitor, so do not publish this private per-pet operations ledger there. The new `apps/mission-control` source is a private management module; any later Site integration must use a separately reviewed, sanitized read-only projection and an authorized deployment. The private [Chibi Place Space](https://chatgpt.com/space/page_6ae648a257c48191820a7a96264e9b75) is the human-readable source map until that feed is verified.

## Cross-product reuse without code leakage

- The Junction repository owns only the original pet knowledge packs, conversation contracts, evaluations, user-safe prompts, adapter interfaces and the demo wrapper.
- Chibi owns account identity, ownership, invitations, paid/trial entitlements, authentication, Cedar authorization, provider/model routing, private memory and real voice/chat execution.
- Valmet/Reality Twin/Factory skills may be **referenced by public, independently licensed interfaces** with provenance. No private app source or data is copied by default.
- Dot can provide conversational handoff and human-visible summaries when a supported connected workflow exists. It is not a substitute for source-controlled receipts or proof of an active Codex Cloud task.

## Plugin fleet and inter-agent showcase

The source for 34 **skills-only** cloud plugin candidates lives in `plugins/junction-<company>/`, with source digests and non-endorsement notices. See [plugin packaging and installation](PET_PLUGINS.md). Private Plugin Creator registration is a separate account action requiring an actual returned plugin ID and independent readback for each package. No fabricated MCP URL or per-pet Chibi credential may be inserted to make this look connected.

**12 November registration checkpoint:** all 34 company identities have provider-readback private Plugin Creator registrations, with exact IDs and release IDs in `ops/plugin-registrations/`. The status generator compares every receipt with the generated source bytes and all four underlying pet source files. `registered-source-matched-reported` is a registration observation only. Actual Chibi installation and host permissions remain unverified; Cloud has the distinct W8 historical provisioning and Aiven actual task receipts described above. Two additional unassigned private provider IDs were preserved (S-Pankki and Scailab); the canonical per-pet mapping remains one-to-one.

The owner-only [Junction Pets Agent Development Control](https://chatgpt.com/space/page_72f945dcf8a48191a72178904f8ab22d) is the separate human-facing handoff. `npm run ops:page:build` creates a single-file embedded **snapshot** from the same private dashboard model; the generated page is not a live Cloud API connection. Verify private Page sharing and refresh from a newly verified source whenever posting a new snapshot.

The [Chibi Council](INTER_PET_COLLABORATION.md) combines four existing pet manifests (OpenAI Codex, MariaDB, NVIDIA and Meta) into a reproducible synthetic delegation trace. `npm run ops:preview` builds **two separate private previews**: `dist/mission-control/` for 34-pet operations and `dist/collaboration-demo/` for the Council. This is a compelling offline rehearsal, **not** proof of real LLM/voice/MCP-to-MCP execution. A live version must use Chibi's real identity/Cedar grants, privacy controls and signed task receipts before model or tool actions can be labeled operational.

## Scale and incident recovery

Do not allocate 34 concurrent workers merely because the manifest set exists. The **authorized coordinator** admits tasks in bounded batches against actually verified provider capacity and budget, recording an exclusive company-writer assignment, a unique attempt and the expected remote HEAD; no distributed lease issuer or always-on cross-cloud dispatcher is implemented here. In a crash, reconstruct from the source branch, durable queue/PR assignment and receipt; no chat transcript is required. An environment/tool outage should block only the affected pet, not remaining independent pets. Every failure ends with owner, reason, and next retry action.

For an independent judge, keep the Junction submission source and the Chibi production/runtime code separated; see [submission boundary](JUNCTION_SUBMISSION.md).
