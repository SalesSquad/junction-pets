#!/usr/bin/env python3
"""Run one unranked level-8 practice world for (seed, policy); print a JSON line.

Policy names map to environment overrides of margin_experiment.MarginDesk or the
frozen admission baseline. Never --board, never --final.
"""
from __future__ import annotations

import json
import os
import sys
import time

POLICIES = {
    "base": {"cls": "admission"},
    # The overlay's own defaults with no environment overrides (= frozen vol360).
    "frozen": {"cls": "frozen"},
    "full": {"SPREAD_MARGIN_RAMP": "1", "SPREAD_MARGIN_TRUST_BPS": "80", "SPREAD_MARGIN_REGION": "1"},
    "ramp": {"SPREAD_MARGIN_RAMP": "1", "SPREAD_MARGIN_TRUST_BPS": "0", "SPREAD_MARGIN_REGION": "0"},
    "price": {"SPREAD_MARGIN_RAMP": "0", "SPREAD_MARGIN_TRUST_BPS": "80", "SPREAD_MARGIN_REGION": "1"},
    "trust": {"SPREAD_MARGIN_RAMP": "0", "SPREAD_MARGIN_TRUST_BPS": "80", "SPREAD_MARGIN_REGION": "0"},
    "region": {"SPREAD_MARGIN_RAMP": "0", "SPREAD_MARGIN_TRUST_BPS": "0", "SPREAD_MARGIN_REGION": "1"},
    "vol": {"SPREAD_MARGIN_RAMP": "1", "SPREAD_MARGIN_TRUST_BPS": "80", "SPREAD_MARGIN_REGION": "0",
            "SPREAD_MARGIN_FLOOR": "240", "SPREAD_MARGIN_BACKLOG": "0", "SPREAD_ADMISSION_EXTRA_SLACK": "0"},
    "tr": {"SPREAD_MARGIN_RAMP": "1", "SPREAD_MARGIN_TRUST_BPS": "80", "SPREAD_MARGIN_REGION": "0"},
    "vol360": {"SPREAD_MARGIN_RAMP": "1", "SPREAD_MARGIN_TRUST_BPS": "80", "SPREAD_MARGIN_REGION": "0",
               "SPREAD_MARGIN_FLOOR": "360", "SPREAD_MARGIN_BACKLOG": "1", "SPREAD_ADMISSION_EXTRA_SLACK": "120"},
    "fee85": {"SPREAD_MARGIN_RAMP": "1", "SPREAD_MARGIN_TRUST_BPS": "80", "SPREAD_MARGIN_REGION": "0",
              "SPREAD_MARGIN_FEE_PCT": "85"},
    "vol_fee85": {"SPREAD_MARGIN_RAMP": "1", "SPREAD_MARGIN_TRUST_BPS": "80", "SPREAD_MARGIN_REGION": "0",
                  "SPREAD_MARGIN_FLOOR": "240", "SPREAD_MARGIN_BACKLOG": "0", "SPREAD_ADMISSION_EXTRA_SLACK": "0",
                  "SPREAD_MARGIN_FEE_PCT": "85"},
    "vol120": {"SPREAD_MARGIN_RAMP": "1", "SPREAD_MARGIN_TRUST_BPS": "80", "SPREAD_MARGIN_REGION": "0",
               "SPREAD_MARGIN_FLOOR": "120", "SPREAD_MARGIN_BACKLOG": "0", "SPREAD_ADMISSION_EXTRA_SLACK": "0"},
    "vol120_fee85": {"SPREAD_MARGIN_RAMP": "1", "SPREAD_MARGIN_TRUST_BPS": "80", "SPREAD_MARGIN_REGION": "0",
                     "SPREAD_MARGIN_FLOOR": "120", "SPREAD_MARGIN_BACKLOG": "0", "SPREAD_ADMISSION_EXTRA_SLACK": "0",
                     "SPREAD_MARGIN_FEE_PCT": "85"},
    "adapt": {"SPREAD_MARGIN_RAMP": "1", "SPREAD_MARGIN_TRUST_BPS": "80", "SPREAD_MARGIN_REGION": "0",
              "SPREAD_MARGIN_ADAPT": "1"},
    "adapt_fee85": {"SPREAD_MARGIN_RAMP": "1", "SPREAD_MARGIN_TRUST_BPS": "80", "SPREAD_MARGIN_REGION": "0",
                    "SPREAD_MARGIN_ADAPT": "1", "SPREAD_MARGIN_FEE_PCT": "85"},
    "v360t100": {"SPREAD_MARGIN_RAMP": "1", "SPREAD_MARGIN_TRUST_BPS": "100", "SPREAD_MARGIN_REGION": "0",
                 "SPREAD_MARGIN_FLOOR": "360", "SPREAD_MARGIN_BACKLOG": "1", "SPREAD_ADMISSION_EXTRA_SLACK": "120"},
    "v360wk": {"SPREAD_MARGIN_RAMP": "1", "SPREAD_MARGIN_TRUST_BPS": "80", "SPREAD_MARGIN_REGION": "0",
               "SPREAD_MARGIN_FLOOR": "360", "SPREAD_MARGIN_BACKLOG": "1", "SPREAD_ADMISSION_EXTRA_SLACK": "120",
               "SPREAD_MARGIN_RAMP_WEEKEND": "1"},
    "v360multi": {"SPREAD_MARGIN_RAMP": "1", "SPREAD_MARGIN_TRUST_BPS": "80", "SPREAD_MARGIN_REGION": "0",
                  "SPREAD_MARGIN_FLOOR": "360", "SPREAD_MARGIN_BACKLOG": "1", "SPREAD_ADMISSION_EXTRA_SLACK": "120",
                  "SPREAD_MARGIN_MULTI": "1"},
    "vol_cheap": {"SPREAD_MARGIN_RAMP": "1", "SPREAD_MARGIN_TRUST_BPS": "80", "SPREAD_MARGIN_REGION": "0",
                  "SPREAD_MARGIN_FLOOR": "240", "SPREAD_MARGIN_BACKLOG": "0", "SPREAD_ADMISSION_EXTRA_SLACK": "0",
                  "SPREAD_MARGIN_BASE_BPS": "13200"},
}
_V360 = POLICIES["vol360"]
POLICIES.update({
    # Runtime switch controller (normal = vol360, tight 480/240, loose 240/0 Wed..Fri 12:00).
    "switch": {**_V360, "SPREAD_MARGIN_SWITCH": "1"},
    # The weekend is not slack: subtract Sat..Mon 07:00 and require 240 min more.
    "v360wk240": {**_V360, "SPREAD_MARGIN_WEEKEND_EXTRA": "240"},
    "switch_wk": {**_V360, "SPREAD_MARGIN_SWITCH": "1", "SPREAD_MARGIN_WEEKEND_EXTRA": "240"},
    # Typed-decision model rules on borderline requests (vol360 refused, loose floor passed).
    "ai_jev": {**_V360, "SPREAD_MARGIN_AI": "jev"},
    "ai_openai": {**_V360, "SPREAD_MARGIN_AI": "openai"},
    "v360wk480": {**_V360, "SPREAD_MARGIN_WEEKEND_EXTRA": "480"},
    # Subtract the weekend from slack, no extra buffer beyond the normal gates.
    "wk_sub": {**_V360, "SPREAD_MARGIN_WEEKEND_EXTRA": "1"},
    "switch_wk_t96": {**_V360, "SPREAD_MARGIN_SWITCH": "1", "SPREAD_MARGIN_WEEKEND_EXTRA": "240",
                      "SPREAD_MARGIN_SWITCH_TIGHT_SHARE": "0.96"},
    # The typed model may refuse gate-passing orders whose window spans the weekend.
    "risk_jev": {**_V360, "SPREAD_MARGIN_AI_RISK": "jev", "SPREAD_MARGIN_AI_MAX": "900",
                 "SPREAD_MARGIN_AI_ACCEPT": "0.5"},
    "risk_openai": {**_V360, "SPREAD_MARGIN_AI_RISK": "openai", "SPREAD_MARGIN_AI_MAX": "900",
                    "SPREAD_MARGIN_AI_ACCEPT": "0.5"},
})

