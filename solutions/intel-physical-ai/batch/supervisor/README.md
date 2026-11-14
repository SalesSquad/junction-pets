# M4 — Offline global safety supervisor and bounded R analysis

This deliberately **does not modify the original M1 anomaly gate, M2 comparator,
M3 studio or any actual device integration**. Run on Node 22+ and optional base R:

```sh
node --test solutions/intel-physical-ai/batch/supervisor/supervisor.test.mjs
node solutions/intel-physical-ai/batch/supervisor/cohort.mjs > /tmp/j26-intel-supervisor-cohort.csv
Rscript solutions/intel-physical-ai/batch/supervisor/analyze.R /tmp/j26-intel-supervisor-cohort.csv
```

A **normal per-item STOP is not a global emergency STOP**. A distinct
`globalStopEpisodeId`, grip loss, camera disagreement/missing view,
a stale synthetic capture or low-confidence fixture trips a **batch-wide
non-actuating latch**. Subsequent episodes are converted to explicit M2
`stop` commands with no software bowl output, and cannot silently
resume within that batch. The latch is scoped to one constructed batch. Starting another batch is NOT
protected by this module: a real host must separately enforce physical E-stop,
human-approved rearm and cross-batch latching before any robot action.

Each audit includes the original request, the exact transformed request,
trip cause, a reused M2 receipt, a control matrix and a SHA-256 root.
`replaySupervisedBatch` recreates and checks the full result and nested M1/M2
replay. Unsigned hashes prove *local reproducibility*, not identity or
trusted capture. All times are simulated fixture clock times, not camera time.

The study deliberately exposes the **cost of conservatism**: fewer
software destinations after a safety trip, with every downstream
episode stopped. The baseline is M2's per-episode STOP, not a hardware
controller. Sensor/fault families and locations are **predeclared,
non-independent synthetic scenarios**; changing seeds only changes
feed positions, never sensor class, independent defect prevalence or
real-world environment. R prints counts and trade-offs, deliberately
**no binomial confidence intervals/p-values or accuracy claims**.

Source admission: authenticated main
`16947f0ccd33d6e3895f08619b7ba425bf453a59`;
`partnerEvidenceKey=ignite-next-and-intel`,
`ownedBriefRefs=[M330]`, 14 Nov latestClarification read first (conflicting
GitHub/PDF judging rubrics unresolved). This is an OFFLINE_NONACTUATING
software safety experiment, **not a robot E-stop**, OpenVINO/Intel
inference, Anomalib trained model, VLA, SO-101, GPU, Isaac Lab or
NVIDIA Omniverse simulation. Real safety needs independent source
calibration, physical emergency-stop wiring, human-authorized rearm,
camera synchronization and sponsor-qualified station tests.

NVIDIA public skills catalog consulted; the relevant robotics
dataset-replay/validation skills can guide a future authorized physical
dataset pipeline, but no NVIDIA stack was installed and no GPU ran.
There are no new background services, APIs, accounts or credentials.
