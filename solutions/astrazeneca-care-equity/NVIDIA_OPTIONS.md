# SAMA: where we stand, every NVIDIA option, and the plan for tonight

Revised Saturday 14 November 2026, 20:55 UTC. This is a read-only analysis. No cloud resource was changed and no paid API was called. The only network calls were public listings (`verda` read-only status, container list and spot availability; `integrate.api.nvidia.com/v1/models`; `openrouter.ai/api/v1/models`) and page reads.
All patient-like data in SAMA is SYNTHETIC. Nothing here is a clinical claim.

How to read the source labels:
- **(R)**: the writer of this file opened the page today, 20:29-20:50 UTC.
- **(S)**: a survey step in this workflow opened the page today. The URL is the one it recorded.
- **UNVERIFIED**: nobody confirmed it on a primary page today.
- Repository facts link to files in this folder. Measured scribe numbers come from `runs/diagnose/*.json`.

**Deadline.** The only record is "Sun 10:00 final submission: video of at most 2 minutes, PDF deck, demo and MIT source" in `../../docs/challenge-research/fable-review.json` (`wave_plan.fixed_deadlines`). 10:00 Helsinki time is 08:00 UTC. The same file says nobody saw the participant guide, so this is UNVERIFIED. AstraZeneca judging is Sunday at 14:00 Helsinki time (12:00 UTC). At 20:55 UTC about 11 hours remain.

**Summary in five lines.**
1. The scribe is not far off. It reads notes well and fails at one job: subtracting "N days/weeks ago" from the note date. Code fixes that for free: test 305 to 651/700, with 0 notes made worse.
2. The biggest gap is not accuracy. It is that Nemotron is not in the running product (the NVIDIA minimum), the AstraZeneca actions are not tied to the national roadmap, and no deck or video exists.
3. The Verda balance was USD 1.14 at 20:46 UTC and reaches zero around 21:09 UTC. The owner must act now.
4. Nemotron 3.5 Super VL can be reached three ways: the event endpoint, NVIDIA Build (needs a key), and OpenRouter (paid, about USD 1-2 for the whole night by my estimate). Line up a second route before relying on the first.
5. Everything else NVIDIA (NeMo RL, AutoModel, NIM, cuOpt, RAPIDS, MONAI) is either a slide or not worth it tonight.

---

## 1. Where we are and where we need to be

### 1.1 The scribe fails at one thing: date arithmetic

The best adapter is `C-270m-all-v2data` (Gemma 3 270M, trained on 1,716 Nemotron-written and 638 Haiku-written notes). Its test exact match is 305/700 (43.6%). The errors split almost perfectly on one feature:

| Test notes (C-270m-all-v2data) | Exact match |
|---|---|
| No relative date in the note | 303/333 (91.0%) |
| At least one "N päivää/viikkoa sitten" | 2/367 (0.5%) |

- 516 of the 520 wrong dates on events whose type was found are relative dates.
- Days-ago dates are exact 2/261 times and weeks-ago dates 1/258 times.
- Other date forms are 98.2-100% exact: numeric 430/431, long 280/280, month 279/280, no-year 111/113.
- The model guesses the size of the offset but does not do the subtraction. The ratio of predicted to stated offset has a median of 1.125, with the middle half between 0.89 and 1.64.
- A bigger model does not help: Gemma 3 1B gets 6/367 relative-date notes right.
- The model already reads the notes well. It finds the right event type for 259 of 263 days-ago events and 258 of 263 weeks-ago events.

Source: `runs/diagnose/diagnose-v1.json`.

### 1.2 Code already fixes most of it, at no cost

`runs/diagnose/resolve_relative.py` finds each relative phrase and resolves it against the note date. It then re-dates predicted events whose date is not written in the note. It needs no GPU and no retraining.

| Run | Test before | Test after | Validation before | Validation after |
|---|---|---|---|---|
| C-270m-all-v2data | 305/700 | 651/700 (93.0%, Wilson 0.909-0.947) | 134/310 | 289/310 |
| V3-270m-all | 277 | 613 | 125 | 277 |
| S-1b (Gemma 3 1B) | 270 | 586 | - | - |
| V3-270m-nemotron | 267 | 564 | - | - |
| v2-selected | 236 | 522 | - | - |

- The fix made 0 notes worse, in every run and every split.
- By writer: Nemotron-written notes go from 210 to 481/500 and Haiku-written notes from 95 to 170/200.
- 49 wrong notes remain. A note can have more than one error (4 notes have several), so the counts below add to 54:
  - 19 have a missing event;
  - 16 have an extra event (12 of these are ordinary non-cancer visits);
  - 9 have a wrong type (4 are REFERRAL_RECEIVED read as REFERRAL_SENT);
  - 6 have a wrong date, and 1 a wrong type and date;
  - 2 cannot be parsed;
  - 1 has a wrong route.

Source: `runs/diagnose/resolve-relative-v1.json` (`residual_after_resolver_test`).

**Caveats.**
- The regex is digits only: `(\d+)\s+(päivää|viikkoa)\s+sitten` (`runs/diagnose/resolve_relative.py`, line 26). It does not cover "kolme viikkoa sitten" (spelled-out number), "eilen" (yesterday), "viikko sitten" (a week ago), "viime kuussa" (last month) or weekdays.
- It was written from the note generator's own date code (`scribe/sample.py`). The synthetic notes use only six date forms, so it covers them by construction.
- The test set has been read several times. 93.0% is a post hoc figure. Validation (289/310) confirms it, but a fresh, frozen test set is still missing.
- The resolver is not yet in the product. `grep` finds it only in `runs/diagnose/`.

### 1.3 What it means for the product

Simulated with the repository's own event-log detector, 1,000 runs per cell (`runs/diagnose/interval-impact-v1.json`). **Limits of this simulation:** the error profiles come from SYNTHETIC notes; missing events are modelled as lost intervals, but "extra predicted events are not modelled" (the file's own `error_model` note); and `runs/diagnose/simulate.py` is a scratch copy, not the committed `eventlog/` design study.

| Measure (primary care / diagnostic / treatment interval) | No extraction error | Scribe as is | Scribe + code resolver |
|---|---|---|---|
| Bias in county median interval | 0 | +17.4 / +15.6 / +12.6 days | +0.17 / +0.09 / +0.06 days |
| Power to locate a 20% slowdown (n = 473 / 513 / 347) | 0.765 / 0.770 / 0.758 | 0.234 / 0.131 / 0.080 | 0.743 / 0.742 / 0.751 |
| False flag: one county documented in text, the rest from structured fields | - | 1.000 | 0.001 |
| False flag: county notes written like Haiku's, country like Nemotron's (primary care) | - | 0.022 | 0.001 |

The last two rows are an equity finding in their own right. Extraction errors can manufacture inequality between counties that does not exist, and so can a difference in documentation style. With the older v2-selected adapter, the writer-style row is 0.126 as is; S-1b plus the resolver is still 0.042.

`DATA_COLLECTION.md` section 4 still says "text extraction is not accurate enough to fill the county indicator without a person confirming every extracted date". That conclusion predates the resolver and needs a rerun before it changes.

### 1.4 Other measured facts

- The review cascade at a 5% error target: with Jev scores, 263/700 notes fall in the "no edit needed" group, with 7 errors among them; with student confidence, 270/700, with 28 errors (`scribe/TEACHING.md`, which calls this "skip review"; in the product a person still confirms every note).
- Nemotron reading its own notes back blind matched 1,465/1,589 (92.2%), but only 170/238 no-event notes (`data/scribe/v3/summary-v1.json`). This is optimistic, because they were its own notes.
- Adding Haiku-written training notes lifted the Haiku-written test from 13.0% to 47.5%, and the pooled figure from 33.7% to 43.6% (`data/scribe/v3/student/compare-v1.json`). Adding 1,506 more Nemotron notes moved the Nemotron-written test from 210 to 209 (`scribe/TEACHING.md`).
- vLLM serving of the 270M adapter on an A100: 100/100 valid JSON, p95 latency 1.80 s, 5.74 notes/s (`TRAINING.md`).
- Evo 2 BRCA1 benchmark: 2,150 of 3,893 variants scored. AUROC is 0.82 overall, but missense is only 0.68-0.71 against CADD's 0.76 (`genomics/README.md`).
- The scribe, its training data and all its tests are Finnish only. No file in the solution mentions Swedish or Sámi notes (a `grep` found only one reference to the "Danish and Swedish model" of cancer pathways in `src/recommend.mjs`).

### 1.5 The gap to winning each track

