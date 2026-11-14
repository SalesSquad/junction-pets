# SpreadGuard — Bahn Express live dispatch runner

Fast, dependency-light strategy for the **official Bahn Express Spread v0 API**.
`dispatch.py` subclasses `spread.starter.Desk` from the official Python SDK;
official code owns HTTP requests, rate limits, action batches, practice advancing,
final WebSocket streaming, reconnect, and snapshot replay. Python 3.10+.

Official kit: `https://spread.bahnexpress.com/kit/spread-0.1.0-py3-none-any.whl`.
Pinned artifact SHA-256:
`74f93ba5acd17edc17e484bb5ad5a6a200689587461374eb2b13f8af5a214b1c`.
Verify SHA-256 before installation. Do not install from a new unverified mirror.

Example after obtaining a legitimate **team key** using the official `/join` flow,
in an authorized runtime (never print the key or write it into a repository):

```sh
python3 -m venv .venv
.venv/bin/pip install https://spread.bahnexpress.com/kit/spread-0.1.0-py3-none-any.whl
export SPREAD_URL=https://spread.bahnexpress.com
# Set SPREAD_KEY using the host's approved secret/environment mechanism.
.venv/bin/python dispatch.py --level 8 --seed spreadguard-smoke-1
```

When and only when *real official* practice worlds qualify consistently at
at least 90% on-time **in each of five worlds**, run the ranking five-world
sequence (it counts and cannot be replayed):

```sh
.venv/bin/python dispatch.py --level 8 --board
```

For the scheduled test final and Sunday final, run the exact same program:

```sh
.venv/bin/python dispatch.py --final
```

`--final` reconnects to the official server event stream, repairs pending
requests and active gigs from its snapshot, and respects the final's automatically
moving clock. It **never** calls `advance` for a final.

## Strategy and limits

- Quote only one preferred deadline option; estimate feasibility from the
  official 30-place road map, dealer windows, available drivers, observed
  positions/bookings, local order backlog and conservative timing buffers.
- Use dealer-specific trust and win/loss counters from observable events, with
  deterministic recovery from the official historical event log. Booking
  delay observations gradually adjust the minimum required time buffer.
- Normally reserve 15% of won-order revenue and cap escalating driver offers
  by the remaining fee budget, deducting actual driver ledger costs and
  outstanding booked commitments. A `deadline_close` warning allows a bounded
  102% revenue emergency budget to protect the >90% on-time qualification gate.
- For an exact policy comparison on **unranked practice worlds only**, use
  `SPREAD_GUARD_POLICY=baseline` for the original 155–230% payout ramp or
  `SPREAD_GUARD_POLICY=risk_budget` (default) for the bounded policy. Use the
  same official `--seed` for both attempts, and compare sponsor world scores;
  never infer genuine rank from the synthetic sensitivity harness.
- `discovery_experiment.py` is a **separate opt-in, high-risk experiment**, not
  the default/final system. It bids 132% of list with an economic floor at 135%
  of reference fee and starts driver offers at 100% of reference. All five
  independent official unranked level-8 practice seeds passed the 90% on-time
  gate (92.0%, 92.0%, 95.9%, 94.9%, 99.0%), with positive margins. This does
  **not** prove future-world reliability or authorize a ranked/final submission.
  `test_discovery_experiment.py` checks the sponsor SDK action shape.
- `uber_market_experiment.py` is an additional **unqualified, opt-in research
  hypothesis** inspired by Uber's documented batched matching, supply-demand
  pricing and opportunity cost. The Spread SDK does not permit direct driver
  assignment. This experiment instead couples regional demand/available
  driver capacity to quotes and driver fee ramps, reserves virtual capacity
  across concurrent requests, observes right-censored unbooked posting age,
  and penalizes late-completion debt. It also matches open gig demands to
  candidate available drivers on the directed road graph **virtually** to
  avoid assigning one driver's planned capacity to multiple zones. It cannot
  actually assign a driver; the SDK still performs matching.
  Its `test_uber_market_experiment.py` and `offline_market_sweep.py` are
  synthetic contract/structural checks only. The offline sweep covers balanced
  demand, regional backlog, driver shortage, and missing roster data without
  inventing win/late labels. In the deterministic shortage fixture it quoted
  55.8% vs Discovery's 64.0% of synthetic requests, trading quote volume for
  stronger up-front delivery-risk controls. These numbers **cannot** predict
  the official game score. One additional official **unranked** same-seed
  comparison on 2026-11-14 found **inferior results** versus Discovery:

  | Holdout A, same official seed | Discovery | Uber-inspired experiment |
  | --- | ---: | ---: |
  | Orders won (after cancellations) | 301 | 284 |
  | On time | 92.0% | 91.2% |
  | Undelivered | 0.3% | 0.7% |
  | Margin | +€5,418.07 | +€4,603.94 |

  Exact sponsor-world IDs: Discovery `wb66a14d35da664f11487`, Uber
  `wf6ccbe870ec315616e9e`. Both had 1,039 requests; Uber sent 457
  competitive quotes vs 470, and had 16 failed visits vs Discovery's 12.
  This **disproves that the current opt-in version is better on this seed**.
  It is **NOT qualified for `--board` or `--final`** and must not replace the
  five-world-qualified Discovery strategy without additional evidence.
- Delegate correct post/withdraw/repost/rate-limit behavior to the official
  starter, adding optional manual-licence/plates constraints from dealer notes.

The default `dispatch.py` has one real official practice qualification. The
`discovery_experiment.py` has five independently seeded qualifying official
**unranked** practice results. The Uber-inspired variant has **one** official
unranked practice result that passed the 90% on-time gate but **underperformed
Discovery in the same seeded world**. Never conflate their evidence or treat
either unranked result as a leaderboard/final qualification.
The `One Man Raid` team was registered on 2026-11-14; its token stays exclusively
in the owner's Mac Keychain and must never enter this repository. Official
practice is being qualified independently of this draft PR. Algorithm parameters
remain hypotheses until paired real-world practice scores validate them. Keep
the existing PR #101 and its local uncommitted V2 repairs intact.
