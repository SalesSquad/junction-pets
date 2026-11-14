# vLLM smoke run of 2026-11-14 (executed)

Every note in this folder is SYNTHETIC: written by a language model (Nemotron or Claude Haiku) from a
sampled answer key, labelled by code and checked by other models. Research artefact; not a medical
device; not for clinical use. Gemma 3 is used under the [Gemma Terms of Use](https://ai.google.dev/gemma/terms)
and the [Prohibited Use Policy](https://ai.google.dev/gemma/prohibited_use_policy).

## What ran

| item | value | source |
| --- | --- | --- |
| machine | `az-equity-a100-20261114`, NVIDIA A100 80 GB, Verda (deleted at 19:27 UTC) | `runs/v2-gpu.jsonl`, `data/scribe/v3/student/RUNS.md` |
| server | vLLM 0.29.0, xgrammar 0.2.9, torch 2.13.0+cu132, in its own venv on the bare machine (no container) | `runs/v2-gpu.jsonl` step `vllm_venv_install`; `install.log` |
| start script | `tools/start_server.sh`, which runs `serve/entrypoint.sh` (the version before `guard.py`), bound to 127.0.0.1:8000, GPU memory share 0.1 | `tools/start_server.sh`; `vllm.log` non-default args |
| base model | `unsloth/gemma-3-270m-it` at revision `23cf460f6bb16954176b3ddcc8d4f250501458a9`, served as `gemma-base` | `vllm.log` (non-default args) |
| adapter | `A-270m-lora-r16` (config id `5bc648b1983f`), the frozen version-2 selection, served as `pathway-scribe`; copied back as `scribe/v2/artifacts/adapter-selected/` (git-ignored), `adapter_model.safetensors` sha256 `17fee0ba9ef2cd1e2e255346e9abcf5e97f8af0d35e13858f307c660caa129a3` | `vllm.log` (`lora_modules`); local file |
| notes | `heldout-v2-100.jsonl`: the first 50 rows of `test_nemotron` and the first 50 of `test_haiku` in file order (38 standard, 6 careful, 6 no-event Haiku notes), sha256 `67484fa6050b571ff0e826b63aaf417c6fc7eb3e3658859419723c482145a697` | `runs/v2-gpu.jsonl` step `make_smoke_notes`; `tools/make_smoke_notes.py` |
| client | `serve/smoke_test.py` through `tools/run_smoke.sh`, concurrency 8, `max_tokens` 384, once with structured outputs and once without | `tools/run_smoke.sh`; `smoke-*.json` `settings` |

The rows of `heldout-v2-100.jsonl` carry no `synthetic` field; `tools/make_smoke_notes.py` now adds
`"synthetic": true` for any later run. This file was not rewritten, because that would change the
sha256 recorded in both result files.

## Results

`smoke-guided.json` (structured outputs) and `smoke-plain.json` (plain decoding), per-note answers in
`smoke-*-results.jsonl`, server log in `vllm.log` (first line 18:58:36, last 19:05:24 on the machine's
clock; 200 `POST /v1/chat/completions` lines). Valid JSON 100 and 98 of 100; exact match 22 of 100
both ways; latency p50 1.28 s and 1.40 s, p95 1.80 s and 1.99 s.

Compared with the offline evaluation of the same adapter on the same 100 notes
(`data/scribe/v2/training-figures-v1.json`, `serving_parity`, computed by
`scribe/v2/training_figures.py`): the verdict (exact or not) is the same on every note, while the
answers themselves are identical on fewer notes (see that file), and the offline run cut answers at
134 new tokens against 384 here. The 22% must not be read against the 42.0% and 13.0% headline
figures: half of these notes are Haiku-written.

## Not logged at the time

The run passed `--no-log` and wrote no `runs/` lines for the server start, the two smoke runs, the stop
or the copy back (review finding 20). Lines reconstructed from `vllm.log` and the `ts` fields of the
two result files were appended afterwards to `runs/training-md.jsonl`, marked `"reconstructed": true`.
The stop and copy-back times are not recorded anywhere and stay unknown.
