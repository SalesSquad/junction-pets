# SAMA: the big picture, what to fix, and what to build next

> Working notes from the hackathon night; README.md and submission/ are the current versions.

Revision 2. Written Saturday 14 November 2026, 22:15-22:50 UTC, by the wave-2 synthesis step.
Read-only: this file is the only thing written. No git, no cloud resource, no paid API call.
All patient-like data in SAMA is SYNTHETIC. Nothing here is a clinical claim.

**How sources are marked.**
- **(re-checked)**: this step opened the source tonight, 22:20-22:50 UTC. For two sources the live
  page was not reachable, so a copy saved earlier today was read; the row says so.
- **(research)**: a wave-2 research agent opened it on 14 November and recorded it as verified.
- **(panel)** / **(critic)**: a wave-2 panel member or the critic opened it on 14-15 November.
- **UNVERIFIED**: nobody confirmed it on a primary page. Section 7 lists these.
- Repository facts link to files in this folder. Times in file names and logs are UTC unless noted
  (file modification times on this Mac show Helsinki time, UTC+2).

**What "flare" is.** NVIDIA FLARE is NVIDIA's open-source (Apache-2.0) toolkit for federated
learning and federated statistics. The same small program is sent to every site, each site runs it
on its own data, and only filtered results come back. SAMA already ran it tonight on SYNTHETIC data
(section 5).

**What changed in this revision (critic gaps checked tonight; all were real unless noted).**
- The Nemotron planner and the Gemma demo are built but **not on the page**, and `npm test` fails
  1 of 98 because `web/data/app.json` is stale. This is now must-ship item 1 with a named owner.
- The fix list now has owners, a time window and a cut order (section 2.1). It did not fit before.
- DO #2 is **code-only tonight**: no new Gemma or MLX job, because the Mac is out of memory.
- The six-week target is now worded as "reported by the OECD/EU"; Finnish law guarantees six months.
- Kuitunen: route groups are 48 and 39 patients, not 160; the 84-day model prior comes from a figure.
- SAMA's county screening gradient is mostly a capital-region effect; the SII number is dropped.
- Finland has 21 wellbeing services counties plus Helsinki; SAMA's 23 areas include Åland.
- The national lung screening pilot (roadmap 2.3.4) is added; DO #2 covers all lung follow-ups.
- All five companies that supported the Filha lung programme are disclosed; a regulatory line is added.
- One critic number was wrong: MASAI's detection ratio is 1.29 in SAMA's evidence file, not "about 1".

---

## 1. The big picture in five bullets

