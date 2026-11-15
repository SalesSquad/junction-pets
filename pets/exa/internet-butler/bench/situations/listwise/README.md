# Listwise clause judge

Which tier of a provision applies to a situation? The pointwise judge B0 (`gpu/train_group.py`: one yes/no score per clause, Gemma 3 4B-it with LoRA) cannot compare tiers that differ only by a threshold, so it gets worse as a provision has more sibling clauses. The listwise judge reads every sibling tier in one prompt and answers with an option letter. This directory holds its teachers, the policy selection and the pre-registered evaluation on the 906-item test set (the top-level README's "older, harder set").

Every choice (temperatures, fusion weights, cascade threshold, Finnish teacher, prune size) is made on valid with provision-grouped 5-fold cross-validation; test is evaluated once, under the rules in `PROTOCOL.md`. `PROTOCOL.md` and its hash ledger `PROTOCOL.sha256` are copied byte for byte from the training workspace and must not be edited. They name the scripts by their workspace paths: `analysis/` is this directory, `nemotron/` is `teachers/`, `verda/judge/mlx_list.py` is `gemma/mlx_list.py`, `train_list3.py` is `gpu/train_list.py`, `verda/judge/mlx_lk_eval.py` and `mlx_lk_eval2.py` are `gemma/mlx_lk_eval.py` (v2 = this file), `verda/judge/mlx_list_train3.py` is `gemma/mlx_list_train.py`, `verda/job4/run_all4.sh` is `gpu/verda/run_job.sh`.

Owner's rule: Nemotron is never used on Finnish rows. Finnish rows use Claude Haiku 5.5, TypeSafe Jev, both or no teacher, chosen by the same cross-validation.

## Files

| Path | Role |
|---|---|
| `gpu/train_list.py` | Listwise trainer (CUDA, LoRA): letter cross-entropy with the option order reshuffled on every visit; KD from a teacher (`--teacher --beta --kd-skip-lang`); `--extra-train`; option-subset augmentation (`--subset-prob`); permutation-averaged scoring; test accuracy sealed |
| `gpu/train_group.py --dump-scores` | Raw per-clause scores of a pointwise judge (`valid_scores.jsonl`, `test_scores.jsonl`) |
| `gemma/mlx_list.py` | The listwise prompt (trained adapters depend on its exact text) and the MLX data builder and scorer |
| `teachers/nemo.py` | Nemotron 3.5 Super labels: option-letter log-probabilities, two orders |
| `teachers/fi_haiku.py`, `teachers/fi_jev.mjs` | Finnish teachers: Haiku listwise percentages; Jev pointwise P(yes) |
| `teachers/fi_translate.py` | Finnish training augmentation: Haiku translations of English train situations, with digit and length gates |
| `gpu/verda/vm_run_list.sh`, `gpu/verda/guard.sh` | One Verda GPU job (training, then pruned scoring) and its spend guard |
| `gpu/verda/run_job.sh` | Whole Verda round: poll for a GPU, submit through `verda-agent` (stops on an ambiguous provider answer), upload, start, guard, shut down |
| `gemma/mlx_lk_eval.py` | On-device judge: a PEFT LoRA applied to the MLX 4-bit base (unfused, or fused and re-quantized; `--save-fused`), or an MLX-trained adapter (`--mlx-adapter`); same prompt, orders and pruning as the torch judge; `--ms 3,4,5` scores every prune size in one pass |
| `gemma/mlx_list_train.py` | Listwise training on Apple silicon (QLoRA on the 4-bit base): the `gpu/train_list.py` objective, KD language skip, `--extra-train`, option subsets, per-layer gradient checkpointing, wall-clock budget |
| `prune_sets.py`, `prune_merge.py` | Prune-then-listwise: B0's top-m clauses for groups with k > m; m chosen on valid |
| `fi_teacher_dirs.py` | Builds the judge dirs `runs/jev_fi` and `runs/haiku_fi` |
| `select_policy.py` | Valid-only selection (v4, sha256 5c17bab0): `chosen` (cloud-assisted cascade) and `on_device` |
| `compare.py`, `overlap_rows.py`, `*_overlap_questions.json` | Paired comparison with B0 on all, clean and overlap rows (exact McNemar); per-row overlap flags |
| `final_eval.sh`, `score_offline.py` | The one test evaluation; the cache-coverage check that gates the tournament |
| `combine.py`, `fuse_fixed.py`, `valid_by_k.py` | Earlier tools: valid-only combiner, the untuned fusion of the original rules, valid accuracy by group size |

## Reproduce

Run from the repository root. Data and outputs live in the gitignored `bench/datasets/out/` and `runs/`. Teacher calls are paid. Keys come from `VERDA_INFERENCE_KEY`, `ANTHROPIC_API_KEY` and `TYPESAFE_API_KEY` (else the Keychain items or `~/.config/typesafe/env`) and are never printed.

1. **Data.** `bench/datasets/out/training/{train,valid,test}.jsonl` (5,839 / 823 / 906 groups), exported by `bench/situations/export_training.py` as of `de40098` from `pilot.jsonl` and `situations-b1..b3.jsonl` (today's exporter makes the cluster split, a different dataset). sha256: train `4b6f00ec…`, valid `d0e0f3a8…`, test `ea334db4…`. `test.judgments.jsonl` (6,804 lines) holds the cached Jev and Luna judgments.
2. **Teacher labels.**
   ```bash
   T=bench/situations/listwise/teachers; D=bench/datasets/out/training; mkdir -p runs/teachers runs/nemo
   for s in train valid test; do python3 $T/nemo.py label --split $s --out runs/teachers/$s.nemo.jsonl; done
   ln -sf ../teachers/valid.nemo.jsonl runs/nemo/valid_scores.jsonl; ln -sf ../teachers/test.nemo.jsonl runs/nemo/test_scores.jsonl
   for s in valid test; do python3 $T/fi_haiku.py --split $s --out runs/teachers/$s.haiku_fi.jsonl; done
   node --experimental-strip-types $T/fi_jev.mjs $D/valid.jsonl runs/teachers/valid_fi.jev.jsonl  # test Jev: from the cache
   python3 bench/situations/listwise/fi_teacher_dirs.py
   python3 $T/fi_translate.py --out runs/teachers/train.fi_aug.jsonl                              # LK3 only
   ```
3. **B0 scores (GPU).** `python gpu/train_group.py --eval-only --adapter <B0 adapter> --dump-scores --kind causal --model <gemma-3-4b-it> --train $D/valid.jsonl --valid $D/valid.jsonl --test $D/test.jsonl --out runs/b0`. The recorded B0 dump was made with the `de40098` trainer plus the same two dumps (`train_group_dump.py`, sha256 d2de53d1); today's trainer shortens long clauses and scores differently, so check that a new dump reproduces B0's 73.18 % within 0.5 points (amendment 2).
4. **Train on Verda.** `python3 bench/situations/listwise/prune_sets.py` writes `runs/prune/`. Upload the three splits, `train.nemo.jsonl`, `train.fi_aug.jsonl`, `gpu/train_list.py`, `runs/prune` as `prune/`, an `inputs.sha256` and `gpu/verda/vm_run_list.sh` to `/root/job` and start the script detached; its environment variables select the round (the defaults are round 4, LK3; the header lists round 3b). Then `JOB=<job id> VM_HOST=<ssh alias> LOCAL_JOB_DIR=<dir> zsh gpu/verda/guard.sh` pulls `out/run.log` and `out/runs/` and shuts the VM down, at the latest after `LIMIT_MIN`.
5. **Prune size.** Copy the pulled `out/runs/list4b_kd2` to `runs/`, then `python3 bench/situations/listwise/prune_merge.py list4b_kd2 --pruned-scores <dir>/out/runs` writes `runs/list4b_kd2p` (m chosen on valid: 5).
6. **Select, then evaluate once.** `zsh bench/situations/listwise/final_eval.sh runs/policy_v4 runs/list4b_kd2p [B0 judgments]` runs `select_policy.py`, compares its policies with B0 (`compare.py`) and, when `score_offline.py` finds every cloud judgment cached, runs the tournament with `--no-cloud`.

## Results (test, 906 groups)

| System | Accuracy | Only B0 right / only new right | McNemar p |
|---|---|---|---|
| B0, pointwise | 73.2 % (663/906) | | |
| Pre-registered cascade: B0 + 0.5·LK2p on the device, Nemotron on uncertain non-Finnish items (about 6 % cloud calls) | 77.8 % (705/906) | 14 / 56 | 4.3e-7 |
| Post-hoc rule-fixed cascade (v4: Nemotron's temperature fitted without Finnish rows) | 77.9 % (706/906) | 14 / 57 | 2.7e-7 |
| On the device only (LK2p, pruned listwise, no cloud) | 77.5 % (702/906) | 44 / 83 | 0.00068 |

- **Clean rows** (548 rows whose gold clause has no near-duplicate in train, flagged per row): B0 71.7 %, cascade v4 76.3 % (p = 0.00035), on the device 76.3 % (p = 0.0073).
- **Tournament** (`bench/situations/tournament.mjs` at `de40098`, code's tier filter + student): cascade v4 78.1 %; B0 the same way 74.0 %. Today's `tournament.mjs` (ties share credit, gold by full clause text, cluster-bootstrap intervals) gives 77.8 % [70.4, 83.0] and 73.7 % [66.0, 79.3] for the same judgment files.
- **Corrections** (`PROTOCOL.md` amendment 5): the 12B tie-breaker scored 200 test items before it was stopped (it read no labels); gaps in the hash ledger; how the methods were designed; Nemotron's Finnish valid rows reached the v3 choice through its temperature fit (fixed in v4, which picks the same policy); the calls made on test inputs. The pre-registered result stays the primary record.
- **On the device (MLX, Mac mini M6, amendment 7, descriptive):** LK2p's PEFT LoRA on `mlx-community/gemma-3-4b-it-4bit`, unfused: valid 0.8250 with the same pruning (m 5) and 4 orders, against 0.8275 for the torch bf16 judge; its argmax agrees with the torch judge on 96.6 % of valid groups; 2.2 s per group mean, 1.6 s median, with 4 orders while other MLX jobs shared the GPU. A 10-group smoke run of the fused, re-quantized model agreed on 9/10. The full fused valid and the fused test run were stopped by the owner before they finished, so the fused model has no full valid or test number.
- **Pending:** LK3 (amendment 6: Finnish augmentation, option subsets) has not run: the Verda balance was too low, and its MLX version (amendment 7) was stopped by the owner before training started. Either replaces LK2p only if its pruned valid accuracy exceeds 0.8275.

Model adapters and run outputs are not in git; they are in iCloud under `Events/Junction-2026/Models/gemma4b-judge3-20261115`.
