# CRACI V11: chronological bottleneck and V12 pilot sensitivity (source-bound R)

2026-11-15. Independent retrospective **TRAIN-only** comparison of original MuJoCo run 43653579339.
Original archive SHA256 bbf94c662fab3ac0efab3448c9e917dcce473a2644efc82a3f4835dd85792bae.
Product ab6df4054ef6ed350b479469590a48046a0c0a68; harness b1938bee9dbca482f645b5dde3359de38e6c125e.
R requires the SHA-pinned Python extractor and checks 800 source rows; no physics, model training, provider signature or model promotion.

## Chronological stage counts, V5 and V11 paired on same TRAIN world

| World subset | Event | Worlds | V5 | V11 | New | Lost | Exploratory exact paired p |
|---|---|---:|---:|---:|---:|---:|---:|
| near | contact | 128 | 99 | 128 | 29 | 0 | 3.7253e-09 |
| near | lateral_after_contact | 128 | 11 | 13 | 2 | 0 | 0.5 |
| near | chronological_forward_after_lateral | 128 | 2 | 3 | 1 | 0 | 1 |
| near | full_contact_lateral_forward_goal | 128 | 0 | 0 | 0 | 0 | not informative |
| near | any_side_forward_proxy | 128 | 60 | 108 | 48 | 0 | 7.1054e-15 |
| near | true_goal250 | 128 | 6 | 6 | 0 | 0 | not informative |
| changed_near | contact | 62 | 33 | 62 | 29 | 0 | 3.7253e-09 |
| changed_near | lateral_after_contact | 62 | 0 | 2 | 2 | 0 | 0.5 |
| changed_near | chronological_forward_after_lateral | 62 | 0 | 1 | 1 | 0 | 1 |
| changed_near | full_contact_lateral_forward_goal | 62 | 0 | 0 | 0 | 0 | not informative |
| changed_near | any_side_forward_proxy | 62 | 8 | 56 | 48 | 0 | 7.1054e-15 |
| changed_near | true_goal250 | 62 | 0 | 0 | 0 | 0 | not informative |

**Key failure localization:** 62/160 changed full trajectories were all in the 128 near-corridor worlds. Among those 62,
29 new contacts and 48 new non-chronological forward reopenings translated into only
**2** new safe 25-mm lateral movements after contact and **1** new forward reopening after that lateral.
No changed world obtained actual terminal 250-tick safe-goal dwell, and zero completed the full contact–lateral–reopen–dwell path.
All 18 original V5 successful worlds remained unchanged by V11.

The event counts and exploratory paired tests reuse the same already evaluated TRAIN cohort;
they do not establish causal motor improvement or prospective generalization.
The ordered stage definitions are stricter than the non-chronological forward-opening proxy.
Chronological stage completion is NOT universally required to reach a clear-world goal;
this analysis does not change the original physical-goal definition.

## V12 48-world source-only pilot sensitivity (hypothetical, never executed here)

The already proposed 144 episodes are 3 paired policies on only **48 distinct worlds** (40 near, 8 clear).
If candidate unsafe counts are 0 on all 48 and world outcomes were independent random draws,
a one-sided 95% binomial upper bound on unsafe-*world* risk would still be 6.05%. That conditional illustration is NOT a physical or source-sampling safety qualification.
For hypothetical independent near-world novel goal rates 1%, 2%, 5%, the probability of at least one observed new goal in 40 near worlds is 33.1%, 55.4%, 87.1%, respectively.
These are mathematical design examples, not V12 predictions; no observed V12 effectiveness is claimed.
A single pilot novelty is only an exploration signal; original full 250-tick success,
baseline non-regression, shield correctness, independent physics replay and distinct future-world evidence
remain required before any promotion claim.

**No action authorized:** do not rerun V10/V11 original source worlds, spend CRACI credits,
relax goal/safety guards, open locked dev/test/OOD or claim model/robot deployment.
Current V12 product PR #226, harness PR #229 and P1 fix PR #230 remain under their existing owners.
