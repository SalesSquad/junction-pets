"""Time MLX greedy inference on the first 20 validation notes per base size, before committing to the arm list.

Base models without an adapter, version-1 absolute prompt, max 384 new tokens. A base model may not stop early, so
seconds per note is an upper bound for a trained adapter; tokens per second is the comparable speed figure.
One MLX process at a time (sequential subprocesses).
"""

from __future__ import annotations

import json
import subprocess
import sys

import m2common as C


def main():
    results = {}
    for base in ("270m", "1b"):
        out = C.OUT / f"timing/base-{base}-val20.jsonl"
        if out.exists():
            out.unlink()
        cmd = [str(C.MLX_PY), str(C.HERE / "infer.py"), "--base", base, "--format", "absolute", "--split", "val",
               "--limit", "20", "--output", str(out)]
        p = subprocess.run(cmd, capture_output=True, text=True, cwd=C.HERE)
        line = next((x for x in p.stdout.splitlines() if x.startswith("SUMMARY ")), None)
        if p.returncode or line is None:
            results[base] = {"status": "failed", "returncode": p.returncode, "stderr_tail": p.stderr[-1500:]}
        else:
            s = json.loads(line[8:])
            recs = [json.loads(x) for x in out.read_text().splitlines()]
            s["hit_max_tokens"] = sum(r["hit_max_tokens"] for r in recs)
            s["mean_new_tokens"] = round(sum(r["new_tokens"] for r in recs) / len(recs), 1)
            s["mean_prompt_tokens"] = round(sum(r["prompt_tokens"] for r in recs) / len(recs), 1)
            results[base] = {"status": "ok", **s}
        C.log(f"timing-{base}", " ".join(cmd[1:]), inputs={"split": "val", "limit": 20},
              outputs={"file": C.rel(out)}, metrics=results[base], status=results[base]["status"])
        print(base, json.dumps(results[base]), flush=True)
    C.save_json(C.OUT / "timing-v1.json", {"synthetic": True, "created": C.now(), "note": __doc__.strip(), "results": results})
    return 0


if __name__ == "__main__":
    sys.exit(main())
