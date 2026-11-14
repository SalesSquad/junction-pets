# Verda Compute Track: Discord summary and documented process

The track's minimum is a documented process plus a link to a summary, posted in Verda's Discord
channel. Posting is an external message, so the team posts it; nothing here has been posted. Fill
`[SUMMARY LINK]` with wherever the team publishes this summary or the repository.

Every number comes from the file named in Part 2, and `submission/check_numbers.py` recomputes it.
All patient-like data are SYNTHETIC.

---

## Part 1. Post for the Discord channel (ready to paste)

Length is measured by `submission/check_numbers.py` (printed as `verda_post_chars`); it must stay
under Discord's usual 2,000-character message limit.

> **SAMA: equal cancer care across Finland (Junction 2026, AstraZeneca challenge)**
>
> Finland cannot yet see how long cancer patients wait from suspicion to treatment, county by
> county. SAMA asks for two dates and an end reason per patient, and reads the optional dates from
> Finnish notes that cannot leave the hospital. We built a small Gemma scribe designed to run inside
> the hospital (so far tested on a laptop CPU, on SYNTHETIC notes only), and used Verda for the two
> parts a laptop could not do:
>
> 1. **A100 80 GB GPU instance (2.51 h, USD 5.98 at list price).** Seven Gemma 3 LoRA fine-tuning
>    runs with results (2,122 s of training), an ablation inside a 35-minute budget, a vLLM 0.29.0
>    structured-output serving test (100 of 100 valid JSON, p95 1.80 s, 5.74 notes/s), and a genomics
>    benchmark for a separate research appendix (Evo 2 7B, 2,150 variants scored in 951 s).
> 2. **Verda-hosted Nemotron 3.5 Super VL (120B parameters).** As a teacher it wrote 3,222 SYNTHETIC
>    Finnish training notes; one run made 3,551 requests in 268.8 s (about 13.2 a second). As a
>    second reader it got 690 of 700 SYNTHETIC test notes exactly right (2,602 requests, 0 errors).
>    With tool calls it drafted an action plan for 23 of 23 areas from public data, every number
>    checked against SAMA's tools.
>
> The laptop is the edge: the 270M-parameter scribe runs on a CPU with wifi off. Verda is where it
> was trained, tested at serving speed, and checked by a 120B model.
> Next step (planned, not deployed): the scribe as a Verda serverless container that scales to zero.
> Real notes never go to a hosted endpoint; that tier would be self-hosted in a county-controlled
> environment.
>
> All patient-like data are SYNTHETIC. Process, numbers and what failed: [SUMMARY LINK]

---

## Part 2. Documented process

### Why compute made this possible

| Job | Verda product | Why not a laptop | Result | Source |
| --- | --- | --- | --- | --- |
| Gemma 3 LoRA fine-tuning (270M and 1B; 4B attempted) | GPU instance, 1x A100 80 GB, on demand | Seven runs and an ablation in one afternoon; the 1B run peaked at 39.8 GiB of GPU memory | 2,122 s of training across 7 runs with a result; ablation used 2,077 s of a 35-minute budget; recommended adapter trained in 176 s | `data/scribe/v2/training-figures-v1.json` (`gpu`) |
| Serving test | same A100, vLLM 0.29.0 with xgrammar structured outputs | Throughput and latency at concurrency 8 | 100 of 100 valid JSON; p50 1.28 s, p95 1.80 s; 5.74 notes/s | `serve/smoke/smoke-guided.json` |
| Evo 2 7B on BRCA1 (research appendix) | same A100 | A 7B genomic model under a 16 GiB memory cap | 2,150 of 3,893 variants scored in 951 s (stopped by its time budget) | `data/genomics/brca1-evo2-v1.json` (`runtime`) |
| Teacher: SYNTHETIC Finnish notes | Nemotron 3.5 Super VL on the Verda-hosted event endpoint | A 120B-parameter model | 3,222 of the 3,860 training notes; round 2: 4,042 requests, 1,506 notes accepted by the TypeSafe Jev gate | `data/scribe/v3/dataset/train.parquet`, `data/scribe/v3/summary-v1.json`, `runs/teacher2.jsonl` |
| Second reader | same endpoint | as above | 690/700 test notes exact; with Gemma, 651/700 pre-filled for one-click confirmation, 4 wrong among them | `data/scribe/nemotron/reader-v1.json`, `data/scribe/nemotron/cascade-agreement-v1.json` |
| County planner with tool calls | same endpoint | as above | 23 of 23 plans; 255 of 299 sentences kept; 0 kept numbers outside the tool outputs | `data/planner/plans-v1.json` |

