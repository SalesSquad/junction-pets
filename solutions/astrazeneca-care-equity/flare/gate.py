"""Comparability gate: the rule, the clock definition and the site-side computations (SYNTHETIC data only).

Pure Python with no NVIDIA FLARE import, so the rule can be tested on its own and the same functions are
used by the FLARE site (flare/gate_stats.py) and the plain-Python central reference (flare/build_gate.py).

Clock: referral to treatment = REFERRAL_SENT -> TREATMENT_START, whole days. The clock starts when the
referral is SENT (SAMA's REFERRAL_SENT event). 42 days is a PLACEHOLDER: the OECD/EU-reported six-week
target ("six weeks between a referral concerning a suspected case of cancer and the start of primary
treatment", OECD/EU Country Cancer Profile Finland 2025, PDF page 19). Finnish law (STM hoitotakuu,
updated 29 Oct 2026) lets specialised treatment start up to six months after the need is identified and
names no cancer-specific limit. The histogram edge sits at 42.5 days, so the bins below it count exactly
the pathways of at most 42 whole days.

Rule (thresholds are PLACEHOLDERS, not validated limits): a county x scribe-arm cell is "not comparable"
when the scribe's median bias is above 3 days either way, or its missed-event share is above 10%.
  median bias  = median(scribe-measured interval length) - median(true interval length), in days, over the
                 county's within-note intervals whose two endpoints the scribe found (the shift the scribe
                 would put into the county's median clock);
  missed share = gold events not found with their correct type / all gold events of the county's notes.
The raw value of the clock is always kept; the gate only labels it.
"""
from __future__ import annotations

import math
import statistics
from collections import defaultdict

COUNTIES = [f"HVA{i:02}" for i in range(1, 22)] + ["HVA90", "HVA91"]
ARMS = ("raw", "resolver")
RTT_START, RTT_END = "REFERRAL_SENT", "TREATMENT_START"
RTT_THRESHOLD_DAYS = 42
RTT_EDGE_DAYS = RTT_THRESHOLD_DAYS + 0.5
BIAS_LIMIT_DAYS = 3.0  # placeholder
MISSED_LIMIT = 0.10  # placeholder
MIN_COUNT = 5  # SAMA's n < 5 suppression rule (FLARE MinCountCleanser)
ZERO_DAY = 0.5  # eventlog.power.ZERO_DAY: a zero-day interval is logged as half a day

THRESHOLD_LABEL = "placeholder (OECD/EU-reported target)"
RULE_LABEL = "placeholder thresholds"


def rtt_records(events, roster):
    """Per started clock: dict(episode_id, days or None, open flag).

    events: iterable of dicts with episode_id, event_type, event_date (datetime.date).
    roster: list of roster dicts (episode_id, administratively_censored list).
    A clock has started when the episode has exactly one REFERRAL_SENT. It is complete when it also has
    exactly one TREATMENT_START; open when TREATMENT_START is administratively censored (after the data
    cut); otherwise the end date is missing.
    """
    found = defaultdict(lambda: defaultdict(list))
    for e in events:
        found[e["episode_id"]][e["event_type"]].append(e["event_date"])
    out = []
    for ep in roster:
        f = found.get(ep["episode_id"], {})
        starts, ends = f.get(RTT_START, []), f.get(RTT_END, [])
        if len(starts) != 1:
            continue
        days = (ends[0] - starts[0]).days if len(ends) == 1 else None
        if days is not None and days < 0:
            raise ValueError(f"negative referral-to-treatment span in {ep['episode_id']}; validate first")
        is_open = days is None and RTT_END in ep.get("administratively_censored", [])
        out.append(dict(episode_id=ep["episode_id"], days=days, open=is_open))
    return out


def log_days(days):
    return math.log(days if days > 0 else ZERO_DAY)


def median_bias(intervals):
    """median(pred_days) - median(true_days) over found intervals; None when there are none."""
    if not intervals:
        return None
    return statistics.median(q["pred_days"] for q in intervals) - statistics.median(q["true_days"] for q in intervals)


def gate(bias_days, missed_share, bias_limit=BIAS_LIMIT_DAYS, missed_limit=MISSED_LIMIT):
    """Return dict(comparable, reasons). Unknown inputs never pass: no data means 'not comparable'."""
    reasons = []
    if bias_days is None:
        reasons.append("no found interval to estimate bias")
    elif abs(bias_days) > bias_limit:
        reasons.append(f"median bias {bias_days:+g} days is beyond +/-{bias_limit:g}")
    if missed_share is None:
        reasons.append("no gold event to estimate missed share")
    elif missed_share > missed_limit:
        reasons.append(f"missed-event share {missed_share:.3f} is above {missed_limit:g}")
    return dict(comparable=not reasons, reasons=reasons)


def mean_sd(xs):
    """FLARE's definitions: mean = sum / count, stddev with n - 1 in the denominator."""
    n = len(xs)
    if n == 0:
        return None, None
    m = sum(xs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1)) if n > 1 else 0.0
    return m, sd
