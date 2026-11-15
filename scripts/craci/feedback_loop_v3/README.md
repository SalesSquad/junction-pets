# CRACI Feedback Loop V3 — original-physics evidence to next training decision

**Work ID:** `CRACI-FEEDBACK-LEARNING-V3-20261115`  
**Status:** source-only, scientific **STOP**, no runner dispatch, no model promotion.  
**Integrator base:** [`SalesSquad/junction-pets` PR #186](https://github.com/SalesSquad/junction-pets/pull/186) at `4874d15dd68d3a809aaf7d769d6b5bef85d378bd`.  
**Frozen producer source:** `78f1b9de566dedf9ba3800ebee60fffa8ed0cc4f`.

This compiler ingests the **original hosted CRACI V12 ZIP**, not a rewritten
summary, then independently checks its wrapper/receipt, source and harness,
nested lossless raw originals, paired 144 actual MuJoCo episodes, all 4,228
original option transitions, 18D public shield masks, contact/dwell250, and
exact per-trial option hashes. It creates the deterministic checked-in file
[`next_training_decision.json`](next_training_decision.json).

The parent receipt records a succeeded CI job, **not** a qualified new model.
No simulated counterfactual action labels are treated as real physics.

## Original evidence and limits

| Boundary | Exact value |
|---|---|
| CRACI hosted workflow | [run 43657058944](https://github.com/SalesSquad/junction-pets/actions/runs/43657058944) |
| Original hosted artifact | [artifact 14139070947](https://github.com/SalesSquad/junction-pets/actions/runs/43657058944/artifacts/14139070947) |
| Original artifact ZIP SHA256 | `f2bed411c74bd99a4a622bd3ed1853a2542313ede8acc219b9f1d57c08729311` |
| Harness checkout | `4874d15dd68d3a809aaf7d769d6b5bef85d378bd` |
| Product source checkout | `78f1b9de566dedf9ba3800ebee60fffa8ed0cc4f` |
| `training.json` SHA256 | `cdc4d9d8729d61c730048c802579d25813dc45b55cf4e68d61d680840b7e7a2d` |
| `full_transitions.jsonl.gz` SHA256 | `7e8d7c80cb8d035d904338e1a544662181a93933cc5c324458f7195c56f90b91` |
| No DEV/CAL/TEST/OOD opened | Independently checked original source flags; no new splits read |

Measured goal250 scores: frozen V5 **12**, V12 candidate **12**, exploratory
RIGHT4 **12** across the **same** 48 paired TRAIN worlds. Candidate has **zero
novel goals, zero lost baseline goals and zero unsafe episodes**. These are
TRAIN-only pilot observations, not new independent validation. RIGHT4 was
really selected and permitted by the original public mask **31 times across
31 distinct worlds**, but produced zero new physical goal250 wins. Minimum
observed object-goal distance for still-failing V12 candidate traces was
**55.851 mm**, above the true goal threshold. All options were executed in
the prior hosted MuJoCo 3.3.7 run; this module launches **no physics**.

The older V10/V11 feedback is checked as a *historical source-reported safety
regression guard*: V10 raw SHA, 18/18 retained, 0 lost/novel/unsafe and no
model promotion. V3 does not falsely describe V10 raw as newly reverified.

## Why the next experiment is different

The decision lists four hypothesis families, ranked with original evidence
witnesses containing `seed`, `world_hash`, **1-based option index**, executed
`action`, original mask legality and individual transition SHA256:

1. Reopen **physical goal reachability before** an observed live-flag drop
   (for example seed 518003, action6 at option18 after option17). This is
   correlation, not a proof that the drop caused failure.
2. Probe **early live=True abstain** branches (e.g. 518013, action6 at option11)
   only where an alternate physical action remains shield-legal.
3. Prospectively test **RIGHT4 reachability** on fresh worlds, acknowledging
   the 31 observed executions are support, not positive effects or labels for
   unchosen actions.
4. Quantify **near-obstacle contact → lateral clearance → forward reopen →
   sustained 250-tick dwell** in real MuJoCo, not with proxy rewards.

For V13, the distinct new TRAIN-only scan cohort is **519024–519535 inclusive**
(512 seeds), selecting first **128 near** and **32 clear** public initial worlds.
This deliberately leaves optional V12 followup `518512–519023` untouched and
obeys the original `ContactEnv.reset` boundary: **seed >=520000 is invalid**.
No old physics guard is modified. The proposed 160 paired worlds × 2 arms =
320 real episodes exist **only as a frozen future experiment specification**;
none were run by V3.

Hard prospective acceptance: zero unsafe, zero losses of frozen V5 real goal250
wins, at least one novel physically verified *near* goal250, real contact and
dwell, exact source/fixture evidence and independent source review. A change
in exploratory TRAIN performance alone is never model-promotion authority.
For selective evaluation, do not use naive post-selection fixed 95% CIs as
confirmatory proof; later use untouched locked holdout or anytime-valid design.

## Reproduce locally without spending credit

Download the **original** artifact as an authorized collaborator and store it
outside Git. Verify the exact SHA above, then:

```sh
export CRACI_V12_ORIGINAL_ZIP=/absolute/path/to/original-github-artifact.zip
python3 -m unittest discover -s scripts/craci/feedback_loop_v3 -p 'test_*.py' -v
python3 scripts/craci/feedback_loop_v3/cli.py \
  --artifact "$CRACI_V12_ORIGINAL_ZIP" \
  --output /new/task-owned/path/next_training_decision.json
sha256sum /new/task-owned/path/next_training_decision.json
```

The producer creates output exclusively (`xb`); it will not overwrite the
existing decision. The checked-in bytes have SHA256
`f4c9f1c0b994d8c34cad0fcb63579c79f96439dedbfe6c12cb3df57b42fea79c`.
Tests require the original ZIP and include corruption, semantic fake-goal
after a recomputed transition hash, world-mask/cohort drift, V10 unsafe/lost,
forbidden DEV/CAL/TEST/OOD, original seed guard, source-bound witnesses and
byte-level reproducibility. Python standard library only.

No simulator, external model, GPU, API key, CI workflow, recurring controller
or paid runner is added. No provider cost is known; receipt-derived SHA256 is
not CRACI-signed attestation. The original artifact expiry is **not verified**.

**Operational stop:** the global 15 Nov 2026 17:00 UTC credit window remains
in force. This frozen source-only V13 proposal also expires for admission then;
its JSON says `dispatch_authorized:false` regardless of the clock. Only the
existing sole integrator may propose a new source-bound, budget-admitted run
after independent scientific review and fresh explicit authority.
