# Stoa Atlas — Source-bound Architecture

## Execution graph

1. User opens **localhost-only** Node HTTP server (`src/server.mjs`); browser loads `public/index.html`, no SaaS dependencies.
2. Browser imports an ASCII DXF up to 6 MiB or IFC STEP up to 16 MiB. Server `src/dxf.mjs` checks file format, group and entity limits, extracts source layers/coordinates and computes SHA-256. Raw uploaded bytes are never persisted to disk.
3. Server keeps up to three parsed imports in bounded in-process memory with 30-minute expiry. Browser receives source geometry for interactive SVG visualization (`public/app.js`).
4. A question POST references server-side drawing ID. Active resolver `src/quantities.mjs` delegates room areas to `src/grounding.mjs`, which checks supported semantic patterns, source geometry, units, deterministic arithmetic and exact source evidence.
5. If supported, result contains the answer, measured metric, original `entityId`s and explanations. For DXF, the browser highlights original polylines/HATCH boundaries and text insertion coordinates. For IFC, `src/ifc-qa.mjs` returns entity IDs and the browser displays their original STEP records, stored quantities/properties and unit definitions; no floor-plan projection is claimed.
6. If missing/ambiguous, source units unsupported, 2%-inconsistent area, unknown object class or adversarial instruction, engine returns `{status:'abstained',evidence:[]}`. No fabricated bbox or invisible fallback LLM.

## Trust and information boundaries

- Private server defaults to `127.0.0.1:4315`; cross-origin access from non-loopback web pages is rejected and no CORS is granted.
- No external inference, telemetry, data egress, credential requirement or sponsor ZIP auto-download on normal startup.
- Interactive formats: ASCII DXF entities (including single straight HATCH loops) and bounded IFC STEP records. PDF/raster evaluation remains separate; DWG is unsupported.
- Source asset licensing is separate from project code. Real sponsor sample is used only through local temporary fetch; source asset must not be committed/published. The synthetic demo fixture is handcrafted, independently invented and labeled.
- `sha256` of uploaded bytes is captured. This proves the origin of an imported byte sequence if independently compared to the sponsor archive hash, **not** that every parsed region is semantically correct.
- `answerDrawing` has no arbitrary code evaluation, remote tools, or prompt execution path. Question length capped at 400 chars.

## Extension architecture (not shipped)

- Source connectors: PDF text coordinate extraction, raster OCR with affine mapping, DWG decoder and IFC geometry projection; each must attach native file/page/layer/element IDs, never merely a whole-sheet source hash.
- Query planner: exact symbolic queries first, candidate retrieval per region second, optional vision model only for unresolved visual semantics. Every candidate checked against concrete geometry/evidence.
- Scoring/evaluation: sponsor Q&A type exactness and areas within 2%; `benchmark/regions.mjs` scores source/page-bound boxes against independently supplied ground truth. Real citation IoU, end-to-end latency and inference cost still require measured datasets. Negative examples are first-class.
- Reuse existing `pets/stoa` and merged Stoa→NVIDIA evidence composition from historical PR #66 through public, explicit contracts; this slice deliberately adds no cross-agent runtime permissions and copies no protected code.

## Source ownership

All code lives only under `solutions/stoa-blueprint-studio/`. Shared root workspace files, legacy pets, services, CI and other challenge product slices are untouched. `solution.json` is compatible with the staged product workspace contract of integration PR #82, but no integration/merge is claimed.

## Source-bound review workspace

Each server instance owns its import/answer/review cache. Imports expire by timer; the server
resolves citation IDs canonically and hashes the actual engine module bytes. `evidence.mjs`
builds unsigned packets; `review.mjs` applies source-bound, revision-checked commands without
mutating engine answers. Restore recomputes an answer and validates/replays the history before
retaining it. `revisions.mjs` compares unique room IDs or IFC GUID records and uses
`assignment.mjs` for bounded minimum-cost primitive correspondence. Declared alignment and
physical identities remain unverified. `public/workspace.js` owns the review/compare UI through
the same localhost API. `benchmark/instances.mjs` independently scores source memberships.
See `WORKSPACE.md` for commands, formats, limits and design-source pins.
