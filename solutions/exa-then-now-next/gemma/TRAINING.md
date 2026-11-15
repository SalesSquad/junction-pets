# Local Gemma training run (MLX on Apple silicon)

**Goal.** A small clause judge that runs on the device: given a person's situation and every tier of a provision, it names the tier that applies. It is trained and scored on the same question the hosted judges answer in Then · Now · Next.

**Result, 15 November 2026.** Gemma 4 E2B (4-bit) with a LoRA trained on an M5 Pro (24 GB) in 147 minutes picks the right clause for **88.8 %** of the verified test situations when three rotations of the option order are averaged (84.3 % with one order), against 71.0 % untrained. The hosted judges score 92 to 94 %. It runs in the app as an advisor next to the hosted panel and as the only judge in private mode.

## What is being compared

All on `bench/datasets/out/training-v3/test-indep.jsonl`: 1,168 situations from 65 clause-template clusters that no training item shares, chance 32 %. Their labels are known by construction and were recovered blind by two model families that are not judges here (the writer, Qwen3-30B, and Claude Haiku 5.5). Nemotron also checked the full dataset, so the larger `clean` tier is biased in Nemotron's favour and is not used to compare judges. Intervals are 95 % bootstraps over clusters (`bench/results/tournament-v3-indep-all.json`).

| Judge, one choice question over all tiers | Right clause | Finnish | English | German |
|---|---|---|---|---|
| Word overlap (no model) | 53.6 % | | | |
| Gemma 4 E2B 4-bit, untrained (thinking switch off) | 71.0 % [65.9, 75.0] | 63.3 % | 72.2 % | 74.2 % |
| Gemma 4 E2B 4-bit + LoRA (this run), one option order | 84.3 % [79.3, 87.8] | 85.5 % | 85.6 % | 79.8 % |
| **Gemma 4 E2B 4-bit + LoRA, three option orders averaged (as served)** | **88.8 % [84.4, 92.1]** | 90.5 % | 89.4 % | 85.5 % |
| Nemotron 3.5, zero-shot | 91.8 % [89.3, 93.8] | | | |
| Luna | 93.5 % [90.6, 95.6] | | | |
| Jev | 93.9 % [90.9, 96.0] | | | |
| Mean of the three hosted judges | 95.2 % [92.4, 97.2] | | | |
| Mean of the three hosted judges and the LoRA (three orders) | 96.2 % [93.5, 98.2] | | | |

- The LoRA adds 13.4 points [9.8, 17.4] over the untrained model with one option order. Averaging three rotations of the option order adds another 4.5 [2.7, 6.5]: a small model prefers some letter positions, and rotating the options cancels that. The rotation was adopted on the validation split (84.0 → 86.1 % on 1,145 items) before the test set was scored. The untrained model gains less from it (71.0 → 75.5 %).
- As served it is 3.0 points [0.0, 6.6] behind Nemotron, 4.7 [1.7, 8.0] behind Luna and 5.1 [2.1, 8.2] behind Jev.
- By attack variant (three orders) it is weakest on unit rewrites (75 %) and two-event messages (83 %), strongest on injection (94 %), dates and negation (91 %).
- As a fourth voter it would raise the panel's mean from 95.2 to 96.2 % and cut unanimous answers from 86.3 % to 80.1 % of cases for 98.6 → 98.8 % right. So it advises and does not vote.

## Data

`bench/datasets/out/training-v3/`, rebuilt by `bench/situations/export_training.py` from `bench/situations/situations-v3.jsonl`; a copy is in iCloud under `Events/Junction-2026/Datasets/timelaw-situations/v3/`.

- 26,019 situations: train 20,075, valid 1,996, test 3,948. Whole clause-template clusters go to one split (628 clusters). A cluster is named after its alphabetically first provision, so the split is the same on every run.
- Five boilerplate penalty wordings are shared by so many provisions that the split rule ignores them. Test and validation items that share any clause wording with training, those included, are dropped afterwards (351 items); training is never changed by that step.
- Label tiers: `clean` (the writer's family and every other family asked recover the clause blind), `half` (unverified, or the families disagree), `none`.
- Training uses `clean` items only: 10,500 after dropping provisions with more than 16 tiers.
- No output of Jev or Luna is used as a label.

## Method

One prompt per situation with every tier as a lettered option (`gpu/prompting.py: choice_content`), options shuffled on every pass so the letter carries no prior. The loss is the cross-entropy over the option letters at the first answer position. `gemma/mlx_judge.py` is the one reader used by the trainer, the scorer and the server: the same prompt (Gemma's thinking switch is passed explicitly and recorded with the adapter) and the same logits (the output head on the last position's hidden state, float32, without the final soft cap).

Why not `mlx_lm.lora`: Gemma's vocabulary has 262k tokens and the stock trainer computes that output for every token of a prompt of about 1,100 tokens. That took 7 s per step here. The judge is read from one position, so the trainer takes the hidden state there and applies the output head once: about 0.6 s per step, 10 GB peak.

Memory lessons from the first attempts on this machine:

- Calling the model on a whole prompt for scoring builds a (tokens × 262k) matrix per item. The reader prefills the cache with all but the last token and feeds the last token alone: 0.1 s per item instead of 9 s.
- Prompts differ in length, so MLX's buffer cache grows until the Mac swaps (17 GB). Both scripts cap the buffer cache at 1 GB. The trainer also sets MLX's memory limit, which is a guideline (MLX raises only when RAM and swap are exhausted), not a hard stop.
- MLX evaluates on the thread that loaded the model, so the server is single-threaded.

This run: LoRA rank 16 on the last 16 of 35 layers (13.6 M trainable parameters), AdamW, learning rate 1e-4 with warm-up and cosine decay, 8 items per update, two epochs (21,000 steps). It was started before the reader was shared: its prompt has the thinking switch on (mlx_lm's default) and its checkpoint was kept by accuracy on the first 200 validation items, none of which is an attacked message. Both are recorded: `adapter_config.json` carries `enable_thinking: true`, and the choice between the kept checkpoint and the last one was made afterwards on all 1,145 verified validation items (84.0 % against 83.5 %), never on the test items. New runs sample the selection items from the whole validation split and default to the thinking switch off.

## Commands

```bash
cd ~/Developer/internet-butler-20261114
# 1. Train
.venv-mlx/bin/python gemma/train_mlx_choice.py --model mlx-community/gemma-4-e2b-it-4bit \
  --data bench/datasets/out/training-v3 --out adapters/gemma4-e2b-choice --epochs 2 --max-minutes 200
# 2. Choose the checkpoint on validation, score it and the untrained model, compare all judges (cached hosted judgments)
sh gemma/after_training.sh
# 3. Serve it to the app
npm run judge:local
```

## Earlier runs

- Qwen3-1.7B with LoRA on a Verda A100, one yes/no per clause: 64.3 % on the older 906-item test, not significantly better than Jev asked the same way (+2.1 points, interval −3.4 to 12.3). The adapters were lost when the VM was removed.
- `mlx_lm.lora` on gemma-3-1b-it-4bit ran (loss 16 → 2 in 20 steps) but was not scored.

## What would raise it

- A larger base (Gemma 4 E4B) or more verified training items; the validation curve was still rising slowly at the end of the second epoch (80 % at step 3,000, 86 to 89.5 % on the 200 selection items from step 15,000).
- A third writer family (Gemini CLI) for the training data, kept out of the scoring loop so the test set stays independent of any judge.
