# Source-bound review and revision workspace

## Evidence levels and human review

Every new `/api/ask` response includes an `answerId`, `review`, and a result with a method ID,
source revision, actual engine-source SHA-256 and one of these levels:

| Level | Meaning |
| --- | --- |
| `source_observed` | Direct source labels, typed IFC elements or stored quantities/properties. |
| `derived` | A documented layer-convention heuristic or complete aggregate of quantities. |
| `geometry_measured` | Area computed from supported IFC geometry, without annotation agreement. |
| `cross_checked` | DXF polygon area agrees with a unique source annotation within 2%; aggregates validate every contributing room. |
| `unavailable` | The engine abstained. |

These levels describe a method, not confidence probabilities or physical certification. Human
review is a separate record: `confirmed` means a named local reviewer declared confirmation of
the **engine** answer; `corrected` is a separate manually authored answer with canonical source
entity IDs. Neither changes the original engine result, evidence level, metric or benchmark score.
Reviewer names are declarations, not authenticated identities or proof of independent review.

Open **Review and export answer**, enter a reviewer name and optional note. To correct an answer,
enter a corrected answer and cite source IDs (or use **Add selected source to correction**).
Confirm, correct, undo and redo all append history. The last 10 operations appear in the UI;
exports retain the full bounded history. A new edit after Undo clears the Redo branch. Stale
expected revisions return HTTP 409; the UI refreshes the current state before a manual retry.

## Export, verify and restore

**Export evidence packet** resolves citations from the current server-side source. The browser
never supplies its own answer or source geometry to the exporter. The JSON contains:

- source filename, raw-file hash (null for the built-in synthetic demo), content revision, units;
- individual engine file hashes and their aggregate SHA-256;
- original question, engine result and canonical cited entity/quantity records;
- separate reviewer statement, canonical reviewer citations and reversible event history;
- a SHA-256 over deterministic sorted-key JSON, explicitly unsigned.

```sh
node scripts/verify-packet.mjs /path/to/stoa-evidence.json
```

This verifies internal consistency and reports whether the current engine bytes match. It does
not prove authenticity: anyone can alter an unsigned packet and recompute its hash. A complete
recomputation still needs the original source file; the packet contains selected excerpts, not
the entire drawing or a complete IFC geometry graph. Source licences continue to apply.

**Restore exported review** requires the same source to be imported first and the exact engine
hash to match. The server verifies the packet hash, recomputes the engine answer, and replays
validated review commands. It ignores the imported engine answer as authority. A mismatch returns
409; unsupported/forged source IDs and malformed history reject restoration. Reviewer names stay
locally declared. This is local review recovery, not a signed approval import or a migration path
across engine versions.

Each source has at most 100 retained answers and each answer at most 100 review events. Up to
three imports are held in process memory for 30 minutes; timers delete imports and associated
answers/reviews even when idle, and closing the server clears them. No review database, browser
autosave or background cloud storage is created. **Export to keep a review beyond the session.**
Packets are bounded to 16 MiB and over-budget exports fail without truncation.

## Compare revisions

Import both versions, open **Compare source revisions**, and select the earlier source. Both
sources must remain imported/unexpired. Comparison exports bind both source revisions and include
all returned rows and the actual engine file hashes; `scripts/verify-packet.mjs` also checks comparison
exports. The UI explicitly shows at most 200 non-unchanged rows.

- **DXF rooms:** exact unique room identifiers and strict area validation. Reports added/removed
  identifiers, area changes, geometry changes, invalid comparisons and duplicate-ID ambiguity.
  A renumbered room can appear as a removed/added identifier; this is not automatic identity tracking.
- **DXF primitives:** select an exact source layer and matching distance in metres. Unit-normalized
  positions generate same-type candidate edges. A bounded Hungarian solver minimizes total edge
  and unmatched cost, partitioned by sparse connected components. It never uses a hidden greedy
  fallback. Multiple eligible candidates remain marked ambiguous; this does not certify uniqueness.
  Lines/arcs are source primitives, not automatically validated door/window objects.
- **IFC:** matches native product GUIDs and compares source records. Duplicate GUIDs remain
  ambiguous. Changed STEP reference numbers can change records without a physical change.

DXF comparisons require the user to declare a shared origin and orientation for the selected
source pair. Changing the source pair resets that declaration. There is no automatic registration,
scale fitting or cross-format comparison. Declared alignment and all physical-change claims remain
unverified. Room comparison is bounded to 250 IDs and a conservative point/text work budget;
primitive comparisons to 600 entities per side, 20,000 edges and 80-node connected components;
IFC comparisons to 2,000 product GUIDs. Budgets fail explicitly rather than emitting partial reports.

## Instance metrics

```sh
node benchmark/instances.mjs examples/instances.synthetic.json
```

The example deliberately has the correct total count but incorrect grouping. Each instance is a
nonempty set of original source entity IDs. Independently labelled `truth` and `predicted` must
reference the same source SHA-256 and contain no overlapping membership within a partition.
One-to-one matching at the declared membership-IoU threshold reports instance precision/recall,
merged predictions, split truth instances, missed/unknown members and pair precision/recall.
CLI output also pins input and scorer bytes. Empty-denominator metrics are null. These metrics
are separate from box-overlap scoring (`benchmark/regions.mjs`) and answer accuracy. No real
sponsor instance score has been measured. Prepare separate class/source evaluations when
semantic classes legitimately share primitives.

## Design provenance

The source-generation/canonical-resolution pattern was reviewed in
`SalesSquad/valmethack@c86c02f78df8871215f42bfa885220bfcd106904`,
`packages/catalog-core/src/index.mjs` and its Evidence Twin contract. Review history, abstaining
assignment and membership evaluation were reviewed in
`SalesSquad/valmet-truth-engine@21f2cc44bb3d05aeebf481a7a5e5c3f878a1222e`,
`ecre/scale/{workspace,matching,evaluation}.py`. Stoa uses freshly authored JS implementations;
no private Valmet data, database, runtime code or 3D pipeline is vendored or executed. Its assignment
solver was checked against exhaustive optima on 80 small synthetic cost graphs. This checks the
mathematical assignment, not the physical meaning or calibration of its costs.