| Track | What the judges score (repo capture of the challenge pages) | Where SAMA stands | Gap |
|---|---|---|---|
| AstraZeneca "Equal Care Across Finland" (main) | Actionability 30%, Insight 25%, Data quality & transparency 20%, Execution 15%, Clarity 10% (`../../docs/challenge-research/official-detail-pages.json`) | Real-data navigator with an evidence library and checked briefs. Another integrator is wiring the supporting tracks into the app right now (`runs/integrate-tracks-v3.jsonl`, 20:45 UTC; `npm test` now has 72 tests) | No deck or video yet. Actions not tied to the national implementation roadmap. The data-collection story still says extraction is too weak. Language scope (Finnish only) is not stated |
| Google DeepMind "Best Use of Gemma" | "Innovative and impactful use", "strong technical execution", the potential of open models (repo capture of tech-challenges/47) | 43.6% headline; the fix is a regex, not Gemma | A Gemma retrained to copy dates and leave the arithmetic to code, proven on a fresh frozen set against a fair regex baseline |
| NVIDIA "Best Use of Nemotron" (2 x RTX 5080) | Meaningful Nemotron usage, technical execution, quality of AI output, creativity, 25% each. Requires "Use NVIDIA Nemotron 3.5 Super VL model in the working solution" plus a text on "how you improved its outputs" (`../../docs/challenge-research/official-tech-briefs.md`) | Nemotron is used only offline, as the note writer. Its vision input is unused | **Fails the minimum.** Nemotron must run inside the product, with a measured "how we improved it" table |
| Verda Compute Track | Ambition, Fit, Working prototype, Path to scale, 25% each. Minimum: a documented process and a summary link in Verda's Discord. The brief asks teams to "build something you couldn't build on a laptop" (repo capture) | A100 training runs and the vLLM smoke test are documented. The Verda-hosted Nemotron teacher wrote 3,222 training notes (about 13 requests/s, `runs/teacher2.jsonl`) | A Discord post and a path-to-scale slide built on what really needed Verda. A live endpoint needs a top-up |

**Can we still enter every track?** UNVERIFIED. Every challenge page captured on Friday 13 November at 18:11 UTC shows "Status: Closed" next to a countdown of "T -15:48", which ends around Saturday 10:00 UTC. What it counted down to is not recorded. `../../docs/JUNCTION_SUBMISSION.md` notes a one-team-per-challenge rule and says entering every challenge "has not been verified". The owner must check the submission form before Lane B spends six hours on Nemotron (section 4, decision 2).

---

## 2. The full map of NVIDIA possibilities

Verdicts:
- **Do now**: on the critical path tonight.
- **Do if time**: only after "Do now" items are done, or in a spare lane.
- **Vision only**: a roadmap line or slide; do not build tonight.
- **Not worth it**: adds nothing for SAMA.

Hours are engineering hours. "GPU" means NVIDIA GPU time on Verda, which needs a top-up. Costs come from the inputs unless marked as my estimate.

### 2.1 Training

