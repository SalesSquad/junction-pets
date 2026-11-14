"""Judge (note, claimed answer) pairs with Jev and/or Decisions.

  scribe/.venv/bin/python scribe/judges/run.py --in pairs.jsonl --out answers.jsonl
      [--judges jev,decisions] [--max-usd-typesafe X] [--max-tokens-openai N] [--policy path]

Input: one JSON object per line with id, note_text, note_date, entry_route, events
       (events: [{type, date "YYYY-MM-DD", precision "DAY"|"MONTH"}]).
Output: one JSON object per id, in input order:
          {"id", "judges": {"jev": R, "decisions": R}, "rule", "pass", "judge_pass": {"jev": bool, "decisions": bool}}
        R = {"judge", "model", "question_set", "request_sha256", "n_events", "claimed_route", "error",
             "probabilities": {"event_0".."event_<n-1>", "unlisted", "route"}, "route_choice", "route_distribution",
             "usage": {"input_tokens", "output_tokens"}, "latency_s", "cached"}
        probabilities.route is the probability of the CLAIMED route. On an error (NOT_CONFIGURED, BUDGET_STOP, HTTP,
        refusal, malformed answer) "error" is a string and "probabilities" is {}; such a row never passes.
        "rule" and "pass" come from data/scribe/v3/judges/policy.json (null when that file is missing). The policy
        also sets the Jev question set: "v2" adds the day offset computed by code to each DAY-precision date.
Resumable: ids already answered in --out are not asked again, and every request goes through the disk cache.
Keys come from the environment (TYPESAFE_API_KEY, OPENAI_API_KEY); a missing key gives error NOT_CONFIGURED.
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import core  # noqa: E402

JUDGES = ("jev", "decisions")


def read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass  # a line cut off by an interrupted run is asked again
    return rows


def claim_events(row):
    return [dict(type=e["type"], date=e["date"], precision=e.get("precision") or "DAY") for e in row["events"]]


def verdict(results, policy):
    """Pass/fail of the recommended rule; None when there is no policy file yet."""
    if not policy:
        return dict(rule=None, passed=None, judge_pass={})
    th = policy["thresholds"]
    return {
        "rule": policy["rule"],
        "passed": core.rule_pass(policy["rule"], results, th),
        "judge_pass": {j: core.judge_pass(results.get(j), th.get(j)) for j in JUDGES if j in results},
    }


def output_row(ident, results, policy):
    v = verdict(results, policy)
    return {"id": ident, "judges": results, "rule": v["rule"], "pass": v["passed"], "judge_pass": v["judge_pass"]}


async def judge_rows(rows, judges, J, done=None, on_row=None, jev_question_set="v1"):
    """{id: {judge: result}}; `done` holds earlier answers, only missing or failed ones are asked.
    jev_question_set 'v2' (from the policy) asks Jev with the day-offset questions; the answer stays under 'jev'."""
    done = done or {}

    async def one(row):
        results = dict(done.get(row["id"], {}))
        events = claim_events(row)
        for j in judges:
            want = jev_question_set if j == "jev" else "v1"
            if j in results and not results[j].get("error") and results[j].get("question_set", "v1") == want:
                continue
            method = "jev_hint" if (j == "jev" and want == "v2") else j
            results[j] = await getattr(J, method)(row["note_text"], row["note_date"], row["entry_route"], events)
        if on_row:
            on_row(row["id"], results)
        return row["id"], results

    return dict(await asyncio.gather(*(one(r) for r in rows)))


def run_file(inp, out, judges=JUDGES, max_usd_typesafe=2.0, max_tokens_openai=500_000, policy_path=core.POLICY, J=None):
    rows = read_jsonl(inp)
    ids = [r["id"] for r in rows]
    if len(set(ids)) != len(ids):
        raise SystemExit("duplicate ids in input")
    policy = core.load_policy(policy_path)
    done = {r["id"]: r.get("judges", {}) for r in read_jsonl(out) if r.get("id") in set(ids)}  # later lines win
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    t = time.monotonic()
    start = {}

    async def main():
        jj = J or core.Judges(max_usd_typesafe=max_usd_typesafe, max_tokens_openai=max_tokens_openai)
        start.update({j: jj.ledger[j].d["tokens"] for j in JUDGES})
        with out.open("a") as f:

            def on_row(ident, results):  # progress survives an interruption
                f.write(json.dumps(output_row(ident, results, policy), ensure_ascii=False) + "\n")
                f.flush()

            return jj, await judge_rows(rows, judges, jj, done, on_row, (policy or {}).get("jev_question_set", "v1"))

    jj, answers = asyncio.run(main())
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text("".join(json.dumps(output_row(i, answers[i], policy), ensure_ascii=False) + "\n" for i in ids))
    tmp.replace(out)
    summary = dict(
        rows=len(rows),
        judges=list(judges),
        rule=policy["rule"] if policy else None,
        passed=sum(bool(output_row(i, answers[i], policy)["pass"]) for i in ids) if policy else None,
        errors={j: sum(bool(answers[i].get(j, {}).get("error")) for i in ids) for j in judges},
        stats=jj.stats,
        tokens_this_run={j: jj.ledger[j].d["tokens"] - start[j] for j in judges},
        ledger={j: jj.ledger[j].d for j in judges},
        seconds=round(time.monotonic() - t, 1),
    )
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--judges", default="jev,decisions")
    ap.add_argument("--max-usd-typesafe", type=float, default=2.0)
    ap.add_argument("--max-tokens-openai", type=int, default=500_000)
    ap.add_argument("--policy", default=str(core.POLICY))
    a = ap.parse_args()
    judges = tuple(j for j in a.judges.split(",") if j)
    if not judges or any(j not in JUDGES for j in judges):
        raise SystemExit("--judges takes jev, decisions or both")
    s = run_file(a.inp, a.out, judges, a.max_usd_typesafe, a.max_tokens_openai, a.policy)
    core.log(
        "run",
        inputs=[a.inp],
        outputs=[a.out],
        metrics=s,
        cost_usd=s["tokens_this_run"].get("jev", 0) * core.TYPESAFE_USD_PER_TOKEN,  # TypeSafe only; OpenAI is counted in tokens
        status="ok" if not any(s["errors"].values()) else "partial",
    )
    print(json.dumps(s, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
