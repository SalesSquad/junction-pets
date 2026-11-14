# J26-HOSTINGER-M2-20261114 — delivery receipt

## M3 OOD audit — 14 November 2026

Task **J26-PF-HOSTINGER-M3-20261114**, sole code writer in `solutions/hostinger-manipulation-radar/**`, issue80 claim comment **6879753127** as supplied by coordinator. Verified clean branch `codex/j26-hostinger-ood-audit-20261114`, exact source base **`27fb74b999f41718237958e03404390350f75a65`**. Current M3 files remain uncommitted for coordinator review/integration; no commit/push/PR/merge or concurrent writer was created. This section supersedes current-state claims below without rewriting M2 historical evidence.

Delivered independent `stress/ood.mjs` (no existing generator or fixture imports): **8 seeds × 64 = 512 OFFLINE_SYNTHETIC_OOD scenarios**, five predeclared cohorts. Ground truth is author-stipulated legitimate outreach vs concealed deceptive paid control, separate from detector events and outside public source. Time spacing/jitter, ages/unknowns, accounts, text, URL paths/queries, targets, credits and mixed groups vary. `stress/report.mjs` emits exact confusion counts, rates/nulls, Wilson 95% intervals, unchanged-policy vs naive comparator, source/corpus/label hashes, 40 case/label hash samples, and every error with signal evidence, counterevidence and reviewer action. No detector, threshold, weight, gate, M2 fixture or label was changed.

Observed output of **`node stress/report.mjs`** (from product directory):

| Method (512 cases) | TP | FP | TN | FN | Precision | FPR | Recall |
| --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| Radar v1 | 45 | 70 | 250 | 147 | 45/115 | 70/320 | 45/192 |
| Naive rule | 90 | 173 | 147 | 102 | 90/263 | 173/320 | 90/192 |

Radar Wilson 95%: precision **30.7003–48.2633%**, FPR **17.6938–26.7234%**, recall **18.0029–29.9142%**. Total **217 uncorrected errors**: volunteers **50 FP / 128 benign**, community **20 FP / 96 benign**, wire **0 FP / 96 benign**, overt manipulation **51 FN / 96 harmful**, evasive manipulation **96 FN / 96 harmful**. Naive → Radar deltas: precision **+4.9099 percentage points**, FPR **−32.1875 points**, recall **−23.4375 points**. This exposes a serious recall tradeoff; no policy tuning followed. Authored correlated cases are not representative data; intervals do not establish realistic population error bounds.

Reproducibility fingerprints (SHA-256, actual local uncommitted bytes):

- Detector / policy: `f3050adf27f4a588e81cb0ba75e020a05d91fae54af1c7f8b6479eec48dc7455` (unchanged from M2).
- OOD generator: `69920c1188e6eef87fe2cb9f2d0a37e08d744a4afcbb0b0442eedd2c59efc607`.
- Audit reporter: `24aeb48bd9b87df7fbb0783a982690feb595b7c5700735666bde4e41123eb3b6`.
- Combined `sourceSHA256`: `cdc368aae2e15a072c9e7f2bacbeabf5459908ef62e89ede78971f8b0a4fc553` (SHA-256 of ordered JSON map of the three source hashes above; includes policy/detector, excludes UI/docs).
- Serialized cases: `328a8bc10fab9b7c4bfb1cbf2fb53b175b57dacb71d4b893d9feef95df78c7ce`.
- Separate label map: `7c4e12be6d807e9fd9231156d1cbbb1bb770c792caa3802be95df8e1b03b34a0`.

Existing `/api/benchmark` now serves a once-per-process cached OOD aggregate, with unchanged exact asset allowlist and CSP. No raw OOD cases, labels or full error rows enter browser responses. Browser ledger adds cohort/method confusion counts, denominators/intervals, error-family examples and counterevidence/reviewer actions. Example `ood-12011-0-01` is an explicitly legitimate volunteer case scoring 100; reviewer seeks a public shift notice and bulletin provenance, retaining uncertainty rather than banning or automatically dismissing. README gives exact local reproduction. Export explicitly states OOD evidence is authored synthetic, not independently confirmed field results, and analyst dispositions are not truth.

Executed on this isolated Mac Mini, **Node v26.13.0**, 14 November 2026:

```text
node --test --test-skip-pattern='local HTTP smoke' solutions/hostinger-manipulation-radar/tests/*.test.mjs
tests 20; pass 20; fail 0; cancelled 0; skipped 0; todo 0
node --check solutions/hostinger-manipulation-radar/public/app.mjs
node --check solutions/hostinger-manipulation-radar/server.mjs
exit 0 (both)
node solutions/hostinger-manipulation-radar/stress/report.mjs
exit 0; 512 cases; 217 errors retained (metrics above)
```

