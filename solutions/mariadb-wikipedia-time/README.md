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
