# Stoa Atlas — Source-bound Architecture

## Execution graph

1. User opens **localhost-only** Node HTTP server (`src/server.mjs`); browser loads `public/index.html`, no SaaS dependencies.
2. Browser imports an ASCII DXF up to 6 MiB. Server `src/dxf.mjs` checks file format, group and entity limits, extracts source layers/coordinates and computes SHA-256. Raw uploaded bytes are never persisted to disk.
3. Server keeps up to three parsed imports in bounded in-process memory with 30-minute expiry. Browser receives source geometry for interactive SVG visualization (`public/app.js`).
4. A question POST references server-side drawing ID. Pure resolver `src/grounding.mjs` checks supported semantic patterns, source geometry, units, deterministic arithmetic and exact source evidence.
5. If supported, result contains the answer, measured metric, original `entityId`s and explanations. Browser highlights exact original polylines and text insertion coordinates; evidence list selection is linked to SVG.
6. If missing/ambiguous, source units unsupported, 2%-inconsistent area, unknown object class or adversarial instruction, engine returns `{status:'abstained',evidence:[]}`. No fabricated bbox or invisible fallback LLM.

## Trust and information boundaries

- Private server defaults to `127.0.0.1:4315`; cross-origin access from non-loopback web pages is rejected and no CORS is granted.
- No external inference, telemetry, data egress, credential requirement or sponsor ZIP auto-download on normal startup.
- Source format support is intentionally explicit: DXF entities and per-layer semantics, not PDF/DWG/IFC.
- Source asset licensing is separate from project code. Real sponsor sample is used only through local temporary fetch; source asset must not be committed/published. The synthetic demo fixture is handcrafted, independently invented and labeled.
- `sha256` of uploaded bytes is captured. This proves the origin of an imported byte sequence if independently compared to the sponsor archive hash, **not** that every parsed region is semantically correct.
- `answerDrawing` has no arbitrary code evaluation, remote tools, or prompt execution path. Question length capped at 400 chars.

## Extension architecture (not shipped)

- Source connectors: PDF text coordinate extraction, raster OCR with affine mapping, DWG decoder, IFC element index and geometry projection; each must attach native file/page/layer/element IDs, never merely a whole-sheet source hash.
- Query planner: exact symbolic queries first, candidate retrieval per region second, optional vision model only for unresolved visual semantics. Every candidate checked against concrete geometry/evidence.
- Scoring/evaluation: sponsor Q&A type exactness, areas within 2%, region identity IoU, per-answer wall-clock and inference cost. Negative examples are first-class.
- Reuse existing `pets/stoa` and merged Stoa→NVIDIA evidence composition from historical PR #66 through public, explicit contracts; this slice deliberately adds no cross-agent runtime permissions and copies no protected code.

## Source ownership

All code lives only under `solutions/stoa-blueprint-studio/`. Shared root workspace files, legacy pets, services, CI and other challenge product slices are untouched. `solution.json` is compatible with the staged product workspace contract of integration PR #82, but no integration/merge is claimed.
