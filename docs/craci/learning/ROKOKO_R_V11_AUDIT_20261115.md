# CRACI Rokoko V11 — independent source-pinned R audit

2026-11-15: TRAIN-only negative science, not new physics or model promotion.

## Original source provenance

- Hosted original run 43653579339: source-reported SUCCESS, no provider-signed attestation.
- Outer original ZIP SHA256 bbf94c662fab3ac0efab3448c9e917dcce473a2644efc82a3f4835dd85792bae.
- Product SHA ab6df4054ef6ed350b479469590a48046a0c0a68; harness b1938bee9dbca482f645b5dde3359de38e6c125e.
- TRAIN JSON SHA256 c3b3b399344fa18eff7a303cf27e2a510ab9eb74111a6216df1ec11a906579df.
- Full original option gzip SHA256 0a38081a43426ee4774d09d22886202aaf56d59f6b925a0a75cb2f2da14c848b.
- Original source and public observation/shield contracts independently checked by Python: 512 initial public scans, 160 paired TRAIN worlds, 800 five-arm trials, 34,992 original options. The original full raw gzip is SHA checked, not independently replayed as MuJoCo physics.
- Locked dev/cal/test/OOD not read. No actual glasses/robot data, new spending, model promotion or provider signature.

## True goal: 250-tick safe terminal dwell (same-world paired)

| Stratum | Worlds | Frozen V5 | V11 | New | Lost | Changed full traces | Delta pp |
|---|---:|---:|---:|---:|---:|---:|---:|
| all | 160 | 18 | 18 | 0 | 0 | 62 | 0.00 |
| near | 128 | 6 | 6 | 0 | 0 | 62 | 0.00 |
| clear | 32 | 12 | 12 | 0 | 0 | 0 | 0.00 |

- Zero paired goal discordances; exact McNemar test is non-informative (sometimes reported p=1). The observed zero change and bootstrap interval [0,0] do not establish equivalence.
- 0/18 observed V5 goal wins lost: exact two-sided 95% upper loss rate 18.53% *on selected TRAIN winners*; this does not prove future win preservation.
- 0/142 baseline failures recovered: exact two-sided 95% upper new-win rate 2.56% *on selected TRAIN failures*; this is not deployment generalization.
- Near forward reopening increased 60/128 to 108/128, while both completed exactly 6/128 true near goals. Reopening is a proxy.
- Original full trajectories changed in 62/160 worlds, without any new terminal goals. V8 and V10 each recorded one unsafe on this cohort; V5 and V11 recorded zero.

## Decision

NO_GO. Preserve V11 negative science. Do not rerun these 517000+ worlds or tune on them. Separate V12 source owners already own any new 518000+ trial; this audit does not authorize execution or model promotion.

Reproduce from original immutable V11 ZIP with scripts/craci/rokoko_r_v11_extract.py and scripts/craci/rokoko_r_v11_audit.R using an unused output directory.
