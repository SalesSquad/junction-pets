# V13 sustained RIGHT4 contact hypothesis — research source only

Work: `J26-CRACI-V13-RIGHT4-CONTACT-20261115`.
Parent: `c77158f9ae80acc2b1eafaf9284c4397426799b2`.

The previous 520000..520511 proposal was invalid: the original frozen environment
requires `120000 <= seed < 520000`. This new, separately pinned plan uses only
519024..519535, excluding executed V12 518000..518511 and reserved followup
518512..519023. The owner-supplied independent MuJoCo 3.3.7 preflight reports
512 unique resets, public 18D observations, original 7-mask, 178 near and 334
clear. Its path and SHA256 are recorded in the plan as **preflight only**; this
source task neither reran nor authenticated that external report.

Prior V12 history supplied by the owner: 144 real episodes, 31 single RIGHT4
executions; V5, V12 and RIGHT4 each achieved 12/48 safe goals, zero novel goals.
That result does not establish this different burst hypothesis. No V13 physics
results, training results, or device safety claims are provided here.

## Fixed experiment and APIs

`v13-plan.json` fixes all source hashes, 512 ascending fresh TRAIN seeds, the
first 40 near (`abs(initial_public_observation[7]) < .122`) plus first 8 clear
worlds, merged in ascending seed order. It fixes 48 worlds × four strategies =
192 trials, world-major with V5 first:

1. `frozen_v5`: original frozen V5 factory.
2. `v12_phase_dwell_supported_actions`: original V12 `policy_factory`.
3. `train_only_right4_burst2`: V13 burst factory with length 2.
4. `train_only_right4_burst4`: V13 burst factory with length 4.

`policy.right_burst_factory(frozen_v5_factory, model_path, burst_length: int)`
returns an episode policy factory. Use a **new instance each episode**. It loads
and verifies the original V12 model and imports original V12 policy by a unique
source module name, checking its source hash before executing it. There is no
`import policy` collision with V5. It reuses original `gate_input`, `public_abi`
and `checked_action`; action4 weights are never scored or trained.

The initial gate must persist for the original frozen `min_streak`. Each
consecutive burst step again requires the public gate and original mask4.
Completion resets V5 before its next decision; gate/mask loss aborts the burst,
resets V5 immediately and returns its checked fallback. A used or aborted burst
cannot restart. Illegal original V5 output raises a contract STOP. The harness
must stop immediately for wrong/unsafe execution; the policy has no privileged
simulator safety sensor and accepts only public observation/mask.

`protocol.load_plan(path)` validates exact plan bytes and original V12
policy/model/plan hashes. All plan-taking APIs also reject modified in-memory
plans. `derive_cohort(all512, plan)` requires the complete ascending scan and
unique public signatures/world hashes; it never selects using outcomes.

`paired_physical_goal_readout(trials, cohort,
all_512_initial_public_worlds, plan)` rederives the cohort and rejects incomplete,
duplicate, shuffled, mismatched or malformed evidence. Each trial has exactly
the `trialFields` in the plan. `contact_dwell_ticks` means actual original
MuJoCo ticks dwelling under the contact goal, never option count or predicted
dwell. `contacts` is an actual contact count; `final_error_m` is actual final
object-to-goal error. Success must equal the conjunction of >=250 contact dwell
ticks, contacts >0, final error strictly <.02m, no unsafe and no abstention.
Inconsistent claimed success raises STOP rather than counting as a goal.

Any unsafe in any arm, any V5 safe goal lost by any other arm, or zero novel
burst-arm safe goals yields `STOP`. A supported-V12-only novel goal cannot
rescue zero burst novelty. Even positive accounting permits only
`REVIEW_PRELIMINARY_TRAIN_ONLY`: promotion, heldout/DEV/TEST/OOD access,
device safety qualification and independent replay qualification stay false.

This protocol validates evidence consistency, not the truth of simulator
measurements or chronological execution. A separate original-physics harness
must retain full original masks/options/ticks, enforce V5-first execution and
immediate safety stops, authenticate measurements, and independently replay
positive near/clear cases. A forged internally consistent numeric record cannot
be authenticated by this source-only reader. No dispatch is authorized here.

## Targeted verification

```sh
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/private/tmp \
/private/tmp/rokoko-v12-safety-venv-20261115/bin/python \
solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v13_right_dwell_exploration/test_v13.py
```

Fake fixtures only: source pins, 2/4 burst bounds, per-step masks/gates, reset,
contact thresholds, evidence order/completeness/duplicates, loss-plus-novel STOP,
unsafe and zero-novel STOP, and no promotion. No heavy physics, external model,
training, dispatch, network, merge or release occurs in these tests.
