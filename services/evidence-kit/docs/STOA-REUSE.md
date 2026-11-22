# Reusing Stoa capabilities

Evidence Kit 0.2 is the portable entry point for source references, bounded DXF room areas,
CSV totals, review and replay. The Stoa application is a reference implementation. Use this
map when evaluating any additional extraction from it.

| Capability | Source in Stoa | Reuse decision and proof needed |
| --- | --- | --- |
| IFC quantities, counts and properties | [IFC STEP parser](../../../solutions/stoa-blueprint-studio/src/ifc.mjs), [queries](../../../solutions/stoa-blueprint-studio/src/ifc-qa.mjs) | First candidate when a BIM consumer needs stored values. Carry native STEP IDs and unit records. Qualify against known IFC exports with missing quantities, duplicate names and mixed units. Stored values do not establish geometry. |
| Spatial revision correspondence | [Revision matcher](../../../solutions/stoa-blueprint-studio/src/revisions.mjs) | Keep as a reference for pairing geometry under declared alignment. Evidence Kit exposes generic assignment and comparison. Before promoting the Stoa workflow, test ambiguous pairs, split/merge, changed coordinate frames and unmatched objects. |
| Symbol grouping and counts | [Quantities](../../../solutions/stoa-blueprint-studio/src/quantities.mjs), [instance scoring](../../../solutions/stoa-blueprint-studio/benchmark/instances.mjs) | Reuse the instance evaluation design. Supply per-object annotations and report split/merge and exact-count metrics separately. Drawing-specific symbol rules need fresh qualification. |
| Source inspection and correction interaction | [Review workspace](../../../solutions/stoa-blueprint-studio/WORKSPACE.md) | Reuse the workflow of selecting a result and opening cited records in context. The portable component handles review. A CAD viewer integration must verify zoom/highlighting on the cited geometry and source version. |
| Citation localization | [Region benchmark](../../../solutions/stoa-blueprint-studio/benchmark/REGIONS.md) | Use as an evaluation reference. Define coordinate transforms and score citation regions against labelled regions independently of answer accuracy. |
| Raster OCR, PDF QA and model cascades | [Raster experiments](../../../solutions/stoa-blueprint-studio/raster/README.md), [PDF QA](../../../solutions/stoa-blueprint-studio/sheet/sheet-qa.mjs) | Research reference. Require a held-out corpus, platform and provider checks, and measured accuracy, coverage and cost before recommending these paths to agents. Historical Stoa scores apply to the engine evaluated at the time. |

For a downstream adoption, record the package commit, source format and rights, supported query,
validation corpus and failure behavior. Include a negative case where the agent must abstain.
If the adapter rejects the input or the method abstains, report the reason and the evidence
needed to continue. Do not substitute a guessed calculation or promote a historical approval.

DXF adapter and room-area method 1.1 tighten evidence interpretation. Opening a 0.1 packet
preserves its history. Replay with the current adapter generates new DXF evidence and requires
fresh review. A source rejected by the current adapter remains available as a historical packet
through the integrity-only open operation.
