# Post-ablation student runs, 14 November 2026

SYNTHETIC notes only. Research artefacts, not for clinical use.

All runs: Gemma 3 LoRA r16 (alpha 32) on attention and MLP, learning rate 2e-4, cosine schedule, seed
20261114, 324 optimisation steps at an effective batch of 16, unconstrained greedy decoding. One NVIDIA
A100 80 GB on Verda (`az-equity-a100-20261114`), code and environment of `scribe/v2` (Transformers
5.23.0, PEFT 0.21.3, torch 2.15.0). The comparisons were fixed in `preregistration.json` (frozen
19:08:08 UTC). At that moment no run had a test result and the three data arms had no validation
result. The 1B run had written its validation result to the GPU box 5 seconds earlier (19:08:03,
`gpu-logs/queue.log`); the coordinator saw it only afterwards, but strictly the 1B test rule was fixed
after that result existed. Numbers are in `compare-v1.json`, produced by `scribe/v3/compare_students.py`.

| run | training data | where |
| --- | --- | --- |
| `v2-selected` (reference) | 1,716 Nemotron round-1 notes | frozen version-2 selection, copied from the ablation |
| `V3-270m-nemotron` | reference + 1,506 round-2 Nemotron notes accepted by the Jev gate | dataset v3, `train_data=nemotron` |
| `V3-270m-all` | as above + 638 version-2 Haiku notes | dataset v3, `train_data=nemotron+haiku` |
| `C-270m-all-v2data` | reference + 638 version-2 Haiku notes | dataset v2, `train_data=nemotron+haiku` |
| `S-1b-lora-r16` | reference data, Gemma 3 1B | the size step the ablation dropped for time |

Because every run has 324 steps (324 x 16 = 5,184 training examples drawn), a larger training set is
seen for fewer epochs: 1,716 notes 3.0 epochs, 2,354 notes 2.2, 3,222 notes 1.6, 3,860 notes 1.3.
Data arms therefore differ in epochs as well as in data.

## What happened during the runs (from `gpu-logs/`)

- `V3-270m-nemotron` and `V3-270m-all` first stopped before training: one long round-2 note has 1,050
  tokens and the length guard was 1,024 (the guard refuses rather than truncates). The guard was raised to
  1,536 in both configurations (`gpu-logs/cfg-v3-*.json`); nothing else changed.
- The first `V3-270m-nemotron` run then ran out of GPU memory while a 4B attempt was loading on the same
  card (`gpu-logs/v3nem.log`). It was restarted unchanged (`gpu-logs/v3nem2.log`).
- 4B: the first attempt ran out of memory beside the 1B run (`s4b.log`), the second beside three 270M
  runs (`s4b2.log`). A third attempt with batch 4, gradient accumulation 4 and gradient checkpointing was
  stopped by the coordinator after loading (`queue3.log`) because it competed for memory with the
  pre-registered runs and the cloud balance was low. There is no 4B result.
- The first test evaluation of `C-270m-all-v2data` failed because it was started in a different working
  directory from the one its adapter path is relative to (`queue4.log`); it was rerun once from the right
  directory. No test result was produced by the failed attempt.
- `S-1b-lora-r16` beat the reference on validation (17 notes only it got right, 4 only the reference
  got right, exact McNemar p = 0.0072), so under the pre-registered rule it was evaluated on test once.
- The machine was deleted with its disk at 19:27 UTC after every result, log and adapter was copied back.
  Adapters are in `scribe/v3/artifacts/<run>/adapter/` (git-ignored).
