# Pre-registered evaluation protocol: listwise Gemma judge (14 Nov 2026)

Written before any listwise test score is read. Its sha256 is recorded in `PROTOCOL.sha256`.

## Judges
- **B0, the pointwise judge.** Gemma 3 4B-it bf16 with LoRA, trained by `gpu/train_group.py` at internet-butler `de40098`, 1 epoch on the Verda RTX PRO 6000.
  - Test judgments are in `verda/out/gemma4b-group/judgments.jsonl`. They hold the raw score and p.
  - The temperature fitted on valid is 2.0. Valid accuracy is 0.7995.
- **L4, the listwise judge.** Gemma 3 4B-it, 4-bit MLX (`mlx-community/gemma-3-4b-it-4bit`, rev 93724907), with LoRA.
  - Trained by `mlx_lm.lora` 0.32.2: 16 layers, lr 1e-4, batch 1, max length 2048, `--mask-prompt`.
  - Data: listwise rows from `verda/judge/mlx_list.py build --copies 1 --seed 5`. One row per train group, with a seeded random option order.
  - Scored by `mlx_list.py score --perms 4`: identity order, reversed order, and 2 seeded shuffles, with log-probabilities averaged per clause.

## Decisions made on valid only
- L4's valid accuracy (4 orders) is compared with B0's valid accuracy of 0.7995. This is the only model comparison made before test.
- No weight, threshold or temperature is chosen on test.

## Test rules, fixed now
1. **L4 alone:** argmax of the averaged log-probability.
2. **Fused:** `log_softmax(B0_raw / 2.0) + L4_logprob`, fixed 1:1, untuned.
3. **Tournament:** both are scored by `bench/situations/tournament.mjs` with `--student`. Strategies: student, code+student, code+student→luna. Cloud judgments come only from the cached test file, with no new calls.
4. **Reporting:**
   - Full test (906 items), and the subset whose gold clause has no near-duplicate in train. The gids are in `analysis/test_overlap_gids.json`.
   - Paired comparison against B0 on the same items: the B0-only-right and L4-only-right counts, and a two-sided exact McNemar test.
5. **Deployment rule:** rule 2 (fused) is the candidate. It is adopted only if it beats B0 on test by more than the McNemar noise (p < 0.05). Otherwise the result is reported as inconclusive, not as a gain.

## Amendment 1 (made before any listwise or tie-breaker test score was computed)
- The MLX listwise run (L4) was stopped at iteration 2,500. On 150 valid groups its iter-1500 checkpoint
  scored 0.32, which is chance level. No L4 test scores exist, so rules 1 and 2 are void.
- New candidate, fixed by `analysis/tiebreak12b.py`: a zero-shot Gemma 3 12B (MLX 4-bit) top-2 tie-breaker.
  - It applies to B0's low-margin test items: margin below the median, computed from unlabeled test scores.
  - It uses both option orders.
  - The fusion with B0's top-2 log-probabilities is fixed at 1:1.
  - Evidence used: valid only. 12B picked the gold over the nearest sibling in about 0.8 of valid pairs
    (`logs/pair12b.log`).
- It is evaluated once on test with the same tournament and the same reporting as rules 3 and 4, against B0.

Note (no rule change): valid probe stopped at n=151 with gold-vs-nearest-sibling accuracy 0.795 (logs/pair12b.log), 2026-11-14T21:30:54Z.


## Amendment 2 (2026-11-14T23:15Z, before any test score of the judges below is computed)
The file hash before this amendment was 2b12b3f4… (amendment 1 plus the n=151 note above).

