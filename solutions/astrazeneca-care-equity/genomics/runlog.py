"""Append one JSON line per executed step to runs/genomics.jsonl."""
import argparse, datetime, json, os, platform

RUNLOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runs", "genomics.jsonl")


def log_step(step, command="", inputs=None, outputs=None, metrics=None, cost_usd=0, status="ok", host=None, ts=None):
    rec = {"ts": ts or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "step": step, "host": host or platform.node(), "command": command, "inputs": inputs,
           "outputs": outputs, "metrics": metrics, "cost_usd": cost_usd, "status": status}
    os.makedirs(os.path.dirname(RUNLOG), exist_ok=True)
    with open(RUNLOG, "a") as fh:
        fh.write(json.dumps(rec, sort_keys=False) + "\n")
    return rec


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", required=True)
    ap.add_argument("--command", default="")
    ap.add_argument("--inputs", default="null")
    ap.add_argument("--outputs", default="null")
    ap.add_argument("--metrics", default="null")
    ap.add_argument("--cost-usd", type=float, default=0)
    ap.add_argument("--status", default="ok")
    ap.add_argument("--host", default=None)
    ap.add_argument("--ts", default=None)
    a = ap.parse_args()
    print(json.dumps(log_step(a.step, a.command, json.loads(a.inputs), json.loads(a.outputs),
                              json.loads(a.metrics), a.cost_usd, a.status, a.host, a.ts)))
