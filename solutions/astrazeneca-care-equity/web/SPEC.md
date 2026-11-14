# Web demo specification: SAMA, the Care Equity Navigator

"Sama" is Finnish for "the same": the same cancer pathway for everyone, wherever they live.
Audience: AstraZeneca oncology mentors, a senior oncologist who runs cancer care in a wellbeing
services county, and hackathon judges. They have two minutes. The brief they judge against:
identify the gap, locate it on the care pathway, and (most important) recommend what to do, with a
source for every claim and at least one indicator of Goal 3 of the national cancer strategy.

## Hard constraints

- Static, no build step, no dependencies, no CDN, no external fonts or network calls. The page is
  served by `web/serve.mjs` with a self-only Content-Security-Policy. Charts are hand-written SVG.
- Data comes from `web/data/app.json` (already built by `node src/build.mjs`; read it first, it is
  the contract). Do not invent, round away or restate numbers that are not in that file.
- Live recomputation imports the existing modules unchanged: `/src/recommend.mjs`
  (`regionFacts`, `optimise`, `equityShare`, `deathsPostponed`, `centralParameters`, `ASSUMPTIONS`,
  `INTERVENTIONS`, `costOf`) and `/src/stats.mjs`. Do not edit anything under `src/`, `data/`,
  `pipeline/`, `ml/`, `tests/`. You own `web/` only (`index.html`, `app.mjs`, `styles.css`,
  `serve.mjs`, extra modules and `web/data/counties.geo.json`).
- `web/serve.mjs`: keep 127.0.0.1:4179 and the strict CSP. Serve `web/` at `/`, and read-only
  `/src/*.mjs` and `/data/**.json` from the solution root (no path traversal). Add
  `POST /api/verify-claims` (JSON body `{claims:[...]}`, max 64 kB): `import('../src/claim-check.mjs')`
  and return `await verifyClaims(claims)`; if that module is missing or throws, return
  `{status:"NOT_CONFIGURED", results:[]}` with HTTP 200. Add `GET /api/health`.
- Every number on screen carries one of three chips: `MEASURED` (public statistic), `SCENARIO`
  (model output, shown as a range) or `ASSUMPTION` (planning parameter). Never show a scenario
  number without its range. Never present a county comparison as a causal or patient-level claim.
- Keyboard accessible, visible focus, WCAG AA contrast, works at 380 px width, respects
  `prefers-reduced-motion`, light and dark via `prefers-color-scheme`. Print stylesheet for the brief.

## Structure (one page, sticky section nav)

1. **Header and verdict strip.** Product name, one-line promise, data provenance line
   (`provenance.snapshotGeneratedAt`, number of source requests, short snapshot SHA-256). Four
   headline tiles taken from the data: (a) the Finland vs Sweden-Norway five-year lung cancer
   survival gap for men from `analysis.goal3.indicators[0].rows`; (b) cancer deaths per year now, the
   -10% target and the 2035 figure from `demographicPressure`; (c) number of counties missing the
   80% screening target per programme (`indicators.screen_*.countiesMissingTarget`); (d) the public
   vs private/occupational route difference of 84 days (evidence row `kuitunen-2026-route-means`).
2. **Where is the gap?** A map of the 23 wellbeing services counties with a metric selector
   (age-standardised cancer mortality ratio with its shrunk estimate; each screening programme; GP
   wait over 7 days; specialised care wait over 6 months). Try to fetch county geometry once, at
   build time on your side, from Statistics Finland's open WFS
   (`https://geo.stat.fi/geoserver/tilastointialueet/wfs?service=WFS&version=2.0.0&request=GetFeature&typeName=tilastointialueet:hyvinvointialue4500k_2025&outputFormat=application/json&srsName=EPSG:4326`;
   if that layer name fails, list layers with GetCapabilities and pick the wellbeing county layer),
   simplify it to under 400 kB and save it as `web/data/counties.geo.json` with a `source` and
   `license` (CC BY 4.0, Statistics Finland) field. Match features to our ids (`HVA01`..`HVA21`,
   `HVA90` Helsinki, `HVA91` Åland). If geometry cannot be fetched, draw an ordered tile grid
   instead and say so in the caption. Beside the map: a ranked dot-and-interval chart of the same
   metric with uncertainty, flagged counties marked. Diverging colour for ratios, sequential otherwise;
   colour is never the only encoding.
