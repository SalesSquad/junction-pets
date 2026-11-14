# Chronicle Witness — Wikipedia Through Time

Work J26-PF-MARIADB-M1 · partnerEvidenceKey mariadb · ownedBriefRefs M307.
Source: authenticated main 02458b4e9025d9f45b071765c0601e53d6c94877,
shared catalog dated 2026-11-14, latestClarification null.

An editor or reader asks what a Wikipedia article said on a chosen date and how it
changed. This deterministic first product milestone produces a dated snapshot,
revision ID, source digest, lexical comparison, and cautiously labelled short
A–B–A revert candidates. It refuses ambiguous same-time edits, invalid timestamps,
missing revisions, duplicate revision IDs, and unsourced alleged live content.

## Runnable first milestone (Node 22+, no dependencies)

    node solutions/mariadb-wikipedia-time/src/cli.mjs --page demo:harbor-energy --at 2025-01-11T01:00:00Z --compare 2025-01-10T00:00:00Z
    node --test solutions/mariadb-wikipedia-time/tests/chronicle.test.mjs

The bundled example is SYNTHETIC, not Wikipedia data. Output carries
OFFLINE_DETERMINISTIC and NO_MARIADB_CONNECTION. Lexical diffs and rapid reverts
DO NOT prove vandalism, factual truth, bias, or editorial intent. The core has a
5000-revision fixture limit and no source import or external action.
A user-supplied LICENSED_REPLAY label is unverified: the URL is only syntax-/revision-ID checked and the hash only covers imported bytes. Every response explicitly says verified_live_source=false; actual source contents and licence still need independent verification.

## Real database design and blocked dependency

sql/schema.sql is a NOT-YET-EXECUTED MariaDB WITH SYSTEM VERSIONING design.
Crucially, a Wikipedia revision's historical timestamp is not the same as
database SYSTEM_TIME, which measures our later import/correction history.
The real as-of query binds revision timestamp and uses >=2 records to detect ties.

Next: select and license-pin an official sponsor Wikipedia revision dataset,
import through actual MariaDB with prepared statements and provenance hashes,
then check dated/ambiguity/revert outcomes against an independent historical
oracle (including an attempted vandalism and timestamp boundary). Only after
the DB proof: accessible split-pane timeline, multilingual retrieval/vector
search, held-out answer/citation benchmarks and sponsor-ready product demo.
No MariaDB instance, sponsor dataset, live API, vector search, device, deployment,
or FINAL submission is claimed by this milestone.

Maturity 1/6 (replayable deterministic core, not sponsor-integrated).
Product paths are isolated; shared manifest and merge belong to PR integrator.
Reference: https://mariadb.com/docs/server/reference/sql-structure/temporal-tables/system-versioned-tables

## M3: bounded Wikipedia intake and truthful dual-clock readback

Work J26-PF-MARIADB-M307-M3-20261114 supersedes the earlier “no source import”
limitation above. Only `fi.wikipedia.org/w/api.php` is admitted; caller supplies a
numeric **page ID**, a count (1–20), and a new output filename. No URL argument,
credentials, automatic retries, uploads or overwrite. Example (choose your page):

```sh
node solutions/mariadb-wikipedia-time/src/wikipedia.mjs --page 155 --limit 3 --out /tmp/chronicle-snapshot.json
node solutions/mariadb-wikipedia-time/src/cli.mjs --data /tmp/chronicle-snapshot.json --page 155 --at 2026-11-14T00:00:00Z
node solutions/mariadb-wikipedia-time/studio/server.mjs --snapshot /tmp/chronicle-snapshot.json
```

Open `http://127.0.0.1:4177` and select “Admitted local Wikipedia snapshot” to
compare exact revisions against the synthetic demonstration. Paths are startup
arguments only; HTTP never reads caller-selected files or fetches remote data.
Wikitext is displayed as text, never HTML. The studio does not persist user data.
No earlier article state is inferred from an incomplete historical window.

