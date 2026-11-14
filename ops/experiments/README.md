This folder is the versioned, **sanitized** cross-project experiment index.

Initially imported historical pointers are explicitly incomplete and non-promotable.
`capturedAt` on these records is when the inventory was written, not when the
original GPU/Apple/Meta execution finished. Original immutable receipts remain
at their source. Do not add raw training video, model weights, user information,
credentials or private data here. See `services/experiment-registry/README.md`.

For new work: a producer writes an evidence-bound `run` JSON input, invokes the
registry CLI, and delivers these immutable source-pinned records in a task PR.
Failed cases are quarantined; a comparison never directly grants a release.
