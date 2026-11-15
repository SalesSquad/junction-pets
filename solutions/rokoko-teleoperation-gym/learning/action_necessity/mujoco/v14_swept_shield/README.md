# V14 candidate — public 18D predictive swept-obstacle veto

**Research-only, source-only, no physics result or model promotion.** WorkID
`CRACI-V14-SWEPT-PREDICTIVE-SHIELD-20261115`. Base product source
`0751d78b93855bf70820b03b0a543e123d218baf` (draft V13 PR #241). This
versioned folder changes **nothing** in `physics.py`, `env.py`, V13 search,
original seven-action shield, hosted workflow, or original unsafe thresholds.

## Why this candidate exists

The source-bound, hosted V13 TRAIN diagnostic [run #43660619725](https://github.com/SalesSquad/junction-pets/actions/runs/43660619725)
was deliberately stopped by `V13_REAL_PHYSICS_UNSAFE` after 23 branch rollouts
and 394 original physical option events. The first and only reported unsafe
event was seed `518006`, global branch `22` (journal branch ID
`v13-seen-train-518006-16`), zero-based option `37`, original-mask-legal
`PUSH_MEDIUM` (`2`), `cost=1`, `done=true`; original transition SHA-256
`4702034192e3877e42278a1b297e9b8c787955fbe2a30e411dd06fd9a7fee4ba`.
The public/noisy measured obstacle-to-object gap fell from 72.47 mm to
24.98 mm over that option. That does **not** identify the physical unsafe
mechanism: source `MovingContactEnv.step` marks unsafe for impulse >0.006 N·s,
obstacle contact, **or** body XYZ bounds, and the journal omits contact identity,
peak impulse, exact obstacle pose and Z coordinates. Cumulative contacts are
*not* a safety cutoff. V13 retained a deliberately **INCOMPLETE_STOP** record;
downstream independent full-physics replay/qualification was not run, so this
must not be counted as a policy success, certified unsafe root cause or
independently qualified physics finding. Do **not** rerun that seed/branch.

The original `mask()` is a current-observation legal-action filter, **not** a
future physical safety proof. A moving obstacle can approach during one
`10 servo × 10 MuJoCo integration × 2 ms = 0.2 s` option. This candidate tests
whether a much more conservative pre-action swept-envelope veto could reject
an apparent approaching hazard *before* executing an originally legal motor
option. Its one known-hazard **synthetic regression fixture is not a held-out
evaluation or evidence of efficacy**. There is no prospective test/OOD access.

## Pure shadow + opt-in advisory fork API — baseline V5 untouched

```python
from guard import decide, propose_one_fork

# Only the original 18D public floats, original seven mask bits and previous
# PUBLIC positions are admissible. No seed/private future states are inputs.
shadow = decide(public18d, original_mask7, requested_action=2,
                previous_public18d=previous_public18d)
would_veto = shadow.would_veto_requested  # a shadow observation, NOT a command
evidence = shadow.log_record()           # deterministic JSON-compatible dict

# Product DEFAULT: the original frozen V5 action is returned unchanged.
baseline = propose_one_fork(public18d, original_mask7, baseline_action=v5_action)
assert baseline.baseline_action_unchanged == v5_action
assert baseline.experimental_action_advisory_only is None

# Optional source-only research proposal: only at a PUBLIC V5 early legal
# ABSTAIN trigger, and only with explicit research opt-in. Never executes.
proposal = propose_one_fork(public18d, original_mask7, baseline_action=6,
                            opt_in=True, experimental_action=2)
assert proposal.baseline_action_unchanged == 6
suggested = proposal.experimental_action_advisory_only  # may be None: vetoed
assert not proposal.external_execution_authorized
```

This is an **offline shadow candidate API**, not a wired controller. The
`decide()` function emits **no executable action at all**. Its hypothetical
`shadow_fallback_action` annotates original-mask ABSTAIN (`6`) or `None` if
the original mask forbids ABSTAIN; it is **not** a replacement command.
`suggested_motor_actions` are advisory, not automatic lateral or retreat
moves. `propose_one_fork()` always preserves the original V5 action in
`baseline_action_unchanged`. When `opt_in=True`, it can name **one** advisory
counterfactual motor only at the V13 source-defined PUBLIC
`EARLY_LIVE_ABSTAIN` trigger: original V5 intended ABSTAIN, current public
`live=True`, `held=False`, and some motor option in the **original** mask is
legal. It never reads V5 success labels, seeds, private mover state or future
observations. If no public trigger, no opt-in, or the candidate vetoes, there
is no experimental proposal and V5 stays unchanged. A future external host
would have to independently enforce a one-fork-per-world budget, fresh public
original-mask admission and authorization; **none exists here**. No motor
command is ever executed by this package. Invalid inputs raise `ValueError`:
a caller must send **no** motor command. HOLD and RETREAT are moving/servo
semantics, not E-stops.

The veto is additive and can only reduce original allowed motor actions. It
cannot enable an originally disabled action or relax the original underlying
unsafe predicate, whose logic remains wholly unchanged.

## Auditable conservative geometry (not a certificate)

From the source `moving_scene.xml` and `physics.py`:

| Parameter | Used | Provenance / limitation |
| --- | ---: | --- |
| Moving obstacle amplitude ceiling | 0.045 m | Source-wide **OOD maximum**; never use the hidden OOD flag, world seed, amplitude or phase |
| Frequency ceiling | 1.0 Hz | Source-wide OOD maximum; same bound in TRAIN |
| Max speed | 0.283 m/s | `2π × A × f`, conservative derivative bound |
| Horizon | 0.200 s | At most 100 original 2 ms integration steps per option |
| Obstacle swept displacement | 0.0565 m | Product of max speed × horizon; isotropic cover is conservative for Y-only source motion |
| Obstacle box XY half-width | 0.018 m | Circumscribed disk radius `√2×0.018` |
| Object cylinder / pusher sphere radii | 0.020 / 0.012 m | Source MuJoCo scene |
| Mapped obstacle / object sensor σ | 0.005 / 0.0015 m | Source `_sense`, but Gaussian noise has **unbounded tails** |
| Sensor confidence margin | 3σ | Heuristic quantile, not a deterministic bound |
| Object motion / pusher tracking slacks | 0.020 / 0.005 m | Candidate **assumptions**, NOT proven dynamics bounds |

For each of the six motor options, compute its approximate original desired
pusher target from the **current public** object/pusher coordinates and public
goal, then test both object-to-obstacle and pusher-path-to-obstacle separation
against the expanded obstacle tube. The candidate has no true pose, hidden
servo target, contact data, forecast oracle, phase, seed or future observation.
The optional previous public frame is used **only** to flag inconsistent
observed map motion; it never shrinks the global possible-mover tube. Public
deadman, hold, low quality, staleness or out-of-bounds input aborts motor.

The numeric expansion intentionally includes the source's broadest OOD mover
bounds even though only previous TRAIN evidence exists. Thus it may abstain
excessively. It may still miss hazards because object/pusher motion slacks are
not proven physical reachability bounds, sensor noise is unbounded, contact
impulse may be unsafe without any obstacle, and physics can deviate from
endpoint approximations. **Do not call it safe, trained, validated on OOD or a
robotic safety layer.** It is a falsifiable candidate for future independent
study, not a certified guarantee.

## No-spend check / future qualification

Run from this folder on a normal Python 3.10+ stdlib runtime:

```sh
python3 -m unittest -v test_guard
```

The tests are deterministic synthetic input checks: original-mask monotonicity,
deadman/held/stale veto, benign current geometry, moving hazard geometry,
pusher path risk, conservative OOD constants, history uncertainty, no automatic
lateral/retreat motor substitution, deterministic provenance, invalid-input
fail-closed. They do **not** import or run MuJoCo, replay any V13 seed, read
private artifact data, spend CRACI/Verda credits, train or estimate efficacy.

### Already-seen V12 retrospective shadow audit — **negative result / STOP**

The optional read-only `shadow.py` consumes a *locally held* V12 artifact ZIP
verified against GitHub original [workflow #43657058944](https://github.com/SalesSquad/junction-pets/actions/runs/43657058944)
(outer SHA-256 `f2bed411c74bd99a4a622bd3ed1853a2542313ede8acc219b9f1d57c08729311`;
raw trace SHA-256 `7e8d7c80cb8d035d904338e1a544662181a93933cc5c324458f7195c56f90b91`).
It consumes the original *already-seen* 48 TRAIN worlds × 3 original arms,
4,228 previously executed options. It computes only what the new public-only
candidate **would veto** at each original public decision; it does not run
physics, simulate the modified future, create a new outcome or infer efficacy.

```sh
python3 shadow.py --artifact /path/to/existing/verified-v12-artifact.zip
```

| Original seen TRAIN arm | Shadow motor vetoes | Original winning V5 worlds whose trace would be interrupted |
| --- | ---: | ---: |
| Frozen V5 baseline | **513 / 821** motor options | **12 / 12** |
| V12 phase/dwell | 727 / 1,047 | 12 / 12 (same frozen winning paths) |
| RIGHT4 exploration | 449 / 761 | 12 / 12 (same frozen winning paths) |

On V5's 12 originally successful trajectories a hypothetical **unconditional**
enforcement of the candidate veto would suppress **112 of 364** original
motor options; on the full V5 cohort it would affect 44 of 48 worlds. This
is an **unacceptable potential completion-regression signal** even though the
true counterfactual success rate is unknown. The actual V14 default is
**shadow-only with exact V5 baseline preservation**, avoiding those automatic
changes. The one-fork research proposal is gated to public early legal V5
ABSTAIN and is never an executable motor command. **STOP any paid prospective
V14 run or promotion of this conservative candidate.** Preserve the negative
result. A separately preregistered follow-up should investigate reducing
unproductive abstentions without opening original forbidden actions, editing
past safety evidence, or treating these already-seen worlds as a held-out test.
No raw original ZIP, observations, world trajectories, or derived per-world
records are added to Git.

Next gate (a **separate reviewed/authorized later experiment**): independent
source and input-schema review; pre-registered independent fresh TRAIN physics
qualification with paired original-mask replay and sealed evidence; then
separately justified DEV/CAL/TEST/OOD boundaries and empirical regressions for
false vetoes, unsafe physical contacts, deadman and regret. Retain all raw
failures and stop on any unsafe or drift. Without this, promotion is **STOP**.
