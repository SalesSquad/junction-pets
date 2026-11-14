# M7 source-bound observations — 14 November 2026

Work ID `J26-INTEL-M330-M7`; base source
`c1e926f624fda2d4063e71a48306d92940d097d3`, initially clean task branch
`codex/j26-intel-vision-m7-20261114`. Only new `vision/**` source is owned.
M6 PR176 is preserved. Coordinator owns independent numerical/provenance review,
push, owning PR and integration. Claim comment on #80 was attempted but the
GitHub connector returned `MCP tool call requires approval, but approval policy
is never`; no successful external claim is asserted. Knowledge OS task/evidence
APIs were absent from the runtime catalog (`registry_identity_unverifiable`).
Local `git add` and `git commit` were attempted after checks but could not
create the linked worktree's `index.lock` under the external
`/Users/mikaelervamaa/Developer/junction-pets-20261111/.git/worktrees/` directory
(`Operation not permitted`). No commit or push is claimed. Coordinator should
run `git add -- solutions/intel-physical-ai/vision` and
`git commit -m "feat(intel): add real-image offline PaDiM inspection pipeline"`
from this checkout before independent exact-HEAD review/delivery.

## Actual results

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
  and no inference-quality claim. This error was not bypassed.
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

Final pipeline SHA256:
`2ecf3ce6ee4058cf294ceab9602458baf9aaf3d82ec4e6ebdb36b705b1873d04`.
`run-m7.log` SHA256:
`2dfd8101db09fac6991fc55c50bbc348b28effb7919ddf4b43f80b46e2ba7870`.
`check-m7-separated.log` SHA256:
`1a51d0a1595b3295bcd288dfd76bfc3e0768aa2c66e0230186903cb652284254`.

Next executable action: coordinator records the #80 claim/handoff, provides
working public official-weight download/cache access and a CPU executor capable
of OpenVINO compilation, independently reviews this exact source, then executes
the README command into fresh `run-m7-network-restored`. Retain `run-m7` intact.
The scientific experiment remains unchanged. Intel hardware, physical station,
object/session independence, safety STOP behavior and sponsor rubric compliance
are not verified by this work.