# Grid around the weekend gate: slack floor x next-day buffer x weekend buffer (vol360 otherwise).
for _f in (300, 360):
    for _n in (120, 240):
        for _w in (240, 480):
            POLICIES[f"g{_f}n{_n}w{_w}"] = {**_V360, "SPREAD_MARGIN_FLOOR": str(_f),
                                             "SPREAD_ADMISSION_EXTRA_SLACK": str(_n),
                                             "SPREAD_MARGIN_WEEKEND_EXTRA": str(_w)}
for _w in (240, 480):
    POLICIES[f"g360n120w{_w}nd"] = {**_V360, "SPREAD_MARGIN_WEEKEND_EXTRA": str(_w),
                                    "SPREAD_MARGIN_WEEKEND_KINDS": "next_day"}
# Weekend gate only while the world's service is under pressure.
POLICIES["wkp96"] = {**_V360, "SPREAD_MARGIN_WEEKEND_EXTRA": "240", "SPREAD_MARGIN_WEEKEND_IF_BELOW": "0.96"}
POLICIES["wkp975"] = {**_V360, "SPREAD_MARGIN_WEEKEND_EXTRA": "240", "SPREAD_MARGIN_WEEKEND_IF_BELOW": "0.975"}
POLICIES["wkp96w6"] = {**_V360, "SPREAD_MARGIN_WEEKEND_EXTRA": "240", "SPREAD_MARGIN_WEEKEND_IF_BELOW": "0.96",
                       "SPREAD_MARGIN_WEEKEND_WARN_ABOVE": "0.06"}
