#!/usr/bin/env python3
"""Start the live final with one named policy from run_pair.POLICIES, or check it offline.

    python final_launcher.py guard_wk --check                       # no network, prints the config
    python final_launcher.py guard_wk --final --i-have-owner-approval

Only one process may ever play the final. The final is never started without the
owner's explicit approval; the flag records that the operator has it. Policies with
an external typed-decision call (SPREAD_MARGIN_AI*) are refused for the final.
"""
from __future__ import annotations

import os
import sys

from run_pair import POLICIES

KEYS = ("SPREAD_ADMISSION_PRICE_PCT", "SPREAD_ADMISSION_EXTRA_SLACK", "SPREAD_MARGIN_FLOOR",
        "SPREAD_MARGIN_BACKLOG", "SPREAD_MARGIN_RAMP", "SPREAD_MARGIN_TRUST_BPS", "SPREAD_MARGIN_REGION",
        "SPREAD_MARGIN_WEEKEND_EXTRA", "SPREAD_MARGIN_SWITCH", "SPREAD_MARGIN_SWITCH_LOOSE")


def apply(policy: str) -> dict[str, str]:
    cfg = dict(POLICIES[policy])
    if cfg.pop("cls", "margin") != "margin":
        raise SystemExit(f"{policy}: not a MarginDesk policy")
    if any(k.startswith("SPREAD_MARGIN_AI") for k in cfg):
        raise SystemExit(f"{policy}: typed-decision gates are practice-only")
    for key in [k for k in os.environ if k.startswith(("SPREAD_MARGIN_", "SPREAD_ADMISSION_"))]:
        del os.environ[key]
    os.environ["SPREAD_ADMISSION_PRICE_PCT"] = "139"
    os.environ["SPREAD_ADMISSION_EXTRA_SLACK"] = cfg.pop("SPREAD_ADMISSION_EXTRA_SLACK", "240")
    cfg.setdefault("SPREAD_MARGIN_FLOOR", "480")
    cfg.setdefault("SPREAD_MARGIN_REGION", "1")
    os.environ.update(cfg)
    return {k: os.environ.get(k, "(default)") for k in KEYS}


def main() -> None:
    policy, args = sys.argv[1], sys.argv[2:]
    resolved = apply(policy)
    for key, value in resolved.items():
        print(f"{key}={value}")
    if "--check" in args:
        from margin_experiment import MarginDesk  # import check only
        print(f"CHECK_OK {policy} -> {MarginDesk.__name__}")
        return
    if "--final" not in args or "--i-have-owner-approval" not in args:
        raise SystemExit("refused: --final needs --i-have-owner-approval (owner decision)")
    from spread import starter
    from margin_experiment import MarginDesk
    starter.Desk = MarginDesk
    sys.argv = [sys.argv[0], "--final"]
    starter.main()


if __name__ == "__main__":
    main()
