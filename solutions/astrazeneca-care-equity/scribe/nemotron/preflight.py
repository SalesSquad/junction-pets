"""Step 4a preflight: one call with a single tool, one call with enable_thinking on. SYNTHETIC text only.

    set -a; . ~/.config/verda-inference/env; set +a
    scribe/.venv/bin/python scribe/nemotron/preflight.py

Writes data/scribe/nemotron/preflight-v1.json and one line in runs/laneB-step4.jsonl.
If the tool call fails, step 6 falls back to a JSON call plan validated against a schema.
"""

import asyncio
import json
import re

import common as C
import data_tools
import pyarrow.parquet as pq
from prompts import canonicalise

TOOL = {
    "type": "function",
    "function": {
        "name": "resolve_relative_date",
        "description": "Return the calendar date that lies n days or n weeks before the note date.",
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "required": ["note_date", "n", "unit"],
            "properties": {
                "note_date": {"type": "string", "description": "YYYY-MM-DD"},
                "n": {"type": "integer", "minimum": 0},
                "unit": {"type": "string", "enum": ["days", "weeks"]},
            },
        },
    },
}


async def main():
    client = C.Nemotron()
    out = {"model": C.MODEL, "synthetic_input_only": True}
    try:
        ids = await client.models()
        out["model_listed"] = C.MODEL in ids

        # 1. a single tool
        r = await client.chat(
            [
                {"role": "system", "content": "You are a careful assistant. Use the tool for any date arithmetic; never compute dates yourself."},
                {
                    "role": "user",
                    "content": "SYNTHETIC note, note date 2025-03-10: 'Lähete erikoissairaanhoitoon lähetetty 3 viikkoa sitten.' On which calendar date was the referral sent?",
                },
            ],
            max_tokens=400,
            tools=[TOOL],
            tool_choice="auto",
            tag="preflight_tool",
        )
        calls = r["tool_calls"]
        tool = dict(seconds=r["seconds"], usage=r["usage"], finish_reason=r["finish_reason"], n_tool_calls=len(calls), content_head=r["text"][:300])
        if calls:
            fn = calls[0].get("function", {})
            tool["name"] = fn.get("name")
            try:
                args = json.loads(fn.get("arguments") or "{}")
                tool["arguments"] = args
                tool["arguments_valid"] = (
                    fn.get("name") == "resolve_relative_date" and args.get("n") == 3 and args.get("unit") == "weeks" and args.get("note_date") == "2025-03-10"
                )
            except ValueError as exc:
                tool["arguments_valid"] = False
                tool["arguments_error"] = str(exc)[:200]
        else:
            tool["arguments_valid"] = False
        tool["ok"] = bool(calls) and tool["arguments_valid"]
        out["tool_call"] = tool

        # 2. enable_thinking on, expression-format extraction of one SYNTHETIC validation note
        row = pq.read_table(C.ROOT / "data/scribe/v2/dataset/val.parquet").to_pylist()[0]
        r = await client.chat(data_tools.expression_messages(row), max_tokens=6000, thinking=True, tag="preflight_thinking")
        think = dict(
            seconds=r["seconds"],
            usage=r["usage"],
            finish_reason=r["finish_reason"],
            separate_reasoning_field=bool(r["reasoning"]),
            reasoning_chars=len(r["reasoning"]),
            think_tag_in_content="</think>" in r["text"] or "<think>" in r["text"],
            content_head=r["text"][:300],
        )
        text = re.sub(r"(?s)^.*</think>", "", r["text"]).strip()
        try:
            obj = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", text))
            pred = data_tools.resolve_expression(obj, row["note_date"])
            think["parsed"] = True
            think["exact"] = pred == canonicalise(json.loads(row["target_json"]))
        except (ValueError, KeyError, TypeError) as exc:
            think["parsed"] = False
            think["parse_error"] = str(exc)[:200]
        out["thinking"] = think
    finally:
        await client.close()
    out["ledger_requests"] = client.ledger.requests
    out["request_errors"] = dict(client.errors)
    C.save(C.OUT / "preflight-v1.json", out)
    C.log(
        "4a_preflight",
        command="scribe/.venv/bin/python scribe/nemotron/preflight.py",
        inputs={"model": C.MODEL, "note": "val.parquet row 0 (SYNTHETIC)"},
        outputs=["data/scribe/nemotron/preflight-v1.json"],
        metrics={
            "tool_call_ok": out["tool_call"]["ok"],
            "thinking_parsed": out["thinking"].get("parsed"),
            "thinking_exact": out["thinking"].get("exact"),
            "thinking_separate_reasoning_field": out["thinking"]["separate_reasoning_field"],
            "chat_calls": 2,
        },
        cost_usd=None,
        status="ok",
    )
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
