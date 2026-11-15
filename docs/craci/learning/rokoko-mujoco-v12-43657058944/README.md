# CRACI Rokoko MuJoCo V12 — original hosted TRAIN pilot, science STOP

This is a **frozen, negative-result audit** of the original hosted run, not a
new model release or a new MuJoCo simulation. The source-bound auditor at
[`scripts/craci/audit_rokoko_mujoco_v12_pilot.py`](../../../../scripts/craci/audit_rokoko_mujoco_v12_pilot.py)
reconstructs the **lossless original** training and trajectory streams from the
unaltered GitHub artifact ZIP, checks their independent receipt/retention hashes,
and recomputes the scientific readout from every recorded public action step.
It **does not** claim signed provider attestation or independently re-run the
underlying MuJoCo engine. The hosted qualification independently claims a full
physics replay and should be kept distinct from this offline byte/contract audit.

## Original identities (do not substitute later heads)

| Source | Frozen identity |
| --- | --- |
| Hosted run | [SalesSquad/junction-pets #43657058944](https://github.com/SalesSquad/junction-pets/actions/runs/43657058944) |
| Receipt run ID | `craci.43657058944.1.93edebd476b31661` |
| Artifact ID | `14139070947` |
| GitHub original artifact ZIP SHA-256 | `f2bed411c74bd99a4a622bd3ed1853a2542313ede8acc219b9f1d57c08729311` |
| Executed product HEAD | `78f1b9de566dedf9ba3800ebee60fffa8ed0cc4f` |
| Executed integrator/harness HEAD | `4874d15dd68d3a809aaf7d769d6b5bef85d378bd` |
| Frozen model SHA-256 | `82cfa42ba2240aff6d00ec3e2b15c06d78386d3c0682986a23e478977f2dbf9e` |
| Frozen plan SHA-256 | `8074f8f8978e2e55bdf201eeb9713888e44befe1d93856da44c1830bb86cfc48` |
| Original `training.json` SHA-256 | `cdc4d9d8729d61c730048c802579d25813dc45b55cf4e68d61d680840b7e7a2d` |
| Original `full_transitions.jsonl.gz` SHA-256 | `7e8d7c80cb8d035d904338e1a544662181a93933cc5c324458f7195c56f90b91` |
| Original paired readout SHA-256 | `2245497c68da38e12353a6f43846ec2a14ad527d57c42491084ada8581873fa5` |
| Final independent qualification SHA-256 | `a370a001a368d43ae8fb46847d73c6623ef692b290f0decbe94ba00018d15e88` |

The private original ZIP is **not checked into Git**. Its proposed durable
archive location is `iCloud Drive/Junction/CRACI/rokoko-v12-43657058944-github-artifact.zip`;
the copy to iCloud has **not been independently verified**. Do not treat that
path as evidence until byte equality to the ZIP SHA-256 above is confirmed.

The companion [`trajectory-sha256.json`](trajectory-sha256.json) is a **public
identifier/hash index only**: 48 `(seed, world_hash)` entries and 144 exact
`(seed, strategy, full_transition_sha256)` entries from the verified originals.
Its canonical sorted compact JSON SHA-256 is
`24460b2ed49635b33db66233dd854f84593e6f65484cde229ee17ec483dd0245`.
No raw 18D observations, masks, actions, private logs, or reward traces are
committed in this index. V13 can check deterministic regeneration against
these hashes; hashes **do not** establish unobserved action counterfactuals,
nor are they model training labels.

## Recomputed original outcome

| Contract / result | Recomputed value |
| --- | ---: |
| Consecutive fresh TRAIN public world scans, `518000..518511` | 512 |
| First-eligible observed near worlds / clear worlds | 40 / 8 |
| Distinct paired worlds / actual MuJoCo 3.3.7 episodes | 48 / 144 |
| Full public 18D observations + seven-option mask events | **4,228** |
| Safe true 250-tick goal outcomes: frozen V5 | **12 / 48** |
| Safe true 250-tick goal outcomes: V12 candidate | **12 / 48** |
| Safe true 250-tick goal outcomes: untrained RIGHT exploration | **12 / 48** |
| Candidate novel goal worlds / lost baseline goals / unsafe worlds | **0 / 0 / 0** |
| RIGHT exploration unsafe worlds | **0** |
| Actual executed RIGHT option 4 / distinct worlds / new goals | **31 / 31 / 0** |
| Executed option counts (0..6) | `[0, 66, 1388, 1037, 31, 107, 1599]` |

The three strategies succeeded on **the identical twelve seed IDs**:
`518000, 518001, 518002, 518004, 518005, 518008, 518011, 518019, 518024,
518054, 518090, 518098`. V12's recorded contact and lateral-motion indicators
improved in some trajectories (at least one contact: V5 38/48, V12 39/48,
RIGHT 43/48; recorded changed action traces in 31/48 worlds). Those are
**mechanistic signals, not new task success**. Action 4 was actually executed
only in the exploratory strategy on 31 near-worlds; 31 legal executions must
never be conflated with the much larger number of times option 4 was merely
available in the mask. It yielded no additional true goal.
Only **2/31** actual RIGHT4 worlds reached at least 25 mm of signed
obstacle-away object displacement; this is an observed per-world outcome, not
a learned counterfactual success label.

Science decision: **STOP — zero novel safe goal250 outcomes.** Do not promote
V12, treat these already-opened TRAIN outcomes as independent heldout
confirmation, or automatically dispatch the proposed `518512..519023`
confirmation cohort. A new physical mechanism with a
separately reviewed TRAIN-only preregistration would be needed to justify
further spending. All dev/cal/test/OOD splits remain sealed by the recorded
manifest. Provider bill is unknown; the hosted receipt explicitly lacks a
signed provider attestation.

## Reproduce the source-bound offline audit

Keep the original GitHub wrapper artifact ZIP and its extracted wrapper tree
in private storage outside this repo. A Python environment with NumPy is
required; no MuJoCo installation, GPU, provider credentials, or outbound API
calls are needed for this audit.

```bash
python3 -m unittest discover -s scripts/craci \
  -p test_audit_rokoko_mujoco_v12_pilot.py -q
python3 scripts/craci/audit_rokoko_mujoco_v12_pilot.py \
  /private/scratch/original-artifact.zip /private/scratch/extracted \
  --verify-trajectory-index \
  docs/craci/learning/rokoko-mujoco-v12-43657058944/trajectory-sha256.json \
  --output-summary /private/scratch/v12-original-recomputed.json
sha256sum /private/scratch/v12-original-recomputed.json
```

For the frozen original artifact, the canonical emitted summary SHA-256 is
`95e758a454bce9cdc806eddbf7d47daa2715b6bae069d5736fca46dea6d1d2f8`.
The output path must be new and outside the original evidence tree; the script
uses exclusive creation and refuses to overwrite source evidence. On any
identity, source-head, mask, 512-seed selection, trajectory-index drift,
event-chain, raw SHA, goal250,
unsafe/abstain, or result mismatch, the verifier fails closed.

### Receipt chronology and limitations

The earlier `paired-readout.json` was generated **before** hosted independent
qualification and contains `independentPhysicsReplayQualified: false`.
The later original `independent-qualification.json` reports
`full_144_real_episode_physics_replay.claim_verified: true`. These are
chronologically distinct receipts, not evidence that the offline auditor
executed physics. The script independently checks original bytes and replays
recorded public transitions, while the original hosted qualification is the
source for the separate real-physics replay claim. The packet preserves both
facts, all negative results, and the full original private trajectories.