- **Amendment 1 is void.** The 12B tie-breaker was cancelled before it scored any test item. The MBP ran out of memory, so only the valid probe was run.
- **New judges.**
  - **N, the teacher.** Nemotron 3.5 Super VL (Verda serverless, model `nemotron-3.5-super-vl`), zero-shot.
    - Prompt: the listwise prompt of `verda/judge/mlx_list.py`, with `/no_think` and thinking off.
    - Scoring: log-probabilities of the option letters (top 20). Two orders, identity and reversed, averaged per clause.
    - Labels: `nemotron/{train,valid,test}.nemo.jsonl`, written by `nemotron/nemo.py` (sha 56661a10).
    - Accuracy so far: valid 0.7886, train 0.7405. Test accuracy has not been computed or printed.
  - **LK, the listwise student with distillation.** Gemma 3 4B-it bf16 with LoRA r16.
    - Trained by `train_list.py` (sha 78b7dd85) on a Verda RTX PRO 6000 (job `gemma-judge3-20261115-rtx`).
    - Loss: listwise cross-entropy over the option letters, plus 0.5 × KL to N's train labels. The option order is reshuffled on every visit.
    - Schedule: 2 epochs, capped at 32 minutes of training.
    - Scoring: 4 orders at test time. The script seals test accuracy and does not print it.
  - **B0 dump.** B0's valid and test raw scores are re-dumped by `train_group_dump.py --eval-only` (sha d2de53d1) with the round-1 adapter.
    - The dump is valid only if its test accuracy reproduces B0's 0.7318 within 0.5 points. This is a check of the dump, not a result.
- **Decisions, made on valid only, by `analysis/select_policy.py` (sha f1418724).**
  - Every judge gets a valid-fitted temperature.
  - On-device side: B0, LK, or B0 + v·LK with v in {0.5, 1, 2}.
  - Policies:
    - on-device side only;
    - N only;
    - fuse(w) = w·side + N;
    - cascade(τ, w): the side's answer when its top probability is at least τ, else fuse(w).
  - Selection: 5-fold cross-validation on valid, grouped by provision (the gid without its date).
  - **Primary policy (`chosen`):** within 1 SE of the best CV accuracy; the fewest teacher calls, then the simplest.
  - **Secondary policy (`on_device`):** no teacher calls; within 1 SE of the best on-device CV accuracy; the simplest side.
- **Test, evaluated once after the selection.**
  1. Primary and secondary are each compared with B0 by `analysis/compare.py`.
     - Report full, clean and overlap accuracy, the discordant counts and the exact McNemar p.
     - Report the teacher call rate on test.
  2. Primary and secondary each go through the tournament with `--student`, using the strategies student, code+student and code+student→luna.
     - Only cached cloud judgments are used. `test.judgments.jsonl` must remain 6804 lines.
  3. N alone and LK alone are reported as descriptive numbers, with no claim attached.
  4. **Deployment rule:** a policy is adopted only if it beats B0 with McNemar p < 0.05. Otherwise it is reported as inconclusive.
     - The primary is a cloud-assisted system, because it calls N. The secondary is the on-device system. The two are reported separately.


## Amendment 3 (2026-11-14T23:34Z, before any test score of the judges below is computed)
The owner's instruction (2026-11-15): do not use Nemotron in Finnish; use TypeSafe, DeepSeek or Haiku instead. No DeepSeek key exists on the owner's Macs, so the Finnish candidates are TypeSafe Jev and Claude Haiku 5.5. The hash before this amendment is 485e0267.

