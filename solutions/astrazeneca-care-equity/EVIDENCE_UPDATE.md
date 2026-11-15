# SAMA: an accountable next step, with explicit evidence limits

Work ID: `junction.astrazeneca.evidence-evaluation-20261115`.
Initial authenticated source: `6d2efadb22678c259dfaf6817b43c883974a9eab`.
Integration base: `0d7923213860287f1c10c188c3a9af8c39941739`; all SAMA and
root contributor-rule blobs were verified unchanged between these commits.
Owned scope: `solutions/astrazeneca-care-equity/**`.

## What changed and why

The challenge asks a decision-maker to identify a gap, locate a possible pathway
problem and understand a concrete improvement proposal within two minutes.
The new opening view gives each county three distinct evidence boxes: observed
outcome, pathway question and missing measurements. Its proposal names an owner,
first 30-day steps, a 90-day review, a numerator/denominator and unresolved costs.
These dates and actions are proposed, not accepted commitments or observed effects.

Candidate investigation order follows existing flags (screening, primary care,
referral), then checks the direction using county and national means over identical
actual years. This prevents a latest national value being silently compared to a
different county period. It is an investigation order, not a causal or benefit rank.
If comparable evidence is absent, the result is measurement-first. General access
indicators remain proxies for cancer care; missing or suppressed mortality stays
unavailable.

The downloaded JSON contains the same decision, source scope and limitations shown
on screen. Its human-approval status remains `REQUIRED_NOT_GRANTED`. The existing
default scenario portfolio is separate and retains its assumptions. The update does
not feed national registry missingness into a county score, portfolio or effect.

## Evidence added

The [Finnish Cancer Registry lung report](https://syoparekisteri.fi/assets/themes/ssy3/factsheets/keuhkosyoparaportti.html),
sections 3.1–3.3 and Table 4, supplies the national 2019–2023 C33–C34 cohort and
its missing extent-at-diagnosis counts. The report's MDT extraction limitation is
also preserved. Missing information is not proof that a clinical activity was absent.
The structured record retains numerator, denominator, reported percentage, period,
population, geography, source locator, retrieval date and comparison limitation.

[FICAN's strategy summary](https://fican.fi/wp-content/uploads/2025/11/Presentation-of-the-Finnish-National-Cancer-Strategy.pdf)
(PDF pages 8 and 11) supports Goal 3.1/3.2 alignment. The
[implementation roadmap](https://stm.fi/documents/1271139/1359637/Kansallinen_syopastrategia_toimeenpanon_tiekartta_2026_2031.pdf/)
(printed pages 86–88) supports a future precision-diagnostics access direction
under Goal 4.3. The interface explicitly labels that direction unimplemented.
BioNeMo is an unevaluated future option; no molecular model, private patient
workflow or clinical benefit is asserted.

## Forecast defects reproduced and corrected

| Finding in the historical source | Correction |
| --- | --- |
| Validation h2 and test h1 share target year 2023 | Shared fixed protocol: train labels through 2021; validation 2022/2023; test 2024/2025 |
| Calendar positions can be mistaken for years in a gapped input | Calendar-indexed input/target slots; absent years remain missing; duplicate/unsorted axes fail |
| Colorectal has no validation winner, but export substitutes persistence | Null stays null and export abstains |
| 44 colorectal bands collapse across 22 counties, yet probabilities appear | Invalid/collapsed bands withheld; no quantile-interpolated risk probabilities exported |
| Supervised models lack recorded effective training support | Count finite historical anchors and targets; require per-horizon support for transformer/ridge |
| Evaluation eligibility can survive suppression of actual output | Separate export disposition and invalid-band counts |
| Report helper inserts fixed test claims and overwrites the historical report | Read explicit new metrics, derive configuration, refuse an existing output |

The old forecast remains exactly:

```text
30befeb52603bcb9698ab41cff324b52fcd9ebd25b9ae2a0288c0be69a91e52c
```

Historical artifacts under `ml/artifacts/` are unchanged. The digest-bound
`data/ml/forecast-v1-audit.json` withholds the old product predictions. New code
cannot turn an old run into a valid new evaluation. Future runs use new default
artifact/output paths, carry protocol/panel evidence, and may legitimately produce
an empty forecast. A corrected public-data run has not been performed. Because
these years have already been inspected, any such rerun is a development evaluation;
an untouched prospective performance claim requires a new holdout.

## Verification and interpretation

The original product baseline passed 50 Node tests and 10 Python tests before the
changes. The overlap, zero-evidence colorectal export and calendar-gap defect were
reproduced against the original files. Independent read-only review reproduced the
two initial updated smoke-test failures: their perfectly linear fixtures correctly
produced collapsed bands and abstained. The successful-export fixtures now contain
deterministic pre-validation variation; their future-only mutation, output-year,
model-refit and changed-panel refusal assertions are preserved. A separate linear
train/evaluate/export regression requires abstention and an explicit reason.

Run the final code checks from this product directory:

```sh
npm test
python -m unittest discover -s ml/tests -v
npm run build
```

The Python suite uses NumPy and PyTorch, with temporary synthetic panels and artifact
roots. It is software/evaluation-policy verification, not a corrected public-data
benchmark. No paid inference or GPU job is part of this update.

The optional DOM integration check executes the real bundled app, changes both
county controls, reads the source scope and exports four representative decision
briefs. It checks the withheld-forecast and future-capability states without any
external request:

```sh
npm install --prefix /tmp/sama-dom --ignore-scripts --no-audit --no-fund jsdom@26.1.0 esbuild@0.25.11
SAMA_TEST_MODULES=/tmp/sama-dom/node_modules node tests/decision-dom.cjs
```

DOM emulation does not qualify a browser layout. In this executor, system Chromium
could not create its local singleton socket (`Operation not permitted`); automatic
approval review rejected escalation. Real browser rendering, mobile layout, dark
contrast, screen reader behaviour and print layout remain unverified for this update.
No deployment or clinical/mentor review was performed.

## Two-minute demonstration

1. Start locally with `npm start`; open `http://127.0.0.1:4179`.
2. In **One county. One next step.**, choose a county. Read the observed outcome and
   pathway question separately. Point out what remains unmeasured.
3. Read the proposed owner, 30-day investigation and 90-day review. Expand the plan
   to show its numerator, denominator, unknown baseline and cost.
4. Expand national recording context. Show that the lung statistic retains its own
   cohort and does not become this county's rate.
5. Download the brief; show its sources and human-review state. Open forecast
   evidence to demonstrate that unsupported warnings are withheld.

The next scientific gate is expert review of the measurement definitions and a
separate source-pinned public-data evaluation. Portfolio PR Recovery owns integration;
the owner separately authorizes merge/publication.
