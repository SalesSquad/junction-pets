# Signal Desk — Hostinger Manipulation Radar

An offline analyst dashboard for **possible coordinated campaigns**, with inspectable evidence, explicit counterevidence and an honest error ledger. **SYNTHETIC / OFFLINE_DETERMINISTIC. Maturity 2/6: functional local prototype, not field or live-host qualified.** No real AI or provider calls. Independent work, not Hostinger endorsement.

## Run without installation

Node >=22, no packages or build step:

```sh
cd solutions/hostinger-manipulation-radar
node server.mjs
# Open http://127.0.0.1:4173
# Ctrl-C stops the server. Optional PORT selects a different local port.
node --test tests/*.test.mjs
node benchmark.mjs
node stress/report.mjs
```

The server binds **127.0.0.1 only**, exposes an exact read-only allowlist and never logs observations. A separate authorized Mac Mini coordinator runner previously confirmed M2 local HTTP smoke and 15/15 focused tests. M2 also passed six CRACI engine/viewport journeys ([source-bound campaign record](../../docs/CRACI_PORTFOLIO_20261114.md)); those results do not qualify the M3 UI additions. M3 opens no ports and uses socket-free handler and DOM contract checks. Remote/public Hostinger deployment remains NOT VERIFIED. No server was left running.

## Walk the complete investigation

1. Start with **Synchronized launch swarm**. Rank findings by score, observation time or account count. Inspect event-linked score contributions and the temporal cluster.
2. Open the event ledger and pairwise links. Every positive and negative signal lists supporting event IDs; the ledger shows exact payloads, ages, destinations and amplification targets. Timeline bars represent event order, not time bins.
3. Remove timing or another signal in the what-if panel. The score and review decision recalculate at fixed threshold. Removing counterevidence may increase the score. This is rule ablation, not causal inference.
4. Switch to **The wire-service trap** and **Organic viral workshop**. Repetition and popularity are insufficient to establish malicious intent. Supplied attribution is unverified and can be spoofed.
5. Use **Mixed investigation desk** to investigate three independent groups. Mark a group Needs investigation, Likely benign or Insufficient context, or reset it. Only disposition enums and synthetic IDs enter localStorage; a denied store falls back to session memory. No text/account observations are persisted.
6. Download a structured JSON report with synthetic observations, signal evidence, base SHA, review dispositions and ablation selections. Benchmark metrics and exact denominators remain visible in the quality ledger. Native controls support keyboard use; layout adapts to narrow screens. Actual visual, screen-reader and device behavior still needs browser qualification.

The original Radar remains synthetic-only. The separate M4 Traffic Forensics journey accepts bounded local Nginx logs, with no raw uploads or persistence; see below.

## Development benchmark, not a field claim

Policy v1 is fixed at **65 points**, a positive timing signal and at least three positive signal families. No keyword, belief, identity or protected-trait features enter Radar scoring. Labels are separate fixture files used only by the benchmark; held-out observations are outside the public server allowlist. The naive baseline flags any repeated text appearing at least three times, or `shocking`, `urgent`, `exposed`.

Unit: a scenario is positive if any group receives analyst review. Eight development scenarios and twelve separate held-out synthetic parameter cases share a generator; this is **not an independent, blinded or representative evaluation**. Labels describe authored intent, which may be behaviorally indistinguishable (benign volunteers). The fixed threshold was not fitted to held-out results. Metrics report exact counts, with null for undefined ratios.

| Split / method | TP / FP / TN / FN | Precision | False-positive rate | Recall |
| --- | --- | --- | --- | --- |
| Development Radar | 3 / 0 / 5 / 0 | 3/3 = 100% | 0/5 = 0% | 3/3 = 100% |
| Development baseline | 3 / 2 / 3 / 0 | 3/5 = 60% | 2/5 = 40% | 3/3 = 100% |
| Held-out Radar | 4 / 1 / 6 / 1 | 4/5 = 80% | 1/7 = 14.3% | 4/5 = 80% |
| Held-out baseline | 4 / 3 / 4 / 1 | 4/7 = 57.1% | 3/7 = 42.9% | 4/5 = 80% |

Radar misses `h-evasive` (delayed adversary) and flags `h-volunteers` (benign coordinated activity). These are exposed, not suppressed. False-positive controls reduce fixture false alarms but do not establish deployment efficacy, bot identity or intent. Expect drift and adaptive evasion. One additional error would materially change these tiny denominators.

## M3: reproducible robustness and false alarms

From this product directory, **`node stress/report.mjs`** prints the complete JSON audit. Node >=22 / standard library only. Mode **OFFLINE_SYNTHETIC_OOD** means an authored distribution shift relative to the M2 generator, not actual licensed data, independent external validation or representative field evidence. The detector is unchanged: threshold 65, positive timing, three positive signal families, identical source bytes. No weights, gates, labels or thresholds were adjusted after observing OOD results.

