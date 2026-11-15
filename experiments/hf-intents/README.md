# CRACI intent-training campaign — 15 November 2026

Owner request: five CRACI runners for each of the two downloaded HF datasets,
until 19:00 Europe/Helsinki today, with datasets, models and results in cloud.
This fresh request authorizes this manual, private campaign; ordinary PR/main
CI and the existing scientific qualification harness remain separate.

## Fixed allocation and stop

- Exactly two datasets × five distinct model families = ten training jobs.
- Each training job requests 8 vCPU / 24 GB RAM, maximum 80 vCPU concurrently.
- A 2-vCPU setup job and a final 2-vCPU evaluation job run before/after them.
- Training stops at **16:40 UTC / 18:40 Helsinki** to reserve 20 minutes for
  final selection, held-out evaluation and cloud preservation.
- Absolute window closes **17:00 UTC / 19:00 Helsinki**. Existing
  `CRACI_CREDIT_WINDOW_OPEN` shutdown remains authoritative.
- Three bounded at most 280-minute controller phases respect GitHub's 360-minute
  step limit, while the self-hosted job is bounded to 900 minutes. Every chunk
  also enforces the earlier absolute training cutoff.
- Only reviewed main can dispatch. A single atomic release lease prevents a
  second campaign under the same tag. No scheduled recurring workload,
  provider inference, GPU rental, hosted-runner fallback or cash top-up exists.

Authenticated CRACI billing observed about 05:00 Helsinki showed EUR995.95 of
Junction credits remaining (starter 10 EUR separate). Published pricing at
https://craci.com/pricing is EUR0.0017/vCPU-minute. Ten 8-vCPU jobs from 05:00
until 19:00 would be about EUR114.24 plus small setup/finalization overhead;
actual metered cost depends on actual runner start/finish times. This reserve
is within the existing EUR1,000 credit-only authority. Admission refuses an
estimate above this campaign's EUR150 cap or the observed available credit;
chunk admission also bounds elapsed resource-minutes at the published rate. It is a conservative
window estimate, not a new provider hard spending cap or a claim about other
campaigns' future usage.

## Data and experiment protocol

`manifest.json` pins public dataset revisions, every downloaded file's SHA-256,
size and actual row counts, original licenses and attribution. Training reads
raw Parquet only; no Hugging Face dataset loader code or model code executes.

| Dataset | Official train | Validation | Held-out test | Labels |
| --- | ---: | ---: | ---: | ---: |
| BANKING77 | 10,003 | fixed grouped split from train | 3,080 | 77 |
| MASSIVE fi-FI | 11,514 | 2,033 official | 2,974 | 60 declared |

MASSIVE Finnish validation and test each contain 59 observed classes; that is
recorded rather than treated as a corrupt file. Duplicate normalized text is
kept in a single training/CV group. BANKING77's development split is fixed and
shared across lanes. Official test files are present in the private dataset
archive but are not downloaded into training jobs.

Each dataset has five different searches: word TF-IDF+SVM, character
TF-IDF+SVM, hybrid linear model, complement Naive Bayes, and SVD+MLP. Seeded
configurations are distinct; each family's best is selected by grouped
training cross-validation. Validation is recorded separately. Finalization
selects among five family winners using validation macro-F1, then evaluates
that chosen model on its official test once. No test score steers search.
Class coverage, split sizes, model configuration, seeds, dependency versions,
source SHA, run ID and model digest accompany results. No benchmark score,
clinical/financial reliability or product deployment is inferred from launch.

## Private cloud preservation

The repository must be verified private before initialization. The cloud
archive is the prerelease tag `hf-intents-20261115` in
`SalesSquad/junction-pets`. Creation is atomic and refuses a different run/source lease; the same exact run/source can resume interrupted uploads.
Its admission record binds the exact reviewed source SHA, run ID, resources
and cutoff. A GitHub prerelease here is a private research artifact archive;
it does not release/deploy a Junction product or public model endpoint.

Initialization uploads the pinned datasets, licenses and manifest. Training
publishes immutable per-lane checkpoint archives at <=10-minute chunk
boundaries when trial history advances, preserving the current best and completed search results. Previous assets are never overwritten
or deleted. A maximum 90 checkpoints × 10 lanes plus setup/final assets stays below
GitHub's 1,000-asset/release limit; each archive is capped well below 2 GiB.
[GitHub release limits](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)
state no total release-size or bandwidth quota. This avoids temporary Actions
artifact-storage dependence; no paid storage service is provisioned.

Models use `skops` rather than arbitrary pickle loading; evaluation refuses
untrusted/custom types. Extraction rejects unexpected names, traversal,
links and excessive sizes. Checkpoint source/run/data binding and model hashes
are checked before selecting or evaluating them. Dependencies are binary-only,
version/hash locked. Training subprocesses receive no GH_TOKEN environment;
they share the same ephemeral VM user, so this is not an OS isolation claim.
The trusted controller uses the short-lived repository token to publish only
to the fixed private release. Workflow dispatch is main-only; untrusted PR
source never receives these publishing permissions.

CRACI networking denies unmatched outbound connections. GitHub/PyPI use
package-aware presets; exact HF storage/CDN TLS hosts serve immutable data.
Those encrypted data transfers are verified by file digest, not claimed as
package-aware SBOM completeness. Existing CRACI network traces and provider
SBOM/vulnerability views remain available for each real job.

Cloud checkpoints survive a cancelled/failed job. If any lane is missing,
finalization must preserve diagnostic/partial results and report failure;
launch, queueing and a partial result are not ten completed models.

## Run and evidence

```sh
gh workflow run craci-hf-intents.yml --repo SalesSquad/junction-pets --ref main
```

Dispatch once after the reviewed source is merged. Existing flag/absolute
cutoffs remain in effect. Actual run and release URLs, runner names, source,
focused control-check results and review disposition belong in the delivery PR.
