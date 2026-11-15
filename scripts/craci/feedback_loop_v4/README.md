# CRACI Feedback V4 — retained physics evidence → one V14 TRAIN proposal

WorkID `CRACI-V13-TO-V14-LEARNING-20261115`. This folder is a **source-only offline compiler**; it creates no new CRACI workflow, daemon, deployment, paid MuJoCo run, model weights or automatic model promotion. A successful exit from the CLI means the **evidence was parsed and the advisory result written**, not that a new model is successful.

## A real negative lesson, not an invented training success

The first original hosted V13 causal diagnostic **#43660619725** used V13 product `0751d78b93855bf70820b03b0a543e123d218baf`, original harness `dc6d745c5facb56eed85016830dfe8f19b25032f`, GitHub artifact #14139354188 (outer ZIP SHA256 `cbbd78d255121102c39708ee2771f88c962e33e831ebce2b2c1c5d58769495b0`). Original retained and SHA-reassembled private records show **INCOMPLETE_STOP / V13_REAL_PHYSICS_UNSAFE** after **23 complete branches, 394 completed original MuJoCo option events across only 2 previously seen TRAIN worlds**. No fresh disjoint test or promotion occurred. This MUST NOT be described as a 36-world study, a new policy gain, an independently estimated collision rate of 1/394, or 394 independent outcomes.

The first and sole observed unsafe original option was seed **518006**, global completed branch **22** (`v13-seen-train-518006-16`), zero-based option **37**, original action **2**, original mask `[1,1,1,1,1,1,1]` (legal), `cost=1`, `done=true`, original transition SHA256 `4702034192e3877e42278a1b297e9b8c787955fbe2a30e411dd06fd9a7fee4ba`. **Mechanism is unknown:** original physics can mark unsafe for impulse above its unchanged .006 threshold, obstacle contact or body bounds, but the retained option trace does not identify which. `contacts_cumulative=2013` counts object/pusher contacts, **not** a measured force threshold. The new compiler emits this source-bound counterexample only; **zero learning rows, no V14 policy, no model update, no further dispatch**.

## Evidence contract

The compiler requires *all* of the following before producing a decision:

1. Externally SHA256-pinned original **outer hosted artifact ZIP**, the exact harness SHA and GitHub run ID. The original wrapper and source-reported CRACI receipt must agree on repository, product/harness, run, workload, exit status and file hashes. This is source/receipt provenance, **not a provider-signed billing attestation**.
2. The exact reviewed V13 retention/packer Git blob `661161cd...` and the independently tested V3 original public shield Git blob `826dd74c...`. It uses these frozen validators unchanged, including exact retained chunk ZIPs, proofs and raw originals. No safety thresholds are relaxed.
3. Frozen original V12 source-trace world index SHA256 `24460b2ed...`: 48 seen TRAIN world signatures, source V12 `78f1b9...`; no hidden DEV/CAL/TEST/OOD dataset, no alternate seed scan.
4. For **COMPLETE** only: independently replayed all 36 V5 failed-world causal branches, 250 actual physics tick safe goals, all journaled options, exact masks and first public forks, complete readout/independent-qualification, no unsafe. Partial/early STOP or corrupted/missing chunk fails closed; partial cannot become a training dataset.

Every original branch is re-bound to an ordered per-step `option_journal.jsonl.gz` by **seed + branch-local ordinal string**. The raw branch's global integer `branch_id` is **not** equal to the journal's string `branchId`. Original 18D observations, 7-option masks, exact transition SHA256, public state chain, original live/deadman and costs are verified; if a complete branch is missing from the journal, STOP. If a partial journal contains extra unfinished options, they remain explicitly unqualified and never train a policy.

## Learning rule *only if a future complete V13 science dataset exists*

The deterministic compiler:

- Deduplicates the first **actually executed** post-fork action per action × original world; requires identical initial public18D+mask7 and exact prefix for comparisons.
- Uses matched one-option public goal progress differences between **different legal actions at the same world/fork**, not the forward-mask reopening proxy. Multiple rollouts from one world are **not** independent; one world contributes at most one posterior sign per proposed action (median of paired alternatives).
- Reports distinct-world action support and a Jeffreys Beta(½,½) posterior; its one-sided 95% lower bound uses the conservative Cantelli inequality, without interpreting this as generalization. Actions unsupported by physical counterfactuals remain untrained.
- Produces **at most one** reproducible, strictly V5-default/public-shield-legal rescue hypothesis when ≥2 distinct previously failed seen-world **actual 250-tick safe goal witnesses**, ≥3 distinct action-support worlds, ≥3 matched distinct-world comparisons and posterior mean >½ support it. Otherwise science STOP, candidate `null`.
- The proposal is **not executed** and never claims efficacy. It needs source-frozen prospective new TRAIN scan `519024..519535`, independent paired original V5 and candidate MuJoCo 3.3.7 evaluation, 0 original V5 lost goals, 0 unsafe, >0 genuinely new physical goal250 and later independent qualification before *any* promotion discussion. The original `ContactEnv.reset` forbids seeds `>=520000`.

## Run against an already collected artifact — no new spend

```sh
python3 scripts/craci/feedback_loop_v4/cli.py \
  --repo-root /path/to/pinned/repo \
  --hosted-artifact /private/rokoko-v13-43660619725-original.zip \
  --artifact-sha256 cbbd78d255121102c39708ee2771f88c962e33e831ebce2b2c1c5d58769495b0 \
  --harness-sha dc6d745c5facb56eed85016830dfe8f19b25032f \
  --github-run 43660619725 \
  --output-dir /private/new-v14-evidence-output
```

If a detached source checkout does not contain the audited V12 public hash index, pass `--v12-index /path/to/trajectory-sha256.json`; the same **hardcoded original SHA** still applies. The output directory must be new. No raw original private trajectories are exported into Git:

- `next_training_decision.json`: STOP/one provisional V14 hypothesis, exact original receipt/source hashes, actual safety counterexample and the required independent gate.
- `training_dataset_manifest.json`: immutable source lineage, eligible row count and SHA, world counts, unresolved uncertainty and **no-model/no-spend** flags.
- `training_rows.jsonl`: only when the original evidence is **complete + independently physically qualified**; contains source-bound public first-fork option examples, never DEV/CAL/TEST/OOD or an unqualified partial.

For #43660619725, the correctly verified result is **`HARD_STOP_UNSAFE_INCOMPLETE`**, `nextSingleV14PolicyProposal=null`, `trainingRowsCount=0`, `seenTrainPhysicallyExecutedDistinctWorlds=2`, and safety mechanism `UNKNOWN`.

Portable synthetic tests (they are not proof of MuJoCo physics):

```sh
cd scripts/craci/feedback_loop_v4
python3 -m unittest -v test_feedback_v4
python3 -m py_compile core.py cli.py test_feedback_v4.py
```