| Component | What it would do for SAMA | Verified (source) | Hours | Cost | Impact | Verdict |
|---|---|---|---|---|---|---|
| NeMo AutoModel (Apache-2.0; SFT, LoRA/QLoRA, knowledge distillation; default SFT config runs on one GPU) | Train a larger Gemma (3 4B, 4 E2B). Its fused linear cross-entropy avoids the 262k-vocabulary logits memory that likely crashed 4B | Yes (R) [github](https://github.com/NVIDIA-NeMo/Automodel); fused loss (S) [docs](https://docs.nvidia.com/nemo/automodel/latest/nemo-automodel/nemo_automodel/components/loss/linear_ce.md); Gemma 4 recipes are VLM, 8-GPU examples (S) [docs](https://docs.nvidia.com/nemo/automodel/v0.5/model-coverage/vision-language-models/gemma-4) | 2-4 + 0.5-2 GPU | USD 0.5-10 | Unknown. Size did not fix dates (1B 6/367 vs 270M 2/367) | Vision only |
| NeMo RL GRPO/GSPO/DAPO + NeMo Gym verifiers (Apache-2.0) | RL with a code-checked reward: event F1, format, no-event penalty | Yes (R) [github](https://github.com/NVIDIA-NeMo/RL); Gemma 4 recipes need 1x8 to 4x8 GPUs (S) [docs](https://docs.nvidia.com/nemo/rl/latest/guides/models/gemma/gemma4.html); Gym structured_outputs environment (S) [list](https://docs.nvidia.com/nemo/gym/evaluation/environment-list). Single-GPU Gemma 3 GRPO UNVERIFIED | 6-10 + 1-2 GPU | USD 3-10 | Unmeasured. Published gains are mostly out of domain ([R1-RE](https://arxiv.org/html/2507.04642v2), S) | Vision only |
| TRL GRPOTrainer on one NVIDIA GPU (not NVIDIA software) | Same RL, with a quicker setup | Yes (S) [docs](https://huggingface.co/docs/trl/main/en/grpo_trainer) | 2 + 1-2 GPU | USD 1-3 | As above; only after the expression format | Vision only |
| NeMo RL DPO (LoRA) | Preference pairs: the student's wrong JSON against the answer key | Yes (S) [docs](https://docs.nvidia.com/nemo/rl/latest/guides/dpo.html) | 3-4 | USD 0-2 | A guess of +1-3 points | Vision only |
| Same-family distillation (AutoModel KD, TRL GKD) | Gemma 12B teacher to 270M student | Yes (S) [KD](https://docs.nvidia.com/nemo/automodel/recipes-e2e-examples/knowledge-distillation.md), [GKD](https://huggingface.co/docs/trl/main/en/gkd_trainer) | 4-6 | USD 10-25 (H100) | Only worth it if a teacher beats the student on validation | Vision only |
| Cross-tokenizer distillation from Nemotron (NeMo RL X-Token, TRL GOLD) | Soft targets from Nemotron | Yes (S) [docs](https://docs.nvidia.com/nemo/rl/latest/guides/xtoken-off-policy-distillation.html): teacher and student must share one node | - | Multi-GPU node | None: our labels are exact answer keys | Not worth it |
| NeMo Customizer / Microservices / NeMo Helix | Managed fine-tuning | Yes (S): archived; Microservices sunset 1 Oct 2026; no Gemma in the tested list [archive](https://archive.docs.nvidia.com/nemo/microservices/latest/customizer/models/index.html), [Helix](https://github.com/NVIDIA-NeMo/nemo-platform) | Hours | - | None | Not worth it |
| Megatron Bridge | Gemma 3 recipes | Yes (S): 8-GPU recipes [docs](https://docs.nvidia.com/nemo/megatron-bridge/latest/models/gemma/gemma3.html) | - | - | None | Not worth it |
| Transformer Engine FP8/NVFP4 | Faster training | Yes (S): small GEMMs "may see little benefit or even a slowdown" [docs](https://docs.nvidia.com/deeplearning/transformer-engine/features/low_precision_training/speedups.html) | - | - | None | Not worth it |
| NeMo Framework repository | LLM training | Yes (S): "pivoted to focus on audio, speech, and multimodal LLMs" [github](https://github.com/NVIDIA-NeMo/NeMo) | - | - | None | Not worth it |
| Verda 1x A100 SXM4 80GB spot (USD 1.193/h; on demand 2.386/h) | CUDA rerun of the winning recipe, comparable with the earlier A100 runs; a first 4B number on an unshared card | Listed as available in FIN-01 by read-only `verda vm availability --spot` at 20:49 UTC (R). The 1B run peaked at 39.8 GiB, so a 40 GB card is risky (`data/scribe/v3/student/S-1b-lora-r16/result.json`). Whether 4B fits on 80 GB: UNVERIFIED | 1.5-3 | USD 1-4 | Credibility, not accuracy | Do if time, only with a top-up |
| Verda V100 spot (USD 0.122/h) | Cheap training | V100 lacking bf16 is general knowledge, not checked today (UNVERIFIED). `TRAINING.md` records Gemma 3 overflowing in fp16 | - | - | - | Not worth it |

### 2.2 Data

| Component | What it would do for SAMA | Verified (source) | Hours | Cost | Impact | Verdict |
|---|---|---|---|---|---|---|
| Nemotron 3.5 Super VL as writer (any route in 2.3) | It already wrote 3,222 of 3,860 v3 training notes (writer column of `data/scribe/v3/dataset/train.parquet`). Tonight: a frozen stress set with new date phrasings, then targeted notes for the residual errors | Yes (R) [model card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-BF16). Finnish not named; see 2.3 | 2 | Route-dependent; Jev about USD 0.06 per 1,000 notes (repo figure) | Makes the headline trustworthy | **Do now** |
| Gemma 4 31B as a second writer (NVIDIA Build) | A writer the student never saw, for the stress set. A licence-clean alternative to Haiku-written training notes (see 4, decision 11) | Yes (R): "over 140 languages", "Structured Output: Not supported", "Function Calling: Supported", "NVIDIA Open Model License Agreement", "Additional Information: Apache License, Version 2.0", trial terms [page](https://build.nvidia.com/google/gemma-4-31b-it). Terms for training on its outputs: UNVERIFIED | 1-2 | Trial; free status not stated on the page | Credibility and the Gemma story | Do if time (needs a key) |
| NeMo Data Designer (Apache-2.0, `pip install data-designer`) | A declarative version of our teacher loop: mixed writers, Python validators, LLM judges, seed data from validation errors | Yes (R) [github](https://github.com/NVIDIA-NeMo/DataDesigner): "NVIDIA Build is intended for evaluation and testing purposes only"; telemetry off with `NEMO_TELEMETRY_ENABLED=false` | 5-7 | Haiku about USD 1.2 per 1,000 notes | Medium after the date fix, but our loop already exists | Vision only |
| NVIDIA Data Flywheel Blueprint | A production flywheel | Yes (R): "Deprecation notice (Apr 2026): This project is deprecated"; 2-6 H100/A100; Llama 3.2 1B student only [github](https://github.com/NVIDIA-AI-Blueprints/data-flywheel) | - | - | Copy its base / in-context / fine-tuned evaluation arms as a method | Not worth it (method only) |
| NeMo Curator | Deduplication and filtering | Yes (S) [github](https://github.com/NVIDIA-NeMo/Curator), [NGC](https://catalog.ngc.nvidia.com/orgs/nvidia/containers/nemo-curator) | - | - | 4,000 notes is too small to need it | Not worth it |
| Nemotron reward and GenRM models | A third judge | Yes (S): English only, 4,096 tokens, one to sixteen 80 GB GPUs [70B reward](https://build.nvidia.com/nvidia/llama-3_1-nemotron-70b-reward), [GenRM](https://huggingface.co/nvidia/Qwen3-Nemotron-32B-GenRM-Principle) | - | - | They score helpfulness, not whether the events match the note | Not worth it |
| NeMo Safe Synthesizer (Gretel's DP tabular synthesis lineage) | A privacy-safe synthetic release of the pathway-interval table, with quality and privacy scores | Yes (R): "Linux only", "NVIDIA GPU (A100 or larger)" [github](https://github.com/NVIDIA-NeMo/Safe-Synthesizer). DP-SGD with epsilon 8 by default (S) [docs](https://docs.nvidia.com/nemo-platform/latest/documentation/synthesize-safe-data/about/data-synthesis). gretel.ai redirects to NVIDIA's page (S) [page](https://www.nvidia.com/en-us/use-cases/synthetic-data-generation-for-agentic-ai/) | 3-5 | USD 2.4-3.6 GPU | Strengthens the publication story | Vision only (slide) |
| SDG-PGMs, Anonymizer, Nemotron-Personas, Nemotron PII datasets | Personas, de-identification, PII data | Yes (S): no DP / tested mostly in English / no Nordic personas / no Finnish [SDG-PGMs](https://github.com/NVIDIA-NeMo/SDG-PGMs), [Anonymizer](https://github.com/NVIDIA-NeMo/Anonymizer), [Personas](https://huggingface.co/collections/nvidia/nemotron-personas) | - | - | None tonight | Not worth it |

### 2.3 Inference and hosted models

**Three routes to the same Nemotron 3.5 Super VL.** The NVIDIA minimum names this exact model, so these rows matter most.

| Component | What it would do for SAMA | Verified (source) | Hours | Cost | Impact | Verdict |
|---|---|---|---|---|---|---|
| **Route 1: event endpoint** (`containers.datacrunch.io/nemotron-3-5-super-vl-b300`, hosted by Verda with NVIDIA) | (a) Escalation reader in the scribe cascade, with a measured prompt v0/v1/v2 table. (b) County action-plan drafter that calls SAMA's own tools. (c) Stress-set writer | On 14 Nov "authenticated model discovery, text generation, one structured function call and basic image input returned HTTP 200" (`~/.agents/docs/nemotron-junction.md`, a repo receipt; not rerun). It uses its own inference key, not a GPU VM. It is **not** among our account's containers: read-only `verda container list` at 20:47 UTC shows only three paused H100 `junction-cuda-*` deployments (R). Whether it keeps working when our balance reaches zero: UNVERIFIED. Price and quota: UNVERIFIED | 5.5-6.5 (both uses) | UNVERIFIED | Meets the Nemotron minimum. Serves AstraZeneca Actionability (30%) | **Do now** |
| **Route 2: NVIDIA Build** `nvidia/nemotron-3.5-super-vl-120b-a12b` (NVFP4) | Same uses; the planned fallback | Yes (R) [page](https://build.nvidia.com/nvidia/nemotron-3.5-super-vl-120b-a12b): input "Text, Image, Video"; function calling and structured output listed as supported; "NVIDIA API Trial Terms of Service"; base URL `integrate.api.nvidia.com/v1`. Listed in [/v1/models](https://integrate.api.nvidia.com/v1/models) (R). Free status and rate limit not stated on the page. The repo capture of the NVIDIA brief calls NVIDIA Build "Free hosted APIs", reports about 40 requests/min per key from forums, and says "each teammate should use their own key". **No key was found on this MacBook** | 0.25 owner + 0.5 | Trial (UNVERIFIED as free) | Removes the single-endpoint risk | **Do now: owner gets a key** |
| **Route 3: OpenRouter** `nvidia/nemotron-3.5-super-vl` | Same uses; a paid backup | Yes (R), public [model list](https://openrouter.ai/api/v1/models) at 20:48 UTC: USD 0.15 per 1M input tokens, USD 0.47 per 1M output tokens, 1,048,576 context, input text/image/video, supports `tools`, `tool_choice`, `structured_outputs`, `response_format`, `reasoning`. A `:free` variant is listed. The brief's capture says free variants are capped at 20 requests/min and 50/day (1,000/day after buying 10 credits); not checked on OpenRouter's own page (UNVERIFIED). Provider data handling: UNVERIFIED | 0.5 | My estimate: under USD 2 for all of Lane B (about 3,000 calls at roughly 1,000 tokens in and 300 out) | Cheapest reliable fallback | Do if Routes 1-2 fail; needs an account and credits (owner) |
| What the model card says about languages | - | (R) [BF16 card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-BF16): "English, 19 other spoken languages". The NVFP4 card's Common Crawl list names Swedish but not Finnish (R) [NVFP4 card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4). The Build page's bias subcard says "Constrained to English-language inputs. Multi-lingual parity is not currently claimed or guaranteed." (R) | - | - | Planner output in English; Finnish quality rests on the code check, Jev gate and Haiku audit | - |
| Nemotron 3.5 Super VL **vision** (page images) | Read a SYNTHETIC scanned referral letter as a picture and propose events through the same schema, resolver and person-confirm path | "Documents can be supplied as page images with accompanying text"; JPEG/PNG; video MP4 up to 2 minutes (R) [NVFP4 card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4). Basic image input on the event endpoint returned HTTP 200 on 14 Nov (guide above). OCR quality on Finnish text: UNVERIFIED | 1-1.5 | About 40-60 calls | Creativity (25% of the NVIDIA score) | Do if time (Lane B, after step 6) |
| Self-hosted Nemotron 3.5 Super VL NVFP4 | Production path: the escalation tier runs inside a county-controlled or Finnish-hosted environment, so real notes never reach a trial endpoint | Deployment options "1× DGX Spark, 1x NVIDIA RTX PRO 6000, 1× H200, 2× H100, or 1× GB200", OpenMDW-1.1 (R) [NVFP4 card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4). Another project ran it locally on two GPUs and passed five text/image/typed-tool probes (`../../docs/VERDA_SERVICE_MAP.md`, line 85) | 0.5 (slide) | 0 tonight | Answers "real notes cannot go to a hosted API" | Vision only (slide) |
| Nemotron 3.5 Bolt E4B (`nvidia/nemotron-3.5-bolt-e4b`) | An offline Nemotron-family reader on the Mac, and a "Gemma inside Nemotron" bridge line: it is "post-trained from Gemma-4-E4B-it" | Yes (R) [card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Bolt-E4B-4GB): OpenMDW-1.1 (Gemma 4 under Apache 2.0), Q4_K_M GGUF 6.18 GB, llama.cpp with a macOS installer, tool calling; languages "English, Spanish, French, German, Italian, and Japanese, among others" (Finnish not named). Listed in /v1/models (R). It is **not** Super VL, so it does not meet the NVIDIA minimum | 1-2 | 0; 6.2 GB of the 19 GiB free disk | Small | Do if time, only as an offline demo fallback |
| Nemotron 3.5 Lightning 30B-A3B | A cheap bulk reader | Yes (R) [page](https://build.nvidia.com/nvidia/nemotron-3.5-lightning-30b-a3b): 30B total, 3B active; function calling and structured output supported; languages English, Spanish, French, German, Italian, Japanese; OpenMDW-1.1; released 11 Aug 2026. Not Super VL | - | Trial | Small | Not tonight |
| Nemotron Parse 2.0 | Turn document images into markdown | Yes (R) [page](https://build.nvidia.com/nvidia/nemotron-parse-2.0): 905M parameters, NVIDIA GPU on Linux, Finnish not named | - | - | Our notes are text; `pdftotext` already reads the roadmap PDF | Not worth it |
| Gemma 4 31B, Gemma 3 4B/12B on NVIDIA Build | "Gemma at every scale" baselines; an unseen writer | Listed in /v1/models (R); 31B page as in 2.2 (R). Its JSON must be validated locally | 1-2 | Trial | Gemma story | Do if time (needs the key) |
| NIM structured generation | `guided_json`, `guided_regex`, `guided_choice`, `guided_grammar`; "The default guided decoding backend is XGrammar" | Yes (S) [docs](https://docs.nvidia.com/nim/large-language-models/1.15.0/structured-generation.html) | 1-2 | 0 (same mechanism in our vLLM path) | +1-2 points, plus a groundedness guarantee once dates are enums of note spans | Do if time (vLLM tonight; NIM on the slide) |
| Model-Free NIM + LoRA (`NIM_PEFT_SOURCE`), air-gapped | Serve our Gemma LoRA inside a hospital network | Yes (S) [model-free](https://docs.nvidia.com/nim/large-language-models/latest/deployment/model-free-nim.html), [LoRA](https://docs.nvidia.com/nim/large-language-models/latest/advanced-use-cases/finetune-lora.html), [air-gap](https://docs.nvidia.com/nim/large-language-models/latest/deployment/air-gap-deployment.html). Production "requires an NVIDIA AI Enterprise license", "available as a free 90-Day license" (S) [FAQ](https://forums.developer.nvidia.com/t/nvidia-nim-faq/300317) | 1 (slide) | 0; a live proof is USD 5-10 plus an NGC key | Credibility | Vision only (slide) |
| Model-specific Gemma 3 1B NIM / Gemma 4 NIM | Serve Gemma | Yes (S): LoRA "No" [1.15 list](https://docs.nvidia.com/nim/large-language-models/1.15.0/supported-models.html), [support matrix](https://docs.nvidia.com/nim/large-language-models/latest/reference/support-matrix.html) | - | - | Cannot host our adapter | Not worth it |
| TensorRT-LLM, Triton, Dynamo | Faster serving | Yes (S) [TRT-LLM](https://nvidia.github.io/TensorRT-LLM/models/supported-models.html), [Triton](https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/index.html), [Dynamo](https://github.com/ai-dynamo/dynamo) | - | - | Speed is not the problem | Not worth it |
| NeMo Guardrails 0.24.1 (Apache-2.0) + Nemotron 3.5 Content Safety | Refuse requests for clinical advice around the planner | Guardrails (S) [github](https://github.com/NVIDIA-NeMo/Guardrails). Content Safety is built on Gemma 3 4B IT with LoRA; Finnish is not among its 12 trained languages (S) [blog](https://huggingface.co/blog/nvidia/nemotron-3-5-content-safety) | 1-2 | 0 library; hosted guard needs the key | Small. Number match plus Jev already stopped 460/460 corrupted sentences | Vision only |
| NeMo Retriever embed/rerank (Finnish evaluated) | Retrieved few-shot examples for a second reader | Yes (S) [embed](https://build.nvidia.com/nvidia/llama-3_2-nv-embedqa-1b-v2), [rerank](https://build.nvidia.com/nvidia/llama-3_2-nv-rerankqa-1b-v2) | 2-3 | Trial | Conditional on a second reader | Not tonight |
| Riva Translate 4B Instruct v2 (Finnish, Swedish) | Swedish county briefs | Yes (S) [page](https://build.nvidia.com/nvidia/riva-translate-4b-instruct-v2) | 1.5-2.5 | Trial | Low-medium; scope creep | Vision only |
| Parakeet-TDT-0.6B-v3 (CC-BY-4.0) | Finnish dictation turned into a note, then events | Yes (S): Finnish supported, FLEURS WER 13.21% [card](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) | 2-3 | 0 / trial | Small, memorable | Vision only |
| OpenCode free Nemotron models | Backup Nemotron for coding agents | Yes (S): work only inside OpenCode, prompts logged, no personal data [docs](https://opencode.ai/docs/zen/) | 0 | 0 | Not usable as a pipeline API | Not worth it for the product |
| Verda serverless L40S (vLLM, scale to zero, USD 2.22/h) | A public scribe endpoint | Yes (S) [Verda](https://verda.com/serverless-containers) | 2.5 | USD 3-6 | Verda "working prototype" | Not tonight, unless topped up and a lane is free |
| NVIDIA Brev | Deploy open weights | Only mentioned in the brief ("deployment on Brev"). Credits for teams: UNVERIFIED | - | - | - | Ask at the NVIDIA table; not tonight |

### 2.4 Healthcare platforms

| Component | What it would do for SAMA | Verified (source) | Hours | Cost | Impact | Verdict |
|---|---|---|---|---|---|---|
| NVIDIA FLARE federated statistics (simulator) | Each county computes its own waiting-time table, and only suppressed aggregates leave. An interim route to county benchmarking before the national register reports | Yes (R): count, sum, mean, std_dev, histogram, quantile; "We do not include min and max values"; MinCountCleanser, HistogramBinsCleanser [example](https://github.com/NVIDIA/NVFlare/tree/main/examples/advanced/federated-statistics). nvflare 2.9.1, Apache-2.0, PyPI OS classifier "POSIX :: Linux" only (S) [PyPI](https://pypi.org/pypi/nvflare/json). macOS install UNVERIFIED | 4-6 (45-min install kill) | 0 | High for the AstraZeneca "how do we get the data" story | Do if time (spare lane) |
| FLARE federated LoRA (`llm_hf` example) | Train the scribe across counties without moving notes | Yes (S) [example](https://github.com/NVIDIA/NVFlare/tree/main/examples/advanced/llm_hf) | 1 (slide) / 6-8 (sim) | 0 | Narrative. Our own numbers show why writer variety matters (13.0% to 47.5%) | Vision only |
| MONAI model zoo / Deploy / Label | Incidental lung-nodule follow-up on existing CTs | Yes (S): a lung-nodule detector exists; no mammography cancer detector [zoo](https://github.com/Project-MONAI/model-zoo/tree/dev/models) | 1-2 (slide) | 0 | Low | Vision only |
| Clara Reason (NV-Reason-CXR-3B) | - | Yes (S): non-commercial licence, chest X-ray only [card](https://huggingface.co/nvidia/NV-Reason-CXR-3B) | - | - | None | Not worth it |
| BioNeMo ESM-2 + Clara CodonFM | Add protein and codon scores to fix the missense weakness | Yes (S) [ESM-2](https://huggingface.co/nvidia/esm2_t33_650M_UR50D), [CodonFM](https://github.com/NVIDIA-Digital-Bio/CodonFM) | 4-9 | 0 local | Low for AstraZeneca | Not tonight |
| Hosted Evo 2 forward (`evo2-7b-forward`, `evo2-40b-forward`) | Finish all 3,893 variants at the published 8,192 bp window | Endpoint (S) [page](https://build.nvidia.com/arc/evo2-7b-forward); logits output (S) [NIM docs](https://docs.nvidia.com/nim/bionemo/evo2/2.2.0/endpoints.md); BRCA1 AUROC 0.87 for BioNeMo Evo 2 7B (S) [docs](https://docs.nvidia.com/bionemo-framework/latest/models/evo2/). Maximum length, dtype and credits UNVERIFIED | 3-5 | Trial; 44-88 GB download (estimate) | Low for AstraZeneca | Not tonight |
| Parabricks, Genomic Analysis blueprint, self-hosted Evo 2 NIM | Faster BRCA analysis | Yes (S) [Parabricks](https://docs.nvidia.com/clara/parabricks/latest), [Evo 2 NIM prerequisites](https://docs.nvidia.com/nim/bionemo/evo2/2.2.0/prerequisites) | - | - | Compute is not what makes BRCA testing unequal | Not worth it |

### 2.5 Optimisation and data science

| Component | What it would do for SAMA | Verified (source) | Hours | Cost | Impact | Verdict |
|---|---|---|---|---|---|---|
| cuOpt (Apache-2.0) | Exact portfolio optimisation | Yes (S): Linux or WSL2, Volta or newer, CUDA 12.0+, macOS not mentioned [requirements](https://docs.nvidia.com/cuopt/user-guide/latest/system-requirements.html). MIP is beta (S) [intro](https://docs.nvidia.com/cuopt/user-guide/latest/introduction.html) | 1-1.5 | USD 0-0.3 | None. The committed test bounds the greedy within 10% of the exhaustive optimum (`tests/navigator.test.mjs`, line 150). A survey's uncommitted CPU run with SciPy HiGHS found the greedy within 0.71% and solves in 90 ms or less (scratch script `.../scratchpad/opt/exact.py`, not in the repository) | Not worth it (HiGHS on CPU if time, committed with a receipt) |
| RAPIDS cuDF/cuML/cuGraph, cudf.pandas | GPU dataframes | Yes (S) [install](https://docs.nvidia.com/datascience/install/) | - | - | None. The code uses no pandas or sklearn. The 50,000,000-episode calibration stage took 13.5 s on CPU (`runs/eventlog-fix.jsonl`, line 8, `elapsed_seconds` 13.54) | Not worth it |
| Warp, PhysicsNeMo, cuopt-agent | - | Yes (S) [Warp](https://github.com/NVIDIA/warp) | - | - | None | Not worth it |

### 2.6 Methods (most run on any hardware, NVIDIA included)

| Method | What it does | Evidence | Hours | Cost | Impact | Verdict |
|---|---|---|---|---|---|---|
| Code resolves relative dates (post-processor) | Regex plus date arithmetic after the model | Measured: `runs/diagnose/resolve-relative-v1.json` | 2 | 0 | Test 305 to 651/700, validation 134 to 289/310, 0 notes worse; bias +17 to under 0.2 days | **Do now** |
| Resolver with a Finnish lexicon (arm A') | Adds about 20 lines: number words, "eilen", "toissapäivänä", "viikko sitten". Frozen and hashed before the stress set exists | Not built. The current regex is digits only (1.2) | 0.5 | 0 | A fair baseline. Without it, the expression arm's win on new phrasings is built in | **Do now** |
| Expression output format: the model writes `{kind: WEEKS_AGO, n: 3}` and code computes the date | Puts the division of labour into Gemma itself | Implemented, never run: `scribe/v2/formats.py`; "Not run: C-format-expression" in `scribe/v2/RESULTS.md`; all 2,354 v2 and 3,860 v3 training rows have `expression_json` (checked) | 3 | 0 (MLX) | Ceiling about 651/700 on the old test; transfer to new phrasings unmeasured | **Do now** |
| Expression schema scope | `EXPRESSION_KINDS = ("ABSOLUTE", "MONTH", "DAYS_AGO", "WEEKS_AGO")` (`scribe/v2/data_tools.py`, line 70). No months-ago, "viime viikolla", or vague "pari viikkoa sitten" | Checked | 0.5 | 0 | Claim only day and week offsets. Vague phrases must go to a person | **Do now (scope statement)**; a `MONTHS_AGO`/`VAGUE` kind is vision only |
| Fresh frozen stress set with held-out phrasing families | The only clean number tonight | Design from the plans; nothing measured yet | 2 | Route cost + cents of Jev | Turns 93% (post hoc) into a trustworthy number | **Do now** |
| Swedish slice (30-50 SYNTHETIC notes) | Measures what the Finnish-only scribe does with Swedish notes | Writers that can do it: Gemma 4 31B (140+ languages, R); Nemotron's corpus list names Swedish (R) | 1 | Route cost | Turns a hidden equity risk into a stated limitation | Do if time. **Must:** state the language scope |
| Two-reader agreement cascade (Gemma + Nemotron) | A note is pre-filled for one-click confirmation only when both readers agree; otherwise it is flagged for editing. A person confirms every note | `scribe/v3/cascade.py` exists | Inside the Nemotron step | Route cost | More notes pre-filled correctly at a fixed error (unmeasured) | **Do now** |
| Snap model dates to the nearest code-resolved span | Alternative post-processor | A survey's uncommitted scratch script (`.../scratchpad/snap.py`): 557/700 on C-270m test | - | - | Dominated by the resolver (651/700) | Drop |
| Grounded constrained decoding (date field = enum of the note's spans) | The model can only pick dates the note states | NIM/vLLM guided decoding (S) | 1-2 | 0 | +1-2 points and groundedness | Do if time (after the expression arm) |
| Constrained decoding on the absolute format | - | Measured: validation 0.361 against 0.361 (`scribe/v2/RESULTS.md`) | - | - | None | Drop |
| Candidate-span classification (EmbeddingGemma, FinBERT baseline) | Classify each code-found date span | Yes (S) [EmbeddingGemma](https://developers.googleblog.com/en/introducing-embeddinggemma/) | 3-5 | 0 | Baseline only | Not tonight |
| Self-consistency + Jev re-check | Vote over k samples; Jev only on disagreements | Yes (S) [paper](https://arxiv.org/abs/2203.11171) | 2-3 | Cents | Small | Not tonight |
| Active learning: one targeted flywheel turn | New teacher notes aimed at the 49 residual errors | Residual error counts measured | 1.5 | Cents | Small (a few points of the remaining 7%) | Do if time |
| RLVR/GRPO, DPO, distillation, larger Gemma | See 2.1 | - | - | - | - | Vision only |

---

## 3. The recommended plan

The winner is the "maximum deliverable NVIDIA depth" plan, with a hard scope cut and the AstraZeneca core grafted in as a mandatory lane:
- Nemotron goes inside the product as escalation reader and county planner, with a second route ready.
- Gemma is retrained to copy dates while code computes them, and is compared against a fair regex baseline.
- The demo runs offline on the Mac.
- From the AstraZeneca plan: roadmap anchoring, the "fake inequality" insight, a hard deck and video start, and FLARE as a spare-lane stretch.
- From the Gemma plan: held-out phrasing families, preregistration, a within-protocol A/B on MLX, and cascade thresholds set on validation only.

It needs three parallel agent lanes plus the owner. New cloud money: none for the core plan, except a small Verda top-up to protect the event endpoint until its billing is confirmed (decision 1), and optionally USD 2-5 of OpenRouter credit as a Nemotron backup.

**Rules for every lane.**
- A person confirms every extracted event. No wording says notes "skip review" or are "auto-confirmed". We say "pre-filled, one-click confirm" and "needs editing". `scribe/README.md` states that the Gemma Prohibited Use Policy "restricts automated decisions in healthcare, so every extraction stays a proposal that a person confirms".
- One writer per path. Another integrator is editing `src/tracks.mjs`, `web/tracks.mjs`, `README.md` and `web/data/app.json` (`runs/integrate-tracks-v3.jsonl`, 20:45 UTC). Lane C coordinates with it before touching those files.
- All MLX work (training and inference) runs in one queue owned by Lane A. Never two MLX jobs at once: an earlier 1B run at batch 4 used "training process 16 GB, swap used 39.5 of 42.5 GB" and was killed (`scribe/RESULTS.md`, line 49).
- Hosted endpoints receive SYNTHETIC text only.

### 3.1 Timeline (UTC; deadline 08:00, unverified)

| Window | Lane A: Gemma scribe | Lane B: Nemotron | Lane C: AstraZeneca product |
|---|---|---|---|
| 20:55-21:10 | Owner decisions (step 0) | Owner decisions | Owner decisions |
| 21:10-22:30 | Step 1: resolver into the product, plus lexicon arm A' (frozen, hashed). Download the 270M base; time MLX inference on 20 validation notes | 21:15 preflight (step 4a), then step 4: escalation reader | Step 2: roadmap anchoring (coordinate with the tracks integrator) |
| 22:30-01:30 | Step 3: MLX training queue (A, then B). Step 5: stress set generated after A' is frozen | 23:30 on: step 6, county planner | Step 7: demo backend on CPU with PyTorch, precomputed by 00:30. Then step 9 (FLARE stretch) or publication prep |
| 01:30-03:15 | Step 8: preregistered evaluation + cascade | Step 6 checkpoint 02:00; then optional VL test (step 6b) | Deck skeleton; public-repo export prep (step 10) |
| **03:30** | **Code freeze.** Anything not green is reverted | | |
| 03:30-07:30 | Step 10: deck, video, forms, slides (all lanes + owner) | | |
| 07:30-07:45 | Owner submits | | |

### 3.2 Steps

**Step 0. Owner decisions, now to 21:10 UTC (owner, 0.25 h).**
- Why: the Verda balance was USD 1.14 at 20:46 UTC with a burn of USD 2.92/h (read-only `verda status`). It reaches zero around 21:09 UTC. Earlier today Verda deleted every machine when the balance hit zero. The burn comes from one offline instance plus a 100 GB volume in FIN-03. Its owner is not recorded; it is probably the other job's. The balance has fallen from USD 4.65 (brief) to 3.09 (20:00), 2.60 (20:17), 1.63 (20:31) and 1.14 (20:46).
- The event Nemotron endpoint is not one of our containers, so it is probably not billed to us. But it uses a separate Verda inference key, and nobody knows whether it stops when our balance reaches zero.
- Owner decisions: see section 4 (decisions 1-5 are urgent).
- Success: decisions recorded in `PROGRESS.md` by 21:10 UTC.
- Kill: no answer by 21:10 means: every GPU step uses its Mac fallback; Lane B starts on Route 1 and switches to Route 2 or 3 the moment Route 1 fails. No agent touches the offline instance or the volume.

**Step 1. Ship "Gemma reads, code counts" in the product, with a fair baseline (Lane A, 21:10-22:30, 1.5 h, USD 0).**
- What:
  1. Port `runs/diagnose/resolve_relative.py` into `scribe/v3/` as a fixed, declared rule, with unit tests for all six date forms.
  2. Build arm A': the same resolver plus a Finnish lexicon of about 20 lines (number words, "eilen", "toissapäivänä", "viikko sitten"). Write it from general Finnish, not from the stress set. Freeze it and record its sha256 **before** step 5 generates anything.
  3. Call the resolver in `serve/client.py` after schema validation, and in `scribe/v3/cascade.py` before scoring.
  4. Rerun the eventlog design study once (about 12 min of CPU), with the resolver profile and, if time allows, extra and missing events injected per writer. Regenerate the `STUDY:EXTRACTION` block of `DATA_COLLECTION.md` with `audit.py`. Never hand-edit numbers.
  5. Write the "fake inequality" finding (1.000 to 0.001, and the writer-style row 0.022 to 0.001) as an Insight headline, labelled "simulation on SYNTHETIC error profiles; extra events not modelled" until the rerun covers them.
- NVIDIA: none. It runs on CPU after any engine, including vLLM on NVIDIA GPUs.
- Success: repository code reproduces 289/310 validation and 651/700 test for C-270m-all-v2data, with 0 notes worse. The regenerated tables match `interval-impact-v1.json`. Validation is reported as the selection result, test as post hoc. `npm test` stays green (72 tests today).
- Kill: not reproduced exactly by 23:00 means the numbers stay as a labelled analysis result in `runs/diagnose/`.

**Step 2. Tie every action to the national implementation roadmap (Lane C, 21:10-23:30, 2.5 h, USD 0; optional Haiku under USD 0.10).**
- Why: Actionability is 30%. The AstraZeneca-plan step read the roadmap PDF today (https://files.hackjunction.app/resources/Kansallinen_syopastrategia_toimeenpanon_tiekartta_2026_2031.pdf, pages 55-61). It names what SAMA proposes:
  - 2.5.2: standardised referral criteria, piloted in counties 2026-2028.
  - 3.1.4: national quality targets for at least the five largest cancers.
  - 3.2.1: a quality register at the THL Cancer Registry, EUR 2.5M, target of 90% automated clinical notifications by 2030.
  - 3.2.2: benchmarking between counties, EUR 300k.
- What:
  - Map each of the 8 actions and the four-timestamp proposal to a measure ID, with page, owner, schedule and metric, or state "no roadmap measure".
  - Relabel target-time thresholds as placeholders until 3.1.4 defines them.
  - Add a one-county pilot card. State its language scope: the scribe reads Finnish notes only; notes in other languages go to manual entry.
  - Add a test that every quoted Finnish phrase occurs in the `pdftotext` output of the PDF, whose SHA-256 is pinned in the manifest.
  - Expose the mapping as a `get_roadmap_measure` tool for step 6.
- Owner decision: which county the pilot card names (decision 9).
- Success: 8/8 actions carry a measure ID with a page number or an explicit "none". `npm test` stays green.
- Kill: not integrated by 01:00 means it ships as a deck table and README section only. Never force a mapping the PDF text does not support.

**Step 3. Retrain Gemma in the expression format, locally on MLX (Lane A, 22:30-01:30; 1 h of attention, training in the background; USD 0).**
- Data: the **v2** dataset, `data/scribe/v2/dataset/train.parquet`, 2,354 rows (1,716 Nemotron, 638 Haiku). This is the winning recipe's data. All rows have `expression_json`. Match its budget of 5,184 training examples (324 steps at an effective batch of 16, per `data/scribe/v3/student/RUNS.md`). Whether mlx-lm 0.32.2 supports gradient accumulation was not checked; if not, use more steps at a smaller batch.
- What:
  1. Run the round-trip check first: `resolve_expression(expression_target(row))` must equal the label on every row.
  2. Augment phrasing on the training split only. In about a third of the relative-date notes, code rewrites the phrase into Finnish number words 1-6, "eilen" or "viikko sitten". The target stays the same.
  3. **Hold out** number words 7-12 and "toissapäivänä" for the stress set.
  4. Arms, one at a time:
     - A: 270M, absolute format, on MLX, plus the step 1 resolver (control).
     - B: 270M, expression format with augmentation.
     - C: 1B, expression format, only if B looks promising on validation.
  5. Bases: `mlx-community/gemma-3-270m-it-bf16` (not cached yet; a survey found it ungated) and the cached `mlx-community/gemma-3-1b-it-bf16`.
- Time first: MLX inference speed was never measured (the earlier run recorded only training: 726 s for 1,200 notes, `scribe/RESULTS.md`). Time 20 validation notes per model size before committing to the arm list. Score test and stress sets only for arms that pass validation.
- Why: it moves the fix into the model, which is the story the Gemma jury will credit.
- NVIDIA: training data written by Nemotron 3.5 Super VL. Optional CUDA rerun on a Verda A100 80GB (step 11).
- Success: arm B or C reaches at least 0.90 exact match on validation with code resolution, within 3 points of arm A (McNemar not significant), with under 1% parse failures.
- Kill: if the round-trip check fails on any row, fix the targets first. If B is below 0.80 on validation, skip C and ship A plus the resolver; report the expression arm as "run, not selected".

**Step 4a. Preflight for Lane B (21:15-21:30, a handful of calls).** One owner-approved call with a single tool, and one with `enable_thinking` on, through Route 1. The 14 November receipt shows one function call and one image call worked, but one call is not an agent benchmark. If tools fail: Nemotron writes a JSON "call plan" validated against a schema, code runs the tools and feeds the results back. That is still Nemotron doing tool use. Or switch to Route 2 or 3, whose listings show tool support.

**Step 4. Nemotron as the cascade's escalation reader, with a measured "how we improved it" table (Lane B, 21:30-23:30, 2 h).**
- What:
  1. On the 310 validation notes, run prompt versions:
     - v0: absolute dates.
     - v1: expression format, with the existing `resolve_expression` code computing dates.
     - v2: v1 plus local validation against `serve/schema.json` and one repair retry.
     - Optional v3: v2 with `enable_thinking` on.
  2. Select on validation, then run the 700 test notes once.
  3. Cascade rule: a note is **pre-filled for one-click confirmation** only when Gemma plus resolver and Nemotron agree exactly; otherwise it is **flagged for editing**. A person confirms every note either way. Set thresholds on validation only, with the leak guard in `cascade.py`.
  4. Report Haiku-written notes as the primary slice. The 92.2% read-back was on Nemotron's own notes and is optimistic.
- NVIDIA: Nemotron 3.5 Super VL; `enable_thinking` as one measured arm.
- Cost: about 1,700-2,400 calls. Route 1 price UNVERIFIED; on Route 3 my estimate is under USD 1. No OpenAI Decisions calls.
- Success:
  - A validation table v0 to v1 to v2 (to v3) with Wilson intervals.
  - On test at a 5% validation-set error target: the share of notes pre-filled correctly for one-click confirmation, and the error among them, against today's 263/700 with 7 errors.
  - A plain "N of 100 notes need no edit before the person confirms".
- Kill: errors above 10% or unreachable for 30 min on the current route means switching route. If no route works, the round-2 read-back becomes the Nemotron evidence.

**Step 5. Build a fresh, frozen stress set (Lane A, 22:30-00:30, 2 h, after arm A' is frozen).**
- What:
  1. Draw 240-300 new answer keys with a new seed from the existing sampler.
  2. Render required date phrases: the held-out families from step 3, the six standard forms, and about 10% vague or month phrases ("pari viikkoa sitten", "viime kuussa") whose correct outcome is "send to a person". Score those separately: does the model invent a precise date?
  3. Add terse (25-49 words), long (110-260 words) and no-event notes.
  4. Writer: Gemma 4 31B on NVIDIA Build if the owner's key works, because the student never saw it. Its page says "Structured Output: Not supported", but notes are free text, so this does not matter here. Otherwise Nemotron with new phrasing. Stagger calls with Lane B.
  5. If a writer is available: a 30-50 note Swedish slice, scored separately as a limitation.
  6. Gate: code checks that each phrase appears verbatim and resolves to the key; then the Jev gate.
  7. Write the sha256 and a preregistration JSON (arms A, A', B, C; primary comparison B against A'; test once) **before** any model sees the set.
- Cost: Jev about USD 0.02-0.05; route cost as above.
- Success: at least 250 accepted notes, at least 40% with a held-out phrasing; hash and preregistration written first.
- Kill: fewer than 150 accepted by 01:30 means a deterministic, code-rendered phrasing shift of validation and test notes. Label it as such, not as an unseen writer.

**Step 6. Nemotron county action-plan drafter with tool calls (Lane B, 23:30-03:00, 3.5 h; checkpoint at 02:00).**
- What:
  - Batch mode, one run per county (23 counties).
  - Nemotron gets four tools: `get_county_brief` (`src/claims.mjs`), `get_portfolio(budget_meur, equity_weight)` (optimiser rows in `web/data/app.json`), `get_evidence(action_id)` and `get_roadmap_measure` (step 2).
  - It writes three actions, each with an owner role, an indicator and the roadmap measure it serves, plus one line on what the evidence does not support.
  - Every sentence passes the number check against tool outputs and then TypeSafe Jev. Failed sentences are dropped, never repaired.
  - Output is in English, because the model card does not name Finnish and the Build page says it is "Constrained to English-language inputs". Finnish stays in the Haiku path.
  - The UI panel says "Draft for a planner, drafted by Nemotron 3.5 Super VL; numbers checked".
  - **The demo shows cached plans by default.** One live call is optional, with a recorded fallback: the event endpoint may be switched off before judging at 12:00 UTC Sunday.
- Cost: about 50-100 calls; Jev cents.
- Success:
  - At least 20/23 counties get a plan with at least 3 kept sentences.
  - 0 kept sentences contain a number that does not equal a tool output.
  - 10 scripted off-limits prompts (individual treatment advice, an invented county, ranking hospitals) are refused or produce no plan.
- Kill: at 02:00, more than 3 of the first 10 counties still failing to parse means falling back to Nemotron rewriting the templated brief under the same gate. If that also fails, cut the step and keep step 4 as the Nemotron story.

**Step 6b. Optional, Lane B after step 6: Nemotron reads a picture of a referral (02:30-03:30, 1 h).**
- What: render 20 SYNTHETIC referral letters to PNG (one rotated, one photo-like). Nemotron reads the image and writes expression JSON, which goes through the same schema, resolver and person-confirm path. Compare exact match with the text-input baseline on the same 20 notes.
- Why: Creativity is 25% of the NVIDIA score, and the "VL" in the model name is otherwise unused.
- Kill: more than 5 of 20 notes with misread "ä/ö" or dates means one honest line in the NVIDIA text ("tested, not good enough yet") and no UI.

**Step 7. Offline demo on the Mac (Lane C, 23:00-00:30, 1.5 h, USD 0).**
- The earlier plan used `scribe/mlx_fallback.py infer`. That does not work as written:
  - it evaluates whole datasets and loads MLX-format adapters;
  - the adapters worth showing (`scribe/v3/artifacts/*/adapter`) are PEFT adapters; `C-270m-all-v2data` sits on `unsloth/gemma-3-270m-it`;
  - `serve/convert_mlx_adapter.py` converts only MLX to PEFT;
  - the 270M base is not in the local Hugging Face cache (only Gemma 3 1B, 12B and Gemma 4 E2B are).
- What instead: `serve/.venv` already has torch 2.15.0, transformers 5.23.0 and peft 0.21.3. Load `unsloth/gemma-3-270m-it` (download size about 0.5 GB, UNVERIFIED) plus the PEFT adapter on CPU in one persistent process behind `POST /api/scribe` in `web/serve.mjs`, then run the resolver. This avoids MLX, so it never competes with step 3.
- The screen shows the note, the highlighted date phrase, the expression JSON or prediction, the computed date, and "a person confirms".
- Precompute 20 demo notes as a fallback. Swap in the step 3 adapter only if it wins and a PEFT export exists.
- Success: at least 18 of 20 demo notes match the stored CUDA outputs (CPU and GPU greedy decoding can differ slightly), at under 3 s per note.
- Kill: not working by 00:30 means the precomputed outputs and a recorded run.

**Step 8. Preregistered evaluation and cascade recalibration (Lane A, 01:30-03:15, 1.75 h, Jev about USD 0.1).**
- What:
  - Score arms A, A', B (and C) on validation (selection), the 700 test notes once (confirmatory, already seen) and the frozen stress set (primary).
  - Report exact match with Wilson intervals, McNemar tests, results by date form and by writer, interval error, parse failures, the vague-phrase outcome and, if present, the Swedish slice.
  - Recalibrate the cascade on validation only, adding the Nemotron agreement signal from step 4.
- Success (preregistered):
  - On stress notes with held-out phrasing, B beats A' (resolver plus lexicon) by at least 10 points (McNemar p < 0.01), and stays at 0.85 or more on standard phrasing. If A' wins, that is the honest headline: "a careful Finnish rule beats the learned reader on these phrasings".
  - At validation-chosen thresholds, at least 60% of notes are pre-filled correctly for one-click confirmation, with 5% or less error among them, against 37.6% (263/700) today. A person still confirms every note.
- Kill: do not tune on the stress set. Report only the 5% target if 2% is unstable on n = 310.

**Step 9. Stretch, spare lane only: FLARE federated county statistics on the SYNTHETIC event log (Lane C, 00:30-02:30; 45-min install kill; USD 0).**
- What:
  - 23 simulated county sites.
  - Log-duration statistics, plus a histogram with a bin edge at each target threshold, which gives the share treated within target.
  - MinCountCleanser with `min_count = 5`, matching SAMA's n < 5 suppression.
  - An equivalence diff against `data/eventlog/county-intervals.json`.
- NVIDIA: FLARE 2.9.1 federated statistics and privacy filters.
- Success: count, mean and SD per county and interval equal the central table to 1e-6, and the suppressed cells are identical.
- Kill: no working install within 45 min on macOS and a further 30 min in an OrbStack Linux container means it becomes one box on the path-to-scale slide. Present the legal fit (Findata, the Secondary Use Act) only as "one possible route, to be confirmed with THL and Findata".

**Step 10. Deliverables and publication (all lanes + owner, prep from 01:30, main work 03:30-07:30, about 4.5 h, USD 0).**
- A PDF deck for non-technical judges, with the technical depth in an appendix.
- A video of at most 120 s.
- A rehearsed demo plus a screen recording as fallback.
- **MIT source.** There is no LICENSE file in the solution folder or at the repository root. The solution sits in a private monorepo next to other projects. Prepare a public export of this folder only, with an MIT `LICENSE`, a Gemma Terms of Use notice for any Gemma derivative, and a secrets and personal-data scan (gitleaks or similar) before anything is published. `.codex-logs/` is git-ignored but present; the challenge-research captures include a sponsor contact address; neither belongs in the export. Time-box 45-60 min. Publishing is the owner's call (decision 10).
- **The adapter is not in the source.** `*.safetensors` and `scribe/v3/artifacts/` are git-ignored. Decide whether and where to publish it (decision 10).
- The NVIDIA form text, built from the step 4 and 6 tables.
- A Gemma write-up.
- A Verda Discord summary built on what really needed Verda: the A100 training runs (`TRAINING.md`) and the Verda-hosted Nemotron teacher that wrote 3,222 notes at about 13 requests/s. The laptop is presented as edge inference, not as a replacement.
- One path-to-scale slide: Model-Free NIM with our LoRA inside the hospital; the Nemotron escalation tier self-hosted as NVFP4 on one RTX PRO 6000 in a county-controlled or Finnish-hosted environment, or person-only; FLARE for county statistics; NVIDIA AI Enterprise for production. Hosted endpoints are for SYNTHETIC text only. Every box is labelled "run" or "design, not deployed", with its doc link.
- A language-scope line in the deck, `DATA_COLLECTION.md` and the pilot card: Finnish notes only; other languages go to manual entry.
- Owner decisions: who records the voice-over; the owner submits the forms and posts the Discord summary, since these are external messages.
- Success: a person outside the team can state the gap and the first action after one viewing. Every number links to a `runs/` or `data/` file.
- Kill: none. If time is short, cut steps 9, 6b, 6 and 3, in that order.

**Step 11. Optional, only with a top-up and a free lane: CUDA confirmation on one Verda A100 80GB spot (USD 1.193/h, listed as available at 20:49 UTC; 1.5 h; USD 2-4).**
- What: rerun the winning recipe with `scribe/v2/run_gpu.sh` and the vLLM structured-output smoke test on the stress set. Copy the results back and delete the instance with a receipt.
- Success: CUDA validation exact match within 3 points of MLX and 100% schema-valid output.
- Kill: no top-up by 23:30, no spot instance within 15 min, or setup longer than 45 min.

### 3.3 The demo story (two minutes)

> A synthetic Finnish note says the referral arrived "kolme viikkoa sitten" (three weeks ago) and treatment started "eilen" (yesterday). On a laptop with wifi off, Gemma reads it. It does not guess dates. It writes what it read, and ten lines of code turn that into calendar dates. A nurse checks the pre-filled events and confirms with one click. That timestamp is what no Finnish county publishes today. Before, Gemma tried the subtraction itself and got 2 of 367 such notes right. Gemma reads, code counts: 93% on the old test (post hoc) and [X]% on a fresh set frozen before scoring. Without this, a county that documents in text would be flagged as slow every time. Nemotron 3.5 Super VL taught Gemma, re-reads the notes Gemma is unsure about, and drafts each county's action plan by calling SAMA's own tools. Every number in the plan is checked, and each action names the roadmap measure it serves. The ask: one county, one cancer, a 2027 pilot.

Write the final script for whichever arm wins in step 8. If arm A' (the lexicon rule) wins, the demo still works, because A' also reads "kolme viikkoa sitten" and "eilen". The current digits-only resolver does not, so the demo must not run on it.

### 3.4 What we drop

- GRPO, DAPO and DPO tonight (NeMo RL or TRL). Code already fixes the dominant error, and these need a funded GPU and setup time.
- Distillation, whether from Nemotron (cross-tokenizer) or from a 12B Gemma. The labels are exact, and no proven-better teacher exists.
- Training Gemma 3 4B or Gemma 4 E2B. Size did not fix dates, 4B ran out of memory twice, and the balance is near zero.
- Untargeted Nemotron note volume. Round 2 moved the Nemotron-written test from 210 to 209.
- The snap-to-nearest-span post-processor (557/700 against 651/700), and constrained decoding in the absolute format (0.361 against 0.361).
- NIM, TensorRT-LLM, Triton or Dynamo deployments, and Verda serverless without a top-up. Speed is not the problem; NIM stays a slide.
- Porting to Data Designer, the Flywheel Blueprint, Curator, Customizer or Helix. The loop exists.
- Lightning, Bolt (except as an offline fallback) and Parse. None of them is the Super VL model the NVIDIA minimum names.
- cuOpt, RAPIDS and Warp. The problems are tiny and the CPU is enough.
- Evo 2 hosted rescoring, ESM-2/CodonFM, Parabricks, MONAI, Clara Reason, Parakeet, Riva Translate and Guardrails. Keep Evo 2 out of the AstraZeneca pitch as a research appendix.
- Simulator frailty recalibration and the CVaR "robust" portfolio. They are real findings, but they change many tables the night before judging. Disclose them as limitations.
- New OpenAI Decisions judge calls. About 1.04M of the 2M daily tokens were already used; Jev only.
- Any wording like "hospital-grade", "clinically accurate", "works on real notes", "auto-confirmed" or "skips review".

---

## 4. Owner decisions needed now

Urgent (before about 21:10 UTC):

1. **Verda.** Balance USD 1.14 at 20:46 UTC, burning USD 2.92/h, zero around 21:09 UTC. Decide whose offline instance (created 18:14 UTC) and 100 GB volume this is, and delete it or top up. Agents will not touch it. **Recommendation:** stop the drain, and also keep the balance above zero with a small top-up (USD 10-20) until the Verda booth confirms that the event Nemotron endpoint does not depend on our balance. The core plan needs no Verda GPU. Spend more only for step 11 (one A100 80GB spot at USD 1.193/h). Skip V100, serverless L40S and 8-GPU nodes.
2. **Open the submission form now.** Confirm that "Best Use of Nemotron" and "Verda Compute Track" can still be selected next to AstraZeneca and Gemma. The challenge pages showed "Status: Closed" on Friday, and a one-team-per-challenge rule exists. If Nemotron cannot be selected, Lane B moves to step 2 and the deck, and Nemotron stays only as the measured escalation reader.
3. **A second Nemotron route.** Get an NVIDIA Build key now (the NVIDIA table or Discord; the brief says each teammate should use their own). Store it in Keychain. Never paste it in chat. Say whether it may be used with SYNTHETIC notes for `nvidia/nemotron-3.5-super-vl-120b-a12b` and `google/gemma-4-31b-it`.
4. **Optional third route:** an OpenRouter account with USD 2-5 of credit for `nvidia/nemotron-3.5-super-vl` (listed at USD 0.15 per 1M input and USD 0.47 per 1M output tokens). This is new spending and needs your yes.
5. **Confirm the deadline and format** on the Junction platform. The repository has only a relayed "Sun 10:00 Helsinki" (08:00 UTC): video of at most 2 min, PDF deck, demo and MIT source.

Tonight:

6. **Event Nemotron endpoint.** Approve about 2,500-3,000 calls with SYNTHETIC notes (steps 4, 5, 6, 6b). Its price and quota to the team are unknown.
7. **Change the demo story** to "Gemma reads, code counts; Nemotron teaches, double-checks and drafts the county plan; every action tied to the roadmap; a person confirms every event". Approve English output for the Nemotron planner, labelled "draft for a planner".
8. **Reporting rule.** Validation is the selection evidence. The 700-note test is labelled "already seen, post hoc". The new frozen stress set is the headline number, and the primary comparison is the expression arm against the lexicon rule A'.
9. **Pilot county** for the action card. The plan suggested Satakunta (1.10 times national cancer mortality) or Lapland (1.24 times for lung cancer). Prefer a county whose clinical notes are written in Finnish, because the scribe reads Finnish only. Lapland includes the Sámi homeland (general knowledge, not checked today).
10. **Publication.** (a) Export this folder to a new public repository with an MIT LICENSE, after a secrets and personal-data scan. (b) Whether and where to publish the adapter (Hugging Face Hub or a release asset). Both are external publications and need your explicit yes.
11. **Haiku-written training notes and publication.** The best adapter was trained on 638 notes written by Claude Haiku. Anthropic's Commercial Terms D.4 say the customer may not "access the Services to build a competing product or service, including to train competing AI models" ([terms](https://www.anthropic.com/legal/commercial-terms), effective 17 June 2025, R). Whether a 270M domain extractor counts as "competing" is a legal question (UNVERIFIED). **Safer option** for any published adapter: train it on Nemotron-written (and Gemma 4 31B-written) notes only, and keep Haiku notes for evaluation. `V3-270m-nemotron` already exists (267/700 as is, 564/700 with the resolver). Disclose the training data either way. Terms for training on Nemotron (OpenMDW-1.1) and NVIDIA Build outputs were not checked today either.
12. **Enter the Verda track?** Only with the honest summary (A100 runs plus the Verda-hosted teacher). If you prefer not to frame the laptop demo against the brief's "something you couldn't build on a laptop", skip it.
13. **Who records the video voice-over, and who submits the forms and posts on Verda's Discord.** These are external actions only you can take.

---

## 5. What is unverified

- **The deadline** (Sun 10:00 Helsinki, 08:00 UTC) and the format. Relayed by an AI review that did not see the participant guide.
- **Whether one project may still enter AstraZeneca, Gemma, Nemotron and Verda.** The captured pages say "Status: Closed" with a countdown to about Saturday 10:00 UTC; its meaning is unknown.
- **The event Nemotron endpoint**: whether it is up now (last used by this project at 18:44:59 UTC), its price, quota and rate limit, and whether it keeps working when our Verda balance reaches zero. It is not on our account's container list.
- **Tool calling and image input at scale.** One function call and one image call returned HTTP 200 on 14 November. Agent-length tool use and OCR quality on Finnish text are untested.
- **Nemotron's Finnish.** No NVIDIA page names Finnish, and the Build page says "Constrained to English-language inputs". The only evidence is 92.2% blind read-back on its own synthetic notes.
- **NVIDIA Build**: whether a key exists, which models it can call, whether the trial is free, credits and rate limit. The "about 40 requests per minute" figure comes from forum posts relayed in the brief.
- **OpenRouter**: the free-variant caps (20/min, 50/day) come only from the brief's capture; how providers handle prompts was not checked.
- **Brev credits** for teams.
- **Licence terms for training on model outputs**: Anthropic D.4 as applied to our adapter, OpenMDW-1.1 and NVIDIA Build trial terms for Nemotron and Gemma 4 31B outputs.
- **The 93% resolver result on real text.** The synthetic notes use six date forms only, and the regex reads digits only. 93% is post hoc on a test set that has been read before.
- **The simulation's extra-event effect.** Extra predicted events are not modelled in `interval-impact-v1.json`.
- **Expression-format gains** are expected, not measured. MLX training and inference times are estimates. Whether mlx-lm 0.32.2 supports gradient accumulation was not checked. The 270M base download sizes (MLX and `unsloth/gemma-3-270m-it`) were not checked.
- **CPU demo parity**: PyTorch on CPU may not reproduce the stored CUDA outputs exactly.
- **Language scope in practice**: how many notes in a given county are written in Swedish or another language. Finland's two national languages and the Sámi homeland in Lapland are general knowledge, not checked today.
- **nvflare on macOS arm64.** PyPI declares Linux only.
- **The legal fit of county-local federated statistics** under Findata rules and the Secondary Use Act. This is an interpretation, to be confirmed with THL and Findata.
- **Whether Gemma 3 4B fits** on a single A100 80GB for LoRA. Single-GPU Gemma 3 GRPO in NeMo RL is also unchecked.
- **V100 lacking bf16** is general knowledge, not checked on a page today.
- **Hosted Evo 2 forward**: maximum length, response dtype, credits, and whether `evo2-40b-forward` really serves 40B.
- **The judges' backgrounds** (marketing and business-excellence staff) come from a planning step.
- **The roadmap measure details** (2.5.2, 3.1.4, 3.2.1, 3.2.2) come from the AstraZeneca-plan step's reading of the PDF. Step 2 must re-check every quote against `pdftotext` before it ships.
- **The HiGHS optimiser figures** (within 0.71%, 90 ms) and the snap post-processor figure (557/700) come from uncommitted scratch scripts.
- **Free disk.** 19 GiB free at 20:45 UTC (`df`), down from 29 GiB at 20:26. Plan downloads and the 6.2 GB Bolt file around that.
