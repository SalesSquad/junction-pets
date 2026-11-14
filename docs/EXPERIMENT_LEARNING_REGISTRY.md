# Joint experiment history and learning loop — Meta, Verda and Apple

Source of truth: [`services/experiment-registry/README.md`](../services/experiment-registry/README.md),
[`ops/experiments/`](../ops/experiments/). This is developer evidence metadata,
not Chibi private memory, provider authorization, a background scheduler or an
automatic GPU spend permission.

## What is actually inventoried

- Meta source kernel (PR #60): synthetic source tests, **not glasses**.
- Meta numeric model (draft PR #70): synthetic candidate ranking and shifted
  false-positive risk; **no real visual model**.
- Apple native source port (draft PR #73): Swift source/typecheck; **no device**.
- Verda Savi V2: separate project's genuine GPU training, synthetic held-out
  mean IoU improved 0.2501 to 0.6967, **not qualified for release**.
- Verda Wan draft: actual GPU-generated 3-second video, **not model training**.

Existing historical metadata is imported as non-promotable because not all
independent split, evaluator and checkpoint digests are available from one
verified source. Never silently fill a missing proof with a synthetic value.

## Operating procedure (agent-readable)

1. Before an experiment, freeze `source.commit`, dataset/split sample-set hash,
   evaluator protocol, primary/safety metric policy and its SHA-256.
2. Run on an already-authorized executor. Store private data in its owner-approved
   private store; produce a redacted run envelope with receipt/source hashes.
3. Write the new immutable run under `ops/experiments` via the CLI and deliver
   it by source-pinned task branch/PR. Review changes to metric definitions.
4. Record any observed failure by case digest; derive a quarantined case
   proposal, review independently, and create a next-training *plan* (no run).
5. Evaluate baseline and candidate on the **same frozen independent test set**.
   Submit the candidate with `record-run --baseline ... --policy ...` to trigger
   comparison automatically; a safety regression, missing proof or incompatible split
   blocks advancement. A model-only `record-run` without these options exits 2
   with `not-compared`: the first baseline is preserved but never silently
   admitted. `candidate-eligible-for-review` is not production.
6. If a run is from a different repo (Savi, Reality Twin, video, Verda CLI),
   preserve original repo/commit and receipt location; do not copy raw assets.

### Outstanding integrations

- No live automatic subscription to Verda jobs or Apple/Xcode Cloud reports:
  those producers must emit run JSON and commit an immutable update.
- Meta's real DAT capture, licensed first-person data, hardware identity
  proof and authenticated Chibi host receipts are **not implemented by this**.
- The independent evidence reviewer must verify source and exact comparison
  bytes before anyone promotes the candidate beyond research.
- The initial Meta numeric shifted false-candidate rate 13.71% is unacceptable
  for autonomous identity claims and stays visible as a blocker.
