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
  official 30-place road map, dealer windows, shortage at driver home towns,
  local order backlog, conservative buffer and expected fees.
- Use dealer-specific trust and win/loss counters from observable events, with
  deterministic recovery from the official historical event log.
- Start funded gigs at 155% of reference fee, escalate to 230% if still
  unbooked, and use a faster emergency schedule on `deadline_close`.
- Delegate correct post/withdraw/repost/rate-limit behavior to the official
  starter, adding optional manual-licence/plates constraints from dealer notes.

This is **runnable API integration**, not a claim of >90% real qualification.
No registered team key, official practice score, ranking run, or final execution
was available when this artifact was authored. Algorithm parameters are a
first hypothesis, not trained or validated against the hidden worlds. Keep the
existing PR #101 and its local uncommitted V2 repairs intact.
