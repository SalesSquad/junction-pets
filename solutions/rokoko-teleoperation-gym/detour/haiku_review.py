#!/usr/bin/env python3
"""One bounded visible-text Haiku safety critique, never a motion command."""
from pathlib import Path
from datetime import datetime, timezone
import os
import json
import hashlib
import urllib.error
from advisors import post_json

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"evidence"/"haiku-visible-review.json"
if OUT.exists():
    raise SystemExit("Refuse duplicate provider call or overwrite")
key=os.getenv("ANTHROPIC_API_KEY")
if not key:
    raise SystemExit("No Anthropic API key in approved local process")
sources={n: (ROOT/n).read_text() for n in ("planner.py","env.py")}
prompt=("Read-only review of an original SYNTHETIC MuJoCo detour planner and actuator wrapper. "
        "We ran 100 paired DEVELOPMENT worlds: old 3 safe/100, new 3 safe/100, "
        "abstentions old 74/100 new 18/100; no unsafe in either. "
        "New cases mainly time out or stay held. Give 4 actionable P1 causes "
        "with exact source patterns, and a safe training/verification plan for "
        "genuine task-success improvement WITHOUT relaxing deadman, contact/impulse, "
        "or workspace limits. Highlight route-target recomputation, intermittent "
        "sensor HOLD, physical push alignment, and how to measure actual settled "
        "goal vs false-success. This is not real Rokoko hardware; avoid approval claims. "
        "Deliver visible plain text under 900 words. CODE:\n"+
        "\n---PLANNER---\n"+sources["planner.py"]+
        "\n---ENV---\n"+sources["env.py"])
payload={"model":"claude-haiku-5-5","max_tokens":2200,
         "thinking":{"type":"disabled"},
         "output_config":{"effort":"low"},
         "messages":[{"role":"user","content":prompt}]}
try:
    raw=post_json("https://api.anthropic.com/v1/messages",payload,{
        "x-api-key":key,"anthropic-version":"2023-06-01",
        "Content-Type":"application/json"},timeout=35)
except (RuntimeError,ValueError,urllib.error.URLError) as e:
    raise SystemExit("Haiku provider rejected bounded call: "+str(e)[:90])
content="\n".join(b.get("text","") for b in raw.get("content",[]) if b.get("type")=="text")
u=raw.get("usage",{})
it,ot=u.get("input_tokens"),u.get("output_tokens")
if raw.get("model")!="claude-haiku-5-5" or not isinstance(it,int) or not isinstance(ot,int):
    raise SystemExit("Invalid Haiku response identity or token usage")
if not content.strip():
    raise SystemExit("Haiku returned no visible analysis; do not claim a review")
estimated=(it*.10+ot*.50)/1e6
if estimated>=15:
    raise SystemExit("Owner budget exceeded (would preserve trace separately)")
report={
 "schema":"rokoko.m6.haiku_independent_comment.v1",
 "source_sha256":{k:hashlib.sha256(v.encode()).hexdigest() for k,v in sources.items()},
 "model":raw["model"],"stop_reason":raw.get("stop_reason"),
 "input_tokens":it,"output_tokens":ot,"usd_estimated_list":estimated,
 "budget_usd":15,"actual_provider_invoice":"NOT_READ",
 "comment":content[:13000],
 "source_kind":"SYNTHETIC_DEVELOPMENT_OBSERVATION_ONLY",
 "external_motor_decisions":0,
 "utc":datetime.now(timezone.utc).isoformat()
}
OUT.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
print(json.dumps({"visible_review":True,"text_chars":len(content),"model":raw["model"],
                  "stop_reason":raw.get("stop_reason"),
                  "estimated_usd":estimated,"tokens":{"input":it,"output":ot}}))
