# SAMA: live demo script (2 minutes, 30-second version, fallbacks)

Written 15 November 2026, 00:45-01:15 UTC; updated 01:40-01:50 UTC after the demo fixes (Note 4
opens by default, the plan comes before its method, plain numbers lead the scribe results), and at
03:00 UTC: the click path now opens on the page's "Start here" decision card (merged from #246). The
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
   old server on port 4179 was stopped at 02:45 UTC on 15 November; start your own on 4191 as in
   step 1.
3. Browser window about 1440 px wide, zoom 100% (or 90% on a 1280 px projector). Scroll to the top.
4. Do **not** click "Check claims" in the analyst brief: with a TypeSafe key on the server it calls
   a hosted API; without one it only says NOT_CONFIGURED. The stored checks are already on screen.
5. Do **not** click "Run live on this computer" unless the live CPU worker has been started and
   warmed up on purpose. With `SAMA_SCRIBE_LIVE=0` it falls back to the stored output; for Note 4
   the verdict stays "Pre-filled for one-click confirmation" and the footer says "live run not used"
   (screenshot `14c-gemma-demo-live-fallback-1440.png`).
6. Open the fallback recording `submission/fallback/SAMA-demo-fallback.mp4` (silent, 2:00, recorded
   at 02:55 UTC on 15 November from a fresh server on port 4191 with `SAMA_SCRIBE_LIVE=0 SAMA_NEMOTRON_LIVE=0`) in QuickTime, paused at 0:00, and the folder `submission/shots/` in
   Preview, sorted by name. Either can replace the browser at any step. The recording follows the
   click path below to the second (sections start at 0:00, 0:15, 0:40, 0:55, 1:15, 1:40); a
   small badge in its lower-left corner names the step. Re-record with
   `submission/fallback/record.mjs` and `encode.sh` (commands at the top of `record.mjs`) after any
   later data rebuild.

7. **Live Nemotron (for the NVIDIA jury).** To let the page call Nemotron 3.5 Super VL live, start
   the server with the endpoint settings loaded instead of step 1:
   `set -a; . ~/.config/verda-inference/env; set +a; SAMA_SCRIBE_LIVE=0 PORT=4191 node web/serve.mjs`.
   Then "Ask Nemotron live (second reader)" under Note 4 answers in about 3 s (2.7 s in the test run,
   `runs/nemotron-live-demo.jsonl`). Without the settings, or with `SAMA_NEMOTRON_LIVE=0`, the button
   shows the stored answer and says why. Try it once before the judges arrive.

## The 2-minute click path

About 250 spoken words (counted from the "Say" column; 2.3 words a second leaves about 10 seconds for clicks). Each step: what to click, what to say, which number to point at, and the
file that number comes from.

