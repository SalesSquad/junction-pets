# Architecture and detection contract

## Local boundary

`server.mjs` uses Node HTTP and filesystem reads only. GET/HEAD assets are explicitly allowlisted; all other methods receive 405 and all non-allowlisted paths 404. `/api/benchmark` computes aggregate synthetic benchmark metrics without exposing label files. CSP permits same-origin code only, blocks frames, forms and objects; no remote dependencies, cookies, analytics, uploads or outbound calls. It is a local prototype, not a hardened public service.

`public/app.mjs` renders native controls, tables, expandable evidence and a score-ablation tool. Observations are text nodes, never HTML or clickable external URLs. JSON exports use Blob downloads. localStorage holds only synthetic scenario/group disposition pairs; storage failure falls back to memory. Downloaded reports contain synthetic observations and should not be adapted for private data without a separate governance design. The Node server writes nothing.

## Detector v1, immutable policy within this task

`public/detector.mjs` is browser/Node portable and has no fixture imports. Input is capped at 400 events and 512 KiB of JSON before normalization; fields are allowlisted and strings truncated, with control/bidi characters stripped. Text is limited to 600 characters, IDs to 60, attribution to 100. Invalid IDs, duplicate IDs and invalid dates fail closed. Unknown ages contribute zero evidence. URL normalization accepts HTTP(S) only, removes query/fragment/trailing slash, and retains hostname + path. Query-specific campaign IDs can therefore be lost; canonicalization can also over-merge destinations. URLs are never fetched.

Sort by timestamp and ID. Compare pairs at most 24 hours apart. Link events by common normalized URL, a common amplification target or token-set Jaccard similarity ≥0.72 (both texts have at least four distinct words, URL text excluded). Connected components are **candidate groups**, not proof of campaign identity. Transitive linkage can merge unrelated activity. All-to-all comparison is bounded; worst-case component evidence work is O(n³) at n≤400, with O(n²) linkage memory. Only the first 100 pairwise links are displayed; event-level rule evidence remains complete. This is unsuitable for high-volume streaming without redesign.

For each component, count **distinct accounts**, finding the densest 60-second window. Account metadata is supplied, not verified. One account's earliest event represents its metadata; inconsistent later metadata is not independent evidence.

| Signal | Points | Required evidence |
| --- | --- | --- |
| Timing | +25 | At least 4 distinct accounts in 60 seconds |
| Text reuse | +20 | At least 3 accounts and ≥60% of events linked by cross-account near-copy text |
| URL reuse | +10 | At least 3 accounts and ≥70% share a destination |
| Account naming | +15 | At least 4 accounts; ≥70% share a digit/hyphen/underscore-stripped stem |
| Recent cohort | +15 | At least 4 accounts; ≥75% of all distinct accounts have supplied age ≤14 days |
| Amplification | +15 | At least 4 accounts; ≥70% of events share an amplification target |
| Attributed syndication | −35 | ≥80% of events (minimum 3) declare attribution |
| Organic counterevidence | −20 | ≥4 accounts; all ages known and >180 days, naming concentration <50%, reused text <50% |

Sum and clamp 0–100; review requires ≥65, positive timing, and ≥3 positive families. Signal families can be correlated; scores are heuristic points, **not calibrated probability or independent likelihoods**. Negative evidence is deliberately inspectable, not a blanket whitelist. Attribution can be forged; account naming and age can be evaded; established accounts can be compromised. Synchronized legitimate volunteers may still trigger review, and slow campaigns can be missed. No semantic truth, political belief, protected trait, deception or bot-status prediction is performed.

Ablation sets selected signal contributions to zero and reevaluates the same rule gates, without changing observations or grouping. This explains sensitivity to missing evidence; it is not a simulation of changing behavior, causal impact or a fitted threshold.

## Fixture / truth boundary

`public/generator.mjs` creates deterministic synthetic observations; `public/scenarios.mjs` selects development scenarios. `fixtures/held-out.mjs` selects a separate frozen parameter set, not served publicly. `fixtures/*-labels.json` are authored scenario intent labels read only by `benchmark.mjs`. Scoring strips unknown input fields including truth/label metadata. No trained model, fitting loop, keyword verdict or runtime label lookup exists.

The benchmark uses one prediction per scenario (any group flagged), exact confusion counts and ratio denominators, plus SHA-256 of the detector source, serialized observations and parsed labels. Separate cases share a generator and do not establish external validity. Held-out results were inspected after fixing policy v1; no threshold adjustment followed. An independent licensed labelled corpus, data provenance/consent, target prevalence and an evaluation protocol are prerequisites to meaningful field precision/FPR claims.

## Unqualified external boundary

Base SHA `b7a51ee7acc3b1923fa0506b31a0f2eafb56f402`, partnerEvidenceKey `hostinger`, official M357, snapshot 2026-11-14. No Hostinger SDK, secret, scraping integration, AI Router, model call, provider activation, public deployment or automatic enforcement exists. All real Hostinger integration and public deployment remain **NOT VERIFIED**. Valid licensed labelled data and authorized live coupon/deployment access are the exact next dependencies.


## M4 traffic isolation

`public/traffic/core.mjs` is a dependency-free browser/Node parser and conservative review detector, separate from the unchanged Radar policy/OOD corpus. It refuses whole invalid imports. Original client addresses exist only in a per-call map; sequential aliases reset on every import. Only allowlisted constant routes survive normalization. The browser File API reads ≤1 MiB locally; no fetch, storage or raw DOM rendering exists. All derived display values use textContent. Async import generations prevent stale reads replacing a newer import. Dispositions are session-memory enums. Export is an explicit Blob download.

Four exact new GET/HEAD static assets are served under `/traffic/`; existing CSP and method guards remain intact. No upload endpoint or host integration is added. `traffic/cli.mjs` reads at most limit+1 bytes from a regular file and prints only the normalized report, or exclusively creates the operator-selected output. Errors omit raw data and filenames. CLI always declares USER_SUPPLIED_UNVERIFIED_LOG; browser demo alone explicitly sets SYNTHETIC. Fixed-window co-occurrence cannot establish actor identity, intent or statistically independent likelihood. Detailed limits and review gates are in README. Metadata remains sensitive despite removing direct identifiers.