`stress/ood.mjs` imports neither the public generator nor existing fixtures. Five cohorts and their counts/intent stipulations are declared before evaluation: eight fixed Mulberry32 uint32 seeds (`12011, 24029, 36037, 48049, 60077, 72091, 84121, 96137`), 64 cases per seed, **512 total, 320 benign / 192 harmful**. Posts vary spacing/jitter, account count and age (including unknown), naming, text reuse, destination paths/query strings, amplification targets, credits and 1–3 interleaved participant groups. Emergency/civic coordination is explicitly legitimate; harmful labels stipulate concealed paid control, which cannot be proved from these observations. Truth maps stay outside events and the detector receives only `c.events`.

| Predeclared cohort | Cases | Radar TP / FP / TN / FN | Naive TP / FP / TN / FN |
| --- | ---: | --- | --- |
| Legitimate volunteers | 128 | 0 / 50 / 78 / 0 | 0 / 84 / 44 / 0 |
| Journalism / wire | 96 | 0 / 0 / 96 / 0 | 0 / 57 / 39 / 0 |
| Organic community | 96 | 0 / 20 / 76 / 0 | 0 / 32 / 64 / 0 |
| Overt concealed amplification | 96 | 45 / 0 / 0 / 51 | 58 / 0 / 0 / 38 |
| Slow / evasive concealed amplification | 96 | 0 / 0 / 0 / 96 | 32 / 0 / 0 / 64 |
| **All** | **512** | **45 / 70 / 250 / 147** | **90 / 173 / 147 / 102** |

| Method | Precision (Wilson 95%) | FPR (Wilson 95%) | Recall (Wilson 95%) |
| --- | --- | --- | --- |
| Unchanged Radar | 45/115 = 39.13% (30.70–48.26%) | 70/320 = 21.875% (17.69–26.72%) | 45/192 = 23.4375% (18.00–29.91%) |
| Naive comparator | 90/263 = 34.22% (28.75–40.14%) | 173/320 = 54.0625% (48.59–59.44%) | 90/192 = 46.875% (39.95–53.93%) |

The before/after comparator is naive rule → existing Radar, **not a newly fitted revision**: fewer false alarms accompany worse recall. All **217 Radar errors** are retained in CLI JSON with case IDs, reasons, signal contributions/event IDs, counterevidence and reviewer actions. Undefined rates and CIs are `null`. Wilson intervals are descriptive binomial calculations; correlated authored cases and fixed seeds do not justify population inference or realistic accuracy claims. Zero observed wire false alarms (0/96) still has an upper Wilson bound of 3.85%.

The existing `/api/benchmark` adds `robustness`, computed once lazily per server process and cached; refresh does not regenerate 512 cases. It exposes aggregate cohort counts/intervals and a few diagnostic IDs, never raw OOD events, truth maps or complete per-case errors. The exact asset allowlist is unchanged. The browser quality ledger presents both methods, cohort denominators, biggest uncorrected families, and an expandable analyst workflow. Scenario JSON exports explicitly disclaim independently confirmed OOD field results; no OOD observations or author labels are added to exports or storage.

For a reproducible analyst investigation:

1. Read the ledger's family counts and example IDs, then run `node stress/report.mjs` and locate the same ID under `errors`. For example, **`ood-12011-0-01`** is a legitimate volunteer false positive scoring 100, with timing evidence `e0,e2,e4,e6`.
2. Inspect observations and fixed-rule evidence locally, before using the separate synthetic stipulation. This command prints only the selected observations (change the ID to another reported case):

   ```sh
   node --input-type=module -e "import {corpus} from './stress/ood.mjs'; import {analyze} from './public/detector.mjs'; const c=corpus().cases.find(c=>c.id==='ood-12011-0-01'); console.log(JSON.stringify({case:c,analysis:analyze(c.events)},null,2));"
   ```

3. For volunteers, seek the public shift schedule, sign-up and approved bulletin template; compare them to the exact flagged event IDs. For syndication, trace dispatch and permission/credit history. For community activity, compare public event timing and original commentary. These are requests for counterevidence, not verified facts about a real subject.
4. Record evidence and uncertainty in the review handoff; keep **Insufficient context** until provenance is verified. A **Likely benign** disposition needs supporting evidence. OOD cases have no browser review persistence; development scenario dispositions are a separate workflow. Slow/evasive misses require authorized longitudinal evidence. Never auto-ban, auto-dismiss, or lower the threshold from this audit.

