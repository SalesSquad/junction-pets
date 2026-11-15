"""Gate of teaching round 2: judge the Nemotron candidates that passed the code check.

  scribe/.venv/bin/python scribe/v3/gate.py prepare
  scribe/.venv/bin/python scribe/v3/gate.py judge --judges jev [--limit N] [--name jev]
  scribe/.venv/bin/python scribe/v3/gate.py judge --judges jev,decisions --limit N --name decisions --openai-step-tokens 600000
  scribe/.venv/bin/python scribe/v3/gate.py report

prepare  writes data/scribe/v3/gate/input.jsonl: the candidates whose kept note passed the code check, in the
         fixed order of SHA-256("scribe-v3-gate|" + id), and a snapshot of the judges' token ledgers.
judge    runs scribe/judges/run.py (unchanged) on the first N rows of that order. Keys come from the
         environment; they are never printed. The OpenAI limit is the ledger at `prepare` plus the step allowance.
report   writes judged.jsonl (one row per judged candidate) and gate-v1.json.

All text is SYNTHETIC. Nothing here is for clinical use.
"""

import argparse
import collections
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    CANDIDATES,
    CURRICULA,
    GATE,
    JUDGES_DIR,
    POLICY,
    ROOT,
    frac,
    log,
    now,
    order_key,
    read_jsonl,
    save_json,
    sha256_file,
    write_jsonl,
)

SALT = "scribe-v3-gate"
INPUT = GATE / "input.jsonl"
LEDGER_START = GATE / "ledger-start.json"
TYPESAFE_USD_PER_TOKEN = 0.042 / 1e6  # the same price as scribe/judges/core.py
# gpt-6-luna on the Decisions API: "uncached input costs $0.10 per 1M tokens", "Output tokens are not charged"
# (https://developers.openai.com/api/docs/guides/decisions, opened 2026-11-14 through a summarising fetch).
# Cache discounts, regional premiums and long-context multipliers are not applied: a list-rate figure, not a bill.
OPENAI_USD_PER_INPUT_TOKEN_UNCACHED = 0.10 / 1e6
JUDGES = ("jev", "decisions")


def ledgers():
    out = {}
    for name, f in (("jev", "usage-typesafe.json"), ("decisions", "usage-openai.json")):
        p = JUDGES_DIR / f
        out[name] = json.loads(p.read_text()) if p.exists() else None
    return out


def prepare(_):
    rows = read_jsonl(CANDIDATES)
    ids = [r["id"] for r in rows]
    assert len(set(ids)) == len(ids), "duplicate candidate ids"
    passed = [r for r in rows if r["code_check"]["passed"]]
    passed.sort(key=lambda r: order_key(r["id"], SALT))
    write_jsonl(
        INPUT,
        [
            dict(
                id=r["id"],
                order=i,
                curriculum=r["curriculum"],
                note_text=r["note_text"],
                note_date=r["note_date"],
                entry_route=r["entry_route"],
                events=[dict(type=e["type"], date=e["date"], precision=e["precision"]) for e in r["events"]],
            )
            for i, r in enumerate(passed)
        ],
    )
    if not LEDGER_START.exists():
        save_json(LEDGER_START, dict(taken=now(), ledgers=ledgers()))
    m = dict(candidates=len(rows), code_check_pass=len(passed), candidates_sha256=sha256_file(CANDIDATES))
    log("prepare", inputs=[str(CANDIDATES.relative_to(ROOT))], outputs=[str(INPUT.relative_to(ROOT))], metrics=m, cost_usd=0, status="ok")
    print(json.dumps(m))


def judge(a):
    rows = read_jsonl(INPUT)
    part = rows[a.offset : (a.offset + a.limit) if a.limit else None]
    inp = GATE / f"in-{a.name}.jsonl"
    out = GATE / f"out-{a.name}.jsonl"
    # the same ids must stay in the file across calls, because run.py rewrites --out with exactly the input ids
    old = read_jsonl(inp) if inp.exists() else []
    have = {r["id"] for r in old}
    merged = old + [r for r in part if r["id"] not in have]
    write_jsonl(inp, merged)
    start = json.loads(LEDGER_START.read_text())["ledgers"]
    before = ledgers()
    cmd = [sys.executable, str(ROOT / "scribe/judges/run.py"), "--in", str(inp), "--out", str(out), "--judges", a.judges]
    cmd += ["--max-usd-typesafe", str(a.max_usd_typesafe)]
    openai_limit = (start["decisions"] or {}).get("tokens", 0) + a.openai_step_tokens
    cmd += ["--max-tokens-openai", str(openai_limit)]
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    after = ledgers()
    try:
        summary = json.loads(p.stdout)
    except json.JSONDecodeError:
        summary = None
    used = {j: (after[j] or {}).get("tokens", 0) - (before[j] or {}).get("tokens", 0) for j in JUDGES}
    m = dict(
        rows_in_file=len(merged),
        rows_added=len(merged) - len(old),
        judges=a.judges.split(","),
        openai_cumulative_limit=openai_limit,
        tokens_this_call=used,
        summary=None
        if summary is None
        else {k: summary[k] for k in ("rows", "rule", "passed", "errors", "stats", "tokens_this_run", "seconds")},
        returncode=p.returncode,
        stderr_tail=p.stderr[-400:] if p.returncode else "",
    )
    log(
        "judge:" + a.name,
        command=" ".join(cmd[1:]).replace(str(ROOT) + "/", ""),
        inputs=[str(inp.relative_to(ROOT))],
        outputs=[str(out.relative_to(ROOT))],
        metrics=m,
        cost_usd=used["jev"] * TYPESAFE_USD_PER_TOKEN,  # TypeSafe only; OpenAI is counted in tokens here
        status="ok" if p.returncode == 0 and summary and not any(summary["errors"].values()) else "partial",
    )
    print(json.dumps(m, indent=1))