- **No Nemotron on Finnish rows, in any policy.** `analysis/select_policy.py` (sha 4c8c9c90) reads Nemotron only for rows whose `lang` is not Finnish. A synthetic test confirmed this: with a Nemotron oracle on Finnish rows, no policy's Finnish accuracy rose above that of its Finnish teacher.
- **Finnish teacher candidates, selected by the same valid cross-validation:** none, Haiku, Jev, or Haiku + Jev.
  - **H (Haiku):** Claude Haiku 5.5 (`claude-haiku-5-5`), effort low, structured output (answer letter plus a percentage per option).
    - It uses the same listwise prompt as N and two orders. Percentages are floored at 0.5, renormalised and averaged as log-probabilities.
    - Files: `nemotron/{valid,test}.haiku_fi.jsonl`, written by `nemotron/fi_haiku.py`. Valid Finnish accuracy: 0.7005. Test accuracy was not printed.
  - **J (Jev):** TypeSafe Jev pointwise P(yes); the score is logit(p).
    - Valid Finnish: 728 new calls through `nemotron/fi_jev.mjs`, plus 22 smoke-test calls on the same keys. Valid Finnish accuracy: 0.6364.
    - Test: read from the existing cache. `test.judgments.jsonl` is unchanged (6804 lines). Its Jev values were computed in round 1, and their Finnish tournament accuracy was seen then. That number is not used for any choice here.
- **LK2 replaces LK as the listwise student.** It is identical to LK except that Finnish train groups get no Nemotron distillation, only gold cross-entropy (`train_list.py` sha a2ca8c26, `--kd-skip-lang Finnish`, job `gemma-judge3-20261115-rtx`, round 3b).
  - In `select_policy.py` the on-device side is chosen from B0, LK2 and B0 + v·LK2.
  - LK alone and LK2 alone are reported only as descriptive numbers.
- **Unchanged from amendment 2:** the selection rules (primary `chosen`, secondary `on_device`), the test comparisons with B0, the tournament with cached cloud judgments only, and the McNemar deployment rule.
  - If round 3b fails or runs out of time, the selection runs with LK in LK2's place, and this is reported.


## Amendment 4 (2026-11-15T00:06Z, before any test score of the judges below is computed)
The hash before this amendment is 0456eebb.

- **Prune-then-listwise for large groups.**
  - For a group with k > m, B0's raw scores pick the top-m clauses, written by `analysis/prune_sets.py`. No labels are used for the pruning.
  - LK2 then scores only those m clauses, with 4 orders (round 3c, `vm_run5.sh`).
  - Pruned-out clauses get the lowest kept log-probability minus 5.
  - B0's top-m recall on valid groups with k > m: m=3 0.9425, m=4 0.9476, m=5 0.9568.
- **Choosing m on valid.** m is chosen from {none, 3, 4, 5} by the valid accuracy of the merged LK2 judge alone (`analysis/prune_merge.py`).
  - On a tie, none wins, then the smaller m.
  - The chosen judge (`runs/list4b_kd2p`) is the `lk` judge in `select_policy.py`, and the run is `final_eval.sh runs/list4b_kd2p`.
- **Descriptive only.** The same procedure for LK (round 3) and the unpruned LK2 are reported as descriptive numbers.
- **Fallback.** If round 3c fails or runs out of time, m = none, so the judge is LK2 itself.
- **Unchanged:** everything else in amendments 2 and 3.


## Amendment 5 (2026-11-15, after the one test evaluation of amendments 2–4: corrections and one post-hoc fix)
The pre-registered result is `runs/policy` from `final_eval.sh runs/list4b_kd2p` (00:53Z, `select_policy.py` v3 sha 4c8c9c90). It stays the primary record. An independent read-only verification ran afterwards (four verifiers and a skeptic) and found the following.

1. **Correction to amendment 2.** The 12B tie-breaker was not cancelled before scoring test items. It scored 200 of 453 low-margin test items before it was stopped (`logs/tiebreak.log`). It read no labels, saved no output and computed no accuracy.
2. **Ledger gaps.**
   - Hash 2b12b3f4 (amendment 1 plus the n=151 note) was never written to `PROTOCOL.sha256`.
   - Hashes 79b743d0, 7271f525 and 5348077a are timestamp-fix drafts, each replaced within seconds.
   - Amendment 3's `train_list.py` (sha a2ca8c26) is the file `verda/job3/train_list2.py`.
