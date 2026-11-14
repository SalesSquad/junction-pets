# Bahn Express Spread: opt-in rescue candidate (14 Nov 2026)

**Status: executable experiment, not sponsor-qualified for 97%.** This stacked
change extends PR #128 (`5a0cb61c6083ce13c465b46b9958c90e066e142e`)
without replacing the proven Discovery runner or changing `dispatch.py`.
The baseline competition objective is **gross margin**, subject to the
sponsor's **at least 90% on-time** eligibility requirement. Our 97% goal is
an ambitious *internal* threshold, not a documented sponsor threshold.

## Verified execution path

On the authorized MacBook Pro, the pinned `spread==0.1.0` official SDK is
already installed in `/tmp/spread-race-20261114-venv`. The complete task
source is available as a detached, isolated sparse worktree at
`/private/tmp/bahn-rescue-97-20261114`; the other existing worker checkout
has not been modified. The following completed without starting a sponsor
practice/ranked/final world:

```bash
/tmp/spread-race-20261114-venv/bin/python -m unittest discover \
  -s /private/tmp/bahn-rescue-97-20261114/solutions/bahn-spreadguard-live \
  -p test_rescue_experiment.py -v
# 15/15 targeted tests passed at commit 485e5c0b1b5b8f4fcee4d7874da21bc4058a7427

/tmp/spread-race-20261114-venv/bin/python \
  /private/tmp/bahn-rescue-97-20261114/solutions/bahn-spreadguard-live/offline_rescue_sweep.py
# 5 deterministic scenarios, 1,500 simulated *won* orders per scenario

/tmp/spread-race-20261114-venv/bin/python \
  /private/tmp/bahn-rescue-97-20261114/solutions/bahn-spreadguard-live/rescue_experiment.py --help
# Verified flags: --level (1..8), --seed, --board, --final
```

The official sponsor runner requires `SPREAD_URL` and `SPREAD_KEY`. Retrieve
these via the **existing authorized account/Keychain workflow**, never put
secrets into Git or test logs. The runner defaults to the opt-in `full`
strategy; `SPREAD_RESCUE_MODE=fees` compares fee rescue only and
`SPREAD_RESCUE_MODE=discovery` preserves the baseline quote policy. The
default `SPREAD_RESCUE_CURVE=offer_first` avoids the earlier uneconomic
immediate fee ramp; `rush` is an experimental ablation.

**Do not run `--board` or `--final` as an incidental smoke test.** As of
this checkpoint, all 8/8 official unranked practice worlds had been
consumed. No additional official world was executed or claimed by this
work. Before any authorized ranked/final run, refresh the source checkout,
confirm challenge clock/state and credentials, and explicitly choose the
entrypoint/mode. The sponsor may charge scarce ranking/final attempts.

## What was added

- Deadline-aware risk uses actual sponsor `lastPickupAt`, plus observed
  booking delays and failed visits; quotes are capped to remaining fee budget.
- Targeted `offer` invitations use official sponsor action API, directed-road
  deadhead, homebound cost and driver history; they are **not** assignments.
- Offer limit of two per driver/simulation day and two pending per gig;
  held quota on unknown result, 10-minute expiry and a 22:45 invitation cut-off.
- Fail-closed invitation behavior after a process restart when the official
  rejoin snapshot does not expose historical offer state.
- Drop/no-show repricing, negative driver history, and immediate event wakes
  without adding artificial ticks; no cross-repo or shared runner changes.

## Paired synthetic sensitivity sweep

The synthetic generator has fixed seed `97141114`; all figures below are
**conditional on the order already being won**, not a booking-conversion or
sponsor world replay. `margin` is synthetic EUR gross margin with an
**invented EUR 150 per missed-delivery penalty**. Fee acceptance rates,
capacity and delays are hypothetical. It does not model all bidder behavior.

| Synthetic scenario | Discovery on time | Rescue fees | Full rescue | Full margin / Discovery margin |
| --- | ---: | ---: | ---: | ---: |
| Balanced | 96.47% | 99.07% | **99.20%** | 90.52% |
| Scarce drivers | 90.00% | 94.73% | **95.40%** | 88.05% |
| Highly fee-elastic | 95.20% | 99.60% | **99.60%** | 90.49% |
| No fee elasticity | 88.53% | 88.53% | **90.60%** | 91.30% |
| Severe shortage | 76.33% | 81.87% | **82.47%** | 88.87% |

The full policy improves on-time service in these *invented worlds* but
reduces gross margin significantly. It does **not** establish ≥97% in real
competition, nor superiority against Discovery on the real scoring objective.
The real five-world Discovery baseline was 92.0%, 92.0%, 95.9%, 94.9%,
99.0% on-time; that baseline remains the safer proven candidate. The
separately tested Uber-style market policy underperformed Discovery in its
holdout and was not promoted.

## Independent critique and promotion gate

An actual Claude Fable 5.2 read-only review of the controller identified
over-broadcasting, fee-margin erosion, invitation quota uncertainty,
restarts and unnecessary premiums as material risks. The offer-first
strategy, narrower risk criteria, restart fail-close and bounded invitations
were changes driven by that review. These changes have been targeted-tested
but **not** official-world-qualified.

Promote only if a permitted, genuinely out-of-sample world has ≥97% on-time,
keeps sponsor eligibility in every scenario, and the actual gross margin
outperforms (or meets an explicitly accepted tradeoff versus) Discovery.
Log exact repository SHA, official SDK version, seed/world identifier,
driver/quote outcomes, margin and run type in an access-controlled receipt.
Otherwise preserve Discovery as the production/competition default.

Reference: official [Spread rules](https://spread.bahnexpress.com/kit/RULES.md),
[handbook](https://spread.bahnexpress.com/kit/HANDBOOK.md), and
[API](https://spread.bahnexpress.com/kit/API.md).