def table_2x2(rows):
    """Read-back consistency against the rule's verdict, over the rows the rule judged."""
    t = collections.Counter((bool(r["readback_consistent"]), bool(r["pass"])) for r in rows if r["pass"] is not None)
    return dict(
        readback_consistent_rule_accept=t[(True, True)],
        readback_consistent_rule_reject=t[(True, False)],
        readback_inconsistent_rule_accept=t[(False, True)],
        readback_inconsistent_rule_reject=t[(False, False)],
        n=sum(t.values()),
    )


def usage(rows, judge_name):
    rs = [r["judges"][judge_name] for r in rows if judge_name in r["judges"] and not r["judges"][judge_name].get("error")]
    return dict(
        answered=len(rs),
        input_tokens=sum(r["usage"]["input_tokens"] for r in rs),
        output_tokens=sum(r["usage"]["output_tokens"] for r in rs),
        tokens=sum(r["usage"]["input_tokens"] + r["usage"]["output_tokens"] for r in rs),
    )


def block(cands, judged):
    """Counts of one curriculum (or of all): candidates, code check, read-back, each judge, the rule."""
    cc = [c for c in cands if c["code_check"]["passed"]]
    j = [judged[c["id"]] for c in cc if c["id"] in judged]
    out = dict(
        candidates=len(cands),
        code_check_pass=frac(len(cc), len(cands)),
        readback_consistent=frac(sum(c["readback"]["consistent"] is True for c in cc), len(cc)),
    )
    for name in JUDGES:
        asked = [r for r in j if name in r["judges"]]
        ok = [r for r in asked if not r["judges"][name].get("error")]
        out[name] = dict(
            asked=len(asked),
            answered=len(ok),
            errors=len(asked) - len(ok),
            accepted=frac(sum(bool(r["judge_pass"].get(name)) for r in ok), len(ok)),
        )
    ruled = [r for r in j if r["pass"] is not None]
    out["rule"] = dict(
        judged=len(ruled),
        not_judged=len(cc) - len(ruled),
        accepted_of_judged=frac(sum(bool(r["pass"]) for r in ruled), len(ruled)),
        accepted_of_candidates=frac(sum(bool(r["pass"]) for r in ruled), len(cands)),
    )
    out["readback_vs_rule"] = table_2x2(j)
    both = [r for r in j if all(n in r["judges"] and not r["judges"][n].get("error") for n in JUDGES)]
    t = collections.Counter((bool(r["judge_pass"]["jev"]), bool(r["judge_pass"]["decisions"])) for r in both)
    out["jev_vs_decisions"] = dict(
        both_accept=t[(True, True)],
        jev_accept_decisions_reject=t[(True, False)],
        jev_reject_decisions_accept=t[(False, True)],
        both_reject=t[(False, False)],
        n=len(both),
    )
    return out


