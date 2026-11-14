import datetime
import json
import pathlib
import socket

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data/scribe"


def log(
    step, command="", inputs=None, outputs=None, metrics=None, cost_usd=0, status="ok"
):
    p = ROOT / "runs/scribe.jsonl"
    p.parent.mkdir(exist_ok=True)
    with p.open("a") as f:
        f.write(
            json.dumps(
                dict(
                    ts=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    step=step,
                    host=socket.gethostname(),
                    command=command,
                    inputs=inputs,
                    outputs=outputs,
                    metrics=metrics,
                    cost_usd=cost_usd,
                    status=status,
                )
            )
            + "\n"
        )


def save(p, x):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(x, ensure_ascii=False, indent=2))
