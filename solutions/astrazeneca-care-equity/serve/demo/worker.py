#!/usr/bin/env python3
"""Persistent CPU inference process for POST /api/scribe (web/serve.mjs). Run with serve/.venv/bin/python.

Protocol: JSON lines. The model is loaded once at start; then one request per stdin line, one response per stdout
line, in order. stdout carries protocol lines only: everything else (library warnings, progress bars) goes to stderr.

  start    -> {"event": "ready", "provenance": {...}, "load_seconds": s}  or  {"event": "error", "error": "..."}
  request  {"id": "r1", "op": "extract", "note_text": "...", "note_date": "YYYY-MM-DD", "note_id": "...", "synthetic": true}
  response {"id": "r1", "ok": true, "result": {...}}  or  {"id": "r1", "ok": false, "error": "...", "input_error": bool}
  request  {"id": "r2", "op": "ping"}      -> {"id": "r2", "ok": true, "result": {"pong": true}}
  request  {"id": "r3", "op": "shutdown"}  -> {"id": "r3", "ok": true, "result": {"bye": true}}, then exit 0

The process exits when stdin closes, so it never outlives the web server that started it. It reads only local files:
HF_HUB_OFFLINE=1 is set before transformers is imported, so a missing base model is an error, never a download.
A person confirms every event this process proposes.
"""

import json
import os
import sys

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")


def main():
    proto = os.fdopen(os.dup(1), "w", buffering=1, encoding="utf-8")
    os.dup2(2, 1)  # stray prints from libraries now land on stderr, never in the protocol stream

    def send(obj):
        proto.write(json.dumps(obj, ensure_ascii=False) + "\n")
        proto.flush()

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        import engine

        model = engine.Engine()
        model.warm_up()
    except Exception as exc:  # noqa: BLE001 - reported to the parent, which falls back to precomputed outputs
        send({"event": "error", "error": f"{type(exc).__name__}: {exc}"[:500]})
        return 1
    send({"event": "ready", "provenance": model.provenance, "load_seconds": model.provenance["load_seconds"]})
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        rid = None
        try:
            req = json.loads(line)
            rid = req.get("id")
            op = req.get("op", "extract")
            if op == "ping":
                send({"id": rid, "ok": True, "result": {"pong": True}})
            elif op == "shutdown":
                send({"id": rid, "ok": True, "result": {"bye": True}})
                return 0
            elif op == "extract":
                result = model.extract(req.get("note_text"), req.get("note_date"), req.get("note_id"), req.get("synthetic"))
                send({"id": rid, "ok": True, "result": result})
            else:
                send({"id": rid, "ok": False, "error": f"unknown op {op!r}"})
        except ValueError as exc:  # bad request (engine.check_note, JSON): the caller answers 400
            send({"id": rid, "ok": False, "error": str(exc)[:300], "input_error": True})
        except Exception as exc:  # noqa: BLE001 - one bad request must not end the process
            send({"id": rid, "ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]})
    return 0


if __name__ == "__main__":
    sys.exit(main())
