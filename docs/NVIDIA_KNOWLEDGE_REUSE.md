# NVIDIA knowledge reuse — verified discovery, 13 November 2026

Private developer handoff for `junction.nvidia.portfolio-reuse-20261113`.
This uses the existing knowledge owners; it is not another index, coordinator,
provider permission or a claim that the portfolio is fully operational.
The dated machine-readable observations are in
[`ops/nvidia-knowledge-reuse-20261113.json`](../ops/nvidia-knowledge-reuse-20261113.json).

## What was actually checked

Both online Macs were inspected through their existing authorized RDC connections.
The bounded scan found **408 Git worktrees on the MacBook Pro and 422 on the Mini**:
830 total, representing 63 case-normalized GitHub repository identities
(52 owner repositories and 11 external repositories). A fresh authenticated
GitHub repository search returned 104 owner repository metadata rows across two
pages; all 52 locally observed owner identities matched that result.

These are metadata inventories, not 830 code reviews. Known development/project/
operations roots were scanned to depth six; caches, weights, datasets and private
credential/browser stores were excluded. The third RDC device was offline.
Ninety-six worktrees did not expose a direct GitHub origin in this scan; local
and proxy origins are included, so this is not evidence of lost or unpushed work.
No source was reset, moved, deleted, merged, or copied into a model request.

## Existing knowledge that works

| Existing owner | Observed useful route | Verification and limit |
| --- | --- | --- |
| DSH / MikaelSystem corpus | `tools/corpus-query.py` and `tools/corpus-query-mcp.py` | Actual local stats, search and feature-row queries succeeded. V3 manifest matches: 1,648 features, 302 atoms, 44 comparison slices, 25 app rows, 175 evidence rows and nine pins. Dataset source `021c40a1ad3082e2794d8b618a705f367cda1ad8`; ten tables / 2,576 total rows. |
| Knowledge OS | Fourteen read-only tools in `scripts/knowledge-mcp.py` | Actual `portfolio_projects` and Factory `project_context` succeeded. Factory `project_source_search` returned unavailable roots. Registry remains dated 31 October: 33 project IDs / 71 GitHub entries. |
| Factory | `knowledge/capsules/catalog.json` and existing capability router | Reuse agent-platform, mcp-runtime, durable-actions, scoped-read-cache, resilient-read and scoped-connector-runtime routes. Candidate definitions still require their own execution gates. |
| Portfolio Mesh | `portfolio-mesh/mesh.py` and `AGENT_CONTEXT.md` | Existing bounded source/freshness/dependency navigation. Its company-knowledge MCP contract is not proof of a deployed endpoint. |
| Mini Graphify | Existing loopback MCP and source-pinned context interface | Actual initialize/tools-list succeeded: Graphify 0.9.95 / 14 tools. A Factory capsule requested at the fresh Factory SHA was rejected as invalid/stale/unverified. No fresh Factory graph context is claimed. |
| DSH harness and bundles | Clean tracked harness checkout, corpus dependency, session tools and GitHub bridge declarations | Existing `session_list`, `session_send`, `session_fork` and related bundles are documented. Profile dependencies are present; current session execution/provider connectivity was not qualified. |

Corpus search permits partial term matches. The broad “vision gpu benchmark”
query returned unrelated revision/version rows; those are **not NVIDIA evidence**.
The useful corpus findings were the source-located agent-tool/provenance pattern,
typed MCP bridge/session separation, and deterministic tool-status vocabulary.
The original rows and their `copy/adapt` labels are advisory: inspect source,
licence and actual applicability before reusing an implementation.

The installed knowledge gateway did not advertise `unified_agent_context`.
Its separate source module exists, but a source file or old instruction does not
establish a callable live tool. Likewise, the Mini's historical status command,
the active R10 pointer and a fresh MCP response have separate provenance.
The pointer is dated 24 October and describes a partial catalog; its historical
“current” labels must not override today's exact-HEAD query refusal.

## Concrete reuse map

All candidate source revisions are recorded in the JSON receipt. The audit read
their entry points; it did not rerun their historic test counts.

| Existing project | Reuse in NVIDIA/Junction | Boundary |
| --- | --- | --- |
| Savi | Typed character/spec proposals; deterministic validation; image/depth/geometry feedback; canonical bytes and SHA identity. | Use the actual default branch `baseline/round2`, not an assumed main. Keep its private engine owner-side. |
| Valmet | Bind a visual claim to exact scene revision, object ID, point membership and catalog evidence. | Same checksum across search/resolve/evidence. No claim that the current NVIDIA demo already invokes Valmet. |
| BIM Register | Typed parameters, units/ranges, instantiate hash, geometry fitting and explicit scale/gauge limits. | Synthetic fixture tools first; no fabricated metric scale from a photo. |
| Reality Twin | SI units, uncertainty, calibration and measured-versus-synthetic provenance. | Keep physical claims separate from model interpretation. |
| JUURI | Schema-generated Rust/TS, SQLite WAL row journal, `juuri-sync::replica_snapshot` and `observe_trusted` scope/epoch/digest checks. | Pre-alpha source, not an authenticated MCP/sync service. |
| LOOM | OPFS Worker two-slot persistence, Web Locks, stale-tab CAS and canonical JSON backup/import. | Future evidence-workspace pattern; not already encrypted multiplayer or Rust/WASM. |
| BankMatch | Separate read/propose/approve/execute; bounded replay-safe dispatch; MCP Apps UI/text fallback. | Reuse the mechanism, never financial data or bank/payment authority. |
| Chibi | Existing typed gateway admission, consent and host execution ownership. | `/v1/gateway/admit` source returns `executed:false`; admission is not inference. |
| SAMPO | Project-memory/recovery/retrieval drafts are candidates for later source review. | Main currently contains only its short README. PR #21 is an unmerged draft candidate; do not claim implemented main code. |

## Apply the knowledge without mixing trust boundaries

1. Identify the work/repository/current SHA through Repo Control and GitHub.
   Consult Knowledge OS / Portfolio Mesh for navigation, not permission.
2. Ask the existing local DSH corpus for a narrow mechanism, then inspect the
   decisive row and source locator. Avoid ingesting whole reports and partial
   keyword matches.
3. Resolve an existing typed tool/engine before inventing a new one. The most
   relevant next NVIDIA slice is **visual observation → typed scene/spec proposal
   → deterministic object/parameter validation → rendered evidence → Nemotron
   verification** using reviewed public/synthetic inputs.
4. Keep raw private source, corpus records, sessions, customer/family data and
   credentials in their owning systems. Only deliberately reviewed public or
   synthetic excerpts may enter the current NVIDIA developer harness.
5. Retain exact input/source/result digests and real tool results. Replays,
   ambiguous provider outcomes and permission/effect boundaries remain host-owned.
   Neither the model nor a retrieved document can manufacture authority.
6. Refresh missing project/source bindings through their existing Knowledge OS/
   Graphify owners. Exact registry IDs `sampo`, `loom`, `reality-twin`,
   `bankmatch`, `juuri`, and `junction-pets` were absent at this observation.
   This does not mean no related notes exist elsewhere.

This audit adds no provider, private-data retrieval tool, daemon or automatic
cross-project prompt injection. The existing Nemotron runtime and generated
companion artifacts remain unchanged. The next multi-project workflow above is
a grounded implementation target, not a completed integration. Actual Nemotron
inference still requires an approved host-side NVIDIA key and a real live test.
