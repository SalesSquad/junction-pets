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
- Delegate correct post/withdraw/repost/rate-limit behavior to the official
  starter, adding optional manual-licence/plates constraints from dealer notes.

This is **runnable API integration**, not a claim of >90% real qualification.
The `One Man Raid` team was registered on 2026-11-14; its token stays exclusively
in the owner's Mac Keychain and must never enter this repository. Official
practice is being qualified independently of this draft PR. Algorithm parameters
remain hypotheses until paired real-world practice scores validate them. Keep
the existing PR #101 and its local uncommitted V2 repairs intact.
