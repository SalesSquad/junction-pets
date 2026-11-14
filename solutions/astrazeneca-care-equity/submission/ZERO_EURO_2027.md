# The zero-euro 2027 plan

The Cancer Organisations say no money for implementing the national cancer strategy is in sight
for **2027**, which they call a gap year (STT, 4 September 2026). Counties are also under deficit
pressure, and non-urgent primary-care maximum times were lengthened from the start of 2025 (STM).
These three actions need no capital spending. Their cost is **staff time**, written below in the
units a county manager budgets; the volumes are what the pilot measures first. Each names its owner,
the national roadmap measure it serves and one KPI. Every number comes from the file named next to
it; `submission/check_numbers.py` recomputes them. Patient-like data in SAMA are SYNTHETIC.

## The three actions

| # | Action | Owner | Roadmap measure | KPI | Staff time instead of euros |
| --- | --- | --- | --- | --- | --- |
| 1 | Put pre-booked appointment times back into every screening invitation letter | County screening unit | 1.3.1 (page 33): participation of people whose mother tongue is not Finnish or Swedish reaches the level of Finnish and Swedish speakers | Participation by mother tongue and education, against the 80% target | One template change by the screening unit; rebookings handled by existing booking staff |
| 2 | Run the overdue-pathway list (the safety net) with existing care coordinators, lung follow-up first | County cancer centre | 1.2.3 (page 32): a named worker who coordinates cancer care | Share of follow-ups closed on time; share resolved within 14 days; each by entry route, education and contact language | One call by a nurse per overdue item; the item count comes from the list itself (SYNTHETIC replay for Satakunta: 16 overdue items among 120 open loops) |
| 3 | Send two dates and an end reason in THL's person-level feed | County data team with THL | 3.2.1 (pages 59-60): the cancer quality register at THL's Cancer Registry | Share of new suspected-cancer pathways with both dates and an end reason | Mapping two dates that already exist into an extract the county must deliver to THL anyway; no new form for clinicians |

## Evidence for each action

1. **Pre-booked times.** When Helsinki removed pre-booked appointment times from cervical screening
   invitations, participation fell from **72%** to about **62%**; after the city returned to the old
   practice it recovered (Yle, 10 December 2025). One city, before and after, no years given: the
   effect elsewhere is a SCENARIO. The gap it targets: cervical screening **57%** against **73%** by
   mother tongue, **51%** against **78%** by education (OECD/EU 2025, p. 15).
2. **The overdue-pathway list.** Since **1 June 2026** a county may identify patients whose care
   does not follow recommendations; processing their data and contacting them must respect data
   protection and self-determination (STM, 21 May 2026). Whether that covers the timing of pathway steps is UNVERIFIED. Faster reading alone
   did not move the pathway: AI prioritisation of 93,326 GP chest X-rays left the median time to CT
   at **53 days** in both arms (LungIMPACT). Close loops before buying speed.
3. **Two dates in THL's feed.** THL's access statistic covers non-urgent care only, as month-end
   snapshots; person-level delivery through TTP is due by 2028 at the latest. Roadmap 3.2.1 is
   budgeted at EUR 2,500,000 in the national roadmap; this action adds fields to it, not money.

## What this plan does not claim

- No effect size for a county: each KPI is measured in the pilot.
- No new national spending; the roadmap measures keep their own budgets and owners.
- The county owns the list, the letters and the care. No patient data leaves the county.

## Sources

`submission/evidence-v2.json` (`stt-2026-no-strategy-money-2027`, `stm-hoitotakuu`,
`yle-2025-helsinki-prebooking`, `oecd-2025-fi-breast-screening-gaps`, `stm-2026-proactive-care-law`,
`lungimpact-2026`, `thl-ttp-person-level`); `data/roadmap/mapping-v1.json` (measures 1.3.1, 1.2.3,
3.2.1); `data/safetynet/safetynet-v1.json` (`counties` HVA06).
