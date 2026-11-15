# CRACI open 3D and video results — 15 November 2026

[Run #43672442214](https://github.com/SalesSquad/junction-pets/actions/runs/43672442214)
completed successfully. The source/harness was
`76138f0c27fca50694aef7b6016af65478df65e4`. CRACI reported fetching and
verifying 112 pinned open-data files and completed all **45 model cells**:
three model families × five group-disjoint folds × three data lines.
This is exploratory offline prediction, not a robot policy, a physical
rollout, safety evidence, or a model release.

| Line / held-out groups | Method | Mean group RMSE | Constant-velocity baseline | Groups better than baseline |
| --- | --- | ---: | ---: | ---: |
| G1 / 30 motion clips | Ridge | 0.09022 rad | 0.11173 rad | 27/30 |
| G1 / 30 motion clips | ExtraTrees | 0.09895 rad | 0.11173 rad | 23/30 |
| G1 / 30 motion clips | MLP | 0.09248 rad | 0.11173 rad | 22/30 |
| RoboMoCap / 10 participants | Ridge | 0.01162 m | 0.01322 m | 8/10 |
| RoboMoCap / 10 participants | ExtraTrees | 0.01199 m | 0.01322 m | 8/10 |
| RoboMoCap / 10 participants | MLP | 0.01098 m | 0.01322 m | 9/10 |
| V2D video / 10 tasks | Ridge | 0.02808 m | 0.01160 m | 0/10 |
| V2D video / 10 tasks | ExtraTrees | 0.01207 m | 0.01160 m | 0/10 |
| V2D video / 10 tasks | MLP | 0.01453 m | 0.01160 m | 0/10 |

The table weights each held-out group equally. V2D's two baselines are both
zero displacement because its input contains video, not tracked pose history.
The three tested video methods all lost to that baseline in every task group.
The video input is downsampled grayscale and the target is 3D object
displacement; a stronger vision method is a research hypothesis, not a
demonstrated repair. Each G1 split holds out clips, not performers; the
RoboMoCap splits hold out participants. These data and folds have been
observed during development, so the table is not an untouched external test.

The selected G1 Ridge and RoboMoCap MLP are best among these three methods on
the displayed cross-validation metric. Selection used the same folds; do not
present the selected scores as an unbiased final-model evaluation. The MLP
reached its 60-iteration limit in **5/5 G1 folds and 5/5 RoboMoCap folds**
(and 1/5 V2D folds), so convergence is not established.

## Source and evidence

The data revisions, selection, license, feature and split definitions are
documented in the [campaign README](README.md). The previous run
[#43672290377](https://github.com/SalesSquad/junction-pets/actions/runs/43672290377)
failed at an unrelated APT source before any data fetch or training; its
failure receipt was retained. The corrected run uses Ubuntu-only APT sources.

- The [original summary](summary-43672442214.json) is byte-identical to the
  run's summary artifact, SHA-256
  `ff2e69c24333c6118fe9cfb6c39c123e0db5c795ec78e5a7ea1c2bf5f0aaa03a`.
- The [artifact index](artifacts-43672442214.json) contains all 48 GitHub ZIP
  IDs, sizes and provider-reported SHA-256 values. All 48 ZIPs were separately
  copied to the execution workspace, totaling 122,877,180 bytes, and matched
  those reported digests. A local tar bundle containing all 48 ZIPs, the
  index, summary, audit, verifier and two sample fold models has SHA-256
  `27a93c2320835b2aaac9e7c7969b78f988ff435ac0d6d7e4ceb10cff106746a2`.
  GitHub's original artifacts expire on 22 November 2026. A workspace copy is
  not an asserted iCloud or cross-device backup.
- The [offline audit](audit-43672442214.json) verified 47 source-bound
  succeeded receipts, the complete set of 45 cells, original manifest and
  model-part hashes, and the 42-cell remainder plan. It independently
  reconstructed all group splits and baseline errors from the retained
  features, then recalculated the published group and pooled summaries.
  Separately downloaded local source files produced byte-identical feature
  archives for all three lines. The audit **did not deserialize the models or
  independently rerun their predictions**. Actual billing and cryptographic
  provider attestation are unverified.

Reproduce the offline audit with the pinned NumPy/scikit-learn versions and
`scripts/craci/verify_hf_open3d_43672442214.py`, passing the 48 downloaded ZIPs,
the artifact index and optionally the independently prepared local features.
To reassemble one selected cell, use `scripts/craci/hf_open3d_extract_model.py`;
it verifies the outer artifact, receipt, inner parts and model hash without
deserializing it. Each output is the model from that fold, trained on that
fold's training groups; it is not a final fit on all available data. The
result is a joblib/pickle file and should be loaded only when the artifact
source is trusted.
The existing collector calls these generic registry records `synthetic-test`;
the observed source data are the public real recordings identified above, and
the collector label is not a provider attestation.

The 48 job timestamps total about 39.0 job-minutes. Multiplying those intervals
by the **requested**, not independently attested, runner sizes and the earlier
EUR 0.0017/vCPU-minute list figure gives roughly EUR 2.09 for this successful
run. This excludes the earlier failed attempt and other account jobs, and is
neither an actual bill nor a verified remaining balance.
