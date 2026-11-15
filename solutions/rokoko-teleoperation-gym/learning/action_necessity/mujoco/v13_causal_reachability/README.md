# V13: finite, causal reachability diagnostic — TRAIN only

**Decision: source-only research, NOT a model, qualified physics result, deployment or promotion.** WorkID `V13-CRACI-LEARNING-20261115`. This additive, versioned folder leaves V5–V12 source, original physics/7-option shield, CRACI workflow, costs and evidence untouched. It creates no background jobs, paid dispatches, PR automations or workflows.

## Why this experiment exists

Frozen V12 hosted original-source MuJoCo pilot (job `43657058944`, 48 paired **previously seen TRAIN** worlds, 144 actual runs, 4,228 actual options) yielded **12/48 V5 safe 250-tick goals, 12/48 V12 goals, 12/48 RIGHT4 probe goals, 0 novel, 0 lost, 0 unsafe**. STOP: no promotion. The three final dwell histories were identical because 12 winning V5 trajectories were frozen; changes were on 31 failed worlds. All 36 failures recorded dwell zero. Within these: 26 V5 runs ended by a legal early ABSTAIN while `live=True`; 10 had the original exogenous deadman `live=False` at option 17, and original mask then permits only option6. **35/36** observed near-obstacle corridor. The exploratory RIGHT4 arm had 31 exact public-state/mask/prefix matched interventions, with only a weak and mixed mean public one-option goal-progress gain (+0.624 mm), no success.

This disproves the prior *hypothesis that forward-mask reopening / side actions alone will increase actual 250-tick goals on those worlds*. It does **not** prove overall unreachability or lack of learnable policy. We test finite original-physics reachability at public, action-legal pre-release forks, before fitting another policy.

## Immutable original evidence and constraints

`forensic.py` only reads SHA-pinned, fully retained source-report and independently replay-qualified **original V12 ZIP**. It checks original source HEAD `78f1b9de566dedf9ba3800ebee60fffa8ed0cc4f`, harness `4874d15dd68d3a809aaf7d769d6b5bef85d378bd`, source run, 512 public initial scans, rederived first 40 near + first 8 clear, exactly 144 full original 18D/7-mask traces, 4,228 executed options, all original SHA/receipt/qualifier/proof hashes, and negative science STOP. No fake output qualifies. A harness may instead regenerate these 144 from exact pinned original MuJoCo source and compare **all 144 complete trace hashes** to the audited source hash index before setting the identical source-bound `independentReplayQualified` provenance; a self-asserted flag alone is never sufficient.

Original release/mask/physics are never patched. Every counterfactual branch calls original `MovingContactEnv.reset(seed)` then **replays the complete identical original action prefix**. It compares original public observation18, mask7, reward, done, contacts, cost, original dwell, next public observation and world signature at each step; failure aborts. `mj_copyState`/`mj_copyData` alone is **not** used: original Python sensor RNG, mutable model geometry, motion phase, servo target and deadman state sit outside generic integrator state.

Candidates choose actions only from current original 7-mask and public18D; public `live=False` means no motor command, ever. No private phase, hidden physics, reward, failure label, source seed or future outcome enters the live action choice. Original 0.006 impulse/obstacle safety and 250 actual MuJoCo tick within20mm with physical contacts and zero unsafe are unchanged.

## Frozen finite diagnostic design

- **Selection**: only 36 known V5 *failed* V12 TRAIN worlds; 12 V5 winners remain untouched. These seen worlds may inform a *TRAIN diagnostic*, never unbiased performance estimates. First causal fork: the first original live, mask-legal early ABSTAIN (26) or fixed prefix index5 before documented option17 deadman release (10).
- **Interventions**: original-shield legal 7-option actions, maximum depth3; deterministic public-only heuristic beam width2; deterministic full continuation up to original 60 options for finite witness attempts. At most20 branches per world,720 total, and1200 seconds recommended host deadline. No fishing/repeated winner selection.
- **Proof**: one fully recorded branch with actual original `info.success`, contacts>0, dwell>=250, no unsafe => `WITNESS` for that one *seen TRAIN* world. Otherwise `NONE_REACHABLE_WITHIN_FINITE_BUDGET`, **never** universal impossibility. Any observed unsafe immediately stops the diagnostic, retains complete partial evidence; no threshold relaxation. A deadline is incomplete, not negative.
- **Retention**: the callable `on_branch(branch)` is invoked synchronously after **each complete real replay** before any further branch, so a hosted append-only fsynced journal can preserve earlier evidence even if later replay fails. The callback cannot influence selection; if journal writing fails, the run fails closed. Host must preserve incomplete/unsafe output and original per-option branch traces; never label incomplete as 720/720 or qualified.

