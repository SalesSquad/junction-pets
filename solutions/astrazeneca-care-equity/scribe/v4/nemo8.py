"""Step 8: the Nemotron 3.5 Super VL reader (Lane B's selected version v3) reads the frozen stress set once.

The protocol is imported unchanged from scribe/nemotron/reader.py (read_note, v3: expression format, local
validation, grounding check, one repair retry, enable_thinking on). Before the first request, `freeze` writes the
sha256 of the v3 system prompt, its configuration and the two source files to data/scribe/v4/eval/nemotron/
prompt-freeze-v1.json, as the preregistration asks. This lane keeps its own request ledger and request log in
data/scribe/v4/eval/nemotron/ (no prompt, no key) and stays at concurrency 6 (the endpoint is shared; cap 8).

Hosted endpoint, SYNTHETIC text only. Keys come from the process environment and are never logged or written:
    set -a; . ~/.config/verda-inference/env; set +a
    scribe/.venv/bin/python scribe/v4/nemo8.py freeze
    scribe/.venv/bin/python scribe/v4/nemo8.py run [--deadline HH:MM]
A person confirms every extracted event; the reader's answer is a proposal.
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import datetime as dt
import hashlib
import json
import pathlib
import socket
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "scribe" / "nemotron"))

import common as NC  # noqa: E402  scribe/nemotron/common.py
import reader as R  # noqa: E402  scribe/nemotron/reader.py

VERSION = "v3"
STRESS = ROOT / "data/scribe/stress/stress-v1.parquet"
STRESS_SHA256 = "ae16f7474a8734bbc108d5e2f5c66bce698cbd0e4c88f60ffd4b742908184dfa"
OUT = ROOT / "data/scribe/v4/eval/nemotron"
CACHE = OUT / "cache" / VERSION / "stress"
FREEZE = OUT / "prompt-freeze-v1.json"
RUNLOG = ROOT / "runs/laneA-step8.jsonl"
CONCURRENCY = 6
CAP = 1500  # request attempts this step may send (308 notes, at most 2 calls each, retries counted)

NC.REQUESTS = OUT / "requests.jsonl"  # this lane's own request log (no prompt, no key)


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha_file(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def log(step, command, inputs=None, outputs=None, metrics=None, cost_usd=None, status="ok"):
    RUNLOG.parent.mkdir(exist_ok=True)
    line = dict(ts=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), step=step, host=socket.gethostname(),
                command=command, inputs=inputs or {}, outputs=outputs or {}, metrics=metrics or {}, cost_usd=cost_usd,
                status=status)
    with RUNLOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def freeze_record():
    cfg = R.CONFIG[VERSION]
    return dict(
        version=VERSION,
        config=cfg,
        max_tokens=R.MAX_TOKENS_THINKING if cfg["thinking"] else R.MAX_TOKENS,
        system_prompt_sha256=sha(R.system_prompt(cfg["fmt"])),
        repair_template_sha256=sha(json.dumps(R.repair_messages({"note_date": "X", "note_text": "Y"}, cfg["fmt"], "Z", ["P"]), ensure_ascii=False)),
        files={"scribe/nemotron/reader.py": sha_file(ROOT / "scribe/nemotron/reader.py"),
               "scribe/nemotron/common.py": sha_file(ROOT / "scribe/nemotron/common.py")},
        selected_by="Lane B step 4 on validation (data/scribe/nemotron/reader-v1.json); not changed here",
    )


def cmd_freeze(_a):
    if FREEZE.exists():
        old = json.loads(FREEZE.read_text())
        now = freeze_record()
        same = {k: old[k] == now[k] for k in ("system_prompt_sha256", "repair_template_sha256", "files", "config")}
        print(json.dumps(dict(already_frozen=old["frozen_utc"], unchanged=same), indent=1))
        return 0 if all(same.values()) else 1
    rec = dict(freeze_record(), frozen_utc=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               note="written before any stress note was sent to the reader")
    NC.save(FREEZE, rec)
    log("nemotron-prompt-freeze", "scribe/.venv/bin/python scribe/v4/nemo8.py freeze", outputs={"file": str(FREEZE.relative_to(ROOT))},
        metrics={k: rec[k] for k in ("system_prompt_sha256", "repair_template_sha256", "files")}, cost_usd=0)
    print(json.dumps(rec, indent=1))
    return 0


async def run(deadline, command):
    if not FREEZE.exists():
        raise SystemExit("run `freeze` first")
    frozen = json.loads(FREEZE.read_text())
    now = freeze_record()
    if any(frozen[k] != now[k] for k in ("system_prompt_sha256", "repair_template_sha256", "files", "config")):
        raise SystemExit("the v3 reader changed after the freeze; refusing")
    if sha_file(STRESS) != STRESS_SHA256:
        raise SystemExit("stress-v1.parquet sha256 differs from the preregistration; refusing")
    import pyarrow.parquet as pq

    rows = pq.read_table(STRESS).to_pylist()
    client = NC.Nemotron(ledger=NC.Ledger(path=OUT / "ledger.json", cap=CAP), concurrency=CONCURRENCY, deadline=deadline)
    start = client.ledger.requests
    counts = collections.Counter()
    t0 = time.monotonic()

    async def chat(msgs, max_tokens, thinking, tag):
        return await client.chat(msgs, max_tokens=max_tokens, temperature=0.0, thinking=thinking, tag=tag)

    async def one(row):
        path = CACHE / f"{row['id']}.json"
        if path.exists():
            counts["cached"] += 1
            return
        try:
            out = await R.read_note(row, VERSION, chat)
            NC.save(path, dict(out, finished_utc=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")))
            counts["done"] += 1
        except Exception as exc:  # the note stays unread; a rerun only repairs this crash
            counts[f"error:{type(exc).__name__}"] += 1

    try:
        await asyncio.gather(*(one(r) for r in rows))
    finally:
        await client.close()
    metrics = dict(notes=len(rows), outcome=dict(counts), requests_this_run=client.ledger.requests - start,
                   requests_ledger=client.ledger.requests, requests_by_tag=dict(client.sent), tokens=dict(client.tokens),
                   request_errors=dict(client.errors), wall_seconds=round(time.monotonic() - t0, 1), concurrency=CONCURRENCY)
    log("nemotron-stress-read", command, inputs={"model": NC.MODEL, "set": "data/scribe/stress/stress-v1.parquet", "sha256": STRESS_SHA256,
                                                   "SYNTHETIC": True, "prompt_freeze": str(FREEZE.relative_to(ROOT))},
        outputs={"cache": str(CACHE.relative_to(ROOT))}, metrics=metrics, cost_usd=None)
    print(json.dumps(metrics, ensure_ascii=False))
    return metrics


def main(argv=None):
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("freeze")
    r = sub.add_parser("run")
    r.add_argument("--deadline", help="HH:MM UTC; no new request after it")
    a = p.parse_args(argv)
    if a.cmd == "freeze":
        return cmd_freeze(a)
    deadline = None
    if a.deadline:
        hh, mm = map(int, a.deadline.split(":"))
        d = dt.datetime.now(dt.timezone.utc).replace(hour=hh, minute=mm, second=0, microsecond=0)
        if d < dt.datetime.now(dt.timezone.utc):
            d += dt.timedelta(days=1)
        deadline = d.timestamp()
    asyncio.run(run(deadline, "scribe/.venv/bin/python scribe/v4/nemo8.py " + " ".join(argv if argv is not None else sys.argv[1:])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
