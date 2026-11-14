# M6 observed-map detour experiment

Work J26-ROKOKO-M6-PATH-REPAIR-20261114. Parent source
59479b42b177c1829a2e6678adfff1fb68aef09c. Only this directory is new.
The original M5 environment, seven option names, 18-feature observation,
MuJoCo XML and historical evidence remain unchanged. Reads original scene
radii (12 mm pusher, 20 mm puck), 18 mm obstacle box half-width and M4 QA's
32 mm contact geometry. Uses installed native MuJoCo CPU, no models or hardware.

`planner.py` consumes only observations. It inflates the observed obstacle box
by body radius plus 21 mm (3 sigma map noise), uses conservative segment/box
intersection and body-radius workspace bounds, and enumerates straight plus
both mirrored lane routes. Each detour has at most three intermediate points.
A route is a geometric candidate, not contact feasibility or execution proof.
Nonfinite/unhealthy/blocked observations reject productive actions and request
human help through terminal abstention. Gaussian tails beyond 3 sigma remain
possible: this is no guaranteed safety bound. Object observation noise, inertia,
slip and servo tracking error are not robustly bounded by this planner.

The original seven options become waypoint-relative skill primitives. At most
5 Hz, ALIGN/approach reposition behind the puck relative to the next temporary
lane; slow push steers toward it, then toward the goal. At every 50 Hz update,
the independent filter checks the whole pusher-centre segment from actual pose
and previous target to the proposed target before accepting it. Full proposed
option segments are also checked. No global object-to-goal veto. The copied
integration loop never calls unrestricted parent `step`. Sensor/HOLD/deadman,
synthetic acknowledgement budget, 0.006 Ns damage proxy, obstacle collisions,
workspace termination, 250-step success dwell and contact requirement are
unchanged. HOLD retains the previous position servo target and may exert force;
it is not E-stop. A refused mid-option proposal retains the old target until the
next decision; this residual pressure can still terminate unsafe.

## Reproduce

From repository root, using only the installed interpreter:

```sh
/tmp/rokoko-m3-venv/bin/python solutions/rokoko-teleoperation-gym/detour/test_detour.py
/tmp/rokoko-m3-venv/bin/python solutions/rokoko-teleoperation-gym/detour/evaluate.py --count 20 --out /tmp/rokoko-new-dev-run
```

Fixed developer cohort: 150000..150099. Reserved untouched holdout:
450500..450599 (`--cohort holdout`), not executed here. No tuning on it.
Paired methods reset identical OOD worlds, sensing, ACK RNGs and 60-option
limits. Original uses its own global shield and original heuristic; detour uses
new shield AND waypoint heuristic. This is a combined intervention comparison,
not RL improvement. Abstain uses original physics and always requests abstain.
No DQN weights were loaded or trained. All contacts and outcome scores are
outcome-only; no true mass, friction, obstacle pose or forces enter planning.

## Actual bounded result: improvement NOT established

Seven focused tests passed, including deterministic native-physics replay with
nonzero object contact, mirrored route clearance, obstacle offsets, uncertainty
negative, HOLD/deadman target rejection and planner input boundary.
`evidence/dev20/receipt.json` and CSV preserve the actual initial source hashes,
dirty state and all 60 same-seed episode outcomes. They were executed before the
local commit; the parent HEAD plus hashes binds the dirty implementation bytes.
Compare producer hashes against the delivered commit, not HEAD alone.

20 OOD developer seeds per method: original 1 success, 0 unsafe, 15 abstentions;
detour 1 success, 0 unsafe, 5 abstentions; safe-abstain 0 successes, 0 unsafe,
20 abstentions. Lower abstention is not success. Remaining episodes time out or
hold; no safe-success improvement demonstrated, and 20 worlds cannot establish
risk noninferiority. Historical M5 metrics were neither rewritten nor rerun.
`human_requests` counts episodes ending held or abstained, a synthetic proxy;
ACKs remain synthetic. Collision/workspace telemetry samples option boundaries
(including immediate unsafe exit); `unsafe` is the authoritative per-physics-step
latched composite, and damage uses the latched peak impulse. No real human or
provider acceptance claim. Initial candidate count is geometric coverage only.

Next experiment: inspect developer trajectories for lane-switch alignment and
pusher reposition failures, then freeze an explicit staged lane state machine
with bounded tracking error before admitting a fresh paired cohort. Do not
interpret route generation or fewer abstentions as solved blocked OOD worlds.
Physical-device performance, contact-force policy, calibrated fragility,
statistical safety, GPU/DQN and external independent critique remain unverified.
