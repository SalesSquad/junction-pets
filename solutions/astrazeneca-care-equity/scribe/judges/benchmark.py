"""Planted-error benchmark of the two judges.

  benchmark.py build     pick 300 notes, write the 600 pairs
  benchmark.py run       ask Jev on all pairs and Decisions on the pairs its token budget allows
  benchmark.py analyse   thresholds and rule on the calibration half, numbers on the report half

Everything written here is computed from the answers on disk; nothing is estimated.
"""

import argparse
import itertools
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import core  # noqa: E402
import corrupt  # noqa: E402
import run as runner  # noqa: E402

TRAIN = core.ROOT / "data/scribe/v2/dataset/train.parquet"
PAIRS = core.OUT / "pairs-v1.jsonl"
ANSWERS = core.OUT / "answers-v1.jsonl"
RESULT = core.OUT / "benchmark-v1.json"
RESULTS_MD = Path(__file__).resolve().parent / "RESULTS.md"
PER_WRITER = 150
WRITERS = {"nemotron": "nemotron-3.5-super-vl", "haiku": "claude-haiku-5-5"}
# Decisions is asked only for the first DECISIONS_PER_STRATUM notes (hash order) of each of the four
# (half, writer) strata: the OpenAI allowance of 500,000 tokens does not cover 600 requests of about
# 1,200 tokens each (measured on the probe request).
DECISIONS_PER_STRATUM = 40


def rel(p):
    return str(Path(p).relative_to(core.ROOT))


# ---- build --------------------------------------------------------------------------------------


def select_notes(rows):
    """150 per writer by hash of the id; first 75 of each (second hash) are the calibration half."""
    out = []
    for name, writer in WRITERS.items():
        pool = [
            r
            for r in rows
            if r["accepted"] and r["writer"] == writer and r["kind"] != "no_event" and corrupt.eligible(r)
        ]
        pool.sort(key=lambda r: corrupt.h("judges-bench-v1", r["id"]))
        chosen = sorted(pool[:PER_WRITER], key=lambda r: corrupt.h("judges-split-v1", r["id"]))
        for i, r in enumerate(chosen):
            half = "calibration" if i < PER_WRITER // 2 else "report"
            out.append(dict(r, writer_short=name, half=half, pool_size=len(pool)))
    return out


def make_pairs(notes):
    pairs = []
    strata = sorted({(n["half"], n["writer_short"]) for n in notes})
    for s, (half, writer) in enumerate(strata):
        group = [n for n in notes if (n["half"], n["writer_short"]) == (half, writer)]
        group.sort(key=lambda n: corrupt.h("judges-kind-v1", n["id"]))
        for i, n in enumerate(group):
            kind = corrupt.KINDS[(i + 3 * (s % 2)) % len(corrupt.KINDS)]  # offset balances 75 = 6*12 + 3
            claim = dict(
                entry_route=n["entry_route"],
                events=[dict(type=e["type"], date=e["date"], precision=e["precision"]) for e in n["events"]],
            )
            bad, change = corrupt.corrupt(kind, claim, n["note_date"], n["id"])
            common = dict(
                note_id=n["id"],
                writer=writer,
                half=half,
                kind=kind,
                decisions_subset=i < DECISIONS_PER_STRATUM,
                note_date=n["note_date"],
                note_text=n["note_text"],
            )
            pairs.append(dict(id=n["id"] + ":clean", label="clean", change=None, **common, **claim))
            pairs.append(dict(id=n["id"] + ":" + kind, label="corrupted", change=change, **common, **bad))
    return pairs


def build(_):
    import pyarrow.parquet as pq

    rows = pq.read_table(TRAIN).to_pylist()
    notes = select_notes(rows)
    pairs = make_pairs(notes)
    PAIRS.parent.mkdir(parents=True, exist_ok=True)
    PAIRS.write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in pairs))
    count = lambda f: {str(k): v for k, v in sorted(_counter(f(p) for p in pairs).items())}  # noqa: E731
    metrics = dict(
        notes=len(notes),
        pairs=len(pairs),
        eligible_pool={w: next(n["pool_size"] for n in notes if n["writer_short"] == w) for w in WRITERS},
        by_label=count(lambda p: p["label"]),
        by_half_writer=count(lambda p: (p["half"], p["writer"])),
        corrupted_by_kind=count(lambda p: p["kind"] if p["label"] == "corrupted" else "(clean)"),
        decisions_subset_pairs=sum(p["decisions_subset"] for p in pairs),
    )
    core.log("benchmark_build", inputs=[rel(TRAIN)], outputs=[rel(PAIRS)], metrics=metrics, cost_usd=0, status="ok")
    print(json.dumps(metrics, ensure_ascii=False, indent=1))


def _counter(it):
    c = {}
    for x in it:
        c[x] = c.get(x, 0) + 1
    return c


# ---- run ----------------------------------------------------------------------------------------


def run(a):
    import asyncio
    import time

    pairs = runner.read_jsonl(PAIRS)
    done = {r["id"]: r.get("judges", {}) for r in runner.read_jsonl(ANSWERS)}
    t = time.monotonic()

    async def main():
        J = core.Judges(max_usd_typesafe=a.max_usd_typesafe, max_tokens_openai=a.max_tokens_openai)
        with ANSWERS.open("a") as f:

            def on_row(ident, results):
                f.write(json.dumps({"id": ident, "judges": results}, ensure_ascii=False) + "\n")
                f.flush()

            ans = await runner.judge_rows(pairs, ("jev", "jev_hint"), J, done, on_row)
            sub = [p for p in pairs if p["decisions_subset"]]
            ans.update(await runner.judge_rows(sub, ("decisions",), J, ans, on_row))
        return J, ans

    J, ans = asyncio.run(main())
    tmp = ANSWERS.with_suffix(".jsonl.tmp")
    tmp.write_text("".join(json.dumps({"id": p["id"], "judges": ans[p["id"]]}, ensure_ascii=False) + "\n" for p in pairs))
    tmp.replace(ANSWERS)
    metrics = dict(
        pairs=len(pairs),
        stats=J.stats,
        jev_answered=sum(not ans[p["id"]].get("jev", {}).get("error", True) for p in pairs),
        jev_hint_answered=sum(not ans[p["id"]].get("jev_hint", {}).get("error", True) for p in pairs),
        decisions_answered=sum("decisions" in ans[p["id"]] and not ans[p["id"]]["decisions"].get("error") for p in pairs),
        ledger={k: v.d for k, v in J.ledger.items()},
        seconds=round(time.monotonic() - t, 1),
    )
    core.log(
        "benchmark_run",
        inputs=[rel(PAIRS)],
        outputs=[rel(ANSWERS), rel(core.OUT / "usage-typesafe.json"), rel(core.OUT / "usage-openai.json")],
        metrics=metrics,
        cost_usd=J.ledger["jev"].d.get("cost_usd"),
        status="ok" if not (J.stats["jev"]["errors"] or J.stats["decisions"]["errors"]) else "partial",
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    r = sub.add_parser("run")
    r.add_argument("--max-usd-typesafe", type=float, default=2.0)
    r.add_argument("--max-tokens-openai", type=int, default=500_000)
    sub.add_parser("analyse")
    a = ap.parse_args()
    if a.cmd == "analyse":
        import analysis

        analysis.main()
    else:
        {"build": build, "run": run}[a.cmd](a)
