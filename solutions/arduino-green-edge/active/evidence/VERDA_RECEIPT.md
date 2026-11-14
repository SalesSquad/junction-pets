# Arduino M5 — verified provider experiment and independent critique receipts

**Source contract:** private `SalesSquad/junction-pets`, parent M4 commit
`eb7ff4cb7fa6c867ced7d944385b4e0bd08d04c4`, Arduino
`partnerEvidenceKey=arduino`, official briefs `M356,T45`,
14 Nov 2026 source catalog `latestClarification=null` (13 Nov guidance next).
All data/models below are **SYNTHETIC/OFFBOARD**. **NO actual UNO Q, camera
capture, measuring hardware, physical output, environmental savings, field
safety, or deployable Arduino inference** is claimed.

## Genuine Verda CUDA experiment — 14 November 2026

- **Provider/executor:** existing authenticated Verda CLI 1.10.0 on authorized
  MBP, pre-existing FIN-01 Tesla V100-SXM2-16GB, existing machine
  `1V100.4V`; PyTorch 2.9.1+cu128 / NumPy2.2.6 in existing Python3.12
  venv, `torch.cuda.is_available()=True`. No new instance/volume or provider
  contract. One original attempt failed because M3 source files were missing on
  the isolated GPU filesystem; moved the exact pinned files and reran the same
  job with all source SHA guards intact; failed precursor remains in the local
  task log, not a green pass.
- **Dataset:** 52 distinct source-pinned synthetic days at
  `--days=4 --seed=1729`: train/validation/calibration 12 each, test16.
  Train/validation/calibration each 17,280 minute rows; test23,040.
  Features time sin/cos + T + RH + connected + sample age, occupancy label
  ONLY for training/offline scoring; no lux/camera or hidden occupancy feature.
  Novel fault scenario only in test, no test-based tuning.
- **Actual GPU training:** 30 executed epochs, default seed42 and
  batch2048; logged **2026-11-14 13:34:34–13:34:41 UTC**. The
  exact remote weights SHA-256 is
  `fe5cda344fd58b4db7b12ccecfe593d1b7d02ff8c2f2df5e1b377e6a387fbd1f`
  and metadata SHA-256
  `34e39c2690ec8d6c0f2eed038020d8acdc737b94c422180b0eb335acf9d98452`.
  Those files are preserved in this folder, downloaded from the actual GPU.
- **Untouched synthetic test at fixed 0.5 classification threshold**
  (false-negative rate among occupied minute observations):
  winter **2.92%** (49 FN), summer **50.54%** (849 FN),
  evening **26.96%** (453 FN), fault **58.81%** (988 FN).
  Minute observations are temporally correlated; these percentages are
  **not** independent person/day samples or a physical reliability claim.
  Model **NO-GO** for occupied-safe decisions outside this toy generator.
- **Actually executed paired policy evaluator:** locally generated
  64 complete M3 source-bound JSONL packets (16 test days × four
  predeclared nominal/drift/correlated-false-empty/untrusted-camera
  variants), gzip SHA-256
  `5296cb6547a5c113ae947f4356767158ebfe474598a38fd20e15a96ca62d51fe`.
  Transported ONLY those synthetic records to the same VM; `eval_policy.py`
  verifies compressed checksum and all 64 complete 8,640-slot packet identities
  before scoring. Ran **2026-11-14 13:43:08–13:43:17 UTC**; 5 paired strategies
  ×64 cases = **320 actual model/strategy comparisons**. Evaluation JSON
  SHA-256 `95a8770c0738ed5fe9462c7108b0494612862ceff5893b52e5732a2a7ebb1b5a`.
- **Main actual paired findings**, all energy figures from authored,
  unmeasured assumptions (4W board ×24h, 1W always-on camera,
  0.01Wh per query, 40/20W fan/lamp):
  `A_timer_only` net **0 Wh/day**, mean camera queries0;
  `B_always_camera_no_AI` net **−132.67 Wh/day**, queries1440;
  `C_fixed_10min_no_AI` net **−97.26 Wh/day**, queries144;
  `D_selective_model` net **−96.11 Wh/day**, queries **10.9**;
  `E_hold_fixed_10min_no_AI` net **−97.26 Wh/day**, queries144.
  All 64 selective days had **nonpositive net** versus timer.
  Extra missed required fan service vs timer was 0 within THIS artificial
  safety shield, not verified in reality. Overall **verdict NO_GO**.
  Evidence shows fewer queries, not savings. The timer itself can miss
  human service. Camera "truth" is an authored noisy proxy, not a video model.
- **Provenance:** SHA-256 of evaluator
  `7e8026d5c72052f987b7ae772e285d160924fce5f2b249b82ccfd4291aaf0e84`,
  output synthetic weights/model/evaluation files byte-checksum match
  after retrieval. Local Node exporter 6/6 focused tests, Python syntax and
  model-free 320 record smoke were also executed by the source worker.
- **Financial boundary:** user incremental ceiling Verda **$20**.
  Existing running GPU listed $0.244/h compute, existing attached volume
  about $0.0274/h. Two successful runs span roughly 16 seconds; no
  extra provisioned VM/storage. Shared-account balance readbacks are
  delayed and include unrelated jobs. **Actual attributable provider charge
  UNKNOWN, not claimed as $20 spent**. No top-up or new paid provider.

