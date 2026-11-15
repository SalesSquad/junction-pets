# Rokoko Shared-World Tournament — frozen comparison, not a leaderboard

**Work ID:** `J26-ROKOKO-HEAD2HEAD-20261114`  
**Base source:** `312130c9f0b63b9623e4cc9401ace74539296733` (Rokoko #153)  
**Status at authoring:** local unsealed contract tests only; **locked tournament not yet run**.

Two separately developed, source-locked policies passed earlier independent
2D synthetic qualification runs, but those were on *different* worlds.
The only scientific purpose of this lane is to compare the frozen policies on
the **same new worlds**, including safety and effort, without adjusting either
model, changing hyperparameters or silently selecting a winner.

| Component | Immutable source | Immutable fitted weights |
| --- | --- | --- |
| Supervised nonlinear DAgger v2 ([PR #158](https://github.com/SalesSquad/junction-pets/pull/158)) | `f96788807c262b2233f034c045df4373cb3c428c` | `1bab986c10be062cf87a4848916917cbab3a78b53e78cda8c2f8673f62d4cc55` |
| Reward-driven tile-coded Expected SARSA ([PR #160](https://github.com/SalesSquad/junction-pets/pull/160)) | `f7b512d93ca46e6ddf7204f62f118eee800f285b` | `3868559e05f81e3148e34ebd99a7d874525e4ceba2ca942779628104d38fef28` |

The policies share an exactly verified `arena.py` and `run.py` world generator,
geometry-aware safety shield and seeded sensor schedule. Each policy receives
its own fresh simulator instance for the **same frozen `World` dataclass**.
This does not make the shields real hardware interlocks.

## Lockbox preregistration — before any qualification

| Split | World seeds | Count | Prior exposure |
| --- | --- | --- | --- |
| `locked_test` | `test:327000..327499` | 500 | None in this task |
| `locked_ood` | `ood:427000..427299` | 300 | None in this task |

These disjoint windows do **not** intersect v1 exposed `320000..320299` /
`420000..420199`, reward TD `325000..325299` / `425000..425199`, supervised
v2 `326000..326299` / `426000..426199`, or the MuJoCo lane's proposed
`329000+` / `429000+` windows. The development-only smoke windows here are
`dev:128500..128599` and `cal:228500..228599`; they may not be treated as
independent confirmation. The model training windows are unchanged.

## Source-bound commands

The integrator should use **three distinct GitHub checkouts** on an authorized
CRACI runner: this harness at its exact task commit, v2 at its exact SHA, and
TD at its exact SHA. The existing `run-receipt.mjs` must bind the harness and
one product source; this program separately verifies the second pinned git
HEAD, tracked cleanliness, shared simulator hashes and **both model digests**.
Both outputs go into the existing `CRACI_RECEIPT_DIR/artifacts/` directory,
never the tracked repository.

```sh
python3 harness/experiments/rokoko-headtohead/tournament.py \
  --v2-root "$GITHUB_WORKSPACE/source" \
  --td-root "$GITHUB_WORKSPACE/comparator" \
  --split locked_test --episodes 500 --confirm-lockbox \
  --output "$CRACI_RECEIPT_DIR/artifacts/shared-test.json"

python3 harness/experiments/rokoko-headtohead/tournament.py \
  --v2-root "$GITHUB_WORKSPACE/source" \
  --td-root "$GITHUB_WORKSPACE/comparator" \
  --split locked_ood --episodes 300 --confirm-lockbox \
  --output "$CRACI_RECEIPT_DIR/artifacts/shared-ood.json"
```

Both are deliberately locked against partial sample inspection. A fresh
unchanged run is **not** permitted simply because it is cheap; the first
outcome, including any failure, stays in the experiment registry. The CRACI
cutoff remains 15 Nov 2026 17:00 UTC, with existing reservation/guard rules.

For a source-level smoke **before** opening test/OOD worlds, use e.g. the
same CLI with `--split dev --episodes 8` and no `--confirm-lockbox` on
verified source checkouts. No sponsor dataset or physical robot data is used.

## Predeclared analysis

- The *primary contrast* is the **paired v2-minus-TD success difference** in
  percentage points, separately on test and OOD, with a 4000-resample
  world-level percentile confidence interval. Positive means v2 had more
  completed worlds; negative means TD had more; zero-centered intervals are
  inconclusive. This is descriptive, not a certified p-value or safety claim.
- Secondary paired contrasts: unsafe events, aborted episodes, mean holds and
  refusals. Raw world rows are retained, including negative effects.
- Both policies are also compared to the same unchanged shielded constant
  baseline. TD additionally reports the same-guard constant (deadman/stale
  fallback asymmetry is labeled). No automatic 'winner' flag or model promotion.
- Training provenance and fixed weights are checked *before* any locked world
  is created. Model changes require **new untouched worlds**, a new work ID
  and another explicit qualification decision; never rewrite evidence.

Output schema: `junction.rokoko.shared-world-tournament.v1`. It contains
`policy_sources`, `weights_sha256`, `shared_simulator_sha256`, `training`,
`result.summaries`, `result.v2_minus_td`, `result.world_fingerprints`,
`result.per_world`, `limitations`, and UTC completion. Files are source-reported
receipts, not provider-signed SBOM, a provider Euro invoice or physical robot
qualification.

## Checks and ownership

```sh
python3 -m unittest discover -v \
  -s experiments/rokoko-headtohead -p test_tournament.py
python3 -m py_compile experiments/rokoko-headtohead/tournament.py
```

The sole code owner is `experiments/rokoko-headtohead/**` on a task-owned
stacked draft PR. The parent integrator owns all edits to
`.github/workflows/craci-pilot.yml` and `scripts/craci/plan.mjs`, CRACI
dispatch, billing reservation and merge/closure decisions.