After a final UI-only fingerprint abbreviation, `node --test solutions/hostinger-manipulation-radar/tests/journey.test.mjs` passed **1/1** again; `node --check` passed for all four changed runtime modules (`public/app.mjs`, `server.mjs`, `stress/ood.mjs`, `stress/report.mjs`). `git diff --check` passed. Exact changed files: `README.md`, `PROGRESS.md`, `public/app.mjs`, `server.mjs`, `stress/ood.mjs`, `stress/report.mjs`, `tests/ood.test.mjs`, `tests/journey.test.mjs`, all relative to this product directory.

Six new OOD tests cover repeatable seeds, disjoint IDs/seeds, bounded varied observations, independent imports, label isolation/poisoning, frozen detector hash/gates, exact confusion denominators, Wilson known values/endpoints/nulls, all errors unsuppressed, sample/source hashes and socket-free allowlist/CSP/405/HEAD tests. Expanded DOM harness verifies new counts/CIs, exposed failures, actionable workflow and export disclaimer, preserving the existing journey assertions. Existing HTTP smoke is intentionally **excluded**, not executed/qualified, because task forbids ports; Node reports only the 20 selected tests. No tests weakened. Skill verification-plan helper was unavailable (`ENOENT` at its documented path); focused product checks above were selected directly. No installs, paid calls, credentials, private data, telemetry, deployment or persistent process.

M2 CRACI's six real browser journeys remain source-bound historical qualification ([campaign record](../../docs/CRACI_PORTFOLIO_20261114.md)); they were not rerun and do not cover this M3 UI. M3 DOM contract is not visual/accessibility/native-download qualification. **Maturity remains 2/6, offline synthetic-only, no Hostinger endorsement or live provider claim.** The current source snapshot's M357/hostinger clarification still offers team booth coupon → KVM2 one month → 5000 AI credits / Instant scrape; own-account activation is unverified. Next external dependency: **licensed labelled external data plus separately authorized coupon activation / Hostinger deployment access**, coordinator/data and deployment owner. Next coordinator action: review the eight-file product-only diff, then own commit/integration. Lifecycle gate may report unsaved work; this task explicitly forbids rescue/push, so preservation is this intact owned worktree.

Snapshot: **2026-11-14**, final checks approximately **02:39 UTC**, executor: isolated Mac Mini restricted local shell, Node **v26.13.0**. Base `b7a51ee7acc3b1923fa0506b31a0f2eafb56f402`; branch `codex/j26-hostinger-manipulation-radar-20261114`. Clean baseline verified before writing. Sole owned scope: `solutions/hostinger-manipulation-radar/**`. No commit, branch switch, push, PR, merge, deployment, provider login, install, paid resource or secret access performed. Files intentionally remain uncommitted for the coordinator.

## Delivered acceptance

- Functional browser dashboard: eight scenario choices, rankable linked groups, temporal evidence, exact event ledger and pairwise links, positive/negative rule contributions, uncertainty and alternative explanations.
- Counterfactual signal ablation recalculates rule score and decision gates. Local browser review dispositions can be set/reset; JSON report download includes observations, provenance, evidence and dispositions. Storage failure is handled. Unknown stored keys/values are discarded.
- Deterministic multi-signal detector with strict size/field limits, sanitized text-node presentation, distinct-account timing, account naming/cohort signals, near-copy text, canonical URLs and amplification. Benign wire syndication and organic-spread controls; no automated enforcement, protected-trait or political-belief inference.
- Separate development and held-out observations/labels, naive keyword/repost comparator, exact confusion counts and denominators, data/source hashes, exposed false positives and misses. No truth label input to runtime scoring or held-out threshold fitting.
- Node standard library only, no install/build step. Read-only loopback server with exact asset allowlist, restrictive CSP, no logs/telemetry/provider calls. Documentation and source-bound manifest included.

## Commands and observed results

Executed from repository root:

```sh
node --check solutions/hostinger-manipulation-radar/public/app.mjs
node --test solutions/hostinger-manipulation-radar/tests/*.test.mjs
node solutions/hostinger-manipulation-radar/benchmark.mjs
```

Syntax check passed. Final targeted suite: **15 tests, 14 passed, 0 failed, 1 explicitly blocked/skipped**. Tests cover deterministic input order, three-group separation, false-positive controls, single-account amplification, missing metadata, exact ablation, evidence IDs, truth-field exclusion, hostile/oversized inputs, near-copy matching, a maximum 400-event case, exact metrics and fixture separation. Maximum-size synthetic analysis completed in roughly 1.1 seconds on this executor; no scalability/field-performance claim follows.

The DOM contract harness exercised scenario selection, evidence, ablation, sort, finding selection, persisted review, reset, JSON Blob export, benchmark display and denied storage. It is a minimal test DOM, **not a real browser, screenshot, screen reader, native download or visual accessibility qualification**.

**Real HTTP smoke initially failed with `listen EPERM: operation not permitted 127.0.0.1`.** The final suite explicitly records that capability as blocked; assertions are retained for an executor with loopback permission. A separate socket-free fallback invokes the actual server request handler and verifies all assets, benchmark JSON, CSP, HEAD behavior, 405 writes and 404 private/traversal paths. This does not establish a working TCP/HTTP client path. No dev server remains running.

