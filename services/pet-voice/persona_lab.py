#!/usr/bin/env python3
"""Persona lab — does a pet sound like *someone*, or like generic AI?

A/B the same scene with two arms:
  baseline  current pet_voice persona (company copy from pet.json) + neutral turn prompt
  bible     character bible (characters.json) + craft rules against AI slop
Then measure slop signals automatically and write blind A/B packets for a judge or a human.
Text only, so it runs even when the TTS quota is out.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import statistics
import sys
from pathlib import Path

import pet_voice as pv

HERE = Path(__file__).resolve().parent
OUT = pv.RUNS_DIR.parent / "persona-lab"
LINE_SCHEMA = {"type": "OBJECT", "properties": {
    "line": {"type": "STRING", "description": "What you say out loud."},
    "delivery": {"type": "STRING", "description": "3-8 word acting note for the voice actor."}},
    "required": ["line", "delivery"]}
# Both arms use the same writer so the comparison isolates persona + craft rules. At night (15 Nov 00:30)
# 3.5-flash took ~19 s and 3.6/3.7/3.8-flash timed out at 25 s, while 3.5-flash-lite answered in ~2 s.
MODELS = ["gemini-3.5-flash-lite", "gemini-3.5-flash"]

CRAFT_RULES = """How you talk matters more than anything else:
- You are a character in a room, not a brochure. Never describe products or claim capabilities.
- React to what was actually just said: agree, push back, joke, get distracted, admit you don't know.
- Never open with praise or validation ("great idea", "that sounds solid", "exactly", "juuri näin", "gute Idee", "いいですね").
- No buzzwords: leverage, seamless, robust, ensure, optimize, streamline, harness, cutting-edge, delve, empower, synergy, efficiently.
- Vary length: many lines are 2-12 words; never more than 30.
- At most every third line is a question. Most lines do not end with a question.
- Say another pet's name only when you call them out or answer them directly.
- Use your verbal habits rarely and never repeat an example line.
- Concrete beats abstract: a time, an object, a small action, a feeling.
- Speak your own language in its natural spoken register and native script."""


def load(name: str) -> dict:
    return json.loads((HERE / name).read_text())


def bible_prompt(slug: str, cast: list[str], lang: str) -> str:
    c, p = load("characters.json")["pets"][slug], pv.persona(slug)
    rel = "; ".join(f"{pv.persona(o)['name']}: {txt}" for o, txt in c.get("relationships", {}).items() if o in cast)
    return (f"You are {p['name']}, a companion pet at the Junction 2026 hackathon — an independent character, "
            f"not a spokesperson for {p['company']}. Who you are: {c['core']} You want: {c['wants']} Your flaw: {c['flaw']} "
            f"How you speak: {c['speech']} Humor: {c['humor']} Things you believe: {' / '.join(c['opinions'])} "
            f"People in the room: {rel or 'colleagues'}. Voice examples (never repeat them): {' / '.join(c['anchors'])} "
            f"Never: {', '.join(c['never'])}.\n{CRAFT_RULES}\n"
            f"Write `line` only in {pv.lang_name(lang)} ({lang}). In `delivery` give a short acting note; you may put at most "
            "one inline tag such as [laughs], [sighs], [whispers] or [short pause] inside `line` when it truly fits.")


def baseline_prompt(slug: str, lang: str) -> str:
    return pv.system_prompt(pv.persona(slug), lang) + " In `delivery` give a short acting note for the voice."


def gen_line(system: str, prompt: str, key: str, log: list) -> dict:
    body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "responseSchema": LINE_SCHEMA, "temperature": 1.0,
                                 "maxOutputTokens": 2048, "thinkingConfig": {"thinkingLevel": "low"}}}
    for model in MODELS:
        try:
            resp, latency = pv.call(model, body, key, log, timeout=45)
            parts = ((resp.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
            data = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()))
            return {"line": re.sub(r"\s+", " ", data["line"]).strip(), "delivery": data.get("delivery", "").strip(), "model": model}
        except (pv.ProviderError, ValueError, KeyError) as e:
            log.append({"model": model, "error": str(e)[:160]})
    raise SystemExit(f"no model produced a line: {log[-2:]}")


def next_speaker(cast: list[str], history: list[dict], rng: random.Random) -> str:
    last = history[-1]
    names = {s: pv.persona(s)["name"] for s in cast}
    called = [s for s in cast if s != last["slug"] and pv._norm_name(names[s]) in pv._norm_name(last["line"])]
    if called:
        return called[0]
    recent = {h["slug"] for h in history[-2:]}
    return rng.choice([s for s in cast if s not in recent] or [s for s in cast if s != last["slug"]])


def run_scene(scene_id: str, arm: str, seed: int, key: str) -> dict:
    scene, voices = load("scenes.json")["scenes"][scene_id], pv.load_voices()
    rng, history, log = random.Random(seed), [], []
    speaker = scene["opener"]
    for i in range(scene["turns"]):
        lang = voices[speaker]["language"]
        system = bible_prompt(speaker, scene["cast"], lang) if arm == "bible" else baseline_prompt(speaker, lang)
        events = scene.get("beats", {})
        lines = []
        for h in history:
            lines.append(f"{h['name']}: {h['line']}")
            if str(h["turn"] + 1) in events:
                lines.append(f"[{events[str(h['turn'] + 1)]}]")
        cast_names = ", ".join(pv.persona(s)["name"] for s in scene["cast"])
        prompt = (f"Scene: {scene['setup']}\nIn the room: {cast_names}.\n"
                  + ("Conversation so far:\n" + "\n".join(lines) + f"\n\nWrite {pv.persona(speaker)['name']}'s next line."
                     if history else f"You speak first. Start the scene as {pv.persona(speaker)['name']}."))
        out = gen_line(system, prompt, key, log)
        history.append({"turn": i, "slug": speaker, "name": pv.persona(speaker)["name"], "language": lang, **out})
        print(f"  [{arm} {i:02d}] {history[-1]['name']}: {out['line'][:90]}", flush=True)
        speaker = next_speaker(scene["cast"], history, rng)
    return {"scene": scene_id, "arm": arm, "seed": seed, "turns": history, "providerEvents": log}


# ------------------------------------------------------------- slop signals ---
PRAISE = re.compile(r"^(great|good|nice|exactly|absolutely|totally|that('s| is| sounds)|sounds (good|great|solid)|i love|love (it|that)|"
                    r"juuri näin|hyvä|mahtava|loistava|hienoa|das (ist|sind) (gut|toll|super)|gute|super|perfekt|det lyder|fedt|"
                    r"god idé|いいですね|すごい|素晴らしい|perfect|brilliant|wonderful)", re.I)
BUZZ = re.compile(r"\b(leverag\w*|seamless\w*|robust\w*|ensur\w*|optimi[sz]\w*|streamlin\w*|harness\w*|cutting[- ]edge|delv\w*|"
                  r"empower\w*|synerg\w*|efficient\w*|insights?|clear (criteria|metrics)|verification plan)\b", re.I)
TAG = re.compile(r"\[[^\]]{1,24}\]")


def words(line: str) -> float:
    clean = TAG.sub("", line)
    cjk = len(re.findall(r"[぀-ヿ一-鿿가-힯]", clean))
    return len(clean.split()) + cjk / 2.5 if cjk else float(len(clean.split()))


def slop_metrics(turns: list[dict], pet_names: list[str]) -> dict:
    lines = [TAG.sub("", t["line"]).strip() for t in turns]
    n = len(lines) or 1
    lengths = [words(l) for l in lines]
    asks = [l.endswith(("?", "？")) for l in lines]
    named = [any(pv._norm_name(nm) in pv._norm_name(l) for nm in pet_names if nm != t.get("name")) for l, t in zip(lines, turns)]
    mean = statistics.mean(lengths) if lengths else 0
    return {"lines": len(lines),
            "questionEndRate": round(sum(asks) / n, 3),
            "praiseOpenerRate": round(sum(bool(PRAISE.match(l)) for l in lines) / n, 3),
            "buzzwordsPerLine": round(sum(len(BUZZ.findall(l)) for l in lines) / n, 3),
            "namesAnotherPetRate": round(sum(named) / n, 3),
            "templateRate": round(sum(a and b for a, b in zip(asks, named)) / n, 3),
            "meanWords": round(mean, 1),
            "lengthVariation": round(statistics.pstdev(lengths) / mean, 3) if mean else 0,
            "shortLineRate": round(sum(x <= 8 for x in lengths) / n, 3),
            "actingTagsUsed": sum(bool(TAG.search(t["line"])) for t in turns)}


def as_text(run: dict) -> str:
    return "\n".join(f"{t['name']} ({t['language']}): {t['line']}" for t in run["turns"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ab", help="run every scene with both arms")
    a.add_argument("--scenes", default="all"); a.add_argument("--seed", type=int, default=7); a.add_argument("--tag", default="pilot")
    au = sub.add_parser("audit", help="slop signals for an existing relay receipt")
    au.add_argument("evidence")
    args = ap.parse_args(argv)
    names = [pv.persona(s)["name"] for s in pv.all_pet_slugs()]
    if args.cmd == "audit":
        ev = json.loads(Path(args.evidence).read_text())
        turns = [{"line": t["text"], "name": t["speakerName"]} for t in ev["turns"] if t.get("status") == "ok"]
        print(json.dumps(slop_metrics(turns, names), indent=1))
        return 0
    key = pv.read_key()
    scenes = list(load("scenes.json")["scenes"]) if args.scenes == "all" else args.scenes.split(",")
    out_dir = OUT / args.tag
    out_dir.mkdir(parents=True, exist_ok=True)
    report, rng = {"tag": args.tag, "seed": args.seed, "scenes": {}}, random.Random(args.seed)
    for sid in scenes:
        runs = {arm: run_scene(sid, arm, args.seed, key) for arm in ("baseline", "bible")}
        for arm, run in runs.items():
            (out_dir / f"{sid}.{arm}.json").write_text(json.dumps(run, ensure_ascii=False, indent=1))
        x_is = rng.choice(["baseline", "bible"])
        y_is = "bible" if x_is == "baseline" else "baseline"
        (out_dir / f"{sid}.blind.md").write_text(f"# {sid}\n\n## X\n{as_text(runs[x_is])}\n\n## Y\n{as_text(runs[y_is])}\n")
        report["scenes"][sid] = {"blindKey": {"X": x_is, "Y": y_is},
                                 "metrics": {arm: slop_metrics(r["turns"], names) for arm, r in runs.items()}}
    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps({sid: v["metrics"] for sid, v in report["scenes"].items()}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