### Python callable ABI for an independently reviewed hosted harness

```python
import causal, forensic, protocol

# Preferred: original immutable fully source-proven ZIP and receipt.
source = forensic.load_original_v12(archive_dir, receipt_path)
diagnosis = forensic.source_failure_diagnosis(source)

# Independently verified original source checkout (MuJoCo==3.3.7):
# env_factory=original physics.MovingContactEnv
# world_signature=original original v7 _world_signature
# The callback appends each branch immediately to a lossless private journal.
readout = causal.run_budgeted_diagnostic(
    source, env_factory, world_signature,
    max_depth=3, beam_width=2, max_world_branches=20,
    deadline=monotonic_deadline, on_branch=append_and_fsync_branch,
)
# Retain: source/qualification hashes + manifest.json,
# diagnostic-readout.json, branch/full_transitions.jsonl.gz and its SHA256.
# STOP if status != TRAIN_ONLY_DIAGNOSTIC_COMPLETE, or unsafe / incomplete.
```

`source` is a dict with `rows[(seed,strategy)]`, `traces[(seed,strategy)]`, `training`, exact `sourceSha`, exact `fullTransitionsSha256` and qualified provenance. Each callback branch includes `seed`, `sourceWorldHash`, fork index, original public decision18D/mask7, full actual per-option `trace`, canonical `traceSha256`, actual `contacts`, `dwell`, goal250/unsafe and completion status. Journal should be SHA-bound and atomically retained; the host owns the runner/workflow and must independently re-execute raw traces before asserting any physical witness.

### Reproduce *existing* source-only verification (no physics or spend)

From this folder:

```sh
python3 -m unittest -v test_causal
python3 -m py_compile forensic.py causal.py protocol.py test_causal.py
```

With the original V12 source ZIP staged and receipt independently pinned:

```sh
python3 -c 'import forensic; s=forensic.load_original_v12("/path/to/original-v12-archive", "/path/to/receipt.json"); d=forensic.source_failure_diagnosis(s); print(len(s["rows"]), sum(len(v) for v in s["traces"].values()), len(d["v5WinningWorlds"]), len(d["v5FailedEarlyLegalAbstainWorlds"]), len(d["v5FailedLiveDropAtOption17Worlds"]), len(d["right4ExactPrefixMatchedOneOptionPairs"]))'
```

Expected exact values **144, 4228, 12, 26, 10, 31** from the retained original V12 corpus; these are historical observations, **not a V13 experiment result**. Portable synthetic tests check the search/replay/shield/stop contract; the development scratch runtime has no `mujoco`, so **zero V13 original-physics counterfactuals have been executed locally**.

## Future cohort: frozen before new observations

`protocol.frozen_plan()` pins entire public-world scan and hash, then rederives first64 near + first16 clear, without outcome selection. New TRAIN seeds `519024..519535` (512 scan) are disjoint from original V12 diagnostic `518000..518511` and reserved `518512..519023`. **The original physics `ContactEnv.reset` forbids seed>=520000**, so the previously suggested 520000+ scan cannot run unmodified. Conditional exploration-only confirmation `519536..519999` has only464 seeds, and therefore **is NOT a 512-world, high-powered independent certification**. If effects are weak, a larger unused/disjoint existing `120000..519999` historical gap requires a separate source-history inventory and prior preregistration. Never select by hidden DEV/CAL/TEST/OOD outcomes.

The next candidate must be frozen *after* finite seen-world causal witnesses but *before* prospective outcomes. Fresh paired original V5 baseline runs first, then candidate in the same registered public worlds, with independent original physics replay, **0 unsafe, 0 lost baseline safe250 goals and >0 genuine novel safe250 goals** even to request further prospective qualification. A seen-world witness is not proof of generalization. No auto-promotion or new spending is authorized by this folder.
