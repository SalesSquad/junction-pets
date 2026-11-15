# Bahn Spread: margin overlay `vol360` (15 Nov 2026)

**Work ID:** `BAHN-SPREAD-MARGIN-20261115` · **Source base:** `957f0c3e2f0e77aef4c9ad045c0b9a9234fecc55`
(`codex/j26-bahn-rescue-97-20261114`) · **Executor:** MacBook Pro, pinned official
`spread==0.1.0`, level 8, **unranked practice worlds only** (no `--board`, no `--final`).
Key read from the existing Keychain item at run time, never written anywhere.

This branch only **adds** files. It does not edit `dispatch.py`,
`admission_experiment.py` or any file of the reliability work in progress.

## What changed (`margin_experiment.py`, class `MarginDesk`)

`MarginDesk` subclasses the frozen 139% / +240 min `AdmissionDesk`. Its defaults are the
frozen **vol360** candidate:

1. **Dealer-trust pricing.** Price = list × (139% + 0.8% × the dealer's counted on-time
   orders), capped at +16%. Level 8 dealers accept +1% per counted order; the old system
   turned that trust into a higher win rate (31% at trust 0–2 → 82% at trust 15+ in the
   recorded worlds) instead of margin.
2. **Night-aware fee ramp.** The Discovery fee schedule (100 → 150% of the reference fee
   over 5 h) kept rising overnight, when nobody books: next-day bookings paid on average
   **1.30×** the reference fee versus **1.05–1.07×** for same-day bookings (24% of all
   bookings, 10 recorded worlds). Raises now pause 21:00–07:00, start on the pickup day,
   take twice as long while more than 20 h remain, and the last raise still lands before
   `lastPickupAt − 3 h`. The urgent (`deadline_close`) schedule is unchanged.
3. **Looser time gates.** Slack floor 480 → **360** min and the next-day buffer
   240 → **120** min. The old gates declined ~45% of all requests; the leaders of the
   practice rankings win ~43% of all requests.

Kept unchanged: driver/backlog/fee vetoes, decline-by-high-quote, manual/plates note
handling, budget caps, rejoin from server history (`MarginDesk.rejoin` also rebuilds its
own counters).

Rejected after testing (all switchable, default off): region "outage" streak pricing
(no gain, one world fell to 89.9%), lower opening fee 85% (on-time down to 82%),
gate 240/120 min (+46–52% margin but 1 of 6 worlds below 90%), adaptive gate on the
`deadline_close` rate (1 of 6 below 90%), quoting every eligible option (−3% vs vol360),
weekend-aware ramp and trust 1.0%/order (both −2–3% vs vol360).

## Results

Paired against the frozen 139% / +240 min baseline on the same seeds. Seeds:
`claude-margin-20261115-01…06` (development) and `claude-holdout-20261115-01…08`
(holdout, chosen after development, no retuning on them). Exact world IDs per run are in
[`evidence/margin_overlay_runs_20261115.csv`](evidence/margin_overlay_runs_20261115.csv).

| Policy | Paired worlds | Baseline € | Policy € | Δ | Better | Worst on-time | Not ranked |
|---|---:|---:|---:|---:|---:|---:|---:|
| **vol360** (frozen) | 14 | 74,712 | 93,688 | **+25.4%** | 14/14 | 92.9% | 0 |
| tr (trust + ramp only) | 14 | 74,712 | 87,577 | +17.2% | 12/14 | 93.5% | 0 |
| v360t100 | 14 | 74,712 | 92,234 | +23.5% | 14/14 | 91.3% | 0 |
| v360wk | 14 | 74,712 | 91,107 | +21.9% | 14/14 | 93.4% | 0 |
| v360multi | 14 | 74,712 | 91,547 | +22.5% | 14/14 | 92.5% | 0 |
| vol (gate 240) | 6 | 33,586 | 48,974 | +45.8% | 6/6 | **89.4%** | 1 |
| adapt | 6 | 33,586 | 44,296 | +31.9% | 6/6 | **89.8%** | 1 |
| region | 5 | 27,308 | 27,271 | −0.1% | 2/5 | **89.9%** | 1 |
| fee 85% variants | 6 | 33,586 | ≤53,942 | — | — | **81.7–87.0%** | 1–2 |

vol360 per-world on-time: 92.9–98.3% (baseline 92.9–99.6%); per-world margin €3.2k–10.3k.

## Honest limits

- **Not top-10 level.** The level 8 practice rankings (round 10, 240 teams) put the
  top-10 cut-off at about **€16–17k per world** with 400–500 orders at ~97% on time.
  vol360 makes ~€6.7k per world on average (~€3k–10k). It improves the system; it does
  not close a ~2.5× gap.
- 14 worlds give no guarantee for an unseen final world. The hardest seed
  (`claude-margin-20261115-06`) sits at 92.9% for both baseline and vol360.
- The final runs on a live clock and was not rehearsed here. A restart from server
  history was exercised once with `rejoin_smoke.py` (see the receipt below).

## Reproduce

```sh
# Unranked practice only. SPREAD_PY = venv with the pinned official SDK.
zsh run_campaign.sh /tmp/out/c.jsonl 4 my-seed 6 base vol360
python3 summarize_campaigns.py /tmp/out/c.jsonl
python3 analyze_recorded_worlds.py '<data>/historical/*.json.gz'   # pricing/fee evidence
python late_why.py <ended world id> ...                              # late-order causes
```

`python margin_experiment.py --final` would play the final with the vol360 defaults.
It is **not** authorised by this branch; the owner decides what runs in the final.

## Receipts (15 Nov 2026, ~02:45 EET, MacBook Pro)

- **Defaults = vol360.** `run_pair.py <seed> frozen` (no environment overrides) on
  `claude-margin-20261115-01` gave world `w12307f63223210076c15`: €8,517.16, 259 orders,
  96.91% — identical to the vol360 run `wcf1cc95c9d747d185c3f` on the same seed.
- **Restart from server history.** `rejoin_smoke.py claude-rejoin-20261115-01` played to
  Wednesday 12:00, discarded the desk, rebuilt it with `MarginDesk.rejoin` from
  `world.events()` + `world.snapshot()` and finished: world `wd61a95d9d45ff05c2ace`,
  €9,156.94, 306 orders, 96.41%, ranked; counters before/after the rebuild matched
  (126 recent wins, 3 deadline warnings, trust sum 70). This exercises the rejoin path
  only; the live final stream and clock were not rehearsed.
- Unit tests of the existing files were not rerun (no existing file changed).