| Time | Click | Say | Point at | Source |
| --- | --- | --- | --- | --- |
| 0:00 | Nothing: the page is at the top. | "SAMA means 'the same': the same cancer pathway wherever you live, whoever you are, however you enter care. Finnish men's five-year lung cancer survival is 17.9 percent; Sweden and Norway, 31.1. And no county can see its own pathway clock yet." | Tile "The survival gap": "17.9% vs 31.1%". | `web/data/app.json` `analysis.goal3.indicators[0].rows` (lung, male: `finland` 17.9, `benchmark` 31.1) |
| 0:15 | Nav "Start here" (Satakunta is selected). | "Start with one county, one next step. Satakunta's cancer mortality ratio is 1.10: an outcome difference, not a cause. Its specialist referrals wait over 21 days more often than nationally, 3 against 1.3 percent. So, first 30 days: name a pathway lead, agree the timestamps, publish a baseline; review at 90 days. A proposal for people to decide." | The card "Standardised, timed cancer pathways with a fast-track referral": 01 observed outcome, 02 pathway question, then "Proposed first 30 days". | `src/decisions.mjs` `buildDecisionBrief(app, 'HVA06')` on `web/data/app.json` (`analysis.mortality.all_cancers` HVA06 shrunk 1.097, 1.063-1.132; `referral_handled_over_21d` 3 vs 1.33, 2023-2025) |
| 0:40 | Nav "Close the loop". | "Then the follow-up becomes a nurse's list. Synthetic Satakunta replay: 120 open loops, 16 overdue. A nurse confirms every item." | The four tiles (120, 16), then the three SYNTHETIC rows. | `data/safetynet/safetynet-v1.json` (`counties` HVA06: `open_loops` 120, `overdue` 16, imaging `overdue` 10, referral `overdue` 6) |
| 0:55 | Nav "Comparability gate". | "A county is compared only when it can see itself. NVIDIA FLARE computed each county's clock where its synthetic data live, 253 of 253 cells matching. With the model's own dates, 15 of 23 counties are not comparable; when Gemma reads and code counts, 1." | "The model's own dates: 15 of 23" and "Gemma reads, code counts: 1 of 23". | `data/flare/gate-v1.json` (`summary.raw`, `summary.resolver`, `flare.equivalence`: 253 of 253) |
| 1:15 | Nav "Gemma demo". Note 4 opens by default and its stored output loads by itself. | "Gemma reads the note on this laptop and copies '25 viikkoa sitten'; code computes the date. Nemotron reads it too; they agree, so it is pre-filled for one-click confirmation, and a person confirms. On 308 frozen stress notes Gemma alone gets 85 wrong; with the second reader, 3." | Row "MDT decision": 9.9.2023 with 8.10.2023 struck out; the box "Pre-filled for one-click confirmation". | `data/scribe/demo/demo-outputs.json` (`results.demo-04`); `data/scribe/v4/eval/results-v1.json` (`sets.stress.systems.C` 223 of 308; `cascade.configurations` C + agreement, stress 220 pre-filled, 3 wrong) |
| 1:40 | Nav "Nemotron county plan" (Satakunta is the default). | "Nemotron drafts each county's plan through SAMA's tools; code checks every number. Our ask: a 2027 pilot in Satakunta, owned by the county. Gemma runs locally; the second reader runs inside the county, or a person does that step." | The plan's footer line "Across 23 counties: 255 of 299 drafted sentences kept". | `data/planner/plans-v1.json` (`summary`: `keptSentences` 255, `sentences` 299); `data/roadmap/mapping-v1.json` (`pilotCard`) |

At 1:15, if the NVIDIA jury is present and step 7 was used, click "Ask Nemotron live (second reader)"
and say: "This is Nemotron answering now, on this synthetic note; the same rule applies to its answer."

If a judge asks about errors at 1:15, pick "Note 19": Gemma invents a symptom date in a note about
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
| 0:10 | Nav "Start here", then "Close the loop". | "For Satakunta, one next step: name a pathway lead, agree the timestamps, publish a baseline. Then a nurse's list of stalled pathways: in the synthetic replay, 16 of 120 open loops are overdue." | `src/decisions.mjs` (HVA06); `data/safetynet/safetynet-v1.json` HVA06 |
| 0:20 | Nav "Gemma demo", Note 4. | "Gemma copies the date phrase, code counts the days, a person confirms. Our ask: a 2027 pilot in Satakunta, lung follow-up first." | `data/scribe/demo/demo-outputs.json` `results.demo-04`; `data/roadmap/mapping-v1.json` `pilotCard` |

## If a part fails

Switch to the fallback recording (scrub to the step's time) or to Preview on `submission/shots/`
and keep talking; the script does not change. Files are
named `<order>-<section>-<width>.png`; use the 1440 versions on a projector and the 390 versions
only to show the phone layout (captured at device scale 1 to keep the folder at about 15 MB).

| What fails | What you see | Do this | Fallback screenshot |
| --- | --- | --- | --- |
| Server does not start or the port is taken | Connection refused | Start on another port (`PORT=4192`); if it still fails, play the fallback recording from 0:00 and speak over it | `submission/fallback/SAMA-demo-fallback.mp4`; all of `submission/shots/` |
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
