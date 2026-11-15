# SAMA: live demo script (2 minutes, 30-second version, fallbacks)

Written 15 November 2026, 00:45-01:15 UTC; updated 01:40-01:50 UTC after the demo fixes (Note 4
opens by default, the plan comes before its method, plain numbers lead the scribe results). The
screenshots in `submission/shots/` were re-shot from the fixed page at 01:33 UTC. Check that the
numbers below still match their files after any later data rebuild.

Everything patient-like on screen is SYNTHETIC and labelled. A person confirms every extracted
event and every worklist item. Say "pre-filled for one-click confirmation" or "needs editing" for
the two outcomes, nothing else.

## Before the judges arrive

1. Start the product on a free port with the live model switched off (the stored outputs are the
   demo):
   `SAMA_SCRIBE_LIVE=0 PORT=4191 node web/serve.mjs`, then open `http://127.0.0.1:4191/`.
   Check `http://127.0.0.1:4191/api/health` answers `{"status":"OK"}`.
2. **Use a server started after 01:30 UTC on 15 November.** Since then `web/serve.mjs` reloads
   `data/scribe/demo/demo-notes.json`, `demo-outputs.json` and the stored Nemotron answers whenever
   one of them changes on disk. A server started earlier runs the older code, which read the demo
   outputs once and kept them (seen during QA: Note 1 showed "pre-filled" from an old file). The
   server already running on port 4179 since 14 November 16:47 local time is such a server: start
   your own on 4191 as in step 1, or restart that one.
3. Browser window about 1440 px wide, zoom 100% (or 90% on a 1280 px projector). Scroll to the top.
4. Do **not** click "Check claims" in the analyst brief: with a TypeSafe key on the server it calls
   a hosted API; without one it only says NOT_CONFIGURED. The stored checks are already on screen.
5. Do **not** click "Run live on this computer" unless the live CPU worker has been started and
   warmed up on purpose. With `SAMA_SCRIBE_LIVE=0` it falls back to the stored output; for Note 4
   the verdict stays "Pre-filled for one-click confirmation" and the footer says "live run not used"
   (screenshot `14c-gemma-demo-live-fallback-1440.png`).
6. Open the fallback folder `submission/shots/` in Preview, sorted by name, so it can replace the
   browser at any step.

## The 2-minute click path

About 250 spoken words (counted from the "Say" column; 2.3 words a second leaves about 10 seconds for clicks). Each step: what to click, what to say, which number to point at, and the
file that number comes from.