1. **Cancer care is moving from "detect faster" to "close the loop".**
   - AI saves reading time but does not by itself move the pathway. AI-supported mammography cut
     screen-reading workload by 44%, detection ratio 1.29 (1.09-1.51) (MASAI, Lancet Digit Health
     2025;7(3):e175, `data/evidence/literature-v1.json` `masai-2025-workload`). AI prioritisation of
     93,326 GP chest X-rays left the median time to CT at 53 days in both arms, ratio 0.97
     (0.93-1.02) (LungIMPACT, Nature Medicine 32(5):1737-1744, online 24 Mar 2026,
     https://eprints.whiterose.ac.uk/id/eprint/239649/, re-checked).
   - NHS-Galleri missed its primary endpoint; the stage IV incidence rate ratio was 0.86 and
     mortality is unknown (GRAIL release, 30 May 2026, [BioSpace](https://www.biospace.com/press-releases/grail-reports-full-results-from-nhs-galleri-trial-demonstrating-substantial-reduction-in-stage-iv-cancer-diagnoses-at-2026-asco-annual-meeting), research).
   - Process tools work: patient navigation raised breast screening, RR 1.50 (1.30-1.75), over 42
     RCTs; no study described harms (INCa summary of a JAMA Intern Med 2025 meta-analysis, 13 Jun 2025,
     [page](https://en-www.cancer.fr/professionnels-de-sante/veille/nota-bene-cancer/bulletin-n-648-du-13-juin-2025/patient-navigation-services-for-breast-and-cervical-cancer-screening-and-follow-up-a-meta-analysis), research).
   - Finland's own lung screening pilot started in early 2026 in Helsinki and eight wellbeing
     services counties, randomised, and expands regionally in 2026-2028 (roadmap measure 2.3.4,
     p. 46, `data/roadmap/roadmap.txt`, re-checked). Every scan, screening or incidental, creates a
     follow-up that someone has to close.
2. **Our neighbours measure pathway time by region. Measuring alone did not fix it, and new
   patient-record systems broke the statistics.**
   - Sweden: 47% within the stated lead time in 2025 (45% in 2024) against an 80% goal; the three
     regions that missed the inclusion goal had all changed patient-record systems (SVF annual
     report, 27 Mar 2026, [PDF](https://cancercentrum.se/download/18.7c07b08019d24db18e31c22a/1774867469204/%C3%85rsapport%20%C3%B6verenskommelse%202025%20J%C3%A4mlik%20och%20effektiv%20cancerv%C3%A5rd%20med%20kortare%20v%C3%A4ntetider_bilaga%201%20SVF.pdf), research and panel).
   - Norway: no regional health authority met the 70% target in 2023-2025; figures are withheld
     after a record-system error (Helsedirektoratet, 24 Sep 2026, [page](https://www.helsedirektoratet.no/statistikk/kvalitetsindikatorer/kreft-behandling-og-overlevelse/pakkeforl%C3%B8p-for-26-organspesifikke-kreftformer), research).
   - England: 78.6% diagnosed or ruled out within 28 days in August 2026, target 80%; in April-June
     2026 it was 54.8% for patients diagnosed with cancer against 79.5% for those ruled out
     (Cancer Research UK, 12 Oct 2026, [page](https://news.cancerresearchuk.org/2026/10/12/cancer-waiting-times-latest-updates-and-analysis/), re-checked).
3. **Finland has a target it cannot see, a weak legal floor, and no new money.**
   - The OECD/EU reports maximum waits for Finland "such as six weeks between a referral concerning
     a suspected case of cancer and the start of primary treatment" (OECD/EU Country Cancer Profile
     Finland 2025, [PDF](https://cancer-inequalities.jrc.ec.europa.eu/sites/default/files/docs/ccp2025/ec-oecd-fi-2024-1666-en.pdf), re-checked).
   - The law itself is looser. In specialised care, assessment starts within three weeks of the
     referral, tests within three months, and treatment within six months; the page names no
     cancer-specific limit (STM, hoitotakuu, updated 29 Oct 2026, [page](https://stm.fi/hoitotakuu), re-checked).
     The same page says non-urgent primary-care maximums were lengthened from the start of 2025
     (adults now three months).
   - Stage is recorded for 42% of cancers nationally: Pirkanmaa 72%, Sisä-Suomi 60%, other areas
     33-42%, against an aim of at least 70% (Syöpäjärjestöt, 17 Jun 2026, [page](https://www.syopajarjestot.fi/uutinen/syovan-levinneisyystiedoissa-suuria-alueellisia-eroja-suomessa/), re-checked).
   - The Cancer Organisations say no strategy money is planned for 2027 (STT, 4 Sep 2026,
     [page](https://www.sttinfo.fi/tiedote/72294557/syopajarjestot-varoittaa-kun-jarjestoilta-leikataan-paine-terveydenhuollossa-kasvaa?lang=fi), research).
   - New: since 1 June 2026 a county may identify patients "joiden hoito ei vastaa suosituksia" (whose
     care does not follow recommendations) and contact them, respecting data protection and
     self-determination (STM, 21 May 2026, [page](https://valtioneuvosto.fi/-/1271139/lakimuutokset-parantavat-hyvinvointialueiden-mahdollisuuksia-ennakoivaan-terveydenhuoltoon), re-checked).
4. **The largest documented gap is who you are and how you enter care, not where you live.**
   - No significant regional difference in five-year survival was found ("do not significantly
     differ across regions"). By education: 64% (men) and 65% (women) with lower education against
     77% and 78% with higher (OECD/EU 2025, re-checked).
   - Breast screening: 66% against 85% by education, 63% against 82% by mother tongue (2020-21).
     Cervical screening: 51% against 78% by education, 57% against 73% by mother tongue (same PDF,
     p. 14, re-checked).
   - Lung cancer, within each sex: five-year survival about 13% for men with basic education against
     about 18% with tertiary education; women about 20% against 30% (2020-22, Cancer Registry data;
     Filha lung programme preprint pp. 11-12, PDF created 21 May 2026, [PDF](https://www.filha.fi/wp-content/uploads/2026/05/Valtakunnallinen-keuhkosyopaohjelma-2026-2035_180526_preprint.pdf),
     re-checked from the copy saved today).
   - Entry route: median 127 days from symptom to treatment through a public primary-care
     appointment (48 patients) against 76 through private or occupational care (39 patients),
     p = 0.027; means 201 against 126 (Kuitunen J et al., Cancer Medicine 15(5):e71920, online
     10 May 2026, [full text](https://www.ebi.ac.uk/europepmc/webservices/rest/PMC13158131/fullTextXML);
     re-checked from the copy saved at 21:41 UTC, because the live endpoint returned HTTP 500 at
     22:42 UTC).
5. **Data that stays home is becoming the norm, and AI rules are arriving.**
   - NORDCAN already runs `nordcan.R` inside each Nordic registry and exports only aggregate tables
     (Frontiers in Oncology, 8 Aug 2023, https://pmc.ncbi.nlm.nih.gov/articles/PMC10442944, research).
   - NCI's FLAIMME consortium federates MedGemma across four cancer centres on NVIDIA FLARE
     (cancer.gov, talk 16 Sep 2026, [page](https://www.cancer.gov/about-nci/organization/cbiit/news-events/events/federated-learning-across-nci-cancer-centers-flaimme-nvidia-flare-2026), research).
   - EU secondary use of health data under the EHDS applies from March 2029 ([Commission page](https://health.ec.europa.eu/ehealth-digital-health-and-care/european-health-data-space-regulation-ehds_en), research).
   - EU AI Act: high-risk rules for Annex III systems apply from 2 December 2027 and for AI in
     regulated products from 2 August 2028, after the AI Omnibus entered into force on 27 July 2026
     (European Commission, updated 19 Oct 2026, [page](https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai), re-checked).

**Where SAMA fits.** SAMA is the missing measurement and action layer. On public data it shows who,
how and where the gap is. It names the few dates Finland must record to check its own target, shows
on synthetic data that each county can compute them at home, refuses to rank an area that cannot see
itself, and turns the clock into a nurse's list of people whose next step is overdue.

---

## 2. What we can do better

### 2.1 Must-ship order tonight, with owners and a cut line

Time left at 22:50 UTC: 4 h 40 min to the code freeze at 03:30 UTC (`NVIDIA_OPTIONS.md` 3.1). The
previous fix list (about 13-16 h) plus the three tonight items (5-7.5 h) did not fit.

**Who is free.** Lane C finished step 7 at 22:36 UTC and step 9 at 22:00 (`runs/laneC-step7.jsonl`,
`runs/laneC-step9.jsonl`). Lane B finished step 6 at 22:11 (`runs/laneB-step6.jsonl`). Lane A is
running MLX training arm B again after a watchdog kill, with step 8 next (`runs/laneA-step3.jsonl`).
The tracks integrator, who owned `README.md`, `src/tracks.mjs`, `web/tracks.mjs` and
`web/data/app.json`, last logged at 20:53 UTC (`runs/integrate-tracks-v3.jsonl`). Treat it as not
running: Lane C takes over those files plus `web/app.mjs` and `web/index.html` unless the
integrator answers before 23:00. One writer per file.

| Order | Item | Owner | Window (UTC) | If it is late |
|---|---|---|---|---|
| 1 | Put the Nemotron planner (`web/planner.mjs`, cached `data/planner/plans-v1.json`, label "Draft for a planner") and the Gemma demo (`web/scribe-demo.mjs`, `POST /api/scribe`) on the page; rebuild `app.json`; `npm test`; browser check | Lane C; Lane B on call for the planner | 22:50-00:00 | Hard deadline 00:00. Fallback: the cached plans as a static block. Never ship a stale `app.json` |
| 2 | Route figure: medians 127 vs 76 days, 48 vs 39 patients, "Kuitunen J" | Lane C | 00:00-00:15 | Text only |
| 3 | Move Evo 2 "09 / TREATMENT SELECTION" off the AstraZeneca page | Lane C | 00:15-00:30 | Footer link to an appendix page |
| 4 | Hide section 06 "Signals ahead" | Lane C | 00:30-00:40 | |
| 5 | Headline a process metric instead of "576 (0-1,543) deaths postponed" | Lane C | 00:40-01:15 | Keep the deaths line, relabelled "upper-bound scenario" |
| 6 | DO #1 panel ("who, how and where") | Lane C | 01:15-02:15 | Becomes a deck slide |
| 7 | DO #2 static worklist panel, code only | Lane B, from 00:00 | 00:00-01:30 | One deck slide |
| 8 | DO #3 stretch: FLARE referral-to-treatment edge and a coverage column | Lane B, after Lane C hands over `flare/` | 01:30-02:30 | Deck slides only (the default) |
| 9 | Final rebuild, `npm test`, browser check at 375 px and desktop | Lane C | 02:15-03:00 | Revert anything not green at 03:30 |
| - | MLX queue only: arm B, then step 8. Nothing else runs beside MLX | Lane A | as planned | |
| After freeze | All deck, video and README text fixes in 2.2 | Lane C and owner (step 10) | 03:30-07:30 | |

Whoever owns `PROGRESS.md` should record this cut order there.

### 2.2 Full ranked fix list

Ranked by expected score gain per hour. "Checked" says what this step verified tonight.

| # | Issue | Why it hurts | Fix | Hours | When |
|---|---|---|---|---|---|
| 1 | Planner and Gemma demo not on the page. Checked: `web/app.mjs` imports only `claims.mjs`, `bindings.mjs` and `tracks.mjs`; `app.json` built 20:53 UTC, before `plans-v1.json` existed; `npm test` 97/98, failing on a stale `app.json` (`runs/laneA-step1b.jsonl` 22:31, `runs/laneC-step7.jsonl` 22:36) | The NVIDIA minimum needs Nemotron "in the working solution" (`NVIDIA_OPTIONS.md` 1.5). The Gemma judge needs to see Gemma work | Must-ship 1 | 0.75 | 22:50-00:00 |
| 2 | No time plan. Checked: fix list plus tonight items ≈ 18-23 h against 4.7 h | Half-done items on the page at freeze | Section 2.1 | 0 | now |
| 3 | Route figure "207 vs 123 days on average" in `README.md` line 30, `submission/DECK.md` line 63, `submission/VIDEO_SCRIPT.md` line 30. Checked: neither number appears in the paper's text; they are read from Figure 1. Route groups are 48 and 39 patients (Table 3); both evidence rows cite "Kuitunen H" | A statistician who opens the paper finds different numbers | Medians 127 vs 76, p = 0.027, 48 vs 39 patients; "Kuitunen J"; keep 207/123 only as "read from Figure 1" | 0.25 | 00:00 |
| 4 | Evo 2 "09 / TREATMENT SELECTION" on the AstraZeneca page (`web/index.html`) | BRCA status gates AstraZeneca's Lynparza (AZ release, 4 Aug 2022, [page](https://www.astrazeneca.com/media-centre/press-releases/2022/lynparza-approved-in-eu-for-early-breast-cancer.html), critique): a compliance distraction | Appendix page, footer link | 0.25 | 00:15 |
| 5 | Section 06 shows percentage intervals below zero and zero-width bands with p = 0.98 | One impossible number spoils the rest | Hide for the demo | 0.17 | 00:30 |
| 6 | Headline "576 (0-1,543) deaths postponed" rests on extrapolations. Checked: `src/recommend.mjs` `routeGapDays` = 84 (range 51-84), from the Figure 1 means; the paper's text means differ by 75 days, the medians by 51. `DATA_COLLECTION.md` line 92 also calibrates on 207/127 and 123/76 | 0-1,543 reads as "unknown"; medical affairs cannot repeat it | Headline a process metric (share followed up on time; share treated within the placeholder six-week threshold). Disclose: "the 84-day prior is read from Figure 1; the text means differ by 75". Owner decision 6 on the range | 0.5-1 | 00:40 |
| 7 | "Who" is missing; county gradients exist but are not shown. Checked: breast screening r = -0.59 across 22 counties (2024 values against the education index) falls to -0.35 without Helsinki. The five lowest attenders are all in the capital region: Helsinki 74.3%, West Uusimaa 76.1%, Vantaa-Kerava 76.7%, East Uusimaa 79.8%, Central Uusimaa 80.5%. Vantaa-Kerava, Helsinki and West Uusimaa also have the highest foreign-background shares (288.9, 216.1 and 199.8 per 1,000, 2025; `web/data/app.json`) | Insight 25%. Showing "SII -8.43" as an education effect would be wrong | DO #1, without the SII number | 1-1.5 | 01:15 |
| 8 | The page fails the two-minute test: SHA in the hero, chips on every number, 10 sections, a 42-row table | Clarity 10%; caps Actionability 30%. Judges are two marketing staff and one Business Excellence person (repo capture, `../../docs/challenge-research/official-detail-pages.json`) | Tonight: SHA to the evidence section, chips on hover, only if time after item 9 of 2.1. Full "Decision view" lives in the deck | 0.5 | if time |
| 9 | Six-week target spoken as Finnish fact. Checked: STM's treatment-guarantee page gives three weeks, three months and six months and no cancer-specific limit (updated 29 Oct 2026) | THL statisticians will catch it | Say "the OECD/EU reports a six-week target; the law allows up to six months". Label every 42- or 42.5-day threshold "placeholder (OECD/EU-reported target)" | 0.1 | text |
| 10 | "23 wellbeing services counties" (README line 8, deck lines 28 and 237, video line 17). Checked: STM says "There are a total of 21 counties" and Helsinki organises its own services ([page](https://stm.fi/en/wellbeing-services-counties), no date, re-checked). SAMA's 23rd area is Åland (HVA91), which the page does not mention | Factual error in the first sentence | "21 wellbeing services counties, Helsinki and Åland (23 areas)". State that national measures and the 2026 law are not claimed for Åland (Åland's own health legislation: general knowledge, UNVERIFIED) | 0.25 | text |
| 11 | Pilot rationale. Checked: shrunk lung mortality (C32-C34, includes larynx) is Lapland 1.237, Kymenlaakso 1.132, Satakunta 1.126, East Uusimaa 1.114 (`web/data/app.json`). The Filha preprint says regional lung mortality "noudattelee samaa kuin ilmaantuvuus" (follows incidence), p. 12 | "Highest lung mortality" is false and the excess is mostly exposure | Justify Satakunta on process grounds (DO #2). Write "lung (C32-C34, incl. larynx)" in data labels | 0.25 | text |
| 12 | The `ldct-pilot` card says "invite ... to low-dose CT", as if no pilot exists. Checked: roadmap 2.3.4 (p. 46) and `data/roadmap/mapping-v1.json` already say "join or extend the existing pilot" | Judges handed out the roadmap | Card text: "Join the national lung screening pilot (2.3.4); propose expansion by lung mortality" | 0.1 | with item 5 |
| 13 | Satakunta's "gap at referral" sentence rests on a whole-percent indicator whose latest value equals the national value | The THL statistician will pick it | Tonight: say "possible signal" in the deck. Code rule (latest year and three-year mean must agree, plus a minimum absolute difference) only if time | 0.25 / 1 | text |
| 14 | Chips mislabelled; raw codes shown; two death baselines (13,424 and 13,289) | Labelling is SAMA's transparency point (Data quality 20%) | TARGET chip, plain names, one baseline | 1 | after freeze in deck; page if time |
| 15 | Optimiser output reads as an artefact (timed pathways in 19 areas, navigators only in Åland) | A county director cannot act on it | Present per county in the deck; exclude or label Åland | 1 | deck |
| 16 | Overdue thresholds conflict. Checked: the `navigation` action already flags a work-up at 90 days without diagnosis (`src/recommend.mjs` `PUBLIC_WORKUP.stallAfterDays = 90`, relabelled a placeholder in `mapping-v1.json`); DO #2 used day 42 | Two different triggers for one idea | DO #2 is the operational form of `navigation` (roadmap 1.2.3); one placeholder table (DO #2) | 0.1 | with DO #2 |
| 17 | Sponsor optics. Checked: the Filha programme's planning-phase supporters were Amgen, Sanofi, AstraZeneca, Roche, Boehringer Ingelheim and two foundations, who "eivät ole osallistuneet ohjelman sisällön suunnitteluun" (did not take part in planning the content), p. 26. The pilot is lung-only, and the cited governance precedent is a CKD pilot, also an AstraZeneca area | A patient-finding pilot in the sponsor's therapy area looks promotional | "Every overdue suspected-cancer referral, lung follow-up first". "SAMA is sponsor-independent; any company role is a documented, non-promotional collaboration owned by the county." Disclose all five companies. Say "no patient data leaves the county" | 0.25 | text |
| 18 | No regulatory line | Medical affairs will ask | Pilot card: "a workflow aid: it copies the radiologist's written recommendation, computes a date, and a nurse decides. Device qualification under the MDR to be confirmed with Fimea before the pilot (UNVERIFIED). AI Act high-risk dates 2 Dec 2027 and 2 Aug 2028 tracked" | 0.1 | text |
| 19 | The national ask names only THL's TTP feed. Checked: roadmap 3.2.1 (p. 59) funds a cancer quality register at the THL Cancer Registry, EUR 2,500,000; the THL-Cancer Registry-FICAN research project runs to the end of 2027 with five cancers first; the decree is updated in 2026-2028; metrics: 90% data coverage including stage, and 90% of clinical notifications automated by 2030 | Misses the window where the variable set is being fixed | Deck slide 7: two carriers, TTP for the clock and 3.2.1 for stage and route; "add these fields while 3.2.1 is being specified" | 0.25 | deck |
| 20 | Language is not handled: no scope line, no contact language, Lapland deferred for the wrong reason | Bilingual Finland; 1.3.1 targets exactly this gap | Scope line "Finnish notes only; other languages go to manual entry". Contact-language column in DO #2. Lapland waits because Sámi-language outreach must be co-designed with the Sámi Parliament (Sámi language rights: general knowledge, UNVERIFIED) | 0.25 | text and DO #2 |
| 21 | Three counties are under the state assessment procedure: South Karelia, South Ostrobothnia, Kymenlaakso (valtioneuvosto, 16 Jun 2026, [page](https://valtioneuvosto.fi/-/10623/hyvinvointialueen-arviointimenettely-kaynnistyy-kolmella-alueella-), research and critic). Nemotron plans exist for all 23 areas | Naming them in a blame context is risky | Default the planner panel and demo to Satakunta; never name the three in blame contexts; label every plan "draft input on public data, not an assessment" | 0.1 | with item 1 |
| 22 | `gp_wait_over_7d` measures against a 7-day limit; the legal maximum changed from 2025. Checked: national value 43.4% (2024) to 54.7% (2025) in `app.json` | A trend that is partly a law change | Footnote: "the legal maximum changed from 2025; post-2024 values are not comparable" | 0.1 | text |
| 23 | AI imaging story is one-sided (LungIMPACT only) | Diagnostics mentors and the sponsor run AI reading programmes | "AI saves reading time (MASAI); it does not by itself move the pathway (LungIMPACT); spend the time saved on closing loops and reaching non-attenders." Roadmap 2.4.2 (p. 48) says the two-radiologist rule "haittaa merkittävästi" (significantly hampers) AI in breast screening | 0.1 | text |
| 24 | The story speaks about 12 figures | Non-technical judges | At most five spoken number items; the rest as captions (section 4) | 0 | done here |
| 25 | Precision wording | Small errors cost trust | CRUK split is April-June 2026; "no study described harms"; "the Cancer Organisations say no strategy money is planned for 2027"; "no significant regional difference was found"; "Sweden-Norway average 31.1"; "five-year relative survival"; "we found no Finnish statistic that counts it" | 0.25 | text |
| 26 | No mentor input recorded; no hosted demo | The brief names mentor insight | Record any mentor conversation; hosting is the owner's call | 0.1 | owner |

---

## 3. New ideas, ranked by the panel's combined score

Three panel members scored 23 ideas from four lenses (patient and clinician, health system and
policy, AI and NVIDIA, contrarian) on five criteria: equal-care impact, novelty, credibility,
feasible tonight, jury fit (1-10 each). Combined score = sum over the three members, maximum 150.

**Panel verdict.** All three members picked "who, how and where" and "close the loop". For the third
slot two members picked the measurement-plus-visibility gate and one picked the zero-euro 2027 plan.
The gate wins; the zero-euro plan becomes one slide. After the critic's time and memory check, DO #2
is code-only and DO #3 is deck slides by default.

### 3.1 Score table

| Rank | Idea | P1 | P2 | P3 | Total | Verdict |
|---|---|---|---|---|---|---|
| 1 | Who and how, not where | 39 | 39 | 43 | 121 | **DO #1** |
| 2 | Who, not only where (policy lens) | 41 | 38 | 38 | 117 | **DO #1** (merged) |
| 3 | The Pathway Clock (fields on THL's person-level feed) | 39 | 38 | 39 | 116 | **DO #3** (slide 7); FLARE edge a stretch |
| 4 | Close loops, don't count them | 39 | 33 | 40 | 112 | **DO #2** |
| 5 | Nobody lost after the scan | 37 | 33 | 39 | 109 | **DO #2** (merged) |
| 5 | Stalled-pathway safety net (2026 law) | 37 | 34 | 38 | 109 | **DO #2** (merged) |
| 5 | Ask for two dates, not nine | 36 | 36 | 37 | 109 | **DO #3** (framing of the ask) |
| 8 | Completeness before comparison | 34 | 37 | 36 | 107 | **DO #3** (coverage chip); funding critique a footnote at most |
| 9 | Incidental lung-nodule loop clock | 36 | 32 | 37 | 105 | **DO #2** (one example row, rule-based) |
| 10 | Cancer into the state steering cycle | 34 | 32 | 35 | 101 | Vision |
| 10 | Comparability gate via FLARE | 31 | 31 | 39 | 101 | Rule in DO #3; per-county scribe bias vision |
| 12 | Timestamps for free (scribe event spec) | 33 | 32 | 32 | 97 | Gate in DO #3; spec vision |
| 13 | Zero-euro 2027 plan and "not yet" list | 36 | 26 | 31 | 93 | Vision slide; "not yet" list rejected |
| 14 | Stage from text, copy only | 28 | 31 | 31 | 90 | Part (a) in DO #3; part (b) vision |
| 14 | Gemma audits, it does not author | 28 | 29 | 33 | 90 | Vision (one line) |
| 16 | Same pathway in every language | 29 | 28 | 32 | 89 | Stratifier in DO #1, contact language in DO #2; Swedish slice vision |
| 16 | Two-tier privacy, Nemotron bulletin | 28 | 29 | 32 | 89 | Vision |
| 18 | Federate across entry routes | 28 | 27 | 29 | 84 | Vision (one line) |
| 19 | Two budgets (FICAN EUR 139M) | 30 | 26 | 26 | 82 | 2027 half to the zero-euro slide; rest rejected |
| 20 | Federated LoRA for the scribe | 25 | 23 | 29 | 77 | Vision |
| 21 | One trip, not five (travel burden) | 25 | 25 | 26 | 76 | Vision (one line) |
| 22 | My pathway clock (patient-facing) | 23 | 22 | 28 | 73 | Rejected |
| 23 | Attested confidential inference on Verda | 19 | 19 | 21 | 59 | Rejected |
| - | Emergency presentation as a late-diagnosis indicator (added by panel 2 after scoring) | - | - | - | not scored | Vision, one "how" line in DO #3 |

### 3.2 Do tonight (three items)

#### DO #1. "Who, how and where" panel (combined 121 and 117)

- **Pitch.** County averages cannot see Finland's main cancer inequality. Show it right after the map,
  attach the actions that already target it, and report every indicator by education, entry route
  and mother tongue within each county.
- **What is new.** The ecological county pattern runs against the individual one, and the reason is
  visible: programme attendance is lowest in the capital region. The OECD says Helsinki's low
  attendance is "likely" due to more screening outside the programme, and the three lowest-attending
  areas have the highest foreign-background shares (item 7 of 2.2). A county league table therefore
  measures recording and population mix, not who is missed. We found no Finnish dashboard that shows
  this (UNVERIFIED absence claim).
- **Evidence.**
  - OECD/EU 2025 profile (re-checked): survival, screening by education and mother tongue (section 1,
    bullet 4); Helsinki's low participation "likely" due to opportunistic screening, p. 14.
  - SAMA's own data (`web/data/app.json`, checked tonight): correlation of breast attendance with the
    education index r = -0.59 across 22 counties, -0.35 without Helsinki (simple correlation computed
    by this step; not SAMA's SII method).
  - Filha preprint (re-checked from the saved copy): lung five-year survival by education within sex,
    men about 13% against 18%, women about 20% against 30%. Do not use the "30% against 13%"
    contrast: it mixes sex and education.
  - Kuitunen J et al. 2026 (re-checked from the saved copy): median 127 against 76 days, 48 against
    39 patients, p = 0.027; over-70s median 135 days; widowed median 202 days.
  - Zai et al., BMJ Public Health 2025 (research; also `data/evidence/literature-v1.json`
    `zai-2025-mortality-education`): cancer mortality HR 1.13 (men) and 1.14 (women), low against
    high education, adjusted for region.
- **The action row that ends the panel.**
  - Roadmap 1.3.1 (EUR 400,000, p. 33, re-checked) has the exact metric: participation of people whose
    mother tongue is not Finnish or Swedish should reach the level of Finnish and Swedish speakers.
  - SAMA's matching actions: mailed HPV self-sampling to cervical screening non-attenders, Finnish RCT
    relative participation 1.21 (1.13-1.30) (Virtanen 2011, doi 10.1158/1055-9965.EPI-11-0307) and
    pooled 2.33 (1.86-2.91) (Arbyn 2018 BMJ, doi 10.1136/bmj.k4823), both in
    `literature-v1.json`; restoring pre-booked appointment times (Helsinki cervical participation
    fell from about 72% to 62% when they were removed and recovered after reverting; Yle,
    10 Dec 2025, [page](https://yle.fi/a/74-20198630), panel; one city, no years given).
- **Tonight.** 1-1.5 h, USD 0, Lane C, 01:15-02:15 UTC. Kill at 02:15: it becomes a deck slide.
  1. Left: a small chart of 2024 breast attendance with the capital-region areas marked. Caption:
     "Programme attendance is lowest in the capital region, where many women screen privately and
     many people speak other languages; county averages cannot show who is missed." No SII number.
  2. Right: the individual-level figures above, with correct programme labels.
  3. Bottom: the action row.
  4. Promise line: "wherever they live, whoever they are, however they enter care". Keep the map as
     the hero.
  5. New figures enter through `data/evidence/literature-v1.json`, so `tests/tracks.test.mjs` and
     `submission/check_numbers.py` still hold.
- **After the hackathon.** Link the event log to Statistics Finland education and language data at
  analysis time under a Findata permit; report Goal 3 indicators by route, education and language;
  target navigators and self-sampling by group within each county.
- **Tracks.** AstraZeneca (Insight, Data quality, Actionability).
- **Risks.** County and individual figures are different kinds of data: say "cannot see", not "points
  the wrong way". Education and language are sensitive: aggregates only, n < 5 suppressed. The route
  gap is one cohort of one cancer with 87 patients in the two route groups.

#### DO #2. Close the loop: a county worklist for overdue suspected-cancer pathways, lung follow-up first (combined 112, 109, 109, 105)

- **Pitch.** Give one county a daily list of people whose suspected-cancer pathway has stalled: an
  urgent referral with no next step after the placeholder time, or a lung scan (incidental or from
  screening) whose recommended follow-up has not happened. A nurse confirms each item and calls. The
  county's statistic comes out of the same list.
- **What is new.** It moves SAMA from observatory to operation, on a legal basis five months old.
  It is the operational form of SAMA's existing `navigation` action (roadmap 1.2.3), not a new card.
  Faster reading is not the bottleneck (LungIMPACT); closing the follow-up is. Every expansion of the
  national lung screening pilot (2.3.4) creates more follow-up loops to close.
- **Evidence.**
  - Law in force 1 June 2026 (STM, 21 May 2026, re-checked). Whether "recommendations" covers the
    timing of pathway steps is UNVERIFIED; confirm with STM and THL.
  - Filha preprint (re-checked from the saved copy): earlier-stage lung cancers "löytyvät useimmiten
    sattumalta" (are mostly found by chance) on lung imaging taken for another reason; regional
    variation in diagnosis speed is large; no national timetable for diagnostic steps; targets of 10%
    more curative treatment and at least 14% better five-year survival.
  - Roadmap 1.2.3 (named care-coordinating worker, EUR 100,000) and 3.5.3 (digital pathways and AI
    tools, EUR 1,140,000), `data/roadmap/roadmap.txt` (re-checked by the earlier revision).
  - AstraZeneca Päijät-Häme CKD pilot (12 Mar 2026, [release](https://www.mynewsdesk.com/fi/astrazeneca/pressreleases/kroonisen-munuaistaudin-riskipotilaiden-tunnistaminen-kaeynnistyy-paeijaet-haemeessae-digitaalisella-tyoekalulla-3437062),
    re-checked by the earlier revision): the county provider owns the pilot and the care, nurses
    contact patients from a pseudonymised list, and no patient data goes to AstraZeneca. Cite it in
    the deck only with the owner's yes (decision 7).
  - Navigation for follow-up after an abnormal breast result: RR 1.23 (1.15-1.41), only 3 trials and
    1,008 participants (INCa summary, panel). Do not carry it over to lung as an effect size.
- **Placeholder thresholds (one table, all labelled).**

  | Clock | Threshold | Source of the number |
  |---|---|---|
  | Referral to treatment | 42 days | Placeholder: the OECD/EU-reported six-week target |
  | Referral to diagnosis (worklist trigger) | SAMA placeholder, default 90 days as in `navigation` | `src/recommend.mjs`, relabelled in `mapping-v1.json` |
  | Imaging follow-up | The due date the radiologist wrote | Copied, never decided by SAMA |

  The clock starts when the referral is **sent** (SAMA's `REFERRAL_SENT` event); say so on the panel.
- **Tonight.** About 1.5 h, USD 0, Lane B, 00:00-01:30 UTC, after the planner is green. Kill at
  01:30: one deck slide. New paths only.
  1. Code renders about 60 SYNTHETIC Finnish radiology sentences ("kontrolli-TT 3 kuukauden
     kuluttua", ranges, "ei jatkotoimia"). Code templates, not a model writer.
  2. A forward-phrase lexicon rule in a new module copies the written recommendation and computes the
     due date. Ranges and vague phrases go to a person. **No Gemma and no MLX job tonight**: at 22:23
     UTC Lane A's training was killed when swap grew from 33.6 to 44.55 GB beside another project's
     12B MLX job (`runs/laneA-step3.jsonl`); at 22:39 UTC this step read 432 MB of swap free and other
     projects' Python and MLX jobs still running (`sysctl vm.swapusage`, `ps`). Do not touch the
     frozen resolver or lexicon (`data/scribe/v4/resolver/freeze.json`).
  3. Join with the SYNTHETIC event log in a separate extension file (do not edit `eventlog/schema.py`).
  4. Panel: counts first (N overdue, share followed up on time), then at most 3 unnamed SYNTHETIC rows:
     episode code, age band, route, contact language (fi/sv/se/other, interpreter flag), days
     overdue, missing step, "nurse confirms / needs editing".
  5. Governance line: "The county owns the list and the care. No patient data leaves the county. Any
     company role is a documented, non-promotional collaboration owned by the county."
  6. Regulatory line (item 18 of 2.2).
- **Pilot county: Satakunta, on process grounds.** Finnish-language services; not under the state
  assessment procedure; already on the pilot card (`mapping-v1.json` `pilotCard`); high lung burden
  (shrunk 1.126, 1.045-1.21). Not "highest lung mortality": Lapland (1.237) and Kymenlaakso (1.132)
  are higher. Satakunta is probably outside the screening pilot: the five regions named in the pilot's
  January release (Uusimaa, Pirkanmaa, Pohjanmaa, Pohjois-Pohjanmaa, Varsinais-Suomi; STT,
  21 Jan 2026, research) make up "Helsinki and eight" counties if Uusimaa counts as Helsinki plus four.
  That is this step's inference, UNVERIFIED; ask a mentor. If Satakunta is in a randomised pilot arm,
  the worklist's evaluation design must change.
- **After the hackathon.** A 12-month pilot under roadmap 1.2.3 and 3.5.3, with a data protection
  impact assessment and opt-out. KPIs: share of follow-ups closed on time, share resolved within
  14 days, stage at diagnosis; each reported by route, education and contact language, so the safety
  net cannot reproduce the gap. Lapland second, once Sámi-language outreach is designed with the Sámi
  Parliament.
- **Tracks.** AstraZeneca (Actionability). Gemma reads the referral note in the existing demo
  (`runs/laneC-step7.jsonl`: 18/20 exact on CPU, median 4.8 s over HTTP); the radiology line is a code
  rule tonight. Optional Nemotron VL reading of report images belongs to Lane B's step 6b, only after
  02:30.
- **Risks.** False "overdue" alerts and nurse workload. SAMA never decides what follow-up is due. Do
  not present Lapland's excess lung deaths as the benefit: mortality follows incidence (Filha p. 12).
  Name no vendor or product; no biomarker or drug content.

#### DO #3. Measure it only where it can be seen: the clock and the visibility gate (combined 116, 109, 107, 101)

- **Pitch.** Ask for the smallest national dataset that measures Finland's target, show it can be
  computed where the data live, and refuse to rank an area that cannot see itself.
- **What is new.**
  - The national minimum shrinks to Sweden's mandatory points: date of well-founded suspicion, end
    date with end reason (treated, ruled out, other), county of residence and entry route. SAMA's
    four timestamps become the optional points a pilot county records to locate a delay
    (473 / 513 / 347 complete episodes, `data/eventlog/design-study-v1.json`).
  - Two carriers already exist: THL's person-level waiting-list feed (TTP) for the clock, and the
    roadmap 3.2.1 quality register project, whose variable set is being fixed by the end of 2027,
    for stage and route.
  - Coverage before comparison: SAMA's simulation flags a county whose dates come from text in 1.000
    of runs with no real slowdown, and 0.003 with the code resolver
    (`data/eventlog/design-study-v1.json`, `measured_interval_extraction`, SYNTHETIC).
  - Add one "how" line from the same feed: the share of cancers first seen in emergency care, by
    county, route and education. Internationally 24.0%-42.5% of diagnoses across 14 jurisdictions
    (including Denmark and Norway) came through emergency presentation, with higher 12-month
    mortality in every stratum (adjusted OR 2.62-3.53) (McPhail et al., Lancet Oncol 2022, ASCO Post
    19 Apr 2022, [page](https://ascopost.com/news/april-2022/diagnosis-of-cancer-within-30-days-after-emergency-hospital-admission/),
    re-checked). SAMA's schema already has `entry_route` = `EMERGENCY` (`eventlog/schema.py`).
- **Evidence.**
  - THL's specialised-care access statistic covers non-urgent care only, as month-end aggregates;
    person-level delivery via TTP is due 1.1.2028 in one section and 1.1.2026 in another (THL quality
    report, updated 17 Aug 2026, [page](https://thl.fi/data-ja-tilastot/tiedon-laatu/tilastojen-laaturaportit/laaturaportti-hoitoonpaasy-erikoissairaanhoidossa), research and panel). Say "by 2028 at the latest".
  - Roadmap 3.2.1, p. 59 (re-checked; item 19 of 2.2).
  - Sweden's mandatory points and monthly reporting by county of residence without the personal
    identity number; 148,441 pathways in 2025 (SVF report, research and panel).
  - Stage completeness 42% (re-checked); clinical treatment notifications fell from over 90% to under
    50% coverage (roadmap 4.1.4, research).
- **The gate on real data applies to areas, not counties.** Stage completeness is published by area
  only. Satakunta's area is very likely below 70% (UNVERIFIED), so the pilot county would read "cannot
  be assessed". Use that as the pitch: "the pilot is how Satakunta learns to see itself". County-level
  gating appears only in the SYNTHETIC clock.
- **Tonight.** Default: deck slide 7 rewritten with the two carriers, the minimum, the gate and the
  placeholder labels (Lane C, text, after the freeze). Stretch, Lane B 01:30-02:30 after Lane C hands
  over `flare/`: add referral-to-treatment with a histogram edge at 42.5 days, labelled "placeholder
  (OECD/EU-reported target)", and a coverage column to the existing FLARE job. FLARE already
  reproduces the central share within its thresholds exactly (`data/flare/RESULT.md`). Kill at 02:30.
- **After the hackathon.** Propose the fields to THL's TTP specification and to the 3.2.1 project;
  publish a monthly residence-based table with n < 5 suppression and an EHR-migration log; compute
  per county with FLARE or THL's own environment.
- **Tracks.** AstraZeneca (Actionability, Data quality); NVIDIA (FLARE; does not count toward the
  Nemotron minimum).
- **Risks.** Two points show that a pathway was late, not where. "Well-founded suspicion" needs
  clinical consensus and can be gamed. THL guidance 21/2016 may already define cancer access dates
  (UNVERIFIED): check before saying Finland never defined them. Measuring alone did not fix Sweden, so
  pair it with DO #2.

### 3.3 Vision only (slides or one line each)

| Idea | Pitch and what is new | Key evidence | After the hackathon | Tracks | Risks |
|---|---|---|---|---|---|
| Cancer into the state steering cycle | A checked one-page cancer annex per county for THL's yearly assessment and the ministry negotiation; needs no new money | THL's steering role strengthened from 1 Jun 2026 ([valtioneuvosto, 13 May 2026](https://valtioneuvosto.fi/-/1271139/thl-n-rooli-hyvinvointialueiden-sosiaali-ja-terveydenhuollon-ohjauksessa-vahvistuu), research) | Nemotron county plans become the annex format | AstraZeneca, Nemotron | "Cancer is absent from THL assessments" rests on one 2024 text layer (UNVERIFIED). Satakunta only; no THL-like layout |
| Zero-euro 2027 plan | One slide: pre-booked screening times, the worklist with existing nurses, two dates in THL's feed. Context line: counties under deficit pressure; primary-care maximums lengthened in 2025 | STT, 4 Sep 2026 (research); Yle, 10 Dec 2025 (panel); STM hoitotakuu (re-checked) | Re-run the optimiser with the next government's envelope | AstraZeneca | Pre-booking evidence is one city's before-after; effect is a SCENARIO |
| Scribe event spec | Any scribe emits four dated events a clinician confirms in one click | Länsi-Uusimaa rolls out an AI scribe to about 7,000 staff by end-2027 ([STT, 24 Aug 2026](https://www.sttinfo.fi/tiedote/72254203/lansi-uudenmaan-hyvinvointialue-uudistaa-kirjaamista-tekoalyn-avulla?lang=fi), research) | JSON Schema and FHIR mapping in the appendix | Gemma, AstraZeneca | Vendor-neutral; name no product |
| Stage from text, copy only (part b) | Copy an explicit stage string or route to the registrar; never infer | Stage 42% (re-checked) | Registry pilot in one low-completeness area | Gemma | A wrong stage corrupts survival statistics |
| Gemma audits, it does not author | 200 sampled notes estimate a county's completeness to about ±7 points | 1.96 × sqrt(0.25/200) ≈ 0.069 | Monthly audit inside a county or Findata Kapseli | Gemma | Would undercut Lane A's preregistered story if pivoted tonight |
| Same pathway in every language | A Swedish scribe slice; Sámi route | OECD language gaps (re-checked) | Swedish evaluation on real notes in a secure environment; Sámi route designed with the Sámi Parliament | AstraZeneca, Gemma | Templated Swedish notes would test our own templates; Sámi counts too small to publish |
| Two-tier privacy, Nemotron bulletin | Gemma reads notes in the county; FLARE carries aggregates; Nemotron writes a monthly bulletin from aggregates only | EHDS allows only non-personal downloads from secure environments (Commission page, research) | Self-hosted Nemotron in Finland | Nemotron | Aggregates still need a disclosure policy |
| Federate across entry routes | A county federation cannot see occupational and private first contacts, the fast route | Route gap (re-checked) | National route view via THL or Kela | AstraZeneca, NVIDIA | Kanta holding usable occupational first-contact dates is UNVERIFIED |
| Federated LoRA | Teach the scribe every county's writing style without moving notes | Other-writer test 13.0% to 47.5% when that writer's notes were added (`data/scribe/v3/student/compare-v1.json`, SYNTHETIC); FLARE LLM fine-tuning docs ([page](https://nvflare.readthedocs.io/en/main/programming_guide/llm_fine_tuning.html), research) | 3-5 county clients with DP or clipping | Gemma, NVIDIA | Competes with MLX memory tonight |
| One trip, not five | Distance as a fourth "how" axis; one-stop diagnostic day | Some residents live over 400 km from a central hospital (roadmap, research); Vaasa HR 1.47 (UNVERIFIED) | Road travel times and Kela claims via Findata | AstraZeneca | Must not argue against centralisation |
| Emergency presentation (not scored) | Late-diagnosis indicator from the same feed, no new data entry | ICBP via ASCO Post (re-checked) | Findata linkage of registers; Finnish feasibility UNVERIFIED | AstraZeneca | Linkage needs a permit |

### 3.4 Rejected, and why

- **Attested confidential inference on Verda.** New spending with a near-zero balance; SYNTHETIC
  inputs make attestation meaningless to judges; a confidential VM is not a Findata-audited
  environment; FLARE's confidential computing is a technical preview.
- **My pathway clock (patient-facing card).** Risk of resembling MyKanta, wrong clocks from
  incomplete data, anxiety, and a wider digital gap. The law allows six months; the six-week figure
  is OECD-reported.
- **FICAN EUR 139M budget case before the 18 Apr 2027 election.** The Goal 3 share would be our
  invention, and a sponsor-judged entry must not look like lobbying for public budgets.
- **The "not yet" list naming specific technologies.** Off-message next to a sponsor with AI imaging
  partners. Keep the two-sided AI line instead (item 23 of 2.2).
- **Tonight only:** pivoting the Gemma story to "audits", synthetic stage extraction, demoting the
  map from the hero, any new Gemma or MLX job, Nemotron writing the synthetic radiology lines (use
  code templates), and Zulueta's stage figures on a slide (secondary summary, groups never compared).
- **Framing county excess mortality as deaths avoidable by better care.** Mortality mixes incidence
  and survival.

---

## 4. The new two-minute story

274 spoken words (counted with `wc -w`, captions excluded); `submission/check_numbers.py` allows 276,
so any added word means cutting another. Spoken number
items: 17.9 vs 31.1, 127 vs 76, six weeks vs six months, 42 percent. Everything else is a caption.
Every patient-like screen is labelled SYNTHETIC.

> **[0:00]** In Finland, five years after a lung cancer diagnosis, relative survival for men is 17.9
> percent. The Sweden and Norway average is 31.1. The national lung programme says curable cases are
> mostly found by chance, on scans taken for something else. What happens next decides who is cured.
> *[Caption: NORDCAN; Filha lung programme 2026]*
>
> **[0:20]** Where you live is not the main gap. Studies find no significant difference in survival
> between regions. They do find one by education, and by how you enter care. In one Finnish lymphoma
> study, the median from first symptom to treatment was 127 days through a public health centre
> appointment, and 76 through occupational or private care.
> *[Caption: OECD/EU 2025: 64-65% vs 77-78% five-year survival by education. Kuitunen 2026: 48 vs 39
> patients, p = 0.027]*
>
> **[0:45]** The OECD reports a six-week target from suspected-cancer referral to treatment. The law
> allows up to six months. No county can show whether it meets either, and stage is recorded for only
> 42 percent of cancers. SAMA asks for two dates and an end reason per patient. On synthetic data,
> NVIDIA FLARE computed each county's figures where the data live; only totals left. A county is
> compared only when it can see itself.
>
> **[1:15]** Measuring is not enough. Since June, a county may find patients whose care does not
> follow recommendations, and contact them. SAMA turns that into a nurse's list: every overdue
> suspected-cancer referral, lung follow-ups first. Gemma reads the referral note on county hardware,
> code counts the days, and a nurse confirms and calls.
> *[Demo, SYNTHETIC. Caption: in a trial of 93,326 chest X-rays, faster AI reading did not shorten
> the wait for CT]*
>
> **[1:45]** Nemotron drafts each county's plan, and code checks every number. Our ask: Satakunta,
> lung follow-up first, a 2027 pilot inside the national roadmap. The county owns it, and no patient
> data leaves the county. Everything patient-like here is synthetic.

**Sources.** 17.9 and 31.1: NORDCAN in `web/data/app.json`. "Found by chance": Filha preprint
(re-checked). 64-65 and 77-78, six weeks: OECD/EU 2025 (re-checked). Six months: STM hoitotakuu
(re-checked). 127, 76, 48, 39: Kuitunen J 2026 (re-checked). FLARE: `data/flare/RESULT.md`
(SYNTHETIC). 42 percent: Syöpäjärjestöt (re-checked). "Since June": STM, 21 May 2026 (re-checked).
93,326: LungIMPACT (re-checked). Nemotron plans: `runs/laneB-step6.jsonl`.

**Conditions.**
- `check_numbers.py` will fail until the OECD survival figures, 42%, 93,326, the six-week target and
  the six-month limit are added as evidence entries; the owner of `submission/` adds them through the
  evidence file.
- Say "Nemotron drafts each county's plan" only if must-ship item 1 is green; otherwise cut that
  sentence and show the cached plans on a slide.
- If DO #2 shipped, the radiology line on screen was read by a code rule: caption it "code reads the
  follow-up recommendation". "Gemma reads" stays only for the referral note, which the existing demo
  shows.
- Say "two dates and an end reason" only if decision 4 is yes; otherwise "four dates".
- If the clip runs long, trim the FLARE sentence first.

---

## 5. NVIDIA FLARE and privacy infrastructure, in plain language

**What FLARE is.** An open-source NVIDIA toolkit (Apache-2.0; version 2.9.1 on PyPI, 12 Nov 2026,
https://pypi.org/project/nvflare/, research). Instead of sending data to one place, you send the same
small program to every site. Each site runs it on its own data and returns only results. For
statistics it computes "count, sum, mean, std_dev, quantiles and histogram"; it states "We do not
include min and max values to avoid data privacy concerns". Filters run before anything leaves a
site: `MinCountCleanser` drops a feature with too few records, `HistogramBinsCleanser` drops a
histogram with too many bins for its count, and `AddNoiseToMinMax` adds noise when a histogram range
must be estimated ([GitHub example](https://github.com/NVIDIA/NVFlare/tree/main/examples/advanced/federated-statistics), re-checked by the earlier revision).

**What it already did for SAMA tonight** (`data/flare/RESULT.md`, SYNTHETIC, 21:42-22:00 UTC):
- 23 simulated county sites on one Mac, no container, no cloud, USD 0. Install about 7 s. PyPI still
  lists Linux only, but it ran on macOS arm64.
- 92 of 92 county-by-interval cells equal SAMA's central table within 1e-6.
- A finer run (1,932 cells) suppressed the same 40 small cells as SAMA's n < 5 rule.
- The share within each placeholder threshold, read from FLARE's histogram, equals the central share
  exactly.
- Three lessons: FLARE rounds to 4 decimals by default (fixed with `precision=12`); its national row
  is wrong when a county is suppressed (compute it from unsuppressed rows); the histogram filter needs
  about 95 cases per cell for 9 bins.

**What it would do for SAMA.** Each county computes its own pathway clock next to its own records;
only suppressed totals leave. That answers the question every judge will ask: how do you get waiting
times without moving patient data? The precedent judges will recognise is NORDCAN, whose survival
figure opens SAMA's story and which is already produced this way.

**What it is not.**
- Not the idea itself. The idea is the clock and the gate; FLARE carries them.
- Not a legal permit. Aggregates still need a disclosure policy. The Finnish legal route (the
  Secondary Use Act and a Findata permit) is an interpretation to confirm with THL and Findata.
- Not the Nemotron track minimum, which needs Nemotron on the page (must-ship item 1).
- Not able to see occupational and private care when only counties are nodes.
- Its confidential-computing mode is a technical preview, and aggregation in a TEE "is not a
  cryptographic secure-aggregation protocol" ([docs](https://nvflare.readthedocs.io/en/main/user_guide/confidential_computing/index.html), research).

**Other privacy infrastructure** (research, opened 14 Nov):

| Piece | What it is | Tonight |
|---|---|---|
| Findata Kapseli | Finland's secure research environment: no internet, results leave only after an anonymity check, Python 3.12 with torch, no GPU listed, Linux S EUR 141/month ([findata.fi](https://findata.fi/en/kapseli/), updated 23 Sep 2026) | Slide: where the scribe would first be validated on real notes |
| EHDS | EU rules for secondary use of health data: from March 2029 for most categories, March 2031 for the rest; only non-personal data may be downloaded from secure environments (Commission page) | One dated line on the roadmap slide |
| EU AI Act | High-risk duties from 2 Dec 2027 (Annex III) and 2 Aug 2028 (regulated products) (re-checked) | One line on the pilot card |
| vantage6 / DataSHIELD | Registry-native federated analysis (vantage6 ran survival analyses across 94 European registries, Taiwan and Japan, [PMC10534949](https://pmc.ncbi.nlm.nih.gov/articles/PMC10534949), 13 Sep 2023) | Mention as alternatives; do not install |
| NeMo Safe Synthesizer | Differentially private synthetic tables; Linux, A100 or larger; DP off by default ([GitHub](https://github.com/NVIDIA-NeMo/Safe-Synthesizer)) | No |
| Verda confidential VMs | Attested GPU VMs; RTX PRO 6000 CC USD 2.893/h on demand ([verda.com](https://verda.com/gpu-instances)) | No (rejected) |

**Realistic tonight:** one slide, plus at most DO #3's stretch (one 42.5-day edge and a coverage
column in the existing FLARE job, 01:30-02:30 UTC). No federated training, no confidential VM, no new
spending, no new MLX load.

---

## 6. Owner decisions needed

1. **Memory.** Pause other projects' MLX and model jobs on this Mac until Lane A's step 8 finishes
   (at 22:39 UTC this step saw 432 MB of swap free and other projects' jobs running, including
   `verda/judge/mlx_list_train.py` on a 4B model), or accept the risk to the preregistered evaluation.
2. **Integrator.** Confirm Lane C takes over `web/app.mjs`, `web/index.html`, `README.md` and
   `web/data/app.json` from the tracks integrator (last log 20:53 UTC).
3. **Patient-like rows in front of AstraZeneca judges.** Recommendation: counts first, then at most
   3 unnamed SYNTHETIC rows, or counts only.
4. **The national ask.** "Two mandatory dates plus end reason, residence and route; four dates
   optional" instead of "four timestamps". It changes deck slide 7 and the framing of
   `DATA_COLLECTION.md`, whose owner must agree.
5. **Pilot.** Satakunta, "every overdue suspected-cancer referral, lung follow-up first", justified
   on process grounds. Ask a mentor whether Satakunta is in the lung screening pilot.
6. **Route model.** Keep the 84-day prior with the disclosure line (recommended at midnight), or set
   the range to 51-75 days and rebuild, which changes the scenario tables.
7. **Sponsor disclosures in the deck.** Disclose all five companies that supported the Filha
   programme's planning phase; cite the Päijät-Häme governance precedent or not; say "no patient data
   leaves the county".
8. **Remove the Evo 2 "treatment selection" section** from the AstraZeneca page and video.
9. **Headline.** Move from "deaths postponed" to a process metric.
10. **No external contact tonight** with THL, STM, Fimea, Findata or any county. Any such message is
    yours to send.
11. **Still open from `NVIDIA_OPTIONS.md` section 4:** deadline and form check, publication of the
    source and adapter, Haiku-written training notes, Verda track entry, who records the voice-over
    and who submits.

---

## 7. What is unverified

- Whether "recommendations" in the 1 June 2026 law covers the timing of pathway steps or follow-up
  imaging (confirm with STM and THL).
- The legal status of the six-week target. Only the OECD/EU wording was read; STM's page lists no
  cancer-specific limit. THL guidance 21/2016 was not read and may already define cancer access dates.
- THL's TTP deadline: the same page says 1.1.2028 and 1.1.2026.
- Which eight counties are in the lung screening pilot, and whether Satakunta is one (this step's
  inference says probably not).
- Satakunta's stage completeness (published by area only; very likely below 70%).
- Whether SAMA's worklist qualifies as medical device software under the MDR (MDCG 2019-11 returned
  HTTP 403 to the critic). Industry-code rules for joint working (Lääketeollisuus, EFPIA).
- Åland's separate health legislation, and Sámi-language service rights (general knowledge only).
- Any Finnish count of incidental lung nodules without follow-up (none found; measuring it is the
  pilot's first output).
- The Helsinki pre-booking effect: one city, no years given in the article.
- Sweden and Norway waiting-time figures: verified by research agents, not re-checked by this step.
- Kanta holding usable occupational first-contact dates.
- "Cancer is absent from THL's county assessments": one 2024 document's text layer.
- Nemotron's Finnish; Gemma 4 licence terms; Verda confidential-computing instance names and locations.
- The 93% resolver result on real text (post hoc, synthetic date forms only); the frozen stress-set
  result is still pending.
- "We found no Finnish dashboard that shows this": an absence claim from searches, not proof.
- The deadline (08:00 UTC Sunday) and whether one project can still enter every track.
- **Resolved tonight:** nvflare runs on macOS arm64 (`data/flare/RESULT.md`); Kuitunen's route group
  sizes (48 and 39) and first author (Joonas Kuitunen); Finland has 21 wellbeing services counties;
  AI Act application dates; the Filha supporter list and the within-sex lung education figures; the
  ICBP emergency-presentation figures.