## Exact benchmark outcome

Unit: scenario containing at least one flagged group. Ratios below show exact denominators.

| Partition / method | TP | FP | TN | FN | Precision | FPR | Recall |
| --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| Development Radar (8) | 3 | 0 | 5 | 0 | 3/3 (100%) | 0/5 (0%) | 3/3 (100%) |
| Development baseline (8) | 3 | 2 | 3 | 0 | 3/5 (60%) | 2/5 (40%) | 3/3 (100%) |
| Held-out Radar (12) | 4 | 1 | 6 | 1 | 4/5 (80%) | 1/7 (14.3%) | 4/5 (80%) |
| Held-out baseline (12) | 4 | 3 | 4 | 1 | 4/7 (57.1%) | 3/7 (42.9%) | 4/5 (80%) |

Known held-out errors: `h-evasive` is a false negative (slow campaign); `h-volunteers` is a false positive (benign coordination). The held-out partition shares a generator with development and has authored intent labels; it is not blinded, independently collected, statistically representative or sufficient to claim production efficacy. A policy threshold of 65 and timing/three-signal gates were fixed before inspecting held-out metrics. Later fixes corrected development fixture text separation and status wording, not held-out labels, scores or thresholds.

SHA-256 evidence emitted by the benchmark:

- Detector source: `f3050adf27f4a588e81cb0ba75e020a05d91fae54af1c7f8b6479eec48dc7455`
- Development serialized observations: `a08fac47f726c7f6d24c3bdc3c3dae7a5c542204b8cb7ec781a7f80c0fe472fa`
- Development parsed labels: `c78eb7a68b12a366f15a36b8e1b12c4eaede93c1a7b57bd0bef7723543e9bff7`
- Held-out serialized observations: `93f5bc9e35aee348b855a94f57d34d7460e086c4e6b9140bfa04bd8eae460bdc`
- Held-out parsed labels: `2c85915a2230c1775fd5b4c45bfe3e19fcbd235dfbad5ba4461de931e85daf17`

These bind local observations to the detector/fixtures above, not an unmade commit or cloud receipt.

## Challenge evidence and next owner

Read the supplied clone's START_HERE, AGENTS, AGENT_SOURCE_INDEX and CURRENT_SOURCES; selected `partnerEvidenceKey: hostinger`, official **M357** and its **latestClarification**, snapshot **2026-11-14**, plus the company research and source routing. M357: detection/false positives/explainability 40%; live Hostinger technical execution 25%. Current clarification: booth team coupon, KVM 2 for one month, 5000 AI credits, Instant web scraping; own-account activation unverified, separate activation stages for VPS / AI Router / possible AI Builder. No remote-source refresh is claimed.

Maturity **2/6**. All real Hostinger integration, coupon activation and public deployment remain **NOT VERIFIED**. No real AI or production efficacy claim. Browser rendering, real keyboard/screen-reader behavior, native download and local TCP/HTTP smoke remain unqualified.

Next executable action, coordinator: integrate the uncommitted product scope, then run `node server.mjs` and the targeted tests in an authorized loopback/browser-capable environment. The exact next external dependency is **valid licensed labelled data + authorized live coupon / Hostinger deployment access**, owned by the data/deployment coordinator; do not activate or deploy from this task. The lifecycle done gate may report unsaved work; do not rescue/push because this task explicitly reserves integration and commits to the coordinator.

## Coordinator integration correction and independent qualification — 14 Nov 2026

- **Manifest correction:** adapted product `solution.json` to the exact 10-field `validateSolution` contract from pending workspace successor PR #82 (`45f7755a2f8e88e40f14588d0505f2e1aff9f799`). Its version/maturity/partnerEvidenceKey/challenge M357/clarification and evidence stay in this PROGRESS receipt and README, not extra unrecognized manifest fields. The future shared integrator owns PR #82.
- **Separate authorized Mac Mini execution** outside the restricted Codex subprocess independently ran the final product-local `node --test tests/*.test.mjs`: **15/15 PASS, 0 skip** including **actual TCP localhost HTTP GET/HEAD/405/404/CSP/asset/benchmark smoke**. This resolves ONLY the local HTTP capability blocked by the writer's sandbox; it does not qualify a real browser, public endpoint, Hostinger VPS or SDK. The original writer's separate **14 pass / 1 socket-denied skip** is preserved above as historical evidence, not silently rewritten. All product `.mjs` files passed `node --check`; quick static injection search found no `innerHTML`, `eval`, `document.write`, or `sendBeacon`.
- **Source:** authenticated main `b7a51ee7acc3b1923fa0506b31a0f2eafb56f402`; partner key `hostinger`; official M357, source snapshot 2026-11-14. **Local synthetic results remain tiny and authored:** held-out precision 4/5, FPR 1/7, recall 4/5. No direct user data, model calls, sponsor credits, secrets, releases or live provider qualification.
- **Remaining acceptance:** actual visual/a11y browser, independently licensed labels and reproducible Hostinger deployment/AI integration; no live access currently asserted.