| Time | Click | Say | Point at | Source |
| --- | --- | --- | --- | --- |
| 0:00 | Nothing: the page is at the top. | "SAMA means 'the same': the same cancer pathway wherever you live, whoever you are, however you enter care. Five-year relative survival from lung cancer for Finnish men is 17.9 percent; Sweden and Norway average 31.1." | Tile "The survival gap": "17.9% vs 31.1%", subline "13.2 percentage points below Sweden–Norway". | `web/data/app.json` `analysis.goal3.indicators[0].rows` (lung, male: `finland` 17.9, `benchmark` 31.1, `gap` -13.2) |
| 0:15 | Nav "Who, how and where". | "Where you live is not the main gap. Survival differs by education, 64 against 77 percent for men, and by entry route: in one Finnish lymphoma cohort, 127 against 76 days from symptom to treatment." | Right column: "lower education 64% · higher education 77%"; then the last bar pair, "How you enter care". | `submission/evidence-v2.json` `oecd-2025-fi-survival-education`, `kuitunen-2026-route-medians-groups` |
| 0:35 | Nav "What to do". | "Today no county can measure treatment within target times. First action: record two dates and an end reason per patient, roadmap measure 3.2.1." | Grey box: "Not measurable in any of the 23 areas today"; then "Roadmap measure 3.2.1". | `web/data/app.json` (`analysis.goal3`, indicator `treatment-within-target`, `NOT_PUBLICLY_MEASURABLE`); `data/roadmap/mapping-v1.json` (3.2.1) |
| 0:50 | Nav "Comparability gate". | "On synthetic data, NVIDIA FLARE computed each county's clock where its data live; 253 of 253 cells match the central result. With the model's own dates, 15 of 23 counties would be 'not comparable'; when Gemma reads and code counts, 1 of 23." | Box "A county is compared only when it can see itself": "The model's own dates: 15 of 23" and "Gemma reads, code counts: 1 of 23". | `data/flare/gate-v1.json` (`summary.raw`, `summary.resolver`, `flare.equivalence`: 253 of 253) |
| 1:10 | Nav "Close the loop". | "Since June 2026 a county may identify patients whose care does not follow recommendations. SAMA makes that a nurse's list. Synthetic Satakunta replay: 120 open loops, 16 overdue: 10 imaging follow-ups past the radiologist's date, 6 referrals with no diagnosis by the day-42 placeholder." | The four tiles (120, 16), then the three SYNTHETIC rows. | `data/safetynet/safetynet-v1.json` (`counties` HVA06: `open_loops` 120, `overdue` 16, imaging `overdue` 10, referral `overdue` 6); `submission/evidence-v2.json` `stm-2026-proactive-care-law` |
| 1:30 | Nav "Gemma demo". Note 4 opens by default and its stored output loads by itself. | "Gemma copies the date phrase '25 viikkoa sitten'; code computes the date, and Gemma's own date is struck out. Nemotron's stored answer agrees, so the note is pre-filled for one-click confirmation. A person still confirms it." | Row "MDT decision": 9.9.2023 with 8.10.2023 struck out; the box "Pre-filled for one-click confirmation". | `data/scribe/demo/demo-outputs.json` (`results.demo-04`; `two_reader`: 15 of 20 pre-filled, 0 wrong) |
| 1:45 | Nav "Nemotron county plan" (Satakunta is the default; the plan sits right under the county list). | "Nemotron drafts each county's plan through SAMA's tools; code checks every number: 255 of 299 sentences kept. Our ask: Satakunta, lung follow-up first, a 2027 pilot. The county owns it; no patient data leaves the county." | The plan's footer line "Across 23 counties: 255 of 299 drafted sentences kept; 0 kept sentences with a number that is not in a tool output" (the same figures open the box below the plan). | `data/planner/plans-v1.json` (`summary`: `keptSentences` 255, `sentences` 299, `keptSentencesWithUnmatchedNumber` 0); `data/roadmap/mapping-v1.json` (`pilotCard`) |

If a judge asks about errors at 1:30, pick "Note 19": Gemma invents a symptom date in a note about
a tennis elbow, Nemotron disagrees, and the note "needs editing" (screenshot
`14b-gemma-demo-demo-19-1440.png`). Optional one-liner, source
`data/scribe/v4/eval/results-v1.json` (`cascade.configurations`, Gemma 1B + Nemotron agreement): "On
700 synthetic test notes the two readers agreed on 684, and 4 of those were wrong; on a harder
stress set of 308, 220 were pre-filled with 3 wrong and 88 need editing." The same three plain
numbers open the scribe results below the demo (section 10).

Note 1 ("kolme viikkoa sitten") is a rewritten note that Nemotron never read, so it shows "Needs
editing. Why: Nemotron, the second reader, never read this rewritten note, so a person edits it"
(screenshot `14b-gemma-demo-demo-01-1440.png`). Use Note 4 for the click path.

Under the Satakunta plan a small grey caption reads "Drafted on an earlier data build; 1 sentence
withheld by the check (...)". If asked, say: "The drafts were written on an earlier data build;
code re-ran their tool calls on today's data and withholds a sentence that today's data no longer
supports." The method (prompt v1 and v2, off-limits requests, the re-check) is in the folded block
"How the drafts were checked and improved" below the plan; do not open it in the 2-minute version.

## The 30-second version

| Time | Click | Say | Source |
| --- | --- | --- | --- |
| 0:00 | Top of the page. | "SAMA: the same cancer pathway wherever you live, whoever you are, however you enter care. Finnish men's five-year lung cancer survival is 17.9 percent; Sweden and Norway, 31.1." | `web/data/app.json` `analysis.goal3` |
| 0:10 | Nav "Close the loop". | "SAMA gives a county nurse a list of stalled suspected-cancer pathways: in the synthetic Satakunta replay, 16 of 120 open loops are overdue." | `data/safetynet/safetynet-v1.json` HVA06 |
| 0:20 | Nav "Gemma demo", Note 4. | "Gemma copies the date phrase, code counts the days, a person confirms. Our ask: a 2027 pilot in Satakunta, lung follow-up first." | `data/scribe/demo/demo-outputs.json` `results.demo-04`; `data/roadmap/mapping-v1.json` `pilotCard` |