3. **Disclosure of how the methods were designed.**
   - The round-1 error analysis, `analysis/analysis.json` (19:32Z, before the first protocol hash), used B0's test accuracy by group size, margin and language. That analysis motivated the listwise judge, the cascade, the pruning of large groups and the Finnish routing.
   - Every numeric choice was made on valid; the verification re-derived each one from valid alone.
   - LK1's sealed test metrics were on disk before amendment 4. No script read them. The agent states it did not open them, but this cannot be verified.
4. **Defect: Nemotron reached the policy choice through Finnish data.**
   - `select_policy.py` v3 fitted Nemotron's temperature on all valid rows, Finnish ones included. No Nemotron score reached a Finnish output, but Nemotron's Finnish valid scores influenced which policy was chosen. This breaks the owner's rule.
   - Fix: v4 (sha 5c17bab0) fits Nemotron's temperature on non-Finnish valid rows only.
   - Perturbation check: with random Nemotron scores on every Finnish valid and test row, v4 gives byte-identical judgments and the same choices.
   - v4 selects the same primary parameters as v3 (cascade, w 0.25, τ 0.5, side B0 + 0.5·LK2p, no Finnish teacher). Nemotron's temperature is 1.5 instead of 2.
   - The v4 policies are evaluated once on test (`final_eval_v4.sh` → `runs/policy_v4`) as a **post-hoc corrected result**, reported next to the pre-registered one.
5. **Calls on test inputs.**
   - Haiku 5.5 judged all 196 Finnish test rows: 392 calls, label-free, as part of the evaluated system.
   - Jev was called 750 times on valid (728 plus 22 smoke-test calls).
   - No new Jev or Luna calls were made on test: `test.judgments.jsonl` is unchanged (6804 lines, mtime 2026-11-14 18:13 local time).


## Amendment 6 (2026-11-15, before any score of LK3 is computed; owner: "toteuta kokonaisuus")
The hash before this amendment is 56b711b5.

- **LK3, a new listwise candidate.** It is trained by `train_list3.py` (sha 1316f6d1). This is `train_list2.py` plus `--extra-train` and option-subset augmentation, run as `verda/job4/vm_run6.sh` on a fresh Verda GPU.
  - Data: train plus `nemotron/train.fi_aug.jsonl` (sha 918afcab). It holds 2943 English train situations translated into Finnish by Claude Haiku 5.5 (`nemotron/fi_translate.py`, sha af8701a9).
    - Quality gates: structured output, an identical digit multiset, and a length ratio of 0.6–1.8. 373 translations were dropped by the digit gate and 7 were empty.
    - Clauses and targets are unchanged. Valid and test are never translated.
  - Augmentation: with probability 0.5, a group with k ≥ 4 is shown as a random subset of 2–5 options. The subset keeps one gold option.
  - Distillation: Nemotron KD with β = 0.5 on non-Finnish rows only. All Finnish rows, translated ones included, get gold cross-entropy only.
  - Schedule: 2 epochs, capped at 45 minutes of training.
  - Scoring: 4 orders at test time, with test accuracy sealed. Prune-then-listwise is applied with m ∈ {3, 4, 5} on the same B0 top-m sets as amendment 4.
- **LK3 vs LK2, decided on valid only.**
  - The prune size for LK3 is chosen by `analysis/prune_merge.py` as in amendment 4. Call the result LK3p.
  - LK3p replaces LK2p as the `lk` judge only if its valid accuracy is strictly greater than LK2p's 0.8275. Otherwise LK2p stays, and the v4 results stand.
  - Selection is unchanged: `select_policy.py` v4 (sha 5c17bab0), which never uses Nemotron on Finnish rows and fits Nemotron's temperature without Finnish rows.
  - Evaluation runs once: `final_eval_v5.sh <lk dir>` → `runs/policy_v5`, compared with B0 by McNemar.