Observed M3 checks: **20 tests passed, 0 failed**, using `node --test --test-skip-pattern='local HTTP smoke' tests/*.test.mjs`. One existing socket-opening test was deliberately excluded under this task's no-ports instruction (Node reports 20 selected / 0 skipped); existing assertions were preserved. This includes six OOD tests plus expanded DOM/export assertions and unchanged local detector checks. Syntax checks passed for changed runtime modules. No new real-browser, native-download, TCP, provider or deployment qualification is claimed.

## Source and challenge fit

Current task `J26-PF-HOSTINGER-M3-20261114`, immutable base **`27fb74b999f41718237958e03404390350f75a65`**, branch `codex/j26-hostinger-ood-audit-20261114`; uncommitted owned changes await the coordinator. Historical M2 base: `b7a51ee7acc3b1923fa0506b31a0f2eafb56f402`. Sources were read from the supplied clone, with no remote refresh or provider login. `partnerEvidenceKey: hostinger`, snapshot **2026-11-14**. [Official M357: Decode the Noise](https://hackjunction.app/participate/45/challenges/357), recorded in `../../docs/challenge-research/current-source-catalog.json` and routed by `../../docs/AGENT_SOURCE_INDEX.json`.

M357 weights detection quality, false positives and explainability at **40%** and technical execution / live Hostinger deployment at **25%** (originality 20%, clarity 15%). This prototype addresses the first category through timing, account similarity, text/URL reuse and amplification evidence. It does not satisfy the AI-powered or live-deployment requirements.

The latest supplied clarification states: team booth coupon → KVM 2 for one month → 5000 AI credits and Instant web scraping. VPS, AI Router and possible AI Builder activation are separate. **Own-account activation, all real Hostinger integrations and public deployment: NOT VERIFIED.** No benefit was redeemed or claimed available.

Acceptance and exact execution evidence are in [PROGRESS.md](PROGRESS.md); trust boundaries and scoring rules are in [ARCHITECTURE.md](ARCHITECTURE.md). Next dependency: **valid licensed labelled data + authorized live coupon / Hostinger deployment access**, owned by the coordinator/data and deployment owner. No deployment artifact, submission or production efficacy is claimed.


## M4 / Traffic Forensics (source-only)

Run `node server.mjs`, open `http://127.0.0.1:4173/traffic/index.html` (also linked in Radar navigation), and choose **Open synthetic demonstration**. Inspect the five-minute window, exact event IDs and benign explanations; choose an analyst disposition and export redacted JSON. For a user-selected log choose the file input. Each import clears the prior report and alias mapping; no filename, raw request, original client address, user agent, referer or query is rendered/exported. No browser storage or raw network request is used.

CLI equivalent, from this directory:

```sh
node traffic/cli.mjs traffic/synthetic.txt
node traffic/cli.mjs traffic/synthetic.txt --output my-redacted-report.json
node --test traffic/*.test.mjs
```

The CLI sample is authored SYNTHETIC data, but CLI input always carries `USER_SUPPLIED_UNVERIFIED_LOG`: file contents cannot prove origin. CLI prints JSON by default and writes only an explicitly selected **new** output file (no overwrite). User data is never saved otherwise. Review exported metadata before sharing: sequential aliases are not general anonymization.

Strict supported subset: UTF-8 Nginx combined, numeric IPv4/IPv6 clients, literal `-` identity field, bounded username, HTTP/1.0 or 1.1, known uppercase request verbs and origin-form request paths. Other formats explicitly refuse the whole import. Maximum 1 MiB, 5000 lines, 4096 characters/line, 512-character request target, 160-character path, 1024-character referer/UA, seven-day span, years 2000–2100. CRLF is accepted; invalid encoding, control/bidi characters and malformed dates/offsets fail closed. Only a fixed known-route vocabulary survives; all other paths become `[other path]`. Times use the supplied Nginx UTC offset, which itself is unverified.

Policy `traffic-review-1`: fixed UTC five-minute windows; candidate requires both ≥10 authenticated-route 401/403 events from ≥3 aliases and ≥5 HTTP 429 responses. Volume (≥30 events / ≥3 aliases) is contextual, and ≥5 5xx is operational, neither escalates alone. Alias count is not people count. Two co-occurring response families are not statistically independent evidence of malicious intent. Shared proxies, load tests and ordinary mistakes can satisfy the rule; boundary splitting and evasion can miss activity. There is no bot/attack classification, automatic ban or identity verdict. Counts, denominators, exact IDs, UTC timestamps, provenance, rule version and analyst disposition are exported; original client identifiers are not.

Real labels, field precision/FPR, live Hostinger deployment/provider integration and coupon activation remain **UNKNOWN / NOT VERIFIED**. No efficacy numbers are inferred from the authored examples. Existing M3 policy and OOD corpus are untouched. Next dependency: licensed labelled traffic with an agreed evaluation protocol, followed by separately authorized Hostinger deployment.