## If a part fails

Switch to Preview on `submission/shots/` and keep talking; the script does not change. Files are
named `<order>-<section>-<width>.png`; use the 1440 versions on a projector and the 390 versions
only to show the phone layout (captured at device scale 1 to keep the folder at about 15 MB).

| What fails | What you see | Do this | Fallback screenshot |
| --- | --- | --- | --- |
| Server does not start or the port is taken | Connection refused | Start on another port (`PORT=4192`); if it still fails, present from Preview | all of `submission/shots/` |
| Page stuck on "Loading the public-data snapshot…" | Empty sections | Reload once; check `/api/health`; then Preview | `01-hero-1440.png`, `02-gap-map-1440.png` |
| Map or ranking empty | Blank figure | Point at the ranking; or Preview | `02-gap-map-1440.png` |
| Who, how and where empty | No bars | Preview | `03-who-how-where-1440.png` |
| What to do / pilot card | Missing roadmap IDs | Preview | `06-action-county-first-1440.png`, `07-pilot-satakunta-1440.png` |
| Comparability gate missing | Section 05 ends after the safety net | Preview | `09-flare-gate-1440.png` |
| Safety-net panel missing | No tiles | Preview | `08-safetynet-1440.png` |
| Gemma demo says it "could not be loaded", or the verdict differs from this script | Error line, or "Needs editing" on Note 4 | Restart the server (step 2 above), reload; otherwise Preview | `14b-gemma-demo-demo-04-1440.png` and `14-gemma-demo-stored-1440.png` (both Note 4, pre-filled), `14b-gemma-demo-demo-01-1440.png` (Note 1, needs editing), `14b-gemma-demo-demo-19-1440.png` (needs editing) |
| "Run live" clicked by mistake | Stored output with "live run not used" | Say "this shows the stored output from the same process" and continue | `14c-gemma-demo-live-fallback-1440.png` |
| Planner stuck on "Loading the stored drafts…" | No plan | Preview | `11-planner-nemotron-1440.png` |
| Scribe results question | — | Scroll below the demo or Preview | `15-scribe-results-1440.png` |
| Appendix question (genomics) | — | Footer link "research appendix"; say it is separate from the entry | `17-research-appendix-1440.png` |

Other screenshots in the folder, not on the click path: `04-county-pathway`, `05-goal3`,
`10-insight`, `12-brief`, `13-collect`, `16-evidence`, `14b-gemma-demo-demo-20`.

## Words to keep and words to avoid

- Keep: "synthetic", "a person confirms every event", "pre-filled for one-click confirmation",
  "needs editing", "placeholder" next to day 42, "the OECD/EU reports a six-week target" (not
  Finnish law), "draft for a planner".
- Avoid: any claim that a note or list item needs no human check, that the scribe was tested on
  real clinical text or is clinically validated, that a county's care is worse, or any medicine or
  product name. AstraZeneca sponsors the challenge; SAMA uses no AstraZeneca data.
- The 270M Gemma reader shown in the demo did not meet its preregistered criterion on new
  phrasings (11 of 143 held-out phrasings; the larger 1B reader 95 of 143; source
  `data/scribe/v4/eval/results-v1.json` `primary_result`, `sets.stress`). If asked, say so and add
  that vague or unknown phrasings go to a person.
- Vague phrases on the stress set: the code rule sent 29 of 29 to a person; Nemotron sent 3 of 29
  to a person and left 25 out (`sets.stress.systems.*.vague_outcome`). Do not say Nemotron "sends
  25 to a person". Gemma 1B dated all 29 without a flag (11 to a precise day, 18 to a month).
- The vague-phrase gate is **post hoc** (designed after the stress results were seen): with it the
  two readers pre-fill 218 of 308 stress notes with 2 wrong (without it 220 with 3 wrong), and 29 of
  29 vague facts reach a person (28 without it). Source `data/scribe/vague/results-v1.json`; the page
  shows it as one line labelled POST HOC under the scribe results. Never present it as preregistered.