## Requested independent challenges — actually executed

- **Opus 5.5:** authenticated read-only Claude CLI (`--model opus`,
  `--max-budget-usd 20`, restricted/no tools) returned `is_error=false`,
  canonical model `claude-opus-5-5`, **list-price cost estimate
  $0.2490658**, *not an independently confirmed API invoice*.
  Verdict: weak 20/40W room loads cannot plausibly repay always-on board
  standby. Suggested **Open-Window Heat Sentinel**: Thermo drop requests
  region-cropped camera verification of a window, Knob declares intended airing,
  Buzzer/LED advises; NO mains actuation. Example ventilation heat loss
  720W assumes airflow0.03m³/s and ΔT20K, **unmeasured**; no causal savings
  claim. Reject if slower than demo, cannot infer offline, false window closed
  on occluded frame or fails matched-budget random/periodic camera comparison.
- **Haiku 5.5:** separate **public-only** authenticated restricted Claude CLI
  returned canonical model `claude-haiku-5-5`, **list-price estimate
  $0.00391659**, *not confirmed API charge*. Supplied 24 physical adversarial
  tests, including repeated stale video frame, reflective/printed fake window,
  lamp sunlight/steam/radiator confounding, camera disconnect, MCU crash,
  clock rollback, Knob debounce/expiry, receipt overclaim and matched-budget
  random camera baseline. The existing Haiku API budget helper **blocked**
  a separate source-bound request with `api_calls:0` — it was not bypassed
  or counted as successful API spend.
- **Spending controls:** user Opus $20, Haiku $5 as **upper limits**;
  model calls stayed below per-call limits. Their returned CLI costs use
  **list-price basis**, not actual provider billing; neither balance was
  intentionally exhausted. Reviews were read-only and never controlled
  hardware or credentials.

## Engineering decision / next acceptance

**Retire the 20/40W occupied-room AI saver as the winning hardware pitch**:
a V100-trained model failed shifted occupancy recall and gained no net energy
under even the favorable synthetic assumptions. Preserve its honest failure
as a baseline. The higher-value target is **human-in-the-loop heat-loss
verification**, still unimplemented on Arduino hardware. Its first genuine
gate is a borrowed actual UNO Q, Thermo, USB camera/Modulino Knob+Buzzer,
safe low-voltage window rig and a separately calibrated USB-C/wall power
meter. Verify offline board inference, sensor/MCU watchdog and duty cycle,
then run paired physical tests and report real observed power/latency/errors.
Use only an independently authorized FINAL controller for external submissions.

## Window prototype: focused independent code critique and corrections

Separate **Opus 5.5** read-only source audit (second call) returned
`is_error=false`, list-price cost estimate **$0.6401502**.
The earlier strategic Opus review estimated **$0.2490658**; together
Opus **$0.8892160 list-equivalent** (not a confirmed API debit).
A second **Haiku 5.5** read-only source audit returned
`is_error=false`, **$0.01136838** list estimate; prior physical-adversarial
Haiku review **$0.00391659**, together **$0.01528497** list-equivalent.
Both stayed below user-authorized ceilings. The separately blocked Haiku
API-helper request still has **zero** actual calls.

**Source audit repaired before first PR commit:**
- **P1 camera-query liveness:** jittery sub-five-second Thermo samples no
  longer erase the prior valid cooling slope or a pending camera proposal.
  Humidity confounds and insufficient spans cannot rearm a spent episode; a
  stable baseline must last at least 30 seconds before another query.
  One advisement is emitted per camera query rather than each repeated tick.
- **P1 provenance/privacy:** externally supplied hex frame fingerprints are
  no longer retained in kernel state or treated as proof of freshness.
  An explicitly issued, single-use numerical query ID binds the next
  camera response; absent/wrong/reused ID refuses. This guards the
  **synthetic protocol**, not an untrusted physical camera producer, which
  still requires authenticated capture and anti-replay across restarts.
- **P1 intent:** explicit confirmed Knob airing immediately cancels a
  pending camera query and old camera evidence. The hypothetical 720W
  scenario is now labelled UNVERIFIED_ASSUMPTIONS_ONLY and
  physicalUpperBound:false, never a real causal/upper safety claim.
- **Focused qualification:** final window kernel **16/16 Node tests PASS**,
  including the two new regressions for jitter/query IDs and the earlier
  Haiku humidity/intent findings. Its 90-virtual-second CLI demonstrates
  a **proposed** ROI capture and advisory but performs no actual camera
  or physical Buzzer/LED action.

**Unresolved real-world objection (Opus):** why choose camera instead of
a near-zero-power reed contact sensor? The prize hypothesis is retrofit
operation without installing contact sensors on every window, plus visible
on-board AI, but this is still unproven. A physical fair benchmark must
include a contact sensor where permitted, periodic/random camera baselines,
false-open/false-closed frames, reed-sensor installation complexity,
and measured board duty-cycle energy. No external API/MCP or device access
was granted by the critiques.
