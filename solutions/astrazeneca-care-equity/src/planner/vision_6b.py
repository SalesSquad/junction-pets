"""Step 6b: Nemotron 3.5 Super VL reads a PICTURE of a SYNTHETIC note page instead of its text.

20 SYNTHETIC validation notes (data/scribe/v2/dataset/val.parquet) are rendered to PNG pages with
ImageMagick (Arial, 24 pt). Page 19 is rotated by 4 degrees; page 20 is photo-like (tinted paper,
tilt, blur, noise, JPEG round trip). Per note, three things are measured:
  transcribe  Nemotron transcribes the image (thinking off): character error rate, misread ä/ö,
              misread date strings (the six date forms of scribe/sample.py, read by code).
  image       the step 4 reader protocol with the image as the note: expression JSON,
              data_tools.resolve_expression computes the dates, serve/schema.json validation and one
              repair, enable_thinking on. The grounding check of v2g/v3 needs the note text, which a
              scan does not have, so it is off in BOTH arms ("v3ng").
  text        the same protocol on the same 20 notes with the note text (paired baseline).
The cached step 4 v3 result (text, with grounding) is reported for reference.
Not for clinical use: every extracted event is pre-filled for one-click confirmation or flagged as
needing editing, and a person confirms every event either way.

    set -a; . ~/.config/verda-inference/env; set +a
    scribe/.venv/bin/python src/planner/vision_6b.py render
    scribe/.venv/bin/python src/planner/vision_6b.py run [--deadline 03:00]
    scribe/.venv/bin/python src/planner/vision_6b.py report
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import collections
import datetime as dt
import difflib
import hashlib
import json
import pathlib
import re
import socket
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scribe" / "nemotron"))
import common as C  # noqa: E402  read-only reuse: client, ledger, save
import reader as R  # noqa: E402  read-only reuse: prompts, check(), parsing, printed_dates()

OUT = ROOT / "data/planner/vision"
PNG = OUT / "png"
CACHE = OUT / "cache"
RUNLOG = ROOT / "runs/laneB-step6.jsonl"
C.REQUESTS = OUT / "requests.jsonl"  # this lane's request log, not step 4's
FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"
HEADER = "SYNTHETIC DOCUMENT - NOT A REAL PATIENT"
CFG = dict(fmt="expression", validate=True, ground=False, thinking=True)  # "v3ng"
N_PER_STRATUM = 10
RELATIVE = re.compile(r"\d+\s+(päivää|viikkoa)\s+sitten")


def log(step, command="", inputs=None, outputs=None, metrics=None, cost_usd=None, status="ok"):
    line = dict(ts=C.now().isoformat(timespec="seconds"), step=step, host=socket.gethostname(), command=command, inputs=inputs, outputs=outputs, metrics=metrics, cost_usd=cost_usd, status=status)
    with RUNLOG.open("a") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def sha(b):
    return hashlib.sha256(b).hexdigest()


def select():
    """10 notes with a relative date and 10 without, in a fixed hash order (seed string '6b')."""
    rows = R.load("val")
    order = sorted(rows, key=lambda r: sha(("6b:" + r["id"]).encode()))
    rel = [r for r in order if RELATIVE.search(r["note_text"])][:N_PER_STRATUM]
    non = [r for r in order if not RELATIVE.search(r["note_text"])][:N_PER_STRATUM]
    return [x for pair in zip(rel, non) for x in pair]


def page_text(row):
    return HEADER + "\n\n" + row["note_text"]


def variant(i):
    return "rotated" if i == 18 else "photo" if i == 19 else "clean"


def render():
    PNG.mkdir(parents=True, exist_ok=True)
    manifest = []
    for i, row in enumerate(select()):
        txt = OUT / "text" / f"{i:02d}.txt"
        txt.parent.mkdir(parents=True, exist_ok=True)
        txt.write_text(page_text(row), encoding="utf-8")
        out = PNG / f"{i:02d}.png"
        base = ["magick", "-size", "1100x", "-background", "white", "-fill", "black", "-font", FONT, "-pointsize", "24", "-interline-spacing", "6", f"caption:@{txt}", "-bordercolor", "white", "-border", "70"]
        v = variant(i)
        if v == "clean":
            subprocess.run(base + [str(out)], check=True)
        elif v == "rotated":
            subprocess.run(base + ["-background", "white", "-rotate", "4", str(out)], check=True)
        else:
            tmp = OUT / f"{i:02d}.tmp.jpg"
            subprocess.run(base + ["-background", "#e9e2d0", "-rotate", "-2", "-fill", "#e9e2d0", "-colorize", "12", "-resize", "75%", "-blur", "0x0.8", "-attenuate", "0.6", "+noise", "Gaussian", "-quality", "55", str(tmp)], check=True)
            subprocess.run(["magick", str(tmp), str(out)], check=True)
            tmp.unlink()
        manifest.append(dict(index=i, id=row["id"], variant=v, png=f"data/planner/vision/png/{i:02d}.png", png_sha256=sha(out.read_bytes()), has_relative_date=bool(RELATIVE.search(row["note_text"])), writer=row["writer"]))
    C.save(OUT / "manifest.json", dict(font=FONT, header=HEADER, selection="val.parquet sorted by sha256('6b:'+id); first 10 with a relative date and first 10 without, interleaved", notes=manifest))
    log("6b.render", command="scribe/.venv/bin/python src/planner/vision_6b.py render", inputs={"dataset": "data/scribe/v2/dataset/val.parquet (SYNTHETIC)", "n": len(manifest)}, outputs=["data/planner/vision/manifest.json", "data/planner/vision/png/"], metrics={"variants": dict(collections.Counter(m["variant"] for m in manifest)), "with_relative_date": sum(m["has_relative_date"] for m in manifest)}, cost_usd=0)
    print(json.dumps(dict(rendered=len(manifest)), ensure_ascii=False))


def image_part(i):
    b64 = base64.b64encode((PNG / f"{i:02d}.png").read_bytes()).decode()
    return {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}}


def image_messages(row, i):
    return [
        {"role": "system", "content": R.system_prompt("expression")},
        {"role": "user", "content": [{"type": "text", "text": f"Note date: {row['note_date']}\nThe note is printed on the attached page image (a SYNTHETIC document). Read the note from the image."}, image_part(i)]},
    ]


def repair(msgs, raw, problems):
    return msgs + [
        {"role": "assistant", "content": raw},
        {"role": "user", "content": "A program checked your answer against the output schema and the note. Problems found:\n" + "\n".join(f"- {p}" for p in problems) + "\nAnswer once more for the same note, fixing every problem and keeping every rule. Return only the JSON."},
    ]


async def read(row, msgs, chat, tag):
    """The step 4 protocol (reader.read_note) with a message builder: read, validate, one repair."""
    attempts = []
    r = await chat(msgs, R.MAX_TOKENS_THINKING, True, f"{tag}:read")
    pred, _, problems = R.check(r["text"], row, CFG)
    attempts.append(dict(action="read", raw=r["text"], seconds=r["seconds"], usage=r["usage"], finish_reason=r["finish_reason"], problems=problems, parsed=pred is not None))
    final = 0
    if problems:
        r2 = await chat(repair(msgs, r["text"], problems), R.MAX_TOKENS_THINKING, True, f"{tag}:repair")
        pred2, _, problems2 = R.check(r2["text"], row, CFG)
        attempts.append(dict(action="repair", raw=r2["text"], seconds=r2["seconds"], usage=r2["usage"], finish_reason=r2["finish_reason"], problems=problems2, parsed=pred2 is not None))
        if not problems2 or (pred is None and pred2 is not None):
            final, pred = 1, pred2
    return dict(id=row["id"], prediction=pred, raw=attempts[final]["raw"], flagged=bool(attempts[final]["problems"]), attempts=attempts, calls=len(attempts), latency=round(sum(a["seconds"] for a in attempts), 2))


async def transcribe(i, chat):
    msgs = [
        {"role": "system", "content": "You transcribe page images of SYNTHETIC documents. Return the full text exactly as printed, keeping every letter, digit and punctuation mark. No comments, no Markdown."},
        {"role": "user", "content": [{"type": "text", "text": "Transcribe all text on this page exactly."}, image_part(i)]},
    ]
    r = await chat(msgs, 2500, False, "6b:transcribe")
    return dict(text=r["text"], seconds=r["seconds"], usage=r["usage"], finish_reason=r["finish_reason"])


async def run(deadline=None, command=""):
    rows = select()
    client = C.Nemotron(ledger=C.Ledger(path=OUT / "ledger.json", cap=300), concurrency=4, deadline=deadline)
    start = client.ledger.requests
    counts = collections.Counter()
    t0 = time.monotonic()

    async def chat(msgs, max_tokens, thinking, tag):
        return await client.chat(msgs, max_tokens=max_tokens, temperature=0.0, thinking=thinking, tag=tag)

    async def one(i, row, arm):
        path = CACHE / arm / f"{i:02d}.json"
        if path.exists():
            counts[f"{arm}:cached"] += 1
            return
        try:
            if arm == "transcribe":
                out = await transcribe(i, chat)
            elif arm == "image":
                out = await read(row, image_messages(row, i), chat, "6b:image")
            else:
                out = await read(row, R.messages(row, "expression"), chat, "6b:text")
            C.save(path, dict(out, index=i, id=row["id"], arm=arm, finished_utc=C.now().isoformat(timespec="seconds")))
            counts[f"{arm}:done"] += 1
        except Exception as exc:
            counts[f"{arm}:error:{type(exc).__name__}"] += 1

    try:
        await asyncio.gather(*(one(i, row, arm) for arm in ("transcribe", "image", "text") for i, row in enumerate(rows)))
    finally:
        await client.close()
    metrics = dict(outcome=dict(counts), requests_this_run=client.ledger.requests - start, requests_ledger=client.ledger.requests, tokens=dict(client.tokens), request_errors=dict(client.errors), wall_seconds=round(time.monotonic() - t0, 1))
    log("6b.run", command=command, inputs={"model": C.MODEL, "notes": len(rows), "arms": ["transcribe", "image", "text"], "protocol": "v3ng (expression + resolve_expression + schema validation + one repair + thinking; no grounding)", "SYNTHETIC": True}, outputs=["data/planner/vision/cache/"], metrics=metrics, cost_usd=None)
    print(json.dumps(metrics, ensure_ascii=False))


def levenshtein(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


def umlaut_misreads(src, hyp):
    """ä/ö/Ä/Ö characters of the source that the transcript replaced or dropped (difflib alignment)."""
    sm = difflib.SequenceMatcher(None, src, hyp, autojunk=False)
    n = 0
    for op, i1, i2, _, _ in sm.get_opcodes():
        if op in ("replace", "delete"):
            n += sum(ch in "äöÄÖ" for ch in src[i1:i2])
    return n


def report(command=""):
    rows = select()
    manifest = {m["index"]: m for m in json.loads((OUT / "manifest.json").read_text())["notes"]}
    per = []
    for i, row in enumerate(rows):
        target = json.loads(row["target_json"])
        rec = dict(index=i, id=row["id"], variant=manifest[i]["variant"], writer=row["writer"], has_relative_date=manifest[i]["has_relative_date"])
        tr = CACHE / "transcribe" / f"{i:02d}.json"
        if tr.exists():
            t = json.loads(tr.read_text())
            src, hyp = norm(page_text(row)), norm(t["text"])
            dates_src = R.printed_dates(page_text(row), row["note_date"])
            dates_hyp = R.printed_dates(t["text"], row["note_date"])
            rec.update(cer=round(levenshtein(src, hyp) / max(1, len(src)), 4), umlaut_misreads=umlaut_misreads(src, hyp), umlauts_in_source=sum(ch in "äöÄÖ" for ch in src), date_strings_match={k: sorted(map(str, dates_src[k])) == sorted(map(str, dates_hyp[k])) for k in dates_src}, transcribe_prompt_tokens=(t.get("usage") or {}).get("prompt_tokens"))
            rec["date_misread"] = not all(rec["date_strings_match"].values())
        for arm in ("image", "text"):
            p = CACHE / arm / f"{i:02d}.json"
            if p.exists():
                o = json.loads(p.read_text())
                rec[f"{arm}_exact"] = o["prediction"] == target
                rec[f"{arm}_parsed"] = o["prediction"] is not None
                rec[f"{arm}_flagged"] = o["flagged"]
                rec[f"{arm}_calls"] = o["calls"]
                rec[f"{arm}_latency"] = o["latency"]
                rec[f"{arm}_prompt_tokens"] = sum((a.get("usage") or {}).get("prompt_tokens") or 0 for a in o["attempts"])
        v3 = R.cache_path("v3", "val", row["id"])
        if v3.exists():
            rec["text_v3_cached_exact"] = json.loads(v3.read_text())["prediction"] == target
        per.append(rec)
    done = [r for r in per if "image_exact" in r and "text_exact" in r]
    both = sum(r["image_exact"] and r["text_exact"] for r in done)
    img_only = sum(r["image_exact"] and not r["text_exact"] for r in done)
    txt_only = sum(r["text_exact"] and not r["image_exact"] for r in done)
    neither = sum(not r["image_exact"] and not r["text_exact"] for r in done)
    tr = [r for r in per if "cer" in r]
    misread = [r for r in tr if r["umlaut_misreads"] > 0 or r["date_misread"]]
    summary = dict(
        notes=len(per),
        paired=len(done),
        image_exact=sum(r["image_exact"] for r in done),
        text_exact=sum(r["text_exact"] for r in done),
        both_exact=both, image_only_exact=img_only, text_only_exact=txt_only, neither_exact=neither,
        image_parse_failures=sum(not r["image_parsed"] for r in done),
        text_parse_failures=sum(not r["text_parsed"] for r in done),
        text_v3_cached_exact=sum(bool(r.get("text_v3_cached_exact")) for r in per),
        relative_date_notes=dict(image=sum(r["image_exact"] for r in done if r["has_relative_date"]), text=sum(r["text_exact"] for r in done if r["has_relative_date"]), n=sum(r["has_relative_date"] for r in done)),
        variants={r["variant"]: dict(image_exact=r.get("image_exact"), text_exact=r.get("text_exact"), cer=r.get("cer"), umlaut_misreads=r.get("umlaut_misreads"), date_misread=r.get("date_misread")) for r in per if r["variant"] != "clean"},
        transcription=dict(notes=len(tr), median_cer=sorted(r["cer"] for r in tr)[len(tr) // 2] if tr else None, max_cer=max((r["cer"] for r in tr), default=None), notes_with_umlaut_misread=sum(r["umlaut_misreads"] > 0 for r in tr), umlaut_misreads_total=sum(r["umlaut_misreads"] for r in tr), umlauts_total=sum(r["umlauts_in_source"] for r in tr), notes_with_date_misread=sum(r["date_misread"] for r in tr)),
        notes_with_umlaut_or_date_misread=len(misread),
        mean_prompt_tokens=dict(image=round(sum(r["image_prompt_tokens"] for r in done) / max(1, len(done))), text=round(sum(r["text_prompt_tokens"] for r in done) / max(1, len(done)))),
        mean_latency_s=dict(image=round(sum(r["image_latency"] for r in done) / max(1, len(done)), 2), text=round(sum(r["text_latency"] for r in done) / max(1, len(done)), 2)),
    )
    kill = summary["notes_with_umlaut_or_date_misread"] > 5
    summary["kill_criterion"] = "more than 5 of 20 notes with a misread ä/ö or date string"
    summary["verdict"] = "tested, not good enough yet" if kill else "kill criterion not met"
    t = summary["transcription"]
    summary["statement"] = [
        f"We also gave Nemotron 3.5 Super VL {summary['paired']} SYNTHETIC notes as page images instead of text (one page rotated, one photo-like), with the same reader protocol. "
        f"Exact match was {summary['image_exact']}/{summary['paired']} from the image against {summary['text_exact']}/{summary['paired']} from the text of the same notes "
        f"({summary['relative_date_notes']['image']}/{summary['relative_date_notes']['n']} against {summary['relative_date_notes']['text']}/{summary['relative_date_notes']['n']} on notes with a relative date).",
        f"Asked to transcribe the pages, it misread or dropped ä/ö in {t['notes_with_umlaut_misread']} of {t['notes']} pages and changed a date string in {t['notes_with_date_misread']} of {t['notes']}. "
        f"Image input is tested, {'not good enough yet' if kill else 'and met the kill criterion'}; the product keeps text input.",
    ]
    out = dict(schemaVersion="sama-planner-vision-6b-v1", model=C.MODEL, synthetic=True, protocol="v3ng: expression JSON, resolve_expression, serve/schema.json validation, one repair, enable_thinking on; grounding off in both arms (a scan has no text to ground against)", note="n = 20 SYNTHETIC notes; counts only, no significance test. A person confirms every extracted event.", summary=summary, notes=per)
    C.save(OUT / "vision-6b-v1.json", out)
    log("6b.report", command=command, inputs=["data/planner/vision/cache/", "data/scribe/nemotron/cache/v3/val/ (reference)"], outputs=["data/planner/vision/vision-6b-v1.json"], metrics=summary, cost_usd=None)
    print(json.dumps(summary, ensure_ascii=False, indent=1))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["render", "run", "report"])
    p.add_argument("--deadline")
    a = p.parse_args()
    command = "scribe/.venv/bin/python src/planner/vision_6b.py " + " ".join(sys.argv[1:])
    if a.cmd == "render":
        render()
    elif a.cmd == "run":
        deadline = None
        if a.deadline:
            hh, mm = map(int, a.deadline.split(":"))
            d = C.now().replace(hour=hh, minute=mm, second=0, microsecond=0)
            if d < C.now() - dt.timedelta(hours=12):
                d += dt.timedelta(days=1)
            deadline = d.timestamp()
        asyncio.run(run(deadline, command))
    else:
        report(command)


if __name__ == "__main__":
    main()