### From first idea to working prototype

1. Real public data first: the county navigator runs on THL Sotkanet, Statistics Finland and NORDCAN
   data with no GPU at all.
2. The data gap (no referral-to-treatment times) led to the scribe idea. The first planned GPU
   training never ran: the first GPU machine stopped answering and came back with a different SSH
   host key, which we did not accept. Version 1 ran as a reduced fallback on the laptop.
3. A fresh A100 ran the version-2 ablation, the post-ablation data comparisons, the vLLM test and
   Evo 2, and was deleted at 19:27 UTC once the results were copied back.
4. The Nemotron teacher on the Verda endpoint wrote the training notes; tonight the same endpoint
   served as second reader, with a measured improvement ladder (validation exact match 192/310 with
   absolute dates, 304/310 with the final prompt and code checks).
5. Nemotron with tool calls drafted a plan for 23 of 23 areas (93 calls in the selected version;
   `data/planner/plans-v1.json`).
6. The laptop runs the 270M scribe on CPU behind the product's own endpoint: 18 of 20 demo notes
   exact, median 4.8 s per note (`data/scribe/demo/http-timing.json`). The laptop also ran the
   expression-format retrain (MLX) and the FLARE county statistics; neither needed Verda.

### Cost and use recorded in files

- A100 80 GB (`1A100.22V`, listed at USD 2.386 an hour): 16:56:35 to 19:27 UTC, 2.51 h,
  **USD 5.98 at the list price**. Not the invoice.
- Nemotron endpoint: 4,500 teacher requests in round 1, 4,042 in round 2, 2,602 reader requests and
  181 planner requests tonight. Price not read; recorded as unknown, not zero.
- Source: `data/scribe/v2/training-figures-v1.json` (`machine_cost`, `api_spend`),
  `data/scribe/nemotron/ledger.json`, `data/planner/ledger.json`.

### What did not work

- The first GPU machine was lost before version-1 training (above).
- Gemma 3 4B ran out of GPU memory twice on the shared card; a third attempt was stopped. No 4B
  number exists.
- The A100 sat idle for 55.9 minutes between the Evo 2 run and the next set-up; no run log records
  work in that gap.
- The serverless container is planned, not deployed: no image pushed, nothing spent.
- Source: `TRAINING.md` section 10, `data/scribe/v2/training-figures-v1.json`
  (`gpu.gap_between_recorded_gpu_jobs`).

### Path to scale (each step labelled)

| Step | Status | Doc |
| --- | --- | --- |
| Gemma scribe on CPU behind the product endpoint | run (demo, 18 of 20 exact) | `data/scribe/demo/http-timing.json` |
| Scribe on vLLM with structured outputs on an A100 | run (smoke test, 100 notes) | `TRAINING.md` section 8 |
| Scribe as a Verda serverless container, scale to zero (L40S listed at USD 2.22 per GPU-hour) | design, not deployed | `serve/deploy.md` |
| Nemotron second reader self-hosted in a county-controlled or Finnish-hosted environment | design, not deployed | `submission/PATH_TO_SCALE.md` |
| County statistics computed where the data sit (NVIDIA FLARE, simulator, 23 sites, SYNTHETIC) | run on one laptop: 92 of 92 cells equal the central table | `data/flare/RESULT.md` |
