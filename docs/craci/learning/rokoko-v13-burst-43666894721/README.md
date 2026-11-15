# V13 RIGHT4 burst TRAIN pilot — science STOP, workflow failure

[CRACI run #43666894721](https://github.com/SalesSquad/junction-pets/actions/runs/43666894721) performed the preregistered original MuJoCo 3.3.7 TRAIN-only comparison on 48 paired worlds (40 near, 8 clear), four arms and **192 episodes**. The physics step completed and its separate in-job qualifier reported independently replaying all **4,798 original option transitions**. The overall GitHub workflow **FAILED** in the subsequent contract-test step; this is not a green hosted qualification.

| Observed safe 250-tick physical goals | V5 | V12 | RIGHT4 burst 2 | RIGHT4 burst 4 |
|---|---:|---:|---:|---:|
| Near, 40 paired worlds | 3 | 3 | 3 | 3 |
| Clear, 8 paired worlds | 5 | 5 | 5 | 5 |
| Total, 48 paired worlds | 8 | 8 | 8 | 8 |

All arms won the same eight seeds. Each candidate had **zero novel goals, zero lost V5 goals and zero observed unsafe episodes**. Original controller-mode evidence attributes 149 original-mask-legal RIGHT4 actions to active burst mode (61 in burst-2 and 88 in burst-4), not incidental V5 fallback. The science decision is **STOP** because there was no novel burst goal. This small selected TRAIN cohort does not demonstrate equivalence, population safety, real-device safety or generalization, and no model is promoted. The separate V13 continuation hypothesis is not evaluated by this four-arm burst study.

The two burst arms activated in the **same 35 distinct near worlds**, all of
which the frozen V5 failed; they did not activate in a V5-winning world.
These are retrospective counts from this selected cohort, not evidence that
the interventions caused the failures. The reproducible
[coverage audit](coverage-audit.json) checks the original archive, nested
files and all 192 trace hashes without running new physics. Its script is
`scripts/craci/rokoko-v13-43666894721-coverage-audit.py` (SHA-256
`1c196ff829b467e0eb22f82a6f39d973d0f046e6d05f4f5b0a9b53f494f7e791`);
the summary SHA-256 is
`21565205676cead722ac913439444d79deeb8e6aa9384d452314b65edea926bf`.

Separately, the earlier [V13 causal experiment](../rokoko-mujoco-v13-43660619725/README.md)
ended in a **real unsafe event** and an incomplete STOP after reaching two seen
TRAIN worlds. Its safety stop is not cleared by the burst study's zero observed
unsafe episodes.

## Why the workflow failed

After the physics/replay step succeeded, the workflow ran the V13 unittest discovery from the GitHub workspace outside the harness checkout. One retention test imported `scripts.craci` as a package, which was not on that working directory's Python path. That produced `ModuleNotFoundError: No module named 'scripts'`, and receipt finalization correctly marked the overall job failed. The source-only correction loads the sibling fixture by exact file path; the complete V13 test suite was then run from outside the checkout with `PYTHONPATH` unset. This later test repair does **not** change the historical receipt or turn the failed workflow green. Do not rerun the same already-consumed seed range to repair this infrastructure error.

## Evidence and limits

- Exact product source: `faec266d6d3a44af3a564f46e0778209c1dc3af1`; exact harness source: `5ce3ac346c1ad7c399bf84e2cd678fba041d9fd0`.
- Original artifact `14142925646` ZIP SHA-256 `45ff6ba157771a2a56c6139ec124a30f0fc0f26674fe97f00dd5d4c996e404e2`. A byte-matching local iCloud Drive copy exists at `Junction/CRACI/rokoko-v13-burst-43666894721-github-artifact.zip`; cross-device synchronization is unverified.
- Original reassembled `training.json` SHA-256 `9f4f5301c6dbb2327212f0ca27ca0ea81da65b6b59896cf3a384079f0d89412d`; full trace gzip `f56b8e7c646e925be39ac2d896ed2d110e029d47b344bcfc359f893a91c80495`; paired readout `0c84a86c2e7ff06190ad1a33a541a3481ddd8c20dccb1299b7aca18de6d4e333`. Hosted replay proof `046f0de3ad015997e9694f3efcf41169ca6e0a7869a19084c5d13803f8715cc0` reports replay of every option.
- The separate [policy audit](policy-audit.json) revalidated outer and nested hashes, reassembled originals, checked all 192 trace hashes and original legal masks, and reproduced all 4,798 policy actions and active burst modes from recorded public observations on the owner's Mac. This off-host audit **did not run a new MuJoCo physics replay**. Its script is `scripts/craci/rokoko-v13-43666894721-policy-audit.py` (SHA-256 `654847a38b8fabbc7242851259ee275289ed304dbda98ca909fcd8d0e39b6f8f`). Summary SHA-256 `c54bbd8aa2a86080fc5fc2de768e911f3b4590343a0f114cd79fe1f582dd6e07`. Matching local iCloud Drive copies of both were created alongside the original ZIP; cross-device synchronization is unverified.
- The first hosted attempt [#43665531960](https://github.com/SalesSquad/junction-pets/actions/runs/43665531960) failed at reset-only cross-platform preflight before any episode; see the [preflight record](../rokoko-v13-20261115/PREFLIGHT_CROSS_PLATFORM_20261115.md). Its original failed receipt is preserved separately.
- The receipt reports exact source/harness binding, but no independently verified provider attestation or actual billed cost. The results remain preliminary TRAIN science and do not authorize release or promotion.
