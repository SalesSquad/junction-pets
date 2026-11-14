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
