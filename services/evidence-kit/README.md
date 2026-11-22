# Evidence Kit — reusable source evidence

Dependency-free Node 22+/browser package extracted from the completed Stoa work. It admits
exact source bytes, resolves canonical references, separates method results from human review,
and exports replayable packets. Executable consumers: DXF room area and CSV exact-decimal total.
There is no Stoa server, model call, cloud account, telemetry or database dependency.

**Status:** bounded reuse pilot, not real-document/industrial/authenticated-review qualification.
`@salessquad/evidence-kit@0.1.0` is an internal package; it is not published to an npm registry.

## Run

```sh
cd services/evidence-kit
npm test
npm run demo
npm run benchmark
npm run serve
# http://127.0.0.1:4326
npm pack --ignore-scripts --pack-destination /your/output
```

This package itself requires no dependency installation. Install its local archive in the next
project. Root repository qualification uses the root's own locked dependencies independently.

```js
import {createReview, exportPacket, replayPacket} from '@salessquad/evidence-kit';
import {csvAdapter} from '@salessquad/evidence-kit/csv';
import {sumCells} from '@salessquad/evidence-kit/table';
const dataset = await csvAdapter.ingest(sourceBytes, {
  filename: 'costs.csv', expectedSha256: independentlySuppliedSourceHash,
  rights: {kind: 'user_supplied', attribution: 'Original source rights apply'}
});
const query = {valueIds:['r2c2','r3c2'], unitIds:['r2c3','r3c3'], expectedUnit:'EUR',
  statedTotalId:'r4c2', statedUnitId:'r4c3'};
const claim = await sumCells(dataset, query);
const review = await createReview(dataset, claim);
const packet = await exportPacket(dataset, claim, review);
const replay = await replayPacket(packet, {
  bytes: sourceBytes, adapter: csvAdapter, run: d => sumCells(d, query)
});
```

## Reusable layers

| Layer | Entry | Contract |
| --- | --- | --- |
| Source/extraction identity | `src/dataset.mjs` | Byte hash, adapter version, explicit units/frame/rights, immutable generation. |
| Canonical references | `ref(id)` / `resolve(ref)` | Source + generation + original record hash; missing/stale IDs fail. |
| Method claims | `src/claim.mjs`, `methods/` | Result, method/version/parameters, evidence basis and exact citations. |
| Human review | `src/review.mjs` | Hash-chained corrections, compare-and-swap, idempotency, Undo/Redo. |
| Packets/replay | `src/packet.mjs`, `cli.mjs` | Separate consistency, source-byte verification and actual method replay. |
| Revision comparison | `src/compare.mjs` | Caller-selected stable keys, duplicate ambiguity and explicit frame guard. |
| Assignment | `src/assignment.mjs` | Bounded minimum-cost matching, explicit unmatched endpoints. |
| Browser UI | `components/review-element.mjs` | Framework-neutral `<evidence-review>` with inspection, review and export. |
| Workspace Studio | `components/workspace-studio.mjs` | Host-side source/result/head checking for a captured Studio form. |

## CLI and history migration

```sh
node cli.mjs verify packet.json original.csv
node cli.mjs replay packet.json original.csv --output replayed.json
node cli.mjs migrate-stoa legacy.json original.dxf --room 2.01 --output migrated.json
```

Outputs are create-only, mode 0600. Stoa v1 migration preserves the original packet and review
as historical data, reruns the explicitly selected room method, and starts a fresh active review.
Same-result reviews can survive package upgrades through actual replay. Changed source,
extraction, method version/parameters, result, checks or citations require new review. Unknown
packet versions fail; historical approval is never silently attached to a new result.

## Interpretation

- `cross_checked` means geometry agrees with a separately cited annotation, or an exact sum
  agrees with a separately cited total and unit. This is not independent ground truth or evidence
  of statistically independent measurements.
- `openPacket` checks consistency and optionally raw bytes. **Replay extraction and the method
  before adopting imported results/reviews as current.** Unsigned hashes can be recomputed by a
  forger. Typed reviewer names are declarations, not authenticated independent review.
- `createDataset` and `createClaim` are trusted adapter/method authoring boundaries. Structural
  validity cannot establish extraction or semantic correctness. Source pins must come separately
  from the host; copying a packet's own digest is not an independent trust root.
- CSV has no formulas, XLSX, automatic locale or currency conversion. Totals cover explicitly
  selected cells, not workbook completeness. DXF supports only the bounded subset in its adapter;
  no DWG, INSERT/block transforms, PDF, IFC, PLY, physical calibration or scene registration.
- Packets include normalized records but not raw source bytes. The host owns permissions,
  retention and licences. There is no automatic remote upload, persistence or provider execution.
- Caps: core source 16 MiB (DXF 6 MiB, CSV 2 MiB), 5,000 entities/cells, 8 MiB canonical JSON,
  1,000 claim references, 100 events/review, 10 historical packets and 1,000 polygon vertices.
  Over-budget matching fails; it never quietly switches to greedy/partial output.

Start with [adoption](docs/ADOPTION.md), [contract](docs/CONTRACT.md),
[capabilities](capabilities.json), [agent workflow](skills/evidence-workflow/SKILL.md) and
[qualification](docs/QUALIFICATION.md). Extraction/design pins are in [PROVENANCE.json](PROVENANCE.json).
The Stoa app and private Valmet systems are not modified or executed by this runtime package.
