# Bounded RED/GREEN evidence

Work: `junction.atech-dev.capability-proof`; developer `junction-dev-atech-dev`.
Base: `317aaba5ce1bffc8f248f2bf9b3be128ca12c79a`.
Reservation: PR10 comment6847107799. Initial checkout was clean at
`46dbea8ff244d6fe07bdf5c24bcbfdf3d2d62ff5`; the reserved branch was fetched
and checked out clean at the exact base before edits. Origin is
`https://github.com/SalesSquad/junction-pets.git`. Connector identity was
SalesSquad; open Atech PR search returned none. No task URL was observed.

All runs used Node v24.22.1 in the attached managed Cloud runner. No nested
workers, paid model APIs, hardware, provider execution, deployment or Chibi
writes. Environment/account selection was supplied by the parent; this worker
does not claim an independently observed Pro quota or Cloud task conversation.

`initial-red.log` records the new test importing an absent module (exit 1,
1 test / 0 pass / 1 fail). `quantity-mutation-red.log` records a deliberately
temporary change from `p.amps * p.quantity` to `p.amps`: exit 1, 19 tests /
15 pass / 4 fail, proving detection of incorrect totals, missed conflicts and
overflow. That mutation was reverted before final checks. `restored-green.log`
records exit 0, 19 tests / 19 pass / 0 fail / 0 skipped after restoration.
These are local synthetic Node tests, not the six authored model evals.

Two initial incompatible-range test fixtures accidentally had min > max;
they correctly threw, and the fixtures were corrected to well-formed ranges.
The first npm install failed at the default unwritable npm cache (exit 254).
Using `npm_config_cache=/workspace/work/atech/npm-cache` resolved installation
without manifest, lock, permission or credential changes. The initial failed
dependent suite had 164 tests / 154 pass / 8 fail / 2 skipped due to absent
dependencies; no passing baseline is inferred from that run.

A clean base archive then passed installation, plugin check, validation,
269/269 full tests and ops status. The company target test did not exist yet
(exit 1). Archive build initially failed because it lacked Git metadata;
retrying with the original Git directory and archived work tree passed while
the source HEAD still equaled the base. Working-tree final verification passed
installation, 19/19 targeted, plugin check, validation, 288/288 full tests,
build, ops status and diff check. Clean committed final-HEAD reruns and raw
counts, exits and log SHA-256 hashes belong to the durable draft PR handoff.

Only owned source and unchanged-producer plugin outputs are committed. Package
version is 0.1.1. The six eval definitions, schema and producer are unchanged.
Historical plugin registration is deliberately untouched and may be stale.
Ops command success is a snapshot generation result, not runtime activation.
Root must independently review the final exact SHA and integration diff.
