# Next capabilities, ranked by user value

Delivered in the review workspace: method-based evidence levels, canonical evidence export and
verification, same-source/same-engine review recovery, revision comparisons, reversible human
corrections and membership-based instance metrics. See [WORKSPACE.md](WORKSPACE.md). These tools
are not measured sponsor accuracy, physical recognition or verified registration.

This revision makes source evidence stricter and brings IFC into the local app. The next step
should improve verifiable coverage, not silently loosen acceptance to regain a headline score.

| Priority | Work | Acceptance evidence |
| --- | --- | --- |
| 1 | Requalify strict V2 on an authorized local copy of the licensed dataset | Frozen drawing split; per-question answers, abstentions/reasons, engine/file hashes, accuracy and coverage by format/class. Compare the prior engine on identical questions. |
| 2 | Independently label citation regions | Human-reviewed source/page boxes, answer truth and negatives; run `benchmark/regions.mjs`; report precision/recall alongside answer accuracy. Never create ground truth from engine output. |
| 3 | Room-scoped instance counts | Spatially group and validate windows/doors, then assign instances to room polygons. Shared-boundary openings must return ambiguity rather than arbitrary ownership. Test multilingual scope and multi-class requests. |
| 4 | IFC floor-plan projection | Use a vetted geometry kernel with retained original IFC GUID/entity mapping and transforms. Compare areas and projections with independent viewer renders. Current STEP record inspection is not this feature. |
| 5 | General IFC text/property questions | Exact scalar property lookup is implemented. Next add property-set-qualified selection and an explicit typed query plan. Validate against independently labelled `ifc_bench` questions; never present the current narrow lookup as a solved 249-question suite. |
| 6 | DWG and complex HATCH | Select a licensed, maintained local decoder and verify its licensing, units, blocks/transforms, arcs and holes. Use a bounded subprocess with no network and a synthetic adversarial corpus. No decoder is bundled or automatically downloaded. |
| 7 | Better raster and PDF coverage | Retrieve text/regions first, make sparse bounded vision calls only for unresolved evidence, and measure an unchanged held-out set against baseline. Detector training needs a licensed disjoint corpus; no claim of an accuracy improvement until measured. |
| 8 | Production service | Per-user isolation, authenticated source ownership, persistent deletion/expiry policy, worker isolation and resource budgets. Current localhost app is not a multi-user hosted service. |

Keep direct source quantities and geometry as the primary method. Where geometry lacks an area
annotation, a future **explicit measured-only mode** could expose the computed polygon area with
a different evidence level; do not silently equate it with a cross-checked answer. A useful next
UI addition is an explanation of the exact missing evidence and an actionable request for a
better export, room identifier or scale instead of a generic refusal.

DWG conversion, complex HATCH, full IFC projection and raster-model improvements remain real
engineering work. They cannot be qualified by synthetic tests or by relabelling old benchmark
results. Sponsor files must stay on an authorized local host under their source licences; the
repository prohibits caching them in this cloud workspace.
