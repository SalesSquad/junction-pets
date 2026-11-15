# SAMA: judge Q&A

The 25 hardest questions we expect from the juries (AstraZeneca medical and market-access leads, a
THL statistician, a county cancer-services director, Google DeepMind, NVIDIA, Verda), each with a
short honest answer and its source. Written 15 November 2026, 00:31-00:45 UTC, by the deliverables
Q&A step (log `runs/deliv-qa.jsonl`). Every number was read from the file named under its answer at
that time; if a lane rebuilds one of those files before judging, re-check the number there.

Ground rules for whoever answers:
- Everything patient-like in SAMA is SYNTHETIC: simulated people, and notes written by language
  models. Say so whenever a number comes from notes, the worklist or the clock.
- A person confirms every extracted event and every worklist item. The two outcomes are "pre-filled
  for one-click confirmation" and "needs editing".
- Every 42-day threshold is a placeholder for the OECD/EU-reported six-week target.
- UNVERIFIED means nobody confirmed it on a primary source. Say the word out loud; do not soften it.
- Never say a note or list item needs no human check, that the scribe has been tested on real
  clinical text, that six weeks is Finnish law, or that a county's care is worse.

Numbers to quote exactly (the PDF deck `submission/deck/SAMA-deck.pdf` matches the files; only the
`DECK.md` draft and `PATH_TO_SCALE.md` still carry older figures, so do not read speaker notes from them):
- **Vague date phrases on the stress set** (`data/scribe/v4/eval/results-v1.json`, `vague_outcome`):
  the lexicon rule A' sent 29 of 29 to a person; Gemma B and C sent 0 (B wrote a precise date for 17,
  C for 11). Nemotron sent **3** of 29 to a person and left **25** undated, inventing none. Do not say
  "Nemotron sent 25 to a person".
- **Two-reader rule:** the rule chosen on validation pairs Nemotron with Gemma 3 1B: **684 of 700**
  test notes pre-filled, 4 wrong (post hoc), and on the frozen stress set **220 of 308**, 3 wrong, 88
  need editing. The PDF deck (slide 9, A8) and the video use these. `PATH_TO_SCALE.md` row 4a now leads with these
  figures and mentions 651 of 700 only as the earlier pairing with the 270M product adapter. (651 of
  700 also appears as the exact-match count of the 270M reader plus the code resolver on the test
  set, a different measure from "pre-filled".)
- **Fake-gap simulation:** the page and the PDF deck slide 6 both read `web/data/app.json`
  `insight.falseFlag`: **100.0% → 0.3%**. Only the `DECK.md` draft still says 0.001 (an older
  simulation, `runs/diagnose/interval-impact-v1.json`); quote 0.3%.

---

## A. Real data and how far to trust the numbers

### 1. Has any of this been tested on real patient notes?
*Asked by: AstraZeneca medical lead, THL, county director.*

No. Every note, pathway and worklist row in SAMA is SYNTHETIC: the notes were written by Nemotron and
Claude Haiku from six date forms, and their labels were checked by models, not by clinicians. To test
on real notes we need a legal route and a closed environment: a Findata permit with the work done in
Findata's secure environment Kapseli, or a county pilot with a data protection impact assessment
(DPIA) inside the county network. There, two clinicians would label a sample of real notes and we
would rerun the frozen, preregistered evaluation and the per-county comparability gate before a nurse
ever sees a pre-filled event; real notes would never go to a hosted endpoint.

