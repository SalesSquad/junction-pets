This folder is the versioned, **sanitized** cross-project experiment index.

Initially imported historical pointers are explicitly incomplete and non-promotable.
`capturedAt` on these records is when the inventory was written, not when the
original GPU/Apple/Meta execution finished. Original immutable receipts remain
at their source. Do not add raw training video, model weights, user information,
credentials or private data here. See `services/experiment-registry/README.md`.

For new model work: register the exact frozen comparison policy **first** and
preserve it under `policies/policy.<sha256>.json` in an earlier Git commit.
A producer then writes an evidence-bound `run` JSON input, invokes the
registry CLI, and delivers these immutable source-pinned records in a task PR.
Failed cases are quarantined; a comparison never directly grants a release.

New producers may publish private envelopes for the source-agnostic one-shot
[inbox importer](../../services/experiment-registry/README.md#event-ready-private-inbox-experiment-auto-20261114).
An existing authorized owner job may invoke it after completion with explicit
`--inbox`, `--receipts-root` and `--root /canonical/checkout/ops/experiments`.
This code is not auto-scheduled and never copies private receipt/media bytes into
Git. Originals remain private and retained; only immutable sanitized run metadata
is written here. Model runs require preregistered policy and remain
`not-compared` with exit 2; importing evidence never approves a model or release.