Bounds: 20 revisions, four pagination requests, 10-second total fetch deadline,
1 MiB per response, 128 KiB UTF-8 per revision and 2 MiB content total. Intake
rejects hidden/deleted/missing records, invalid identity/time/content, title
changes within the window, duplicates, timestamp ties, reversed order, invalid
continuation tokens and malformed/truncated JSON. A requested count must be
complete; `has_more` explicitly says whether older revisions remain outside
this **latest-N** window. Historical title changes need a different dataset
adapter; this adapter preserves the API's current page title, not historical titles.

The canonical digest is SHA-256 over the ordered JSON tuple documented by
`snapshotDigest` in `src/wikipedia.mjs`; each revision also hashes exact wikitext.
Retrieval UTC, pinned request URI, canonical revision URLs, attribution and
licence are preserved. Loading a file validates structure/hashes, **not its
origin**: user-recomputed hashes cannot establish Wikipedia or sponsor
authenticity. `WIKIPEDIA_API_SNAPSHOT` describes the format/source claim;
`LOCAL_SNAPSHOT_HASH_ONLY_UNVERIFIED` and `verified_live_source:false` remain
visible. The mocked test inputs are not real Wikipedia evidence.

Attribution: Finnish Wikipedia contributors; each canonical `oldid` link supplies
history attribution. Text reuse is subject to CC BY-SA 4.0 and additional terms;
embedded/third-party material can have separate terms. Preserve citations and
review rights before redistribution. No sponsor dataset is bundled or claimed
verified. Sources: [MediaWiki Revisions API](https://www.mediawiki.org/wiki/API:Revisions),
[Wikimedia reuse terms](https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use),
[MariaDB temporal semantics](https://mariadb.com/docs/server/reference/sql-structure/temporal-tables/system-versioned-tables).

### Optional MariaDB local/test path — NOT_RUN_LIVE_DB

`src/mariadb.mjs` uses the optional `mariadb` Node driver and an explicitly supplied
loopback connection (`host`, numeric `port`, `database`, `user`, optional `password`).
Keep this private JSON outside Git and shared output; it is never logged. Install
the driver project-locally only if needed, without changing root dependencies:

```sh
npm install --prefix solutions/mariadb-wikipedia-time --no-save --package-lock=false --ignore-scripts mariadb
node solutions/mariadb-wikipedia-time/src/db-cli.mjs --snapshot /tmp/chronicle-snapshot.json --connection /tmp/private-local-test.json --page 155 --at 2026-11-14T00:00:00Z --initialize-new-test-schema yes
```

Use only a disposable existing test database. The explicit initialization flag
creates the schema; it never alters/migrates existing tables. Earlier schema
versions need an independently planned migration, not this flag. No daemon,
container pull, production connection or backdated SYSTEM_TIME manipulation.
Import validates the snapshot before starting a bounded transaction, uses
prepared bindings for all values, deduplicates exact IDs and rolls back on
conflicts. Database readback verifies content hashes and canonical URLs/licence.
`--at` queries **Wikipedia revision time**. Optional `--system-at UTC` additionally
uses MariaDB `FOR SYSTEM_TIME AS OF` for **database import/correction time**;
this cannot reveal imports before they occurred. No same-time tie is selected.
The schema retains NO PAD binary identity columns. Rows keep provenance,
retrieval time, request URI, snapshot digest and attribution.

Focused checks:

```sh
node --test solutions/mariadb-wikipedia-time/tests/chronicle.test.mjs solutions/mariadb-wikipedia-time/tests/intake.test.mjs solutions/mariadb-wikipedia-time/studio/studio.test.mjs
```

M3 local evidence: initial combined run 26/27 passed; the existing HTTP listener test was blocked by
`listen EPERM 127.0.0.1` in this sandbox. One real API probe (page 155, limit 1)
returned `WIKIPEDIA_INTAKE_REFUSED`; no snapshot was written or retried. Docker
image inventory was denied at the existing OrbStack socket; no MariaDB client,
server connection or driver was supplied. **NOT_RUN_LIVE_DB**; mock SQL binding
checks are not MariaDB qualification. Browser rendering is not verified.

After the final focused additions: `node --test solutions/mariadb-wikipedia-time/tests/intake.test.mjs` passed 9/9. The earlier core+intake command passed 21/21 before those additions. `node --check` passed for `studio/app.js` and `src/db-cli.mjs`; `git diff --check` passed. No live provider, browser or SQL verdict is inferred.

## M4: offline, release-pinned M Parquet intake

Work `J26-PF-MARIADB-M4-20261115`, M307; changes are based on PR197 HEAD
`8d85d66009f865f096a8d3b9a4c5a267f2b4198d`, left uncommitted for the coordinator.
Existing M3 results and `M3_SOURCE_HASHES.sha256` remain historical evidence;
the README additions here do not retroactively update that hash record.

Supply a **local** `versions-01.parquet` … `versions-16.parquet` and the exact
`SHA256SUMS` asset from the official [m-2026-10 release](https://github.com/MariaDB/mariadb-wikipedia-datasets/releases/tag/m-2026-10).
There is no automatic download. The manifest bytes must hash to
`7d59a6a28b10f996be3c36fc4d82f5faa97624f8fca7a37cbf5d70e4bb809f68`,
observed in the official [release asset metadata](https://github.com/MariaDB/mariadb-wikipedia-datasets/releases/expanded_assets/m-2026-10)
on 15 November 2026. Caller-generated checksums cannot establish official origin.
The shard basename and streaming SHA-256 must match an entry in that pinned
manifest before Parquet decoding. These pins verify a local copy against the
observed release metadata; they do not authenticate a live Wikipedia provider.

```sh
# If PyArrow is absent, optionally create an isolated product-local environment:
python3 -m venv solutions/mariadb-wikipedia-time/.venv-m
solutions/mariadb-wikipedia-time/.venv-m/bin/python -m pip install pyarrow==26.0.1
# Activate only if using this optional environment; no global install is needed.
. solutions/mariadb-wikipedia-time/.venv-m/bin/activate

python3 solutions/mariadb-wikipedia-time/scripts/import-parquet-m.py --parquet /local/versions-01.parquet --sha256sums /local/SHA256SUMS --page 155 --out /tmp/m-replay.json
node solutions/mariadb-wikipedia-time/src/cli.mjs --data /tmp/m-replay.json --page 155 --at 2026-01-02T00:00:00Z --compare 2026-01-01T00:00:00Z

# Alternative Node bridge: import and immediately query; choose a NEW output path.
node solutions/mariadb-wikipedia-time/src/parquet-m.mjs --parquet /local/versions-01.parquet --sha256sums /local/SHA256SUMS --page 155 --out /tmp/m-replay-other.json --at 2026-01-02T00:00:00Z --compare 2026-01-01T00:00:00Z
```

The paths and page/date values above are operator-selected examples, not a claim
that page 155 is present in shard 01. Both import CLIs require all four explicit
flags, reject existing outputs (including symlinks), and never overwrite. Missing
PyArrow fails closed with `DEPENDENCY_UNAVAILABLE`; no dependency auto-install.
The Node bridge uses `python3` from the operator's PATH without a shell.

Intake scans the five required columns in batches of eight, filters one declared
positive uint32 page ID, and retains **all matching versions in that one shard**
only if there are 1–50. It rejects a 51st match rather than silently truncating.
No whole-table `read_table`, sorting of corrupt input, cross-shard completeness
claim or inferred pre-window history. UTC timestamp types, nonempty bounded
text/title, positive uint32 revision IDs, uniqueness, and strictly increasing
revision timestamps are checked; timestamp ties and reversed history fail closed.
Bounds: 128 KiB UTF-8 per revision and 2 MiB total text; manifest 16 KiB.
The shard is hashed again after scanning to detect changes during decoding.
Batching bounds retained rows; Parquet decoding still needs memory for the
format's compressed pages/dictionaries. Only use the admitted official shard.

Output is a `LICENSED_REPLAY` accepted by existing `chronicle.loadDataset()`.
Each record preserves its title, revision UTC and canonical Finnish Wikipedia
`oldid` URL. `intake` records the release, both input hashes, scope and attribution.
Chronicle's existing replay loader deliberately returns
`LOCAL_HASH_ONLY_UNVERIFIED` and does not elevate saved metadata to authenticated
provider evidence; the bridge returns intake metadata alongside its answer.
The existing studio/API-snapshot DB adapter is **not** extended by this intake.
`verified_live_source:false`, `OFFLINE_DETERMINISTIC` and
`NO_MARIADB_CONNECTION` remain truthful. Revert candidates remain tentative.

**Attribution and rights:** Finnish Wikipedia contributors; credit each revision
and the linked page history. Wikipedia text in this dataset is
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), including applicable
attribution and ShareAlike duties. The upstream loader code/documentation is MIT;
that distinct code licence does not relicense the Wikipedia text. This importer
is independently implemented from the documented schema; no upstream loader
code or Wikipedia text is bundled. Preserve the release's README/attribution
alongside the original download and any distributed replay. Official schema and
rights: [dataset README](https://github.com/MariaDB/mariadb-wikipedia-datasets#readme).

Targeted check:

```sh
node --test solutions/mariadb-wikipedia-time/tests/parquet-m.test.mjs
```

Local result: Node v26.13.0 / Python with PyArrow 26.0.1: **3/3 Node tests pass**,
including **4/4 nested Python tests**. Generated tiny Parquet inputs are explicitly
**SYNTHETIC**, not official M data. They cover wrong/valid digest, pinned-manifest
refusal, exact as-of answer, lexical comparison, tentative revert, deterministic
output, page filtering, duplicate/order/tie/size/count/schema rejection, and no
overwrite. When Python/PyArrow is missing, the integration test is explicitly
skipped while pure Node checksum-parser/pin-refusal tests still run.
The initial run exposed Parquet's seconds-to-milliseconds timestamp conversion;
the adapter now admits UTC Parquet timestamp units while requiring whole-second
values. The repaired focused run passed; no M3 historical result was changed.

**Source-author checkpoint:** the initial code worker read the official manifest
and schema and tested synthetic Parquet only; it did not import the official shard.
**Coordinator's later public-data replay (15 Nov 2026):** downloaded
`versions-06.parquet` (9,621,134 bytes, 35,834 rows) and official
`SHA256SUMS` into an MBP task-local lab; SHA256SUMS digest matched the
GitHub release asset `7d59a6a28b10f996be3c36fc4d82f5faa97624f8fca7a37cbf5d70e4bb809f68`
and the shard passed the published per-file checksum. Using that unchanged M4
CLI, page `212820` produced **5 licensed historical revisions**, and a
2026-11-14 as-of query resolved revision `20651356`. The task-local
JSON replay SHA256 was
`e630e7e3e2a456175ebc7749b832976d03e64ca4418925719a97f1782eebb1ea`.
This is a real public offline dataset slice, **not** an authenticated live
Wikipedia response, complete history, independent Wikipedia fact verification,
or a real MariaDB service. No 315 MB full-dataset download, provider inference,
persistent daemon, DB deployment or CRACI run was started. Existing CRACI run43644159235 remains **CANCELLED**, not passing.
Knowledge OS context/evidence tools were unavailable in the runtime catalog
(`registry_identity_unverifiable`, not routed); no saved reference was treated
as source proof. Coordinator still owns final review, commit and push to PR197.

Coordinator note: authenticated GitHub PR197 readback matched the assigned HEAD.
The connector's `main` commit readback returned
`a2d73f70b6e302866e262535fb026fcbfa4c2f4c`, differing from the assignment's
`73669fee92f24fa2acf28d4b683b851e0fa39a1b`; no rebase/merge was attempted.
Reconcile the actual integration base at coordinator handoff. Final checks:
17/17 combined core+M4 Node tests passed, including four nested Python tests;
subsequent affected M4 run passed 3/3 after added boundary/dependency cases.
`git diff --check` passed. The accepted 50-row boundary and absent-PyArrow refusal
are tested with synthetic inputs. The product-local `.venv-m/` is ignored.