- **On-device artifact.** The `lk` adapter that wins on valid is converted to MLX.
  - The base is `mlx-community/gemma-3-4b-it-4bit` (rev 93724907). The LoRA weights are mapped from PEFT to MLX (lora_a = Aᵀ, lora_b = Bᵀ, scale = α/√r) and then fused.
  - On valid, report the accuracy drift against the torch bf16 judge, with the same pruning and orders, and the latency per group on a Mac.
  - The MLX artifact's test accuracy is computed once and reported as descriptive. No choice depends on it.
- **Overlap split.** `analysis/test_overlap_gids.json` marks overlap per gid, which over-includes rows. The overlap split will be recomputed per row (per question) by its original definition, and clean/overlap numbers will be re-reported as descriptive. No choice depends on this split.


## Amendment 7 (2026-11-15, before any score of LK3-MLX is computed; owner: "Ajoa")
The hash before this amendment is df3328bd.

- **Why.** The Verda balance fell to $0.87: another agent's A100 runs on the same account. No GPU was free, and the round-4 submit returned "outcome unknown" without creating an instance. Amendment 6's LK3 on a Verda GPU therefore cannot run without a top-up, and it stays pending.
- **LK3-MLX, a new candidate.** It is trained on the Mac mini (Apple M6) with MLX, directly on the 4-bit base `mlx-community/gemma-3-4b-it-4bit` (rev 93724907) as QLoRA.
  - Trainer: `verda/judge/mlx_list_train3.py` (sha d56382bd), launched by `logs/run_lk3_mlx.sh` (sha a61b6091).
  - The objective matches LK3: letter-softmax CE plus 0.5 × KL to Nemotron on non-Finnish rows only. Finnish rows, including the 2943 Haiku-translated ones (sha 918afcab), get gold CE only. Option-subset augmentation uses p 0.5 and sizes 2–5.
  - LoRA: rank 16 on all seven projections of all 34 layers, scale 8 (the torch run's α/√r).
  - Optimisation: lr 2e-4 with warmup and cosine decay, 16 groups per update, seed 5. Schedule: 2 epochs, capped at 6 hours of wall-clock time.
- **Scoring** uses `verda/judge/mlx_lk_eval2.py` (sha 5196780a) with the MLX adapter.
  - The prompt, the 4 orders and the letter log-softmax match `train_list.py`'s evaluate.
  - Prune-then-listwise runs on B0's top-m clauses for m ∈ {none, 3, 4, 5}, all in one pass. Test accuracy is never printed.
- **Decision rule, on valid only.**
  - m is the value with the best valid accuracy (ties go to none, then the smaller m). Call the result LK3m-p.
  - LK3m-p replaces LK2p as `lk` only if its valid accuracy is strictly greater than 0.8275 (LK2p, torch). If it does, `final_eval_v6.sh` (identical to v5) → `runs/policy_v6` is run once, with `select_policy.py` v4 (sha 5c17bab0), and compared with B0 by McNemar on the per-row clean/overlap split.
  - Otherwise LK2p and the v4 results stand, and LK3m-p is reported as descriptive only.
- **MLX artifact for LK2p (descriptive).**
  - The PEFT LoRA was applied to the same 4-bit base, unfused and fused/re-quantised, by `verda/judge/mlx_lk_eval.py`.
  - Report its valid agreement with the torch judge and its valid accuracy. Its test accuracy is computed once, for the fused (deployable) model only.
- **Landed code.** The PROTOCOL.md copy in internet-butler `bench/situations/listwise/` (merged in PR #1, d0e71d7) ends at amendment 6. This file, in the training workspace, is the live record from amendment 7 on.

- **7a (technical, before training started).** A 24-group smoke run stalled when the mini's free memory reached 9 %, while the LK2p MLX evaluation was running at the same time. The trainer now applies per-layer gradient checkpointing (`mlx_lm.tuner.trainer.grad_checkpoint`) and a 2 GB MLX cache cap. The objective, data and hyperparameters are unchanged. The trainer's sha is now a34f72a2 (was d56382bd).
