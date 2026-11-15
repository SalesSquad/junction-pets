# SAMA: video script (at most 120 seconds)

Voice-over in English, about 2.3 words per second. `submission/check_numbers.py` counts the spoken
words and fails above 276 (120 s at that pace). Who records the voice-over is the team's decision.
The story follows `BIG_PICTURE.md` section 4; spoken numbers are kept to a few, the rest are
captions.

Before recording:
- Say "Nemotron drafts each county's plan" only if the planner panel is on the page at code freeze
  (`BIG_PICTURE.md` must-ship item 1). Otherwise cut that sentence and show the cached plans
  (`data/planner/plans-v1.json`) on a slide.
- The overdue-list screen shows counts first and at most 3 unnamed SYNTHETIC rows, from
  `data/safetynet/safetynet-v1.json` (Satakunta: 16 overdue of 120 open loops; the file's three
  `examples`).
- The radiology follow-up line on the list was read by a code rule: caption it "code reads the
  follow-up recommendation". "Gemma reads" is said only of the referral note, which the CPU demo
  shows.
- Every note and list row on screen carries a visible SYNTHETIC label.
- If the clip runs long, cut the FLARE sentence first.

| Time | Screen | Voice-over |
| --- | --- | --- |
| 0:00-0:20 | Map of the 23 areas. Caption: "NORDCAN, 2020-2024; Filha lung programme 2026". | In Finland, five years after a lung cancer diagnosis, relative survival for men is 17.9 percent. The Sweden and Norway average is 31.1. Finland's lung programme says curable cases are mostly found by chance, on scans for something else. What happens next decides how early treatment starts. |
| 0:20-0:44 | Who, how and where panel. Captions: "OECD/EU 2025: 64-65% against 77-78% five-year survival by education" and "Kuitunen J et al. 2026: 48 against 39 patients, p = 0.027". | Where you live is not the main gap. Survival does not differ significantly between regions. It does differ by education, and by how you enter care. In one Finnish lymphoma study, the median from first symptom to treatment was 127 days through a public health centre appointment, and 76 through occupational or private care. |
| 0:44-1:14 | The Pathway Clock card, then the FLARE sites lighting up one by one. Caption: "SYNTHETIC data; thresholds are placeholders". | The OECD reports a six-week target from suspected-cancer referral to treatment. The law allows up to six months after the need is established. No county can show whether it meets either, and stage is recorded for only 42 percent of cancers. SAMA asks for two dates and an end reason per patient. On synthetic data, NVIDIA FLARE computed each county's figures locally. A county is compared only when it can see itself. |
| 1:14-1:35 | The overdue list: counts, then three SYNTHETIC rows; a referral note with "kolme viikkoa sitten" highlighted and the computed date. Caption: "In a trial of 93,326 chest X-rays, faster AI reading did not shorten the wait for CT". | Measuring is not enough. Since June, a county may identify patients whose care does not follow recommendations; whether that covers pathway timing is unconfirmed. SAMA turns that into a nurse's list of overdue referrals, lung follow-ups first. Gemma reads the note on an ordinary computer, code counts the days, a nurse confirms and calls. |
| 1:35-1:56 | A Nemotron county plan with each number underlined; then the pilot card for Satakunta. Caption: "Draft for a planner; numbers checked". | Nemotron drafts each county's plan, and code checks every number. Our ask: Satakunta, lung follow-up first, a 2027 pilot with no new money. The county owns it; in the pilot, no patient data leaves the county. The same pathway, wherever they live, whoever they are, however they enter care. |
| 1:56-2:00 | End card: "SAMA. The same pathway, wherever they live, whoever they are, however they enter care. Patient-like data shown are SYNTHETIC." | (silence) |

## Where each spoken number comes from

| Spoken | File |
| --- | --- |
| 17.9 and 31.1 percent | `web/data/app.json` (`analysis.goal3`, `nordic-survival`, lung, men; NORDCAN) |
| mostly found by chance | `submission/evidence-v2.json` (`filha-2026-found-by-chance`) |
| no significant difference between regions; by education | `submission/evidence-v2.json` (`oecd-2025-fi-survival-education`) |
| 127 and 76 days | `submission/evidence-v2.json` (`kuitunen-2026-route-medians-groups`); also `data/evidence/literature-v1.json` (`kuitunen-2026-route-medians`) |
| six weeks | `submission/evidence-v2.json` (`oecd-2025-fi-six-weeks`; OECD/EU-reported, not the law) |
| six months after the need is established | `submission/evidence-v2.json` (`stm-hoitotakuu`: treatment no later than six months after the need is established) |
| 42 percent | `submission/evidence-v2.json` (`syopajarjestot-2026-stage-completeness`) |
| FLARE computed each county's figures | `data/flare/summary.json`, `data/flare/RESULT.md` (SYNTHETIC; 92 of 92 cells equal the central table) |
| Since June; pathway timing unconfirmed | `submission/evidence-v2.json` (`stm-2026-proactive-care-law`, in force 1 June 2026; its note marks the scope for pathway timing UNVERIFIED) |
| no patient data leaves the county (pilot condition) | `submission/PATH_TO_SCALE.md` rows 4a-4b: today the second reader runs on the hosted event endpoint with SYNTHETIC notes; a county-controlled second reader is a design, not built |
| 93,326 (caption) | `submission/evidence-v2.json` (`lungimpact-2026`) |
| Nemotron drafts each county's plan | `data/planner/plans-v1.json` (`summary`: 23 of 23 plans, 0 kept sentences with an unmatched number) |
| Satakunta, 2027 pilot | `data/roadmap/mapping-v1.json` (`pilotCard`) and `submission/ZERO_EURO_2027.md` |

Words to avoid on screen and in the voice-over: any claim that a note or list item needs no human
check, that the scribe has been tested on real clinical text, that six weeks is Finnish law, or that
a county's care is worse.