Source: `README.md` ("What it does not claim"); `data/roadmap/mapping-v1.json` (`pilotCard.dataNote_en`);
`BIG_PICTURE.md` section 5 (Findata Kapseli, https://findata.fi/en/kapseli/).

### 2. Why synthetic data?
*Asked by: THL statistician, AstraZeneca medical lead.*

Only the patient-level parts are synthetic: every county figure on the page is real public data (THL
Sotkanet, Statistics Finland, NORDCAN). Secondary use of real patient notes needs a permit (in Finland,
from Findata, the route we would use), and we have not applied for one; we found no open Finnish
clinical-note corpus to use instead. Synthetic data let us publish every note, label and score,
freeze a test set before reading it, and let anyone rerun every check. The price is that we mostly
test our own writers' phrasing; the frozen stress set was built to expose exactly that, and it did
(question 3). Person-level pathway dates are not public either (THL's person-level waiting-list feed
is due by 2028 at the latest), so the clock and the worklist run on simulated people.

Source: `data/scribe/v4/eval/results-v1.json` (`preregistration`, `sets.stress`);
`submission/evidence-v2.json` (`thl-ttp-person-level`); `data/flare/RESULT.md`.

### 3. What do 0 of 143 and 11 of 143 mean, and why was your preregistered criterion not met?
*Asked by: THL statistician, Google DeepMind.*

The stress set is 308 SYNTHETIC notes frozen at 21:57:19 UTC before any system read them; 143 of them
contain a date phrasing no training note used, such as spelled-out numbers from seven to twelve
("seitsemän viikkoa sitten") or "toissapäivänä" (the day before yesterday). Gemma 3 270M with our
Finnish lexicon rule (A') got 0 of those 143 notes fully right, and the 270M model trained to copy the
phrase so code computes the date (B) got 11. We had written down in advance that B must beat A' by at
least 10 points with p < 0.01 and reach 85% on ordinary notes; it beat it by 7.7 points (p = 0.00098)
and reached 73 of 87 (83.9%), so the criterion is not met and we report it as not met. The lesson is
that a 270M model learns our templates, not Finnish: the 1B model got 95 of 143, and Nemotron 120 of
143 (optimistic, because Nemotron wrote the notes).

Source: `data/scribe/v4/eval/results-v1.json` (`primary_result`, `sets.stress.systems.*.slices.heldout`);
`data/scribe/stress/preregistration.json`.

### 4. Your other scribe numbers are above 90%. Why should I believe any of them?
*Asked by: THL statistician.*

Treat the 700-note test results as post hoc: that set had been read in earlier work, and validation
notes chose the versions, so both are optimistic. The clean number is the frozen stress set, where the
best Gemma (1B) got 223 of 308 notes exactly right and the two 270M models 85 and 88. Nemotron wrote
most of the notes, so its own scores (690 of 700 test, 280 of 308 stress) are optimistic too. Exact
match is strict (one wrong date, event type or route makes the whole note wrong), and every figure
carries a Wilson interval in its file.

Source: `data/scribe/v4/eval/results-v1.json` (`sets.test.role`, `sets.stress.systems`);
`data/scribe/nemotron/reader-v1.json` (`caveats`).

## B. The models: Gemma, Nemotron, FLARE, Verda

### 5. Why does Gemma need Nemotron?
*Asked by: Google DeepMind, NVIDIA.*

Because a small model is confidently wrong on phrasings it has not seen, and nothing in its own output
says which notes those are. Alone, Gemma 3 1B got 223 of 308 stress notes right, so 85 notes would be
pre-filled with a wrong answer for the person to catch; when a note is pre-filled only if Gemma and
Nemotron agree exactly, 220 of 308 were pre-filled with 3 wrong, and 88 went to "needs editing". On
the 700 test notes the same rule pre-filled 684 with 4 wrong, and all four read "referral received" as
"referral sent". Gemma stays inside the county; with real notes the second reader must also run in a
county-controlled environment, or a person does that step.

*If asked "why not two local models?"* We checked, post hoc and on stored outputs. If Gemma 3 1B and
Gemma 3 270M (with the Finnish lexicon resolver) must agree, the test set is close (669 of 700
pre-filled, 7 wrong), but on the stress set only 92 of 308 are pre-filled, 6 of them wrong. With
Nemotron as second reader it is 220 of 308, 3 wrong. Nemotron wrote the stress notes, so its figures
there are optimistic; even so, the local-only pair leaves most unseen phrasings to the person.
Nemotron's weights are published on Hugging Face (`NVIDIA-Nemotron-3.5-Super-VL-120B-A12B`), so a
county could host the second reader itself; that needs data-centre GPUs, not a laptop (licence
terms for this use: UNVERIFIED).

Source: `data/scribe/v4/eval/results-v1.json` (`sets.stress.systems.C`, `cascade.configurations`,
Gemma C with agreement); `data/scribe/v4/eval/local-pairs-posthoc-v1.json` (post hoc, written by
`scribe/v4/local_pairs.py`); `submission/PATH_TO_SCALE.md` (box 4b).

### 6. Why Gemma 3 270M, and what does Gemma do if code does the arithmetic?
*Asked by: Google DeepMind.*

The reading has to happen where the notes are, on ordinary county hardware with no internet, and a
270M model runs on a laptop CPU: 18 of 20 SYNTHETIC demo notes exactly right through the product's own
endpoint, median 4.8 s per note. Gemma does the part code cannot: it finds each pathway event in free
Finnish text, names its type and copies the date phrase; code then turns "kolme viikkoa sitten" into a
calendar date. When Gemma did the subtraction itself it got 2 of 367 relative-date test notes right;
with code doing it, 651 of 700 test notes exactly right with the 270M adapter (post hoc). The stress set shows the limit of 270M on unseen
phrasings, so the chosen two-reader rule uses the larger Gemma 3 1B reader, which got 95 of 143. The laptop demo
still runs the 270M model; the 85-wrong figure in Q5 is the 1B model alone, not the 270M.

Source: `data/scribe/demo/http-timing.json`; `runs/diagnose/diagnose-v1.json` (`by_has_relative`);
`data/scribe/v4/resolver/reproduce-v1.json`; `data/scribe/v4/eval/results-v1.json`.

### 7. Is Nemotron really in the working product, and does it understand Finnish?
*Asked by: NVIDIA.*

Yes, in two jobs on the page and one in the data, and the page can call it live: in the scribe demo,
"Ask Nemotron live (second reader)" sends the SYNTHETIC note to the hosted Nemotron 3.5 Super VL
endpoint with the frozen v3 reader protocol, and the two-reader rule is applied to its answer on
screen (test run on 15 November: note 4 in 2.7 s, agrees with Gemma; note 1 in 11.1 s, agrees after
one repair call; `runs/nemotron-live-demo.jsonl`). Without a key or network it falls back to the
stored answer and says so. It drafted a plan for 23 of 23 areas by calling four
SAMA tools, and code dropped every sentence with a number that is not a tool output: 255 of 299
sentences kept, 0 kept with an unmatched number; of 10 off-limits requests the model refused 9 itself,
and the 10th was blocked by a code guard added after seeing the same prompts (post hoc). As
second reader it got 690 of 700 test notes exactly right once code did the date arithmetic (192 of 310
validation notes when it did the arithmetic itself), and as teacher it wrote the SYNTHETIC training
notes. Its model card does not name Finnish, so plans are English drafts for a planner; the page shows
stored drafts (re-running their tool calls on today's build gave identical outputs for 20 of 23 areas,
and the other three carry a small caption: drafted on an earlier data build), and image input was tested but not used (13 of 20
from page images against 19 of 20 from text).

Source: `runs/nemotron-live-demo.jsonl`; `data/planner/plans-v1.json` (`summary`); `data/scribe/nemotron/reader-v1.json`
(`validation`, `test`); `data/planner/vision/vision-6b-v1.json` (`summary`); `web/data/app.json`
(`planner.toolCheck`).

### 8. What does NVIDIA FLARE add? Is it real federation?
*Asked by: NVIDIA, THL statistician.*

FLARE lets each county compute its own statistics next to its own records and send out only filtered
totals, the way NORDCAN already produces Nordic statistics inside each registry. On SYNTHETIC data, 23
simulated county sites reproduced SAMA's central table in 92 of 92 cells, suppressed the same 40 small
cells as our n < 5 rule in a finer 1,932-cell run, and computed the referral-to-treatment clock equal
to the central computation in 253 of 253 cells. It ran in simulator mode on one laptop, with no network
and no site approval, and it is not a legal permit: aggregates still need a disclosure policy. We also
learned three practical things: FLARE rounds to 4 decimals by default, its national row is wrong when a
county is suppressed, and its histogram filter needs about 95 cases per cell for 9 bins.

Source: `data/flare/summary.json` (`equivalence`); `data/flare/gate-v1.json` (`flare.equivalence`);
`data/flare/RESULT.md`.

### 9. What did you use Verda for, and what did it cost?
*Asked by: Verda.*

One A100 80 GB instance for 2.51 hours, USD 5.98 at list price (we did not read the invoice): Gemma
LoRA training (the selected run trained in 176 s), a vLLM serving test (100 of 100 valid JSON outputs,
p95 latency 1.80 s, 5.74 notes a second) and the Evo 2 research appendix; the machine was deleted after
the results were copied back. The Verda-hosted Nemotron endpoint served 2,602 reader requests; its
price is not verified, so the cost is recorded as unknown, not zero, and only SYNTHETIC text ever went
to it. We rejected confidential VMs tonight: new spending, and attesting synthetic inputs proves
nothing to a judge. The next step, a scale-to-zero serverless scribe, is planned and not deployed.

Source: `data/scribe/v2/training-figures-v1.json` (`machine_cost`, `train_seconds`);
`serve/smoke/smoke-guided.json`; `data/scribe/nemotron/ledger.json`; `submission/VERDA_DISCORD.md`;
`BIG_PICTURE.md` section 3.4.

## C. Safety, law and the sponsor

### 10. Who decides what follow-up is due, and what stops a wrong date reaching a patient?
*Asked by: AstraZeneca medical lead, county director.*

The radiologist decides, in the written report; SAMA's code copies that recommendation and computes
the due date, and any range, vague or conditional phrase goes to a person instead of getting a date.
On 60 SYNTHETIC report lines the rule was 60 of 60 right (30 due dates, 20 sent to a person, 10 with no
follow-up), and on 5,002 more lines it made 0 wrong or invented dates and missed 0 recommendations,
while sending 40 dated lines to a person. Those lines come from our own templates, so this shows the
rule does what it says, not how it reads real reports. A nurse confirms every item before any call, and
under the Gemma Terms of Use every model extraction stays a proposal until a person confirms it.

Source: `data/safetynet/safetynet-v1.json` (`rule.metrics`, `cohort.imaging_loops`);
`submission/GEMMA_WRITEUP.md` ("Responsible use").

### 11. Is there evidence that a list like this improves outcomes?
*Asked by: AstraZeneca medical lead.*

Not for lung follow-up yet; measuring that is the pilot's job. The evidence is indirect: AI
prioritisation of 93,326 GP chest X-rays left the median wait for CT at 53 days in both trial arms, so
reading speed was not the bottleneck, and in a US navigation programme navigated patients reached a
diagnosis faster between days 91 and 365 (adjusted hazard ratio 1.51, 1.23-1.84). We do not carry effect sizes from breast
screening or another health system over to Finnish lung follow-up, and the "deaths postponed" scenario
is not a claim about this list (question 23).

Source: `submission/evidence-v2.json` (`lungimpact-2026`); `data/evidence/literature-v1.json`
(`freund-2014-navigation`).

### 12. What is the legal basis for finding patients from a list and contacting them?
*Asked by: county director, AstraZeneca market-access lead.*

Since 1 June 2026 a wellbeing services county may identify patients whose care does not follow
recommendations; processing their data and contacting them must respect data protection and
self-determination (STM, 21 May 2026). UNVERIFIED: whether "recommendations" covers the timing of
pathway steps or follow-up imaging; we would confirm that with STM and THL and do a DPIA with an
opt-out before a pilot. Also UNVERIFIED: whether the worklist is medical-device software under the MDR
(to confirm with Fimea), and whether county-local statistics go through the Secondary Use Act and
Findata (to confirm with THL and Findata); the EU AI Act's high-risk duties apply from 2 December 2027
and 2 August 2028, and we track them. We claim none of this for Åland, which has its own health
legislation (general knowledge, not checked tonight).

Source: `submission/evidence-v2.json` (`stm-2026-proactive-care-law`, `eu-ai-act-dates`);
`BIG_PICTURE.md` sections 5 and 7; STM page:
https://valtioneuvosto.fi/-/1271139/lakimuutokset-parantavat-hyvinvointialueiden-mahdollisuuksia-ennakoivaan-terveydenhuoltoon

### 13. Is this AstraZeneca marketing?
*Asked by: any jury, AstraZeneca leads in particular.*

No. SAMA contains no medicine, biomarker or product content, uses no AstraZeneca data or product
information and recommends no treatment; the Evo 2 genomics benchmark sits on a separate research page
outside this pitch. The county owns the list and the care; no patient data goes to any sponsor, and in
the pilot no patient data would leave the county (the second reader would have to run inside it, which
is designed, not built, or a person does that step). Any company role would be a documented,
non-promotional collaboration owned by the county. Industry-code rules for joint working
(Lääketeollisuus, EFPIA) are UNVERIFIED for a setup like ours and would be checked before any company
role.

Presenter note: the national lung programme we cite was supported in its planning phase by Amgen,
Sanofi, AstraZeneca, Roche, Boehringer Ingelheim and two foundations, which did not take part in
planning its content (programme preprint, p. 26). Name these supporters only if the owner said yes to
decision 7 in `BIG_PICTURE.md` section 6, and do not raise AstraZeneca's own county pilots unless the
owner agreed.

Source: `README.md` ("What it does not claim"); `data/safetynet/safetynet-v1.json` (`text.governance`);
`BIG_PICTURE.md` section 2.2 item 17.

### 14. Six weeks is not Finnish law. Why measure against it?
*Asked by: county director, THL statistician.*

Correct, and we never say it is. The OECD/EU country profile reports a Finnish target of six weeks from
a suspected-cancer referral to the start of treatment; the treatment guarantee in law sets assessment
within 3 weeks, tests within 3 months and treatment within 6 months, and names no cancer-specific
limit. So every 42-day threshold in SAMA is labelled a placeholder, and the real limit is for the
roadmap to set (cancer-specific access times under measure 3.1.2) or the county to choose. THL guidance
21/2016 may already define cancer access times; we could not read it at source, so that is UNVERIFIED.

Source: `submission/evidence-v2.json` (`oecd-2025-fi-six-weeks`, `stm-hoitotakuu`);
`data/evidence/literature-v1.json` (`fi-cancer-target-times`); `data/safetynet/safetynet-v1.json`
(`thresholds`).

## D. The county and the money

### 15. Why Satakunta?
*Asked by: county director, AstraZeneca market-access lead.*

On process grounds, not because its care is worse. Its services are mainly in Finnish, the only
language the scribe reads (that share was not measured); it is not one of the three counties under the
state assessment procedure; and its lung burden is high: lung-cancer mortality (C32-C34, including
larynx) 1.126 times the national level after shrinkage (1.045-1.21), though Lapland (1.237) and
Kymenlaakso (1.132) are higher. Our inference is that Satakunta is outside the randomised national lung
screening pilot, which matters for how the list is evaluated; that inference is UNVERIFIED, and
Satakunta is a default the owner or the county can change.

Source: `data/roadmap/mapping-v1.json` (`pilotCard`); `web/data/app.json` (`analysis.mortality.lung`,
rows HVA06, HVA21, HVA10); `BIG_PICTURE.md` section 3.2 (DO #2) and section 2.2 item 21.

### 16. What does a county do on Monday?
*Asked by: county director.*

Three things that need no new capital money, the zero-euro 2027 plan. The cancer centre names an owner
and existing care coordinators, runs a DPIA and confirms the legal scope, then extracts open
suspected-cancer referrals and imaging reports with a written follow-up from its own records, inside
its own network, and runs SAMA's code on that extract to give a nurse a first list to review. The
screening unit puts pre-booked appointment times back into invitation letters (in Helsinki, cervical
screening participation fell from 72% to about 62% without them and recovered when they returned; one
city), and the data team maps two dates that already exist, plus an end reason, into the extract it
sends THL anyway. Every KPI is reported by entry route, education and contact language from day one,
so the list cannot reproduce the gap.

Source: `submission/ZERO_EURO_2027.md`; `data/roadmap/mapping-v1.json` (`pilotCard`);
`submission/evidence-v2.json` (`yle-2025-helsinki-prebooking`).

### 17. What does it cost, and who pays?
*Asked by: AstraZeneca market-access lead, county director.*

For the county the 2027 pilot asks for no new capital money; the cost is staff time, mainly one nurse
call per overdue item, at a volume the pilot measures first (the SYNTHETIC Satakunta replay shows the
format, 16 overdue among 120 open loops, not a forecast). It runs inside national roadmap measures that
already carry their own budgets, for example EUR 100,000 for the care-coordinating worker (1.2.3) and
EUR 2,500,000 for the cancer quality register (3.2.1); we add fields and a workflow, not a budget line.
Building SAMA cost USD 5.98 of A100 time at list price and USD 0.1344 for the planner's TypeSafe check,
the Nemotron endpoint price is unknown, and running the scribe needs no GPU (a laptop CPU took a median
4.8 s per note).

Source: `submission/ZERO_EURO_2027.md`; `data/safetynet/safetynet-v1.json` (`counties`, HVA06);
`data/roadmap/mapping-v1.json` (measures 1.2.3 and 3.2.1, `resource`);
`data/scribe/v2/training-figures-v1.json`; `data/planner/jev-ledger.json` (TypeSafe gate cost);
`data/scribe/demo/http-timing.json`.

### 18. Will this bury my nurses in false alarms?
*Asked by: county director.*

That is the main risk, and the pilot measures it before anyone scales it: the share of items resolved
within 14 days and the volume per nurse are KPIs, not assumptions. Three things limit noise: SAMA never
decides what follow-up is due (it copies the radiologist's date), anything vague goes to a person
rather than onto the overdue list, and the list starts with lung follow-ups. The counts on our page come
from simulated people and assumed follow-up rates, so they show that the list works, not how many
people are lost in Satakunta.

Source: `data/safetynet/safetynet-v1.json` (`kpis`, `rule`); `submission/DECK.md` (slide 7 speaker note).

### 19. What about Swedish and Sámi speakers?
*Asked by: county director, THL statistician.*

The scribe reads Finnish notes only; notes in Swedish, Sámi or any other language go to manual entry,
so nobody is dropped, their dates are typed by hand. The worklist records contact language (Finnish,
Swedish, Sámi, other) with an interpreter flag, and every KPI is reported by contact language, because
the gap is real: breast screening 63% among speakers of a non-domestic language against 82% among
Finnish, Swedish and Sámi speakers (2020-21). A Swedish scribe needs testing on real Swedish notes in a
secure environment, since templated notes would only test our own templates; Lapland comes second, once
Sámi-language outreach is designed with the Sámi Parliament, and small Sámi counts fall under the
n < 5 suppression rule (Sámi-language service rights are general knowledge we did not check:
UNVERIFIED).

Source: `data/roadmap/mapping-v1.json` (`pilotCard.languageScope_en`); `data/safetynet/safetynet-v1.json`
(`by_language`, `suppression`); `submission/evidence-v2.json` (`oecd-2025-fi-breast-screening-gaps`);
`BIG_PICTURE.md` sections 3.3 and 7.

## E. Statistics

### 20. What do the county education gradients show, and what do they not show?
*Asked by: THL statistician.*

They show that county averages cannot see who is missed. Across 22 counties, breast-screening
attendance in 2024 falls as the county education index rises (r = -0.59), much less without Helsinki
(r = -0.35), and all 10 county slope intervals include zero; the five lowest-attending areas are all in
Uusimaa, where the OECD says many women screen outside the programme, and the three lowest have the
highest foreign-background shares. They say nothing about individuals: the individual-level figures are a different kind of data
(breast screening 66% with lower against 85% with higher education), which the county pattern cannot
see. That is why the page labels the county gradients ECOLOGICAL and puts the individual figures beside
them.

Source: `web/data/app.json` (`analysis.gradients`; r recomputed tonight from
`analysis.indicators.screen_breast` and `education_index`, n = 22 and 21);
`submission/evidence-v2.json` (`oecd-2025-fi-breast-screening-gaps`); `README.md` ("The finding").

### 21. If where you live is not the main gap, why compare counties at all?
*Asked by: THL statistician.*

Because counties own the care and the budgets, so that is where action happens; but we compare a county
only when it can see itself. In our SYNTHETIC simulation with no real difference anywhere, a county
whose dates were read from notes by the scribe as it was, against a country with structured dates, was
flagged as slower in 1.000 of 1,000 runs; with the code date resolver in 0.003, the same as with every
event confirmed by a person. So the gate labels a county "not comparable" when its extraction errors
differ (15 of 23 simulated counties with the raw scribe, 1 of 23 with the resolver; thresholds are
placeholders), and on real public data only Pirkanmaa's area reaches the 70% stage-recording aim today.
Mortality estimates are shrunk with false-discovery control, and where the top two areas differ by
0.001 we claim no rank.

Source: `web/data/app.json` (`insight`, from `data/eventlog/design-study-v1.json`);
`data/flare/gate-v1.json` (`summary`, `realData`); `data/roadmap/mapping-v1.json`
(`pilotCard.snapshotEvidence`).

### 22. The 127 against 76 days route gap: isn't that confounded?
*Asked by: THL statistician, AstraZeneca medical lead.*

Probably in part, and we say so. It is one Finnish cohort of one cancer (diffuse large B-cell
lymphoma), 48 against 39 patients in the two route groups, median 127 against 76 days, p = 0.027, and
people who use occupational or private care differ in work, health and income. We use it as a reason to
report every indicator by entry route, not as a causal effect; in the scenario model it is a prior with
a disclosed caveat (the 84-day central value is read from the paper's figure, while the text gives
medians 51 days apart). The fix is the entry-route field in the Pathway Clock, so Finland can measure
this on its own data; a county-only federation cannot see occupational and private first contacts.

Source: `submission/evidence-v2.json` (`kuitunen-2026-route-medians-groups`);
`data/evidence/literature-v1.json` (`kuitunen-2026-route-medians`); `submission/DECK.md` (appendix A2);
`BIG_PICTURE.md` section 3.3.

### 23. What does "deaths postponed" mean, and why is it not your headline?
*Asked by: THL statistician, AstraZeneca market-access lead.*

It is a SCENARIO from SAMA's portfolio model: if 18 county actions were funded with EUR 5.95 million of
a EUR 6.0 million yearly budget, the central estimate is 177.1 cancer deaths a year moved later
(38.2-351.5 over 300 parameter draws), 60.1% of it in counties with above-average cancer mortality.
"Postponed" because the model mainly applies published delay-mortality hazards to days saved, which
moves deaths later rather than proving cures; the inputs are literature effects and planning cost
assumptions, not Finnish measurements, and the honest lower bound is zero. As a cross-check the model
implies a hazard ratio of 0.965 for a 17-day shorter interval where Denmark observed 0.86 (0.73-1.01),
so it is conservative against that study. The headline is a process metric a county can measure: the
share treated within the placeholder time and the share of overdue follow-ups closed on time.

Source: `web/data/app.json` (`recommendation.portfolio`, `recommendation.validation`);
`ARCHITECTURE.md` ("Scenario model"); `README.md` ("What it does not claim").

### 24. How does this scale nationally, and how much data does a county need?
*Asked by: AstraZeneca market-access lead, THL statistician.*

Nationally the clock rides on carriers that already exist: THL's person-level waiting-list feed (due
by 2028 at the latest) for two dates and an end reason, and the cancer quality register at THL's
Cancer Registry (roadmap 3.2.1) for stage and route, with each county computing its own figures where
the data live. In simulation, to see a county that is 20% slower in one interval at 80% power with 69
comparisons, a county needs 473, 513 and 347 complete episodes for the primary-care, diagnostic and
treatment intervals; at an assumed 37,000 cases a year, 5 of 23 counties get there within a quarter and
20 of 23 within a year. Compute is not the bottleneck (the scribe served 5.74 notes a second on one
A100); comparable data is, and Sweden and Norway show that changing patient-record systems can break
the statistics, so the plan includes a record-system migration log.

Source: `data/eventlog/design-study-v1.json` (`sample_sizes`); `web/data/app.json` (`eventLog.reach`);
`serve/smoke/smoke-guided.json`; `submission/PATH_TO_SCALE.md`; `submission/evidence-v2.json`
(`thl-ttp-person-level`); `BIG_PICTURE.md` section 1 (Sweden and Norway, research).

## F. Next

### 25. What would you do with one more month?
*Asked by: any jury.*

First, real notes: apply for a Findata permit or agree a county pilot with a DPIA, have two clinicians
label a sample inside the secure environment, and rerun the frozen evaluation and the comparability
gate per county. Second, fix what failed: retrain on more writers and phrasings (spelled-out numbers,
and "toissapäivänä", where even the 1B model got 3 of 36), and preregister a new stress set written by
someone other than Nemotron. Third, the legal checks we could not do tonight: STM and THL on the law's
scope, Fimea on the MDR, and a county data protection officer. Fourth, engineering: wire the two-reader
agreement rule into the served scribe, self-host the second reader in a county-controlled environment,
re-draft the three planner drafts whose tool outputs changed, and run FLARE across two real sites on a
real network.

Source: `PROGRESS.md` ("Failed or not done"); `data/scribe/v4/eval/results-v1.json`
(`sets.stress.systems.C.heldout_slice_by_family`); `BIG_PICTURE.md` section 7.

---

## Lunttilappu esittäjälle (suomeksi, 10 riviä)

1. **Oikeat potilastekstit:** ei testattu. Kaikki potilastiedon kaltainen aineisto on SYNTEETTISTÄ. Seuraava askel on Findata-lupa tai hyvinvointialueen pilotti ja tietosuojan vaikutustenarviointi (DPIA).
2. **Ihminen vahvistaa aina:** jokainen poimittu tapahtuma ja jokainen listan rivi vahvistetaan käsin. SAMA ei päätä jatkotutkimuksesta, vaan kopioi radiologin kirjoittaman suosituksen.
3. **Ennakkoon kirjattu kriteeri jäi täyttymättä:** uusia sanamuotoja sisältävistä muistiinpanoista 270M-malli sai oikein 11/143 ja sääntö 0/143. Gemma 3 1B sai oikein 95/143. Kerromme tämän suoraan.
4. **Miksi Gemma tarvitsee Nemotronia:** muistiinpano esitäytetään yhden klikkauksen vahvistusta varten vain, kun molemmat lukijat ovat samaa mieltä. Stressiaineistossa 220/308 esitäytettiin ja niistä 3 oli väärin; 88 meni muokattavaksi. Kahdella paikallisella Gemmalla esitäytettäisiin vain 92/308, ja niistä 6 olisi väärin (jälkikäteen laskettu).
5. **Kuusi viikkoa:** OECD/EU:n raportoima tavoite, ei laki. Hoitotakuu edellyttää hoidon alkavan viimeistään kuuden kuukauden kuluessa. Meidän 42 päivää on paikkamerkki.
6. **Miksi Satakunta:** palvelut pääosin suomeksi, alue ei ole arviointimenettelyssä ja keuhkosyöpäkuolleisuus on korkea (1,126). Emme väitä, että hoito olisi siellä huonompaa.
7. **Oikeusperusta:** 1.6.2026 alkaen hyvinvointialue saa tunnistaa potilaat, joiden hoito ei vastaa suosituksia. Kattaako se hoitopolun aikataulut, on VARMISTAMATTA: kysytään STM:ltä ja THL:ltä.
8. **Ei AstraZenecan markkinointia:** ei lääke- eikä tuotesisältöä eikä AstraZenecan dataa. Alue omistaa listan ja hoidon, eikä potilastieto lähde alueelta.
9. **"Lykkääntyneet kuolemat" on skenaario, ei otsikko:** 177,1 vuodessa (38,2–351,5), alaraja on rehellisesti nolla. Otsikkona on prosessimittari: hoidon aloitus ajallaan ja myöhässä olevien jatkotutkimusten sulkeminen.
10. **Maanantaina ja kustannus:** kolme toimea ilman uutta investointirahaa, kustannus on henkilöstön aikaa. Ajanvaraus takaisin seulontakutsuihin, myöhästyneiden lista olemassa olevilla koordinaattoreilla ja kaksi päivämäärää THL:n tiedonkeruuseen.
