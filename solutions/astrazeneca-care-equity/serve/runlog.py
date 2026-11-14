"""Append-only run log for the serving slice: runs/v2-serve.jsonl.

One JSON object per executed step with the fields the project run log uses
(ts UTC ISO, step, host, command, inputs, outputs, metrics, cost_usd, status).
Never pass a key, token or Authorization header into any field.
"""

import datetime
import json
import pathlib
import socket

ROOT = pathlib.Path(__file__).resolve().parent.parent
PATH = ROOT / "runs" / "v2-serve.jsonl"


def log(
    step,
    command="",
    inputs=None,
    outputs=None,
    metrics=None,
    cost_usd=0,
    status="ok",
    path=None,
):
    entry = {
        "ts": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "step": step,
        "host": socket.gethostname(),
        "command": command,
        "inputs": inputs,
        "outputs": outputs,
        "metrics": metrics,
        "cost_usd": cost_usd,
        "status": status,
    }
    target = pathlib.Path(path) if path else PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Append one step to runs/v2-serve.jsonl")
    p.add_argument("step")
    p.add_argument("--command", default="")
    p.add_argument("--inputs", default="null", help="JSON")
    p.add_argument("--outputs", default="null", help="JSON")
    p.add_argument("--metrics", default="null", help="JSON")
    p.add_argument("--cost-usd", type=float, default=0)
    p.add_argument("--status", default="ok")
    a = p.parse_args()
    print(
        json.dumps(
            log(
                a.step,
                a.command,
                json.loads(a.inputs),
                json.loads(a.outputs),
                json.loads(a.metrics),
                a.cost_usd,
                a.status,
            ),
            ensure_ascii=False,
        )
    )