3. **County view** (select by clicking the map, the chart, or a combobox). A horizontal pathway
   strip of the six stages in `analysis.stages`: detection, primary care, referral, diagnosis,
   treatment start, outcome. Measured stages list their indicators with the county value, the
   national value, the target if any, a tiny trend sparkline from `series`, and a flag when
   `flagged` or `missesTarget`. Unmeasured stages (diagnosis, treatment) are drawn hatched with the
   text from `analysis.dataGaps`: this absence is a finding, show it proudly. State in one sentence
   where this county's gap emerges (`gapEmergesAt`, else "not locatable from public data") and its
   excess deaths per year with interval (`allCancer`).
4. **Goal 3 scoreboard.** The three Goal 3 indicators from `analysis.goal3.indicators`: survival
   gap bars per cancer and sex against the Sweden-Norway benchmark with a small history line;
   deaths per year vs target vs demographic pressure; and "treatment within target times: not
   publicly measurable" as an explicit red-outlined empty state that links to the enabling action.
5. **What to do.** The core. Left: controls for yearly budget (1 to 20 million EUR), inequality
   aversion (0, 1, 3, 6, 10) and the key assumptions (hazard ratio per 4 weeks, share entering via
   primary care, share of route gap closed), each showing its evidence basis from `ASSUMPTIONS`.
   Right: the recommended portfolio recomputed live with `optimise`, grouped by action, as cards:
   title, the concrete action, where (counties), owner, mechanism, cost (ASSUMPTION chip), deaths
   postponed per year with range (SCENARIO chip), how often it stays in the portfolio across the
   sensitivity draws (`stability`, from app.json for the default settings), the indicator to monitor,
   what is not known, and evidence links. Always pin the enabling action `pathway-timestamps` first.
   Then: the "same pathway for everyone" scenario (`recommendation.samePathway`), the efficiency vs
   equity frontier (`frontier`), the Danish validation check (`validation`), and the detection
   track table (`recommendation.detection`) for screening.
6. **Analyst brief.** For the selected county call `buildBrief(app, regionId)` from
   `/src/claims.mjs` (returns `{title, claims:[{id, text, kind, evidence:[ids], sources:[{label,url}]}]}`)
   and render the sentences with their chips and source links. A "Check claims" button posts the
   claims to `/api/verify-claims` and shows a per-sentence result (`SUPPORTED`, `NOT_SUPPORTED`,
   `UNCLEAR`) with the probability, or "claim check not configured" when the status is
   `NOT_CONFIGURED`. Buttons: print the brief; download it as JSON with
   `"humanApproval":"REQUIRED_NOT_GRANTED"` and the snapshot SHA-256.
7. **Early warning** (only when `app.forecast` is not null). For the selected county, each forecast
   indicator as a small chart: history, then the one- and two-year-ahead median with 50% and 90%
   bands, probability of missing the threshold or of worsening. A backtest table from
   `forecast.metrics` showing each method's error and which one was chosen, including when a simple
   baseline won.
8. **Evidence and method.** Every row of `app.evidence` (claim, citation, link, verified or not),
   the data sources with licence and retrieval time from `provenance`, the three method paragraphs
   in `analysis.methods`, and a plain list of what this tool does not claim.

## Design direction

Editorial and calm, like a well-set public health report rather than a SaaS dashboard. Paper-white
background, near-black ink, one deep teal accent, one warm amber for flags, a muted red only for
missing data. System font stack with `font-variant-numeric: tabular-nums`. Generous whitespace,
hairline rules, no gradients, no drop shadows, no emoji, no card grids of equal boxes: let the map
and the pathway strip carry the page. Motion only for state changes, under 200 ms.

## Done means

`node web/serve.mjs` serves the page; opening it shows real numbers with no console errors; all
sections render for at least Satakunta (HVA06), Helsinki (HVA90) and Åland (HVA91, which has
suppressed and missing values); moving the budget slider changes the portfolio; `node --check` passes
for every `.mjs`; the page has no horizontal scroll at 380 px. Finish with a short report of what
was built, what you verified and what you could not verify.