def report(_):
    policy = json.loads(POLICY.read_text())
    cands = read_jsonl(CANDIDATES)
    by_id = {c["id"]: c for c in cands}
    order = read_jsonl(INPUT)
    results = collections.defaultdict(dict)
    for f in sorted(GATE.glob("out-*.jsonl")):
        for r in read_jsonl(f):
            for name, res in r["judges"].items():
                old = results[r["id"]].get(name)
                if old is None or (old.get("error") and not res.get("error")):
                    results[r["id"]][name] = res
    sys.path.insert(0, str(ROOT / "scribe/judges"))
    import core  # the unchanged pass definition

    th = policy["thresholds"]
    judged = {}
    for o in order:
        res = results.get(o["id"])
        if not res:
            continue
        c = by_id[o["id"]]
        jev = res.get("jev")
        rule_answered = policy["rule"] == "jev" and jev is not None and not jev.get("error")
        if rule_answered:
            assert jev["question_set"] == policy["jev_question_set"], "Jev was asked with another question set"
        judged[o["id"]] = dict(
            id=o["id"],
            order=o["order"],
            curriculum=c["curriculum"],
            kind=c["kind"],
            n_events=len(c["events"]),
            readback_consistent=c["readback"]["consistent"],
            repaired=c["repaired"],
            rule=policy["rule"],
            **{"pass": core.rule_pass(policy["rule"], res, th) if rule_answered else None},
            judge_pass={n: core.judge_pass(res.get(n), th.get(n)) for n in JUDGES if n in res},
            judges=res,
        )
    rows = [judged[o["id"]] for o in order if o["id"] in judged]
    write_jsonl(GATE / "judged.jsonl", rows)

    start = json.loads(LEDGER_START.read_text())
    end = ledgers()
    tokens = {}
    for name in JUDGES:
        u = usage(rows, name)
        s, e = start["ledgers"][name] or {}, end[name] or {}
        u["ledger_tokens_at_step_start"] = s.get("tokens", 0)
        u["ledger_tokens_now"] = e.get("tokens", 0)
        u["ledger_tokens_this_step"] = e.get("tokens", 0) - s.get("tokens", 0)
        u["ledger_requests_this_step"] = e.get("requests", 0) - s.get("requests", 0)
        u["ledger_failed_attempts_this_step"] = e.get("failed_attempts", 0) - s.get("failed_attempts", 0)
        # a failed attempt keeps its reservation in the ledger because it may have been billed
        u["ledger_tokens_reserved_for_failed_attempts_this_step"] = e.get("reserved_tokens", 0) - s.get("reserved_tokens", 0)
        u["errors"] = collections.Counter(
            r["judges"][name]["error"] for r in rows if name in r["judges"] and r["judges"][name].get("error")
        )
        tokens[name] = u
    tokens["jev"]["usd_per_million_tokens"] = 0.042
    tokens["jev"]["usd_this_step"] = tokens["jev"]["ledger_tokens_this_step"] * TYPESAFE_USD_PER_TOKEN
    tokens["jev"]["usd_ledger_total"] = (end["jev"] or {}).get("cost_usd")
    tokens["decisions"]["usd_per_million_input_tokens_uncached"] = 0.10
    tokens["decisions"]["usd_this_step"] = tokens["decisions"]["ledger_tokens_this_step"] * OPENAI_USD_PER_INPUT_TOKEN_UNCACHED
    tokens["decisions"]["usd_note"] = (
        "list-rate figure, not a bill: ledger tokens of this step x USD 0.10 per million uncached input tokens "
        "(Decisions guide, opened 2026-11-14 through a summarising fetch; output tokens are not charged). Cache "
        "discounts, regional premiums and long-context multipliers are not applied, and the one refused request "
        "has no recorded usage (3,000 tokens stay reserved for it in the ledger)."
    )

    gate = dict(
        schemaVersion="scribe-gate-v1",
        generated=now(),
        synthetic=True,
        candidates_file=str(CANDIDATES.relative_to(ROOT)),
        candidates_sha256=sha256_file(CANDIDATES),
        policy=dict(
            file=str(POLICY.relative_to(ROOT)),
            sha256=sha256_file(POLICY),
            rule=policy["rule"],
            jev_question_set=policy["jev_question_set"],
            thresholds=policy["thresholds"],
        ),
        order="SHA-256('scribe-v3-gate|' + id), ascending, over the candidates that passed the code check",
        definitions=dict(
            code_check_pass="kept note passed the round-2 code check (teacher's flag code_check.passed)",
            readback_consistent="denominator = code-check passes; the teacher's blind read-back equals the answer key",
            judge_accepted="denominator = pairs the judge answered without an error",
            rule="accepted_of_judged: denominator = code-check passes the rule's judge answered; "
            "accepted_of_candidates: denominator = all candidates of the curriculum",
            readback_vs_rule="rows judged by the rule only",
            jev_vs_decisions="pairs answered by both judges; Decisions was asked for a prefix of the fixed order only",
        ),
        overall=block(cands, judged),
        per_curriculum={c: block([x for x in cands if x["curriculum"] == c], judged) for c in CURRICULA},
        tokens=tokens,
        caveats=[
            "The judges' benchmark (data/scribe/v3/judges/benchmark-v1.json) used notes with 2-8 events and no "
            "no_event, terse or long notes; the thresholds are not calibrated for those curricula.",
            "For a no_event note the rule reduces to: unlisted < unlisted_max and the chosen route equals the claimed one.",
            "Decisions is not part of the rule; it was asked with the v1 questions for the first rows of the fixed order.",
        ],
    )
    save_json(GATE / "gate-v1.json", gate)
    log(
        "report",
        inputs=[str(CANDIDATES.relative_to(ROOT)), "data/scribe/v3/gate/out-*.jsonl"],
        outputs=["data/scribe/v3/gate/judged.jsonl", "data/scribe/v3/gate/gate-v1.json"],
        metrics=dict(judged=len(rows), overall=gate["overall"]["rule"], tokens=tokens),
        cost_usd=tokens["jev"]["usd_this_step"],
        status="ok",
    )
    print(json.dumps(dict(overall=gate["overall"], tokens=tokens), indent=1))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("prepare").set_defaults(fn=prepare)
    j = sub.add_parser("judge")
    j.add_argument("--judges", required=True)
    j.add_argument("--name", required=True)
    j.add_argument("--offset", type=int, default=0)
    j.add_argument("--limit", type=int, default=0)
    j.add_argument("--max-usd-typesafe", type=float, default=2.0)
    j.add_argument("--openai-step-tokens", type=int, default=0)
    j.set_defaults(fn=judge)
    sub.add_parser("report").set_defaults(fn=report)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