# Guard: weekend gate + tight mode under service pressure, never loose.
POLICIES["guard_wk"] = {**_V360, "SPREAD_MARGIN_SWITCH": "1", "SPREAD_MARGIN_SWITCH_LOOSE": "0",
                        "SPREAD_MARGIN_WEEKEND_EXTRA": "240"}

def main() -> None:
    seed, policy = sys.argv[1], sys.argv[2]
    cfg = dict(POLICIES[policy])
    cls = cfg.pop("cls", "margin")
    if cls != "frozen":
        os.environ["SPREAD_ADMISSION_PRICE_PCT"] = "139"
        os.environ["SPREAD_ADMISSION_EXTRA_SLACK"] = cfg.pop("SPREAD_ADMISSION_EXTRA_SLACK", "240")
        # Policies written before the vol360 freeze relied on these older defaults.
        cfg.setdefault("SPREAD_MARGIN_FLOOR", "480")
        cfg.setdefault("SPREAD_MARGIN_REGION", "1")
        os.environ.update(cfg)
    else:
        for key in [k for k in os.environ if k.startswith(("SPREAD_MARGIN_", "SPREAD_ADMISSION_"))]:
            del os.environ[key]
    from spread import starter
    from spread.client import Client  # type: ignore
    if cls == "admission":
        from admission_experiment import AdmissionDesk as Desk
    else:
        from margin_experiment import MarginDesk as Desk
    starter.Desk = Desk
    client = Client()
    world = client.create(level=8, seed=seed, board=False)
    t0 = time.time()
    try:
        starter.play_practice(world, 8)
    except BaseException:
        try:
            world.delete()
        except Exception:  # noqa: BLE001
            pass
        raise
    score = world.score()
    print("RESULT " + json.dumps({"seed": seed, "policy": policy, "world": world.id,
                                  "elapsed": round(time.time() - t0, 1), **score}), flush=True)


if __name__ == "__main__":
    main()
