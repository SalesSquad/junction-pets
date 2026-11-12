# Junction public submission gate (source-only, deny by default)

This is a **pre-release review gate**, not an exporter and not permission to publish.
Use it only for an intentionally assembled, non-Chibi public source tree.
The private SalesSquad/chibi host, ops/, internal Mission Control, cloud and
plugin registration receipts, secrets and payment/Passport records **must not**
enter a judge-facing package. See docs/JUNCTION_SUBMISSION.md.

## How to use

1. On a clean source branch, pick the exact source files intended for the
   particular challenge. Copy these reviewed, *unmodified* UTF-8 files into a
   new proposed export directory outside the repo (not into dist/chibi/).
2. Generate SHA-256 digests of exactly those file bytes. Write a reviewed
   JSON allowlist like this (replace placeholders with actual values):

   ~~~json
   {
     "schemaVersion": 1,
     "sourceRepository": "SalesSquad/junction-pets",
     "sourceRevision": "0123456789abcdef0123456789abcdef01234567",
     "files": [
       {
         "path": "pets/aiven/pet.json",
         "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
       }
     ]
   }
   ~~~

3. Run:

   ~~~sh
   node services/submission-gate/cli.mjs \
     --tree /absolute/path/to/proposed-public-export \
     --repo /absolute/path/to/clean-junction-pets-checkout \
     --allowlist /absolute/path/to/reviewed-allowlist.json
   ~~~

4. Save stdout as the source-bound review receipt. Do **not** interpret a
   passing receipt as permission or proof of publication.

## Exact protection rules

- Every staged relative path must appear exactly once in the reviewed
  allowlist. Extra/missing files and case-insensitive collisions fail.
- Only a narrow set of reviewed public roots is even eligible: selected pets,
  demo/catalog, public collaboration contracts and Council/eval/ledger code,
  specific public docs, source helper files and tests. Unknown service roots,
  internal cloud fleet-control, ops/, plugins/, internal Mission Control,
  dist/, nested private Chibi paths, secrets and credentials fail even if
  somebody includes them in the allowlist.
- Symlinks, special files, paths with traversal, binary assets, invalid UTF-8,
  Git LFS pointers and files over 2 MiB fail by default. The file-size cap is
  enforced on metadata before loading and again during bounded no-follow reads.
  Directory enumeration is streamed and capped relative to allowlisted file count.
- The allowlist source revision must exactly match a **clean Git HEAD**.
  Each reviewed file's SHA-256 must match the proposed export bytes and the
  tracked regular-file blob at that source revision.
- Source filename/path, permission and content checks are deliberately
  conservative. A new submission asset category requires an explicit policy
  extension and tests; do not silently broaden the allowlist.
- Secret scanners look for common private keys, provider tokens and JWTs.
  This is a heuristic, **not** a comprehensive data loss prevention review.
  Generated bundles, media metadata, copyright/licenses, logo/brand assets,
  competition terms and runtime permissions need additional independent review.

## Tests

~~~
node --test services/submission-gate/gate.test.mjs
~~~

The tests construct disposable Git repositories under the OS temporary directory.
They do not use credentials or touch an existing repository.

**Ownership:** This directory's code is owned by W2 Submission Gate; the central
integrator owns package scripts, publication, source locking and any coupling to
existing scripts/package-chibi.mjs. That Chibi-specific bundler is not a
Junction judges' submission exporter.
