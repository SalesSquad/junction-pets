# Counterfactual Contact Gym — M3

Original headless CPU MuJoCo pushing experiment for work
`J26-ROKOKO-FORGE-M3-20261114`, based on
`84dceb0347771590035a7f973a264cb2a4540c7f` (M2 / parent PR #122).
Everything here is `SYNTHETIC_MUJOCO`; the invented glove-derived input is
`UNVERIFIED_REPLAY`. There is **no physical robot actuation**, glove connection,
licensed Rokoko SDK, real demonstration, verified GPU/NVIDIA adapter, OpenAI/Jev
inference, learned policy or sim-to-real qualification.

## Run

From the repository root (Python 3.11, Node for the existing M2 retargeter):

```sh
uv run --no-project --python 3.11 --with mujoco==3.3.7 python solutions/rokoko-teleoperation-gym/sim/experiment.py --seed 104 --trials 30 --output solutions/rokoko-teleoperation-gym/sim/reproduced-receipt.json
uv run --no-project --python 3.11 --with mujoco==3.3.7 python solutions/rokoko-teleoperation-gym/sim/physics_smoke.py
python3 -B solutions/rokoko-teleoperation-gym/sim/test_sim.py
python3 -B solutions/rokoko-teleoperation-gym/sim/decisions.py
```

Actual execution used `/tmp/rokoko-m3-venv/bin/python` with MuJoCo **3.3.7**,
NumPy **2.4.6**, Python **3.11.15**, macOS CPU; no viewer/rendering or GPU.
For the same numerical environment use `--with numpy==2.4.6` too. Wheel installation
initially failed sandbox DNS; the authorized network install succeeded. The native
physics path actually ran, so no kinematic fallback was substituted. Full Playground,
Isaac Sim, learned checkpoints and external inference were neither installed nor run.

`receipt.json` records final seeds, raw per-trial outcomes, platform/time, exact
base SHA, and SHA256 of executed source/scene/M2 inputs. Its execution HEAD is the preceding M3 source commit,
with its subsequently repaired working bytes bound by exact SHA-256 hashes.
The delivering fix commit binds the final code and receipt; it cannot embed its
own Git commit SHA in its content.
`pilot-receipt.json` preserves the first failed exploratory design (0/30 successes
for each comparator, one closed-loop fragility violation); its old script hash
is historical and its exact script is not retained. Two further exploratory runs
used offsets +20000 and +30000; their observed counts were 11/30 and 10/30
closed-loop versus 0/30 replay. They informed the audit, are development evidence,
and are **not** final holdout evidence. The initial +40000 split returned
10/30 versus 0/30 but an independent safety audit found that tracking recovery
was implicitly acting as an operator acknowledgement. After changing that safety
logic, a **new, frozen +50000 holdout** was run without tuning to its outcomes.
Previous +40000 metrics are historical, not final evidence. No broad CI suites were run.

## Historical M3 results before Anthropic review

Paired shifted holdout (30 scenarios per policy, 50104–50133), AFTER ACK repair:

| Metric | Open-loop replay | Object-centered |
| --- | ---: | ---: |
| Independent safe goal successes | 0/30 | 8/30 |
| Mean final ground-truth error | 0.147776 m | 0.087009 m |
| Trials with pusher/object contact | 19/30 | 30/30 |
| False sensor success claims | 0 | 0 |
| Fragility violations | 0 | 0 |
| Trials with object/obstacle contact (rejected) | 1 | 3 |
| Object workspace excursions (rejected) | 0 | 0 |
| Deadman-violating target updates | 0 | 0 |
| Human requests / actual takeovers | 2 / 0 | 22 / 0 |
| Distinct scripted synthetic ACK events / real humans | 26 / 0 | 26 / 0 |

Calibration split: replay 0/6, closed-loop 4/6 safe successes. The final experiment
ran 72 comparator episodes plus one always-released-deadman negative. Contact
smoke, damaging-impact negative, fixed-seed determinism and four contract tests
passed. The controller still fails **22/30** shifted tasks: this is a useful
counterexample generator with modest improvement, not a solved manipulation task
or statistical/real-world generalization claim. Occlusion HOLD, deadman release,
obstacle abstention, friction-dependent slip, lateral instability and goal
overshoot remain explicit failure modes. Raw trial data retain failures.

## API-reviewed M3.1 — fresh shifted cohort after safety corrections

The **50104–50133 result above and its original `receipt.json` are historical**.
The independent Anthropic API Sonnet/high code review on this earlier M3 source
cost **$0.2225865** (per-call $1.50 cap, separate from the $40 owner envelope).
It identified three medium and four low findings. Those were checked against code,
not blindly accepted. Source corrections now:

- Measure forbidden target/control changes **at the actuator command boundary**,
  with injected negative unit cases; a result of zero is no longer tautological.
- Enforce the observation-driven REPLAN and fail closed when a model requests
  unavailable human budget. Even a 100% confidence fixture cannot bypass bounds.
- Apply axis-specific actuator bounds and refuse invalid *proposals* without
  spuriously latching an already-safe position. Refusals are counted.
- Count one human-help request on transition, never every 20 ms tick. Requests
  remain pending with **zero actual person interventions**.
- Reject zero-length/missing demonstrations before trajectory normalization;
  keep cumulative XY progress and preserve the M2 original synthetic provenance.
- Use exceptions, not optimized-out Python `assert`, for compulsory contact/
  deadman evidence gates. No tests, thresholds or safety limits were weakened.

A new **paired and disjoint** 30-scenario shifted cohort was run exactly once
after these corrections, with synthetic seed IDs `60104–60133`.
The previous `50104–50133` cohort was NOT overwritten. The new receipt is
`receipt-anthropic-review.json`, containing exact source/input SHA-256 values.
Executed on the same local CPU MuJoCo 3.3.7 installation; **no learned RL policy**.

| Independently scored metric | Open-loop | Observed-object closed-loop |
| --- | ---: | ---: |
| Safe goal success | 0/30 | 5/30 |
| Final hidden ground-truth goal error | 0.149822 m | 0.106428 m |
| Episodes with pusher/object contact | 14/30 | 30/30 |
| Simulated damage events | 0 | 2 |
| Episodes with object/obstacle contacts | 0 | 6 |
| Episodes with object workspace excursions | 0 | 1 |
| Unsafe deadman command changes | 0 | 0 |
| Human-help requests, **not actual takeovers** | 0 / 0 | 11 / 0 |


### Independent scientific critique — baseline NOT qualified as comparative RL evidence

A second **read-only** Claude Sonnet/high Anthropic API call ($0.3023963)
identified a deeper baseline defect: a 20 mm-radius puck and 12 mm-radius
pusher require roughly 32 mm centre-to-centre contact geometry, yet the current
object-centred controller repeatedly targets only **25 mm behind the puck
centre**, potentially pressing 7 mm into it. Conversely, the open-loop pusher
finishes at x=**0.175 m**, already beyond the object-centre goal x=0.16 m
*without accounting for contact radii*. A zero-success open-loop baseline is
therefore potentially structurally disadvantaged. The 5/30 vs 0/30 numbers
above are **engineering diagnostics, NOT evidence of a better learned policy**.

Additional limitations: true simulated object XY is sampled as noiseless,
1 mm-quantised synthetic "vision"; obstacle map coordinates and occlusion flags
are artificial sensor conveniences; no actual force feedback is available to
the policy; HOLD may retain residual servo pressure on an object; the final
pose has no minimum dwell requirement, and "train" seeds trained no model.
The benchmark cannot validate robot performance, fracture safety, real HIL,
or model calibration. The first review fixed software guardrails, not these
research-design limitations. These observations are **not retroactive fixes**:
both raw receipts are intentionally retained.

**Next source-owned evaluation requirement:** first make the open-loop and
object-centred baselines geometrically feasible using the scene's *actual*
contact radii, add an observed pusher pose/force-proxy boundary, a compliant
release/retreat action and independent goal-dwell and unsafe-cost accounting.
Then freeze parameters on a development cohort and run a new, untouched,
paired and pre-registered holdout, with fixed adversarial shifts and a safe
abstain baseline. Only after that compare a **genuinely trained CPU option-value
learner** using held-out source-verified episode observations and explicit
synthetic intervention masks. Older offsets through +60000 are development
evidence and must not be silently recycled as sealed holdouts. NVIDIA Isaac
Lab, Google DeepMind Playground and live Rokoko SDK remain independently
unverified/unused.

Both Anthropic read-only calls together cost **$0.5249828** against the
owner's $40 maximum API consultation budget; the **remaining authorized
allowance is $39.4750172** at this bounded checkpoint. This is NOT a verified
balance on the Anthropic billing account. The API calls reviewed/advised on
code; **no Anthropic model controlled the simulated pusher or submitted
commands**.

**Important adverse result:** The closed-loop controller made
2 simulated fragile-object damage violations.
The existing toy impulse threshold (0.006 N·s per 2 ms step) is **not calibrated**
against real materials or a robot's safe forces. The success rate is limited and
the controller is **not safe for live actuation**. More physics/sensing experiments,
independent holdout evaluation and a genuinely learned baseline must precede any
real glove/robot adapter. Report these failures; never suppress them or treat
an API review as hardware qualification. External Anthropic inference was used
for **read-only analysis of this source**, never the motion controller itself.

## What is physically simulated

`scene.xml` defines gravity, tabletop, a **free dynamic cylindrical object**,
a static box obstacle, and a dynamic two-slide spherical pusher driven by
force-limited position actuators (3 N per axis). Each 20 ms observation/controller
tick integrates ten 2 ms MuJoCo steps, for six simulated seconds per episode.
There is no object teleport, virtual force assisting the object, prescribed object
trajectory, or object velocity reset. Initial object pose is set once at reset.
Object mass and inertia are scaled together before simulation.

Contact evidence uses MuJoCo's actual solver contact forces from
[`mj_contactForce`](https://mujoco.readthedocs.io/en/3.3.7/APIreference/APIfunctions.html#mj-contactforce).
The fragility proxy latches when **any object–pusher or object–obstacle contact**
exceeds 0.006 N s in a single 2 ms step (force norm × timestep). It excludes table
support force. This is a deliberately simple, timestep-dependent toy damage rule,
not a calibrated fracture/material model or cumulative impulse limit. It affects
**evaluation only**; controllers cannot observe breakage or hidden forces.

The final smoke checks two identical fixed-seed rollouts for exact equality,
requires nonzero pusher/object contact, and drives a deliberately violent negative
impact. On this executor: **1851 positive contact steps**, peak ordinary step
impulse **0.0028838383 N s**; negative impact **0.0281967222 N s**, above 0.006.
The always-released-deadman experiment requires zero pusher/object contacts and
zero deadman-violating target updates. Three standard-library tests cover latched
HOLD/rearm, hidden-state scoring negatives, request/response contracts and hostile
choices/probabilities. These are simulation/software results, not hardware safety.

## Demonstration and policy boundary

The runner invokes the **existing unmodified** `src/retarget.mjs` on
`fixtures/synthetic-retarget.csv` and `fixtures/retarget-map.json`; its exact
provenance is embedded. The three invented poses retarget to
(0.10, 0.10, 0.20), (0.11, 0.11, 0.20), (0.12, 0.12, 0.20) m.
Their normalized XY distance progress `[0, 0.5, 1]` becomes a synthetic planar
pusher target from x=-0.06 to +0.175 m over 3.3 s, y=0. This **rotates, stretches
and slows** a demonstration of progress, not an identified robot trajectory.
The task's object start near (0,0), goal (0.16,0), mass, friction and reward are
new synthetic assumptions, never supplied glove measurements. Grip and Z do not
control this two-axis pusher. No full 26-joint or contact retargeting is claimed.

Two original hand-coded comparators share scene, task, sensor cadence, safety,
velocity cap, intervention budget and **the exact same per-seed scenarios**:

- `open_loop`: replays that fixed target progress; object feedback only enters the
  common safety/decision gate, not its trajectory correction.
- `object_centered`: targets a point 25 mm behind the **observed** object along
  the goal direction; stops proposing changes near the observed goal. This
  intentionally crude contact controller can wedge, overshoot, or push sideways.
  It is **not RL, Q-learning, imitation training or an off-policy value model**.

The six `train` seeds 104–109 are a calibration/development split, with narrow
pose/friction variation and no occlusion/obstacle on the push route. No weights,
model or hyperparameters are fitted by this script. Holdout seeds **50104–50133**
are disjoint, paired across policies, and expand lateral pose to ±45 mm,
friction to [0.15,0.8], with mass [0.05,0.12] kg, independent box locations,
0/160/400 ms occlusions and deterministic deadman releases on seeds divisible by 7.
Table friction is 0.05 so MuJoCo's contact mixing does not mask low object/table
friction. Obstacle positions can produce difficult or initially overlapping
configurations; they are not filtered out after outcome inspection.

The policy receives only rounded millimetre object XY, observation age/quality,
deadman, target workspace status and distance to an obstacle in a known synthetic
map. The occlusion schedule, true object pose/velocity, mass, friction, seed,
contact force, damage and evaluator score never enter policy decisions. The
sensor itself samples ground truth as a **synthetic vision emulator**, not a
verified camera. Success is independently evaluated using hidden MuJoCo body
position within 20 mm, nonzero real pusher contact, no damage, no object/obstacle
contact, and no object workspace excursion. A stale or overoptimistic sensor goal
claim cannot award success. `false_success` explicitly compares claims to that
independent score. Unit negatives reject goal claims without contact, after
damage, outside bounds, or after obstacle contact.

## Safety, uncertainty and human budget

M1 intent is preserved locally: deadman release, poor tracking, age >120 ms or
invalid workspace latches HOLD; rearm needs two healthy ticks and an acknowledgement.
The simulation provides a **separate scripted synthetic ACK event two ticks
AFTER tracking restoration**, not an ACK derived from sensor quality itself;
there is **no real operator approval**. Without the independent scripted event,
the HOLD persists despite arbitrarily many fresh healthy observations. HOLD freezes the requested pusher target,
not simulator time or inertial motion; a position servo can still exert force at
the held target. This is emphatically not an emergency stop implementation.
The target speed cap is 0.08 m/s, far below M1's 1.6 m/s positional proposal limit.

The deterministic L2 decision baseline actually gates both policies using
`CONTINUE`, `REPLAN`, `REOBSERVE`, `REQUEST_HUMAN`, `HALT`. Missing/occluded tracking
abstains; a mapped obstacle within 45 mm requests human help then holds. Each
trial has **two request tokens**, zero simulated human/oracle takeovers; after
exhaustion a nearby obstacle yields HALT. Requests are events/ticks, not evidence
of operator participation. Low-confidence or malformed optional model answers
abstain. Deadman/workspace/tracking rules take priority even over a model's
confidence=1 answer. The primary experiment uses the local deterministic
baseline only; it does not consume invented model probabilities.

## Offline Decisions fixtures and downstream adapters

`decision-fixtures.json` has REDACTED **unsent** requests and invented one-hot
`OFFLINE_STUB` responses for:

- OpenAI `POST https://api.openai.com/v1/decisions`, model `gpt-6-luna`:
  `input` plus named typed questions and value/description choices, per the
  [official guide](https://developers.openai.com/api/docs/guides/decisions).
- OpenRouter `POST https://openrouter.ai/api/alpha/decisions`, model
  `typesafe/jev-1.13`: observed `state` plus keyed choice criteria, verified
  against [OpenRouter's source contract](https://github.com/OpenRouterTeam/skills/blob/main/skills/openrouter-decisions/scripts/lib.ts)
  and [TypeSafe's primitive guidance](https://docs.typesafe.ai/introduction/quickstart).

`decisions.py` strictly validates this deliberately narrow request contract,
allowlists observations, normalizes/validates both answer excerpt shapes, rejects
unknown choices, NaN/non-normalized distributions and hidden-state fields, and
has no HTTP client, key read or send path. Wire responses are **excerpt fixtures**,
not complete provider envelopes; their request IDs, usage and provider metadata
are intentionally absent. Live API acceptance, model calibration and model
performance are unverified. No invented probabilities are model scores.

Isaac Lab can later adapt bounded target proposals and observed states to a
verified robot scene; it must separately establish joint mapping, collision
geometry, licenses, real-time stop semantics and calibration. Jev/OpenAI can later
advise L2 selection without acquiring actuation authority. Neither adapter is
implemented or connected here.

## Research inspiration, not reproduced algorithms

Sources inspected 14 November 2026; **no third-party source code, asset or model
was copied**. This is an original small counterfactual benchmark, not an
implementation or claimed result of these projects:

- [REGRIND](https://github.com/yunhaif/regrind): motivated object/contact-relative
  references; its residual RL and Isaac stack are not used.
- [Human2Sim2Robot](https://github.com/tylerlum/human2sim2robot): motivated treating
  one demonstration as task guidance rather than requiring exact replay.
- [Q-Planning](https://q-planning.github.io/): motivates future learned value-based
  selection among alternatives; **no Q estimator or trained planner exists here**.
- [gym-hil](https://github.com/huggingface/gym-hil): motivated explicit intervention
  accounting; no human intervention or HIL training was executed.
- [DexMachina](https://mandizhao.github.io/dexmachina/): motivated evaluating object
  outcomes independently from hand tracking; no decaying object assistance is used.
- [FlashDexRetarget](https://github.com/Holiday-Robot/FlashDexRetarget): suggests
  future multi-reference learning; this three-point progress path is not such a model.

Use native [MuJoCo Python](https://github.com/google-deepmind/mujoco), not old
Playground JAX recipes or a claim of current Playground compatibility. SDK, GPU,
NVIDIA, Jev/OpenAI, real glove/robot, and trained-policy qualification remain open.
Costs are **unknown**; no paid GPU, provider API or external model call was made.
