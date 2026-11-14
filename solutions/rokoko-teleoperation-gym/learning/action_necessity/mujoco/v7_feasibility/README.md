# V7 — train-only MuJoCo contact/action feasibility

V7 is a **controlled feasibility experiment**, **not** a promoted controller, reinforcement-learning performance claim, or environment change. The frozen V6 source is PR #183 at `0fcf7fe87e6169aa383807ec8616cc6f98694aca`. The actual V6 CRACI run `43637420554` (artifact `14131030766`) was scientifically red: all six trained candidates won zero of 13 observed-corridor training worlds; the selected V6 lost one clear-baseline success in fresh dev. Preserve that negative result.

## What this measures

- Actual MuJoCo **3.3.7**, unchanged 18D observations, 7-option `env.mask`, health/deadman, reward/cost/contact/physics and `ContactEnv.reset` seed bounds. Option `5` is a real **RETREAT** servo motion, not a passive HOLD.
- First **128** near-corridor and **32** clear worlds selected from a contiguous public-observation-only scan starting at train seed `512000`, at most 512 seeds; near iff `abs(initial_observation[7]) < 0.122`. Every scanned seed, first public observed obstacle-y and pretrial world hash is retained in `training.selection_scan`; no result-based selection or hidden-world privileged information at inference.
- Eight source-frozen strategies **on each of the same 160 selected worlds**, 1,280 fully paired trials: frozen actual V5 weights; frozen actual V6 weights; repeated LEFT/RIGHT; ALIGN→LEFT/RIGHT; RETREAT→LEFT; observed obstacle-side branch. Six exploratory macro strategies obey the unchanged mask and use only public observations plus own past actions.
- Record full per-option observation (18), mask (7), actual option, reward, safety cost, terminal state, `success_info` from actual physics, cumulative actual physics contacts (`contacts_cumulative` from step info) and next observation. Verify contacts monotonicity and final total. Physics `env.dwell` is a **consecutive near-goal counter that resets on exit**; preserve raw `dwell_ticks_current` from `env.dwell` per option and a monotone running **peak** as `dwell_ticks_cumulative` for an independently checkable upper envelope (not a raw cumulative elapsed-ticks claim). Terminal success must match `success_info`, require current dwell ≥250, real contact, positive physics steps, public observed object-to-goal distance below .025m and no unsafe/ABSTAIN. `lateral_displacement` is **signed obstacle-away object progress** in meters, recomputable solely from first/last public object-y and first public obstacle-y (`-Δy` when obstacle is above the object, `+Δy` otherwise); negative is toward-obstacle movement, never a success. Include forward-mask reopening and contact→forward→dwell evidence. No oracle seeds, privileged object physics, direct actuator, disabled shield or dev labels.

## Exact command

Run in a clean checkout of the **exact new V7 Git HEAD**, descended from the frozen V6 commit:

```bash
python3 solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v7_feasibility/run.py \
  --mode train-feasibility --require-git --expected-head FULL_40_HEX_V7_HEAD \
  --max-seeds 512 --time-budget-seconds 1200 --output-dir /new/empty/v7-output
```

Source SHA mismatch, tracked-source dirt, ancestry mismatch, forbidden seed ranges, incomplete cohort, time budget, missing real MuJoCo 3.3.7 or any unmasked option are **fatal**. Use a fresh or existing empty output directory; no overwrite. A completed experiment exits `0` even if all eight strategies fail, because that negative is material feasibility evidence. An interrupted/incomplete trial sequence never qualifies.

## Evidence contract

| File | Meaning |
| --- | --- |
| `training.json` | Exact V7 source HEAD; all scanned public observed worlds; selected 128+32; all 1,280 paired trials, source/frozen-model digests; exact sparse transition samples and `dataset_sha256` (SHA256 over canonical sorted-key compact JSON of `trials`). |
| `full_transitions.jsonl.gz` | One gzip JSON line per trial: `{ "seed": int, "strategy": name, "transitions": [all actual per-option objects] }`. Each trial's `full_transition_sha256` verifies canonical sorted-key compact JSON of its **full** transition list; `full_transition_count` is exact. |
| `manifest.json` | Exact physical file-byte SHA256 for `training.json` and compressed JSONL, source/run identity; auxiliary receipt digests. |
| `qualification.json` | **Advisory only:** corridor safe successes, contacts, lateral progress, ABSTAIN and per-strategy failures. It never authorizes promotion. |
| `next_experiment.json` | Proposal only. If no safe near successes, request separately reviewed physics/primitive investigation; do not silently modify the frozen environment. |

Sparse indices are `sorted(set(range(min(12,n))) | set(range(max(0,n-8),n)) | set(range(0,n,5)))` and contain the original complete transition objects, preserving a compact independently checkable training receipt. Only training seeds `512000..512511` are touched. Future training cohort `513000..513999` is a **proposal**, not automatically opened. No dev, calibration, test or OOD evaluation is performed. Reviewer and separate integrator must qualify both source and raw gzip receipts before **one** authorized CRACI run.

## Caveats and decision

Success in these training worlds would establish only a physical mechanism within the sampled synthetic MuJoCo model; independent, previously sealed dev/generalization and safety qualification would remain pending. **Zero successes does not prove a mathematical impossibility**. It indicates the eight preregistered bounded safe policies have not demonstrated a viable route with the unchanged option primitives; investigate contact geometry or propose a *separate explicit environment version* rather than further posthoc dev threshold tuning.

Portable contract checks without MuJoCo:

```bash
python3 -m unittest discover -s solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v7_feasibility -p test_contract.py -v
```

Production run costs, credit utilization and remote provider usage remain **unknown** until independent execution receipts; this code does not dispatch or bill CRACI itself.
