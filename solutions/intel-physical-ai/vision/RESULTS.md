# M7 source-bound observations — 14 November 2026

Work ID `J26-INTEL-M330-M7`; base source
`c1e926f624fda2d4063e71a48306d92940d097d3`, initially clean task branch
`codex/j26-intel-vision-m7-20261114`. Only new `vision/**` source is owned.
M6 PR176 is preserved. Coordinator owns independent numerical/provenance review,
push, owning PR and integration. The coordinator successfully claimed M7 in
[#80 comment 6883502501](https://github.com/SalesSquad/junction-pets/issues/80#issuecomment-6883502501),
following M6 release. This worker’s own connector refused with `MCP tool call
requires approval, but approval policy is never`; that worker refusal does not
negate the coordinator’s real claim. Knowledge OS task/evidence
APIs were absent from the runtime catalog (`registry_identity_unverifiable`).
Local `git add` and `git commit` were attempted after checks but could not
create the linked worktree's `index.lock` under the external
`/Users/mikaelervamaa/Developer/junction-pets-20261111/.git/worktrees/` directory
(`Operation not permitted`). No commit or push is claimed. Coordinator should
run `git add -- solutions/intel-physical-ai/vision` and
`git commit -m "feat(intel): add real-image offline PaDiM inspection pipeline"`
from this checkout before independent exact-HEAD review/delivery.

## Preserved precursor results (before focused repair)

- Official split CSV and all 392 real image byte hashes verified by final
  `pipeline.py validate-manifest` (exact command in README). Dataset manifest
  SHA256 `e45d2caa0107fdc2c4fa973fd378d41d87559d9c2b0cc0f6977db4736a71df26`;
  acquisition reports 45,366,227 image bytes. No dataset modification/download
  by this writer.
- One real-data execution attempted, output lab `run-m7`, log `run-m7.log`.
  **BLOCKED before fitting**, no real model scores, calibrated thresholds or
  heldout AUROC. Official timm `resnet18.a1_in1k` weight retrieval failed DNS
  (`nodename nor servname provided, or not known`), no local cached weights.
  No random-weight fallback. Failure artifact and raw traceback retained.
  `verify --output-dir .../run-m7` verifies that failure directory's integrity;
  this is not a model or inference pass.
- Ten boundary tests passed in `check-m7-boundaries-final.log`, including
  hash mismatch, duplicate cross-split hashes, official split leakage,
  normal-only calibration, unsafe paths/symlinks, nonfinite thresholds,
  quantile/tie behavior, corrupted artifact refusal and exclusive output.
- Synthetic-only CPU PaDiM fitting/inference and safe model reload passed in
  `check-m7-separated.log`. That 11-test execution had ten passes and one
  failure: the separate OpenVINO CPU qualification gate. Export converted
  and serialized the model, but CPU readback compilation returned
  `bad err=11 in Xbyak::Error` / plugin `internal error`. **No CPU parity pass**
  and no inference-quality claim. This sandbox-specific error was not bypassed;
  see the later coordinator host fact below.
- Base-R analysis executed successfully on explicitly synthetic plumbing CSV;
  raw file/log are lab `r-synthetic-plumbing.csv` / `.log`. No real evaluation
  CSV exists because no real model fit completed.

Initial synthetic model reload test asserted bit equality and failed at
9.941849708557129 versus 9.941848754882812. Correction classified as an overly
strict plumbing assertion: the already declared 1e-3 absolute/relative numerical
tolerances now apply, unchanged from the experiment. Original
`check-m7-final.log` is retained. The later export failure is retained separately
in `check-m7-reload-tolerance.log` and `check-m7-separated.log`.
No heldout-driven model/seed/threshold change or second real fit occurred.

## Reproduction and evidence

All raw artifacts/logs remain outside Git in the explicitly requested lab:
`/Users/mikaelervamaa/Developer/j26-intel-vision-lab-20261114`.
No iCloud persistence, hosted service, device motion, network listener, paid API
or GPU execution is claimed. Cost is unknown. Producer versions are pinned in
`requirements.txt`; initial real attempt captured them in `run-m7/config.json`.
Its attempted pipeline hash is
`846a8c154946ecb7d5f33a9613bad4080885d6074e9aa4d18ce4dccd6f7d14c5`;
final source additionally validates actual official CSV membership and supports
safe fitted-model inspection. That blocked run does not qualify later code.

Pre-repair pipeline SHA256 (the audited source, not current bytes):
`2ecf3ce6ee4058cf294ceab9602458baf9aaf3d82ec4e6ebdb36b705b1873d04`.
`run-m7.log` SHA256:
`2dfd8101db09fac6991fc55c50bbc348b28effb7919ddf4b43f80b46e2ba7870`.
`check-m7-separated.log` SHA256:
`1a51d0a1595b3295bcd288dfd76bfc3e0768aa2c66e0230186903cb652284254`.

## Focused source repair and coordinator facts

The independent audit (`lab/audit-labels.log`, reported by coordinator) reproduced
heldout label swaps for normal `0790.JPG` / anomaly `000.JPG` accepted by the
structural helper under the pre-repair pipeline hash above. That helper is now
explicitly plumbing-only. Both `run` and `validate-manifest` call
`validate_benchmark`, which enforces the exact immutable manifest byte SHA256
before structural validation, CSV mapping or any sample decode. Even changed
JSON whitespace is refused. Synthetic fixtures cannot enter REAL_DATA_OFFLINE.
This is a provenance correction, not model/seed/threshold tuning.

Coordinator-supplied facts, not worker-executed results in this repair:
- Authorized MBP downloaded public `timm/resnet18.a1_in1k`, revision
  `491b427b45c94c7fb0e78b5474cc919aff584bbf`, with `token=False`, no credential
  transfer. Cache: lab `hf-cache`; README/config/source receipt: `backbone-source`.
  Safetensors SHA256:
  `80c49dee3da4822c009c5a7fe591e9223c5a2cfcf95a4067ca4dfb5a7b89c612`.
  Upstream model card declares Apache-2.0; data rights are separate.
- Native host OpenVINO CPU compile/inference passed (`lab/openvino-compile.log`).
  This is neither a source fix for the earlier sandbox Xbyak failure nor proof
  of trained PaDiM heldout numerical/proposal parity.
- Actual pretrained fitting/calibration/heldout metrics and R results remain
  **pending**. No new model or OpenVINO run, acquisition, provider call, Git
  action or sandbox change was made during this source-only repair.

Repair also saves recoverable numeric anomaly maps, validates exact exported
score/map shapes, uses only revision-and-hash-validated offline backbone weights,
provides public pinned preparation commands, and makes user-image inspection
OpenVINO-only with corruption checks, complete recorded 200-image parity,
`actuation:false` and `USER_SUPPLIED_UNVERIFIED_DOMAIN`. Per-forward processing
latencies are descriptive; no robot throughput or probability interpretation.
Unsigned hashes check corruption, not authenticity. Safe model reload uses
safetensors, not untrusted pickle.

Focused checks: `python -B -m unittest test_pipeline.FrozenBenchmark -v` from
`vision/`: three structural adversarial tests passed (label swaps/format changes,
synthetic fixture refusal, output shapes/nonfinite refusal, and mutated-bundle
refusal before runtime loading). Syntax was checked
without importing or executing model/preparation code. No full suite rerun.

Next action: coordinator independently reviews final bytes and runs the native
README command into fresh `run-m7-network-restored`, with
`HF_HUB_CACHE=lab/hf-cache HF_HUB_OFFLINE=1 MPLCONFIGDIR=lab/mpl-cache`.
Retain precursor logs and `run-m7` intact; append actual results only after
execution. Coordinator owns Git delivery. The scientific experiment remains
unchanged; Intel target hardware, physical station, independence, STOP behavior
and sponsor rubric compliance remain unverified.

## Native real-image completion — supersedes environment blockers, not failed receipts

The authorized MacBook Pro native CPU executed source commit `c90e93f`
(pipeline SHA-256 `fbf186e29023125568f2c5637539ff29bb3c1a939d18cebb5465d4282f79e2c0`) with pinned offline weights. No
GPU or provider-model calls were used. Anomalib PaDiM fitted 128 normal
VisA candle images; 64 disjoint normals set the predeclared quantiles; all
200 official test images were scored once. No parameters or thresholds were
changed after seeing the heldout. Physical object/session identities are unknown.

**Measured quality is insufficient, not a release pass:** image AUROC 0.8164;
binary TP=23, FN=77, TN=94, FP=6. Three-way raw rule: anomalies 62 good /
38 hold / 0 defect; normals 91 good / 9 hold / 0 defect. R independently
read the generated CSV: 83/200 binary label disagreements and 47/200 holds.
This is file-level public-data evidence, not independent physical trials.

**Actual OpenVINO:** converted and reread XML/BIN; CPU scores/maps and
proposals matched PyTorch for all 200 heldout images within predeclared
atol=rtol=0.001. Max absolute score difference 0.0004272461 and map difference
0.0004653931. This is Apple ARM CPU execution, not Intel NPU/iGPU qualification.
Per-forward mean 0.02231 s excludes preprocessing; not robot throughput.

**Product disposition:** the separate `inspect` command now returns the raw
`diagnostic_proposal`, but its effective proposal is always `hold`, with
`automatic_acceptance:false`, `actuation:false` and
`NOT_QUALIFIED_FOR_AUTONOMOUS_USE`. A real saved-model OpenVINO inspection
on an existing dataset image returned diagnostic good but effective hold;
this is functional replay, not another independent evaluation sample.
No training rerun for this output-only safety change.

**Integrity:** artifact ledger verified; the actual 392-image manifest with
swapped official truth labels is rejected by the corrected boundary. Source
worker performed three new focused structural regressions; prior source
plumbing checks and sandbox failures remain recorded above. No full suite
was repeated. Raw data/model/maps/logs remain in the task-local vision lab,
not Git. `EXECUTED_M7.json` binds hashes, exact results and source.

**Next dependency:** defect-labelled calibration/validation from an authorized
Intel/SO-101 station, before qualifying the policy; do not tune on this
now-exposed heldout. Station ownership, real VLA/grasp/reinspection, physical
E-stop and Intel target inference remain unverified. No merge, production
deployment or submission. Portfolio PR Recovery remains sole integrator.
