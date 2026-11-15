# Safety net data (SYNTHETIC): schema of `safetynet-v1.json` and its companions

Everything in this folder is SYNTHETIC. No real patient, report or county record. Rule-based; no
model ran. Rebuild from the solution root (about 1 s, 155 MB peak RSS on 14 Nov 2026):

```sh
scribe/.venv/bin/python -m safetynet.build
scribe/.venv/bin/python -m unittest discover -s safetynet/tests -t .
```

The page renders `safetynet-v1.json` with `safetyNetHtml(data, regionId)` from `web/safetynet.mjs`
(pure function, returns an HTML string; default county is `pilotRegionId`).

## Files

| File | What it is |
|---|---|
| `safetynet-v1.json` | County panel: counts, breakdowns, at most 3 example rows per county, thresholds, KPIs, text lines, provenance |
| `rule-eval-v1.json` | The 60 SYNTHETIC report lines, gold labels, the rule's reading of each, metrics |
| `imaging-loops.parquet` | Extension table: SYNTHETIC imaging follow-up loops (one row per loop) |
| `tests-output.txt` | Output of the unit tests on the final build |

## `safetynet-v1.json`

| Key | Type | Meaning |
|---|---|---|
| `schemaVersion` | string | `"1.0"` |
| `dataClass`, `synthetic` | string, bool | Always `"SYNTHETIC"`, `true` |
| `generatedAt` | ISO time (UTC) | Build time |
| `asOf` | ISO date | Replay date. The worklist sees only events dated on or before it; later events in the SYNTHETIC log count as not yet happened |
| `pilotRegionId` | string | `HVA06` (Satakunta), chosen on process grounds (`text.pilot`) |
| `text` | object | Display lines: `title`, `synthetic`, `clock`, `as_of`, `governance`, `legal`, `legal_url`, `regulatory`, `pilot`, `scope`, `rule`, `neutrality`, `aland`, `roadmap` |
| `thresholds[]` | `{clock, days, label, source}` | `label` is `PLACEHOLDER` (42 days; 90 days as a sensitivity) or `COPIED` (imaging: the date the radiologist wrote) |
| `kpis[]` | `{name, target}` | Pilot measures. Every `target` is a DESIGN TARGET or requirement; none is measured |
| `suppression` | `{below, rule}` | Counts 1-4 display as `<5`; raw SYNTHETIC counts stay in the file |
| `rule` | object | `version`, `sha256` of `safetynet/rule.py`, `evaluation` file, summary `metrics`, `caveat` |
| `cohort` | object | `imaging_loops` (size, rule and gold outcomes, agreement with gold, `errors` by type and `due_line_sent_to_person_reasons`: a second check of the frozen rule on the cohort's lines, rendered from the same templates with new seeds), `referral_loops`, `event_log_episodes`, `assumptions`, `assumption_notes` |
| `national` | object | Sums of the county rows (never computed from a suppressed table) |
| `counties[]` | object | One per area code in the event log (23), see below |
| `provenance` | object | Input paths and sha256 (event log sample, snapshot), sha256 of every `safetynet/*.py` used, Python and pyarrow versions, command |

### `counties[]`

| Key | Meaning |
|---|---|
| `regionId`, `name` | Area code (`HVA01`-`HVA21`, `HVA90` Helsinki, `HVA91` Åland) and English name from `data/snapshot/public-v1.json` |
| `counts.open_loops` | `imaging.open + imaging.awaiting_person + referral.open` |
| `counts.overdue` | `imaging.overdue + referral.overdue` |
| `counts.imaging.reports_with_recommendation` | Reports dated on or before `asOf` whose line the rule did not read as "no follow-up" |
| `counts.imaging.open` | Code-dated loops whose follow-up scan is not recorded by `asOf` (due or not yet due) |
| `counts.imaging.overdue` | Open code-dated loops whose due date is before `asOf` |
| `counts.imaging.due_passed`, `done_by_due`, `share_done_by_due` | Loops whose due date is on or before `asOf`; of those, follow-up recorded on or before the due date; their ratio. **Reproduces the simulation assumption (0.70) up to noise; not a finding** |
| `counts.imaging.awaiting_person` | Lines the rule sent to a person (range, vague, conditional, no time, ...), reported in the last 14 days (`assumptions.person_window_days`) |
| `counts.referral.open` | REFERRAL_SENT on or before `asOf`, no DIAGNOSIS recorded by `asOf` |
| `counts.referral.overdue` | Open and more than 42 days (placeholder) since REFERRAL_SENT |
| `counts.referral.overdue_at_sensitivity_days` | Same at 90 days (SAMA navigation card placeholder) |
| `counts.referral.clock_passed`, `diagnosed_by_threshold`, `share_diagnosed_by_threshold` | Referrals sent at least 42 days before `asOf`; of those, DIAGNOSIS within 42 days; their ratio (SYNTHETIC event-log simulator output) |
| `by_route[]` | `{route, open, overdue}` over open items, entry routes from `eventlog.schema.ENTRY_ROUTES` |
| `by_language[]` | `{language, open, overdue, interpreter}`; contact language `fi`, `sv`, `se`, `other` is a SYNTHETIC assumption (`assumptions.contact_language_shares`), not Statistics Finland data |
| `examples[]` | At most 3 unnamed SYNTHETIC rows, see below |
| `note` | Present for Åland only: the 2026 amendment and national measures are not claimed for Åland |

### `examples[]` (at most 3 per county)

Selection, deterministic: the most overdue imaging loop; the most overdue referral with age band
40+ (to keep the illustration plausible; the event-log simulator draws age uniformly from 0-4 to
100+); the newest line that needs a person.

| Key | Meaning |
|---|---|
| `episode_code` | SYNTHETIC code: an event-log `episode_id` or `SYNTHETIC-SN-<seed>-<county>-<n>` |
| `loop_kind` | `imaging_follow_up`, `suspected_cancer_referral` or `recommendation_needs_person` |
| `age_band`, `route` | From the event log (referrals) or the imaging cohort |
| `contact_language`, `interpreter` | SYNTHETIC assumption |
| `days_overdue` | `asOf` minus due date (imaging) or minus REFERRAL_SENT + 42 (referral); null if not overdue |
| `missing_step`, `owner_role` | Plain text |
| `status` | `nurse confirms` (date copied by code or from a structured field) or `needs editing` (a person sets the date) |
| `recommendation_copied` | The sentence copied verbatim from the SYNTHETIC report line (imaging kinds only) |
| `due_date`, `report_date`, `referral_sent` | ISO dates or null |
| `synthetic` | Always `true` |

## `imaging-loops.parquet` (extension table; `eventlog/schema.py` is not changed)

One row per SYNTHETIC imaging follow-up loop. Columns: `loop_id`, `county`, `entry_route`,
`age_band`, `contact_language`, `interpreter`, `report_line_id`, `report_date`, `report_text`,
`rule_outcome` (`DUE_DATE`/`PERSON`/`NONE`), `rule_reason`, `rule_due_date`,
`recommendation_copied`, `gold_outcome`, `gold_due_date`, `followup_done_date` (null = not done),
`synthetic`. The extension event types `IMAGING_REPORTED` (= `report_date`) and
`FOLLOWUP_IMAGING_DONE` (= `followup_done_date`) exist only here, never in
`eventlog.schema.EVENT_TYPES`.

How it joins the event log: per county, the number of loops is 0.25 x the county's episodes in
`data/eventlog/sample`, and each loop's entry route is drawn from that county's episode route mix.
Report lines are rendered by `safetynet/reports.py` (new seeds), read by the frozen rule, and the
worklist uses the rule's date, not the gold date. Whether and when the follow-up happened is drawn
from `assumptions` (70% on time, 20% late with mean 45 days, 10% not done), identical everywhere.

## `rule-eval-v1.json`

`lines[]` (`line_id`, `report_date`, `text`, `family`, `gold_outcome`, `gold_due_date`,
`language`, `synthetic`), `rows[]` (the rule's `outcome`, `due_date`, `reason`, `matched_phrase`,
`copied_verbatim`, `correct`), `metrics` (exact due dates, sent-to-person, none-correct, error
types, confusion), `rule_sha256`, `reports_sha256`, `caveat`. The rule was frozen (sha256 in
`runs/ship-safetynet.jsonl`, step `1-rule-frozen`) before the 60 lines were written; both were
written by the same step, so the score measures the rule on its own template family only.
