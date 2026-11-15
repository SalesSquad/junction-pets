#!/usr/bin/env python3
"""Scene engine v2 — Junction pets with personality, talking to each other by voice.

Per turn:  director (who speaks next, with what move)
        -> writer   (the speaker *hears* the previous line as audio, answers in character)
        -> checks   (deterministic slop/tic/script rules)  -> critic (rewrite only if needed)
        -> voice    (the pet's own designed Gemini voice + a vocal direction for this line)
After a scene, memory keeps running jokes and relationship changes for the next scene, and the
owner's blind ratings (taste.json) steer future lines. `--text-only` skips audio for fast iteration.
Stdlib only; reuses pet_voice for the provider, audio, receipts and learning.
"""
from __future__ import annotations

import argparse
import base64
import difflib
import json
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pet_voice as pv

HERE = Path(__file__).resolve().parent
MEMORY_FILE = pv.RUNS_DIR.parent / "memory" / "pets.json"
DESIGNED_FILE = HERE / "learned" / "designed-voices.json"
TASTE_FILE = HERE / "learned" / "taste.json"
SCENE_EVIDENCE = HERE / "scene-evidence"
# 15 Nov 02:00: both 3.5 models hit their free daily caps after ~8 text scenes; the `flash-lite-latest` alias still
# answered in ~1 s (3.6-flash daily-capped, 3.7-flash 503, 3.8-flash and flash-latest timed out, others 404).
WRITERS = ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-flash-lite-latest"]
MOVES = ["react", "answer", "push back", "joke", "tease", "short reaction", "admit doubt", "new idea", "change the subject", "wrap up"]

CRAFT = """How you talk matters more than anything else:
- You are a character in a room, not a brochure. Never describe products or claim capabilities.
- React to what you just heard: agree, push back, joke, get distracted, admit you don't know.
- Never open with praise or validation ("great idea", "that sounds solid", "exactly", "juuri näin", "gute Idee", "いいですね").
- No buzzwords: leverage, seamless, robust, ensure, optimize, streamline, harness, cutting-edge, delve, empower, synergy.
- Vary length: many lines are 2-12 words; never more than 30.
- Most lines do not end with a question.
- Say another pet's name only when you call them out or answer them directly.
- Your catchphrases are seasoning: at most once per scene. Never repeat an example line.
- Concrete beats abstract: a time, an object, a small action, a feeling.
- Speak your own language in its natural spoken register and native script.
- Inline voice tags such as [laughs], [sighs], [whispers] or [short pause] are rare: only when the moment needs it."""


def load(name: str) -> dict:
    return json.loads((HERE / name).read_text())


def characters() -> dict:
    return load("characters.json")["pets"]


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------ memory ---
def load_memory() -> dict:
    try:
        return json.loads(MEMORY_FILE.read_text())
    except (OSError, ValueError):
        return {"pets": {}}


def save_memory(mem: dict) -> None:
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_FILE.write_text(json.dumps(mem, ensure_ascii=False, indent=1))


def taste() -> dict:
    try:
        return json.loads(TASTE_FILE.read_text())
    except (OSError, ValueError):
        return {}


# ----------------------------------------------------------------- prompts ---
def system_prompt(slug: str, cast: list[str], lang: str, memory_notes: list[str], openers: list[str] | None = None,
                  worn: list[str] | None = None) -> str:
    c, p = characters()[slug], pv.persona(slug)
    rel = "; ".join(f"{pv.persona(o)['name']}: {txt}" for o, txt in c.get("relationships", {}).items() if o in cast)
    t = taste().get("pets", {}).get(slug, {})
    owner = ""
    if t.get("liked") or t.get("disliked") or taste().get("notes"):
        owner = ("\nThe person you perform for has rated earlier lines. More like: " + " / ".join(t.get("liked", [])[:2] or ["-"])
                 + ". Less like: " + " / ".join(t.get("disliked", [])[:2] or ["-"]) + ". Their notes: "
                 + " / ".join(taste().get("notes", [])[-3:] or ["-"]))
    mem = ("\nFrom earlier scenes you could call back to (at most one callback in this scene, only if the moment invites "
           "it; then set `callback` to its number): " + " ".join(f"[{i}] {n}" for i, n in enumerate(memory_notes, 1))
           ) if memory_notes else ""
    habits = sorted({o for o in (openers or []) if (openers or []).count(o) >= 2})
    if habits:
        mem += f"\nLately you keep starting lines with: {', '.join(habits)}. Start differently."
    if worn:
        mem += f"\nWords you have leaned on in recent scenes: {', '.join(worn)}. Reach for a fresh image instead."
    return (f"You are {p['name']}, a companion pet at the Junction 2026 hackathon — an independent character, not a "
            f"spokesperson for {p['company']}. Who you are: {c['core']} You want: {c['wants']} Your flaw: {c['flaw']} "
            f"How you speak: {c['speech']} Humor: {c['humor']} Things you believe: {' / '.join(c['opinions'])} "
            f"People in the room: {rel or 'colleagues'}. Voice examples (never repeat them): {' / '.join(c['anchors'])} "
            f"Your catchphrases: {', '.join(c.get('catchphrases', []))}. Never: {', '.join(c['never'])}.{mem}{owner}\n{CRAFT}\n"
            f"Write `line` only in {pv.lang_name(lang)} ({lang}). `voice_direction` is 3-8 words for a voice actor about "
            "pace, volume, pitch and emotion only — never body movement.")


def gen_json(system: str, parts: list[dict], schema: dict, key: str, log: list, temperature: float = 1.0) -> tuple[dict, str, float]:
    body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"responseMimeType": "application/json", "responseSchema": schema, "temperature": temperature,
                                 "maxOutputTokens": 2048, "thinkingConfig": {"thinkingLevel": "low"}}}
    for model in WRITERS:
        if model in pv.EXHAUSTED:
            continue
        try:
            # 3 attempts: a 503 "high demand" storm on Flash-Lite cost ~90 s per line with 6 (15 Nov); fall through faster.
            resp, latency = pv.call(model, body, key, log, attempts=3, timeout=45)
            got = ((resp.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
            text = "".join(p.get("text", "") for p in got if not p.get("thought")).strip()
            label = model if model == resp.get("modelVersion", model) else f"{model}={resp['modelVersion']}"  # aliases resolve
            return json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", text)), label, round(latency, 2)
        except pv.ProviderError:
            continue
        except ValueError as e:
            log.append({"model": model, "status": 200, "code": "BAD_JSON", "message": str(e)[:120]})
    raise pv.ProviderError(0, "GEN_UNAVAILABLE", "no writer model answered")


TAG = re.compile(r"\[[^\]]{1,24}\]")
PRAISE = re.compile(r"^(great|good|nice|exactly|absolutely|totally|that('s| is| sounds) (great|good|solid|smart)|sounds (good|great|solid)|"
                    r"i love|love (it|that)|juuri näin|hyvä idea|mahtava|loistava|hienoa|das (ist|sind) (gut|toll|super)|gute idee|"
                    r"det lyder|god idé|いいですね|素晴らしい|perfect|brilliant|wonderful)", re.I)
BUZZ = re.compile(r"\b(leverag\w*|seamless\w*|robust\w*|ensur\w*|optimi[sz]\w*|streamlin\w*|harness\w*|cutting[- ]edge|delv\w*|"
                  r"empower\w*|synerg\w*)\b", re.I)
PHYSICAL = re.compile(r"\b(gestur\w*|point\w*|star(e|es|ing)|looks?|looking|lean\w*|typ(ing|es)|grab\w*|walk\w*|nod\w*|shrug\w*|"
                      r"crouch\w*|adjust\w*|wav(es|ing)|glanc\w*|scratch\w*|sit(s|ting)?|stand(s|ing)?|hands?|eyes?|fingers?)\b", re.I)
SCRIPTS = {"ja": r"[぀-ヿ一-鿿]", "ko": r"[가-힯]", "el": r"[Ͱ-Ͽ]", "hi": r"[ऀ-ॿ]"}


STAGE = re.compile(r"\([^)]{1,40}\)|\*[^*]{1,40}\*")  # "(fast) Ship it." / "*laughs*" — seen 15 Nov


def clean_line(line: str) -> str:
    """Drop stage directions the writer smuggled into the spoken text; voice tags in [brackets] stay."""
    return re.sub(r"\s+", " ", STAGE.sub("", line)).strip(" -–—")


def words(line: str) -> float:
    clean = TAG.sub("", line)
    cjk = len(re.findall(r"[぀-ヿ一-鿿가-힯]", clean))
    return len(clean.split()) + cjk / 2.5 if cjk else float(len(clean.split()))


def borrows(anchor: str, line: str) -> bool:
    """True when the line lifts a chunk of an example line (4 words, or 8 characters in CJK) — 15 Nov: Wendy glued
    two anchors together, Ignite paraphrased 'talvez até terça'; whole-line similarity missed both."""
    a, l = TAG.sub("", anchor).casefold(), TAG.sub("", line).casefold()
    if re.search(r"[぀-ヿ一-鿿가-힯]", a):
        a, l = re.sub(r"\W", "", a), re.sub(r"\W", "", l)
        return any(a[i:i + 8] in l for i in range(max(0, len(a) - 7)))
    aw, lw = re.findall(r"\w+", a), " ".join(re.findall(r"\w+", l))
    if any(" ".join(aw[i:i + 4]) in lw for i in range(max(0, len(aw) - 3))):
        return True
    # A distinctive three-word chunk (two of its words 5+ letters) counts as a lift too.
    return any(sum(len(w) >= 5 for w in aw[i:i + 3]) >= 2 and f" {' '.join(aw[i:i + 3])} " in f" {lw} "
               for i in range(max(0, len(aw) - 2)))


_NAMES: set[str] = set()


def name_words() -> set[str]:
    """Lower-case words of every pet name ('rokoko', 'aalto', 'bahn', …): an address like 'Aiven,' is not a tic."""
    if not _NAMES:
        _NAMES.update(w for s in pv.all_pet_slugs() for w in re.findall(r"\w+", pv.persona(s)["name"].casefold()))
    return _NAMES


def interjection(text: str) -> str:
    """The one-word exclamation a line opens with ('Fascinating.', 'Nå,', 'Achtung:', 'えっ、'), or ''."""
    m = re.match(r"^\s*(\w{1,14})\s*[.,!:;…、。！]", TAG.sub("", text))
    return m.group(1).casefold() if m else ""


def stems(text: str) -> set[str]:
    """Content-word stems (first five letters of 5+ letter words) — enough to see a pet reheating its own line."""
    return {w[:5] for w in re.findall(r"\w+", TAG.sub("", text).casefold()) if len(w) >= 5 and not w.isdigit()}


def _norm(s: str) -> str:
    return "".join(ch for ch in s.casefold() if ch.isalnum())


def quoted_in(quote: str, refs: list[str]) -> bool:
    """Is `quote` (the writer's own claim of what it answers) really in one of the recent lines? Fuzzy, any script."""
    q = _norm(quote)
    if len(q) < 3:
        return False
    for r in map(_norm, refs):
        if q in r:
            return True
        m = difflib.SequenceMatcher(None, q, r).find_longest_match(0, len(q), 0, len(r))
        if m.size >= max(4, 0.6 * len(q)):
            return True
    return False


def check_reply(responds_to: str, refs: list[str], first: bool) -> list[str]:
    """15 Nov blind judge: v2's worst lines were comebacks that answer nothing ('That is a meeting disguised as a
    train'). The writer names what it reacts to; if that is not in the last lines, the line is a non-sequitur."""
    if first:
        return []
    if not responds_to.strip():
        return ["does not react to anything that was just said"]
    return [] if quoted_in(responds_to, refs) else ["reacts to something nobody just said (non-sequitur)"]


def opener(text: str) -> str:
    """First word (first two when it is a short word like 'I' or 'we') — repeated openers are a classic tic."""
    w = re.findall(r"\w+", TAG.sub("", text).casefold())
    return (w[0] if w and len(w[0]) >= 4 else " ".join(w[:2])) if w else ""


def check_line(slug: str, line: str, direction: str, lang: str, history: list[dict]) -> list[str]:
    """Deterministic rules the critic and the learning loop share. Empty list = clean."""
    c, problems = characters()[slug], []
    clean = TAG.sub("", line).strip()
    if not clean:
        return ["empty line"]
    if words(clean) > 30:
        problems.append("too long (over 30 words)")
    norm = lambda s: "".join(ch for ch in s.casefold() if ch.isalnum())  # noqa: E731
    if any(difflib.SequenceMatcher(None, norm(a), norm(clean)).ratio() > 0.8 or borrows(a, clean) for a in c["anchors"]):
        problems.append("reuses an example line")
    mine = [h for h in history if h["slug"] == slug]
    for cp in c.get("catchphrases", []):
        if cp.casefold() in clean.casefold() and any(cp.casefold() in h["text"].casefold() for h in mine):
            problems.append(f"catchphrase '{cp}' already used in this scene")
    if mine and opener(clean) and opener(clean) == opener(mine[-1]["text"]):
        problems.append("same opening words as your previous line")
    names = name_words()
    ij = interjection(clean)
    if ij and ij not in names and any(interjection(h["text"]) and interjection(h["text"]) not in names for h in mine):
        # 15 Nov: DeepMind swapped "Interesting." for "Fascinating." once the catchphrase was spent — same tic.
        problems.append("opens with a one-word exclamation again (a tic, even with a different word)")
    own = stems(clean) - {n[:5] for n in names}
    if any(len(own & stems(h["text"])) >= 2 for h in mine):
        # 15 Nov: NVIDIA said "ten thousand threads" twice in one scene.
        problems.append("reheats an idea from your own earlier line")
    tags = TAG.findall(line)
    if len(tags) > 1:
        problems.append("more than one voice tag")
    if tags and any(TAG.search(h["text"]) for h in history[-2:]):
        problems.append("voice tag budget: at most one tag per three lines")
    if STAGE.search(clean):
        problems.append("stage direction inside the spoken line")
    if PRAISE.match(clean):
        problems.append("opens with praise or validation")
    if BUZZ.search(clean):
        problems.append("buzzword")
    if clean.endswith(("?", "？")) and sum(h["text"].rstrip().endswith(("?", "？")) for h in history[-3:]) >= 2:
        problems.append("too many questions in a row")
    if PHYSICAL.search(direction or ""):
        problems.append("voice direction describes body movement; it must be vocal (pace, volume, pitch, emotion)")
    letters = [ch for ch in clean if ch.isalpha()]
    script = SCRIPTS.get(lang.split("-")[0])
    if script and letters and len(re.findall(script, clean)) < 0.5 * len(letters):
        problems.append("not written in the language's native script")
    if not script and letters and sum(ord(ch) > 0x24F for ch in letters) > 0.2 * len(letters):
        problems.append("unexpected script for the language")
    return problems


# ---------------------------------------------------------------- director ---
DIRECT_SCHEMA = {"type": "OBJECT", "properties": {"next": {"type": "STRING"}, "move": {"type": "STRING"}, "why": {"type": "STRING"}},
                 "required": ["next", "move"]}


DUET_MAX = 4      # A-B-A-B may run; the fifth line must be a third voice
SOLO_MAX = 3      # nobody past three lines while someone in the cast is still silent


def blocked(cast: list[str], history: list[dict], counts: dict) -> set[str]:
    """Who may not speak next. v2 let Arduino and Atech ping-pong for seven lines while others waited; v2b blocked
    every A-B-A and lost 0/2 blind to it — strict rotation turned the scene back into one-liners nobody answered.
    So an argument may run for DUET_MAX lines, then a third voice has to enter it."""
    if not history:
        return set()
    block = {history[-1]["slug"]}
    tail = [h["slug"] for h in history[-DUET_MAX:]]
    if len(tail) == DUET_MAX and len(set(tail)) == 2:
        block |= set(tail)
    if any(counts[s] == 0 for s in cast):
        block |= {s for s in cast if counts[s] >= SOLO_MAX}
    return block if set(cast) - block else {history[-1]["slug"]}


def fallback_next(cast: list[str], history: list[dict], counts: dict, rng: random.Random) -> str:
    last = history[-1] if history else None
    block = blocked(cast, history, counts)
    if last:
        called = [s for s in cast if s not in block and pv._norm_name(pv.persona(s)["name"]) in pv._norm_name(last["text"])]
        if called:
            return called[0]
    pool = [s for s in cast if s not in block]
    least = min(counts[s] for s in pool)
    return rng.choice([s for s in pool if counts[s] == least])


def direct(scene: dict, history: list[dict], counts: dict, turns_left: int, key: str, log: list, rng: random.Random) -> dict:
    cast, last = scene["cast"], (history[-1]["slug"] if history else None)
    unspoken = [s for s in cast if counts[s] == 0 and s != last]
    if unspoken and len(unspoken) >= turns_left:
        return {"next": rng.choice(unspoken), "move": "react", "why": "everyone speaks at least once", "by": "rule"}
    if not history:
        return {"next": scene["opener"], "move": "react", "why": "scene opener", "by": "rule"}
    block = blocked(cast, history, counts)
    roster = "\n".join(f"- {s}: {pv.persona(s)['name']} — {characters()[s]['core'].split('.')[0]}" for s in cast)
    recent = "\n".join(f"{h['name']}: {h['heardText']}" for h in history[-6:])
    prompt = (f"You direct a scene between companion characters. Scene: {scene['setup']}\nCast:\n{roster}\n"
              f"Lines so far (latest last):\n{recent}\nTimes spoken: {json.dumps(counts)}. Turns left: {turns_left}.\n"
              f"Who would most naturally speak next, and with what move ({', '.join(MOVES)})? Not allowed next: "
              f"{', '.join(sorted(block))}. Let a good argument run for a few exchanges; when it peaks, bring in a third "
              "voice who takes a side, twists it or undercuts it — never someone who changes the topic to their own thing. "
              "Prefer whoever was just addressed, contradicted or teased; let quiet characters in; vary the moves. "
              + ("This is the last line: use 'wrap up'." if turns_left == 1 else "") + " Answer with the cast id in `next`.")
    try:
        data, model, _ = gen_json("You are a sharp, economical scene director.", [{"text": prompt}], DIRECT_SCHEMA, key, log, 0.7)
        nxt = str(data.get("next", "")).strip()
        by_name = {pv.persona(s)["name"].casefold(): s for s in cast}
        nxt = nxt if nxt in cast else by_name.get(nxt.casefold(), "")
        move = str(data.get("move", "react")).strip().lower()
        move = move if move in MOVES else (difflib.get_close_matches(move, MOVES, 1) or ["react"])[0]
        if nxt and nxt not in block:
            return {"next": nxt, "move": "wrap up" if turns_left == 1 else move, "why": str(data.get("why", ""))[:120], "by": model}
    except pv.ProviderError:
        pass
    return {"next": fallback_next(cast, history, counts, rng), "move": "wrap up" if turns_left == 1 else rng.choice(MOVES[:7]),
            "why": "fallback", "by": "rule"}


# ------------------------------------------------------------ writer/critic ---
RESPONDS = ("Copy 2-6 words, in their original language and script, of the line or event your line reacts to — "
            "normally the last line. Empty only when you speak first.")
LINE_SCHEMA = {"type": "OBJECT", "properties": {
    "heard": {"type": "STRING", "description": "Exact transcript of the attached audio in its original language and script; empty if no audio."},
    "heard_language": {"type": "STRING", "description": "BCP-47 code of what you heard, or empty."},
    "line": {"type": "STRING", "description": "What you say out loud."},
    "voice_direction": {"type": "STRING", "description": "3-8 words: pace, volume, pitch, emotion."},
    "responds_to": {"type": "STRING", "description": RESPONDS},
    "callback": {"type": "INTEGER", "description": "Number of the remembered callback your line uses, or 0 (most lines: 0)."}},
    "required": ["heard", "heard_language", "line", "voice_direction", "responds_to", "callback"]}
CRITIC_SCHEMA = {"type": "OBJECT", "properties": {
    "verdict": {"type": "STRING", "enum": ["keep", "rewrite"]}, "problems": {"type": "ARRAY", "items": {"type": "STRING"}},
    "line": {"type": "STRING"}, "voice_direction": {"type": "STRING"}, "responds_to": {"type": "STRING", "description": RESPONDS}},
    "required": ["verdict", "problems", "line", "voice_direction", "responds_to"]}


HARD_PROBLEMS = ("reuses an example line", "catchphrase '", "stage direction", "not written in the language's native script",
                 "unexpected script", "reacts to something nobody", "does not react", "opens with a one-word exclamation again")
CALLBACK_USES = 2   # a remembered note may be called back twice, then it is retired (15 Nov: Rokoko's waltz every scene)


def offered_callbacks(slug: str, memory: dict, history: list[dict]) -> list[dict]:
    """Up to three live memory notes for this pet; none once it has made its one callback in this scene."""
    if any(h["slug"] == slug and h.get("callbackNote") for h in history):
        return []
    used = {h.get("callbackNote") for h in history}
    return [n for n in memory.get("pets", {}).get(slug, []) if n.get("uses", 0) < CALLBACK_USES and n["note"] not in used][-3:]


def reply_refs(scene: dict, history: list[dict]) -> list[str]:
    """What a line may answer: the last two lines and the beat that just happened."""
    n, beats = len(history), scene.get("beats", {})
    return [h.get("heardText") or h["text"] for h in history[-2:]] + [b for k, b in beats.items() if n - 1 <= int(k) <= n]


def critique(slug: str, lang: str, history: list[dict], line: str, direction: str, problems: list[str], key: str, log: list) -> dict:
    c, p = characters()[slug], pv.persona(slug)
    recent = "\n".join(f"{h['name']}: {h['heardText']}" for h in history[-4:]) or "(scene start)"
    prompt = (f"Character: {p['name']} — {c['core']} Speaks: {c['speech']} Language: {pv.lang_name(lang)} ({lang}).\n"
              f"Last lines:\n{recent}\n\nDraft line: {line}\nDraft voice direction: {direction}\n"
              f"Automatic checks found: {'; '.join(problems) or 'nothing'}.\n"
              + ("Every listed problem is a must-fix: verdict 'keep' is not allowed. A near-synonym of a spent catchphrase "
                 "or a light paraphrase of an example line is still the same tic.\n" if problems else "")
              + "Keep the draft if it is good. Rewrite only to fix the listed problems, incoherence with the last line, written-sounding "
              "or translated-sounding phrasing, generic AI or brochure tone, or wrong language/script. Stay in character, stay short, "
              "add no new facts, keep at most one voice tag. The voice direction must be vocal only (pace, volume, pitch, emotion). "
              "A line must answer something in the last lines; put the words it answers, copied from there, in `responds_to`.")
    data, model, _ = gen_json("You are a ruthless script editor who protects each character's voice and hates generic AI dialogue.",
                              [{"text": prompt}], CRITIC_SCHEMA, key, log, 0.4)
    return {**data, "model": model}


def write_turn(scene: dict, slug: str, move: str, history: list[dict], audio: bytes | None, memory: dict, key: str,
               log: list, use_critic: bool = True) -> dict:
    lang = pv.load_voices()[slug]["language"]
    offered = offered_callbacks(slug, memory, history)
    system = system_prompt(slug, scene["cast"], lang, [n["note"] for n in offered], memory.get("openers", {}).get(slug, []),
                           worn_words(slug, memory))
    refs, first = reply_refs(scene, history), not history
    beats = scene.get("beats", {})
    lines = []
    for h in history[:-1] if audio else history:
        lines.append(f"{h['name']}: {h['heardText']}")
        if str(h["turn"] + 1) in beats:
            lines.append(f"[{beats[str(h['turn'] + 1)]}]")
    who = pv.persona(slug)["name"]
    if history and audio:
        last = history[-1]
        ask = (f"The attached audio is what {last['name']} just said. Transcribe it exactly into `heard`, then reply as {who}.")
    elif history:
        ask = f"Reply as {who}."
    else:
        ask = f"You speak first. Start the scene as {who}."
    if history and str(history[-1]["turn"] + 1) in beats:
        ask = f"[{beats[str(history[-1]['turn'] + 1)]}] " + ask
    if history and not any(h["slug"] == slug for h in history):
        ask += (f" This is your first line here: come in on what {history[-1]['name']} just said — take a side, twist it "
                "or undercut it. Do not open a topic of your own.")
    prompt = (f"Scene: {scene['setup']}\nIn the room: {', '.join(pv.persona(s)['name'] for s in scene['cast'])}.\n"
              + (("Conversation so far:\n" + "\n".join(lines) + "\n") if lines else "")
              + f"Director's note for this line: {move}.\n{ask}")
    parts = ([{"inlineData": {"mimeType": "audio/wav", "data": base64.b64encode(audio).decode()}}] if audio else []) + [{"text": prompt}]
    data, model, latency = gen_json(system, parts, LINE_SCHEMA, key, log)
    raw_line = re.sub(r"\s+", " ", str(data.get("line", ""))).strip()
    draft = {"line": clean_line(raw_line) or raw_line, "voice_direction": str(data.get("voice_direction", "")).strip(),
             "responds_to": str(data.get("responds_to", "")).strip()}
    problems = (check_line(slug, draft["line"], draft["voice_direction"], lang, history)
                + check_reply(draft["responds_to"], refs, first))
    final, critic = dict(draft), None
    if use_critic:
        # A second critic round only when a hard problem survived the first (verbatim example line, spent catchphrase,
        # stage direction, wrong script): the v2b robot-dog opener kept Wendy's anchor word for word.
        for attempt in range(2):
            if attempt and not any(p.startswith(HARD_PROBLEMS) for p in problems):
                break
            try:
                critic = critique(slug, lang, history, final["line"], final["voice_direction"], problems, key, log)
            except pv.ProviderError:
                critic = critic or {"verdict": "unavailable"}
                break
            if critic.get("verdict") == "rewrite" and str(critic.get("line", "")).strip():
                cand = {"line": clean_line(critic["line"]) or critic["line"].strip(),
                        "voice_direction": str(critic.get("voice_direction") or final["voice_direction"]).strip(),
                        "responds_to": str(critic.get("responds_to") or final["responds_to"]).strip()}
                cand_problems = (check_line(slug, cand["line"], cand["voice_direction"], lang, history)
                                 + check_reply(cand["responds_to"], refs, first))
                if len(cand_problems) <= len(problems):
                    final, problems = cand, cand_problems
            critic["rounds"] = attempt + 1
    try:
        k = int(data.get("callback") or 0)
    except (TypeError, ValueError):
        k = 0
    return {"heard": str(data.get("heard", "")).strip(), "heardLanguage": str(data.get("heard_language", "")).strip(),
            "draft": draft, "critic": critic, "line": final["line"], "voiceDirection": final["voice_direction"],
            "respondsTo": final["responds_to"], "callbackNote": offered[k - 1]["note"] if 1 <= k <= len(offered) else None,
            "problems": problems, "writer": model, "writerLatencyS": latency, "language": lang}


# ------------------------------------------------------------------- voice ---
def designed_voices() -> dict:
    try:
        return json.loads(DESIGNED_FILE.read_text()).get("voices", {})
    except (OSError, ValueError):
        return {}


def voice_for(slug: str) -> str:
    """The pet's designed voice unless the owner's blind A/B preferred the prebuilt one (taste.json)."""
    prebuilt, t = pv.load_voices()[slug]["voice"], taste()
    designed = designed_voices().get(slug, {})
    if t.get("voicePreference", {}).get(slug) == "prebuilt":
        return prebuilt
    # 👎 on the designed sample counts until the voice is redesigned (a newer createdAt than the rating).
    if t.get("voiceRating", {}).get(slug) == "down" and designed.get("createdAt", "") <= t.get("updatedAt", ""):
        return prebuilt
    return designed.get("id") or prebuilt


def speak_line(slug: str, text: str, direction: str, key: str, tts_order: list[str], log: list, prefer: dict) -> dict:
    """Own designed voice first; Live models only know prebuilt names, so they get the prebuilt fallback voice."""
    voice, prebuilt = voice_for(slug), pv.load_voices()[slug]["voice"]
    style = direction or characters()[slug]["delivery"]
    if voice.startswith("voice_"):
        # The model the voice was designed on goes first: the free tier gives each TTS model only ~10-15 calls a day,
        # so a designed id sent to a model that cannot use it burns quota for nothing.
        home = designed_voices().get(slug, {}).get("model")
        order = ([home] if home else []) + [m for m in tts_order if m != home and not m.startswith("live:")]
        try:
            out = pv.speak(text, voice, style, key, order, log, prefer)
            return {**out, "voiceUsed": voice}
        except pv.ProviderError:
            pass
    return {**pv.speak(text, prebuilt, style, key, tts_order, log, prefer), "voiceUsed": prebuilt}


def voice_script(lines: list[dict], run_id: str, prebuilt: bool = False, models: list[str] | None = None) -> list[dict]:
    """Voice a fixed transcript ([{slug, text, direction?}]) into a run folder listen.py can read — for baselines and
    voice A/B. Resumable: finished turns are kept. prebuilt=True skips the designed voice (Live fallback allowed);
    `models` pins the TTS models (a fair voice A/B uses the same model for both voices)."""
    key, learned = pv.read_key(), pv.load_learned()
    tts_order, prefer = models or pv.model_order(learned, "tts", pv.DEFAULT_TTS_MODELS, None), learned.get("ttsVariant") or {}
    turns_dir = pv.RUNS_DIR / run_id / "turns"
    turns_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for i, ln in enumerate(lines):
        tf, wf = turns_dir / f"{i:03d}.json", turns_dir / f"{i:03d}.wav"
        if tf.exists() and wf.exists() and json.loads(tf.read_text()).get("status") == "ok":
            out.append(json.loads(tf.read_text()))
            continue
        slug, log = ln["slug"], []
        p, style = pv.persona(slug), ln.get("direction") or characters()[slug]["delivery"]
        if prebuilt:
            spoken = {**pv.speak(ln["text"], pv.load_voices()[slug]["voice"], style, key, tts_order, log, prefer),
                      "voiceUsed": pv.load_voices()[slug]["voice"]}
        else:
            spoken = speak_line(slug, ln["text"], style, key, tts_order, log, prefer)
        wf.write_bytes(spoken["wav"])
        turn = {"turn": i, "slug": slug, "speakerSlug": slug, "name": p["name"], "speakerName": p["name"],
                "language": pv.load_voices()[slug]["language"], "text": ln["text"], "style": style, "status": "ok",
                "voice": spoken["voiceUsed"], "ttsModel": spoken["model"], "ttsSpoken": spoken.get("spoken"),
                "ttsFidelity": spoken.get("fidelity"), "audioSeconds": pv.wav_seconds(spoken["wav"]),
                "audioSha256": pv.sha256(spoken["wav"]), "ttsEvents": log}
        tf.write_text(json.dumps(turn, ensure_ascii=False, indent=1))
        print(f"[{i:02d}] {p['name']:<12} {spoken['model']:<40} {ln['text'][:60]}", flush=True)
        out.append(turn)
    return out


def api_post(path: str, body: dict, key: str, timeout: float = 120) -> dict:
    import urllib.error
    import urllib.request
    req = urllib.request.Request(f"{pv.API}/{path}", data=json.dumps(body).encode(),
                                 headers={"x-goog-api-key": key, "content-type": "application/json"}, method="POST")
    try:
        with urllib.request.build_opener(pv._NoRedirect()).open(req, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        raise pv.parse_error(e.code, e.read())
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise pv.ProviderError(0, "NETWORK", type(e).__name__)


def design_voices(slugs: list[str], force: bool = False, model: str = "gemini-3.8-flash-tts") -> dict:
    """Create one persistent Gemini voice per pet from its voice_design description (POST /v1beta/voices)."""
    key, voices = pv.read_key(), pv.load_voices()
    store = {"schema": "junction.pet-voice.designed-voices/v1", "voices": designed_voices()}
    samples = pv.RUNS_DIR.parent / "voices"
    samples.mkdir(parents=True, exist_ok=True)
    report = {"created": [], "skipped": [], "failed": []}
    for slug in slugs:
        if slug in store["voices"] and not force:
            report["skipped"].append(slug)
            continue
        c, lang = characters()[slug], voices[slug]["language"]
        desc = c["voice_design"]
        gender = "female" if re.search(r"\bwoman\b", desc, re.I) else "male" if re.search(r"\bman\b", desc, re.I) else None
        owner = taste().get("pets", {}).get(slug, {}).get("voiceNotes", [])[-2:]
        prompt = f"{desc} Baseline delivery: {c['delivery']}." + (f" The listener's notes on the last voice: {' / '.join(owner)}" if owner else "")
        voice = {"model": model, "type": "prompted", "display_name": f"Junction {pv.persona(slug)['name']}",
                 "language_code": lang, "prompted": {"input": prompt}}
        if gender:
            voice["gender"] = gender
        try:
            resp = api_post("voices", {"store": True, "voice": voice}, key)
        except pv.ProviderError as e:
            report["failed"].append({"pet": slug, **e.record(model)})
            if e.status == 429 or e.status in (401, 403):
                break
            continue
        vid = resp.get("id") or str(resp.get("name", "")).removeprefix("voices/")
        if not vid:
            report["failed"].append({"pet": slug, "status": 200, "code": "NO_ID", "message": json.dumps(resp)[:160]})
            continue
        audio = (resp.get("sample_audio") or resp.get("sampleAudio") or {}).get("data")
        if audio:
            (samples / f"{slug}.wav").write_bytes(pv.normalize_audio(base64.b64decode(audio)))
        store["voices"][slug] = {"id": vid, "model": model, "language": lang, "createdAt": now(),
                                 "descriptionSha256": pv.sha256(desc.encode())}
        DESIGNED_FILE.parent.mkdir(parents=True, exist_ok=True)
        DESIGNED_FILE.write_text(json.dumps(store, ensure_ascii=False, indent=1) + "\n")
        report["created"].append(slug)
        print(f"  designed {slug}: {vid}", flush=True)
    return report


# ------------------------------------------------------------------ memory ---
MEMORY_SCHEMA = {"type": "OBJECT", "properties": {"notes": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
    "pet": {"type": "STRING"}, "note": {"type": "STRING"}}, "required": ["pet", "note"]}}}, "required": ["notes"]}


def remember(scene_id: str, scene: dict, history: list[dict], key: str, log: list) -> list[dict]:
    transcript = "\n".join(f"{h['slug']} ({h['name']}): {h['text']}" for h in history)
    mem = load_memory()
    known = "\n".join(f"{s}: {n['note']}" for s in scene["cast"] for n in mem.get("pets", {}).get(s, []))
    prompt = (f"Scene: {scene['setup']}\n{transcript}\n\nFor up to five characters, write one continuity note each (max 18 words, "
              "English): a running joke, a grudge, a promise, a nickname or a changed relationship that a later scene could call "
              "back to. Use the cast id in `pet`. Only things that actually happened above. A note that only restates a known "
              "note is worthless — skip that character instead.\nKnown notes:\n" + (known or "(none)"))
    data, _, _ = gen_json("You keep continuity notes for a recurring cast.", [{"text": prompt}], MEMORY_SCHEMA, key, log, 0.5)
    mem, notes = load_memory(), []
    for n in data.get("notes", [])[:5]:
        pet = str(n.get("pet", "")).strip()
        text = str(n.get("note", "")).strip()[:160]
        old = [o["note"] for o in mem.get("pets", {}).get(pet, [])]
        if pet in scene["cast"] and text and not any(difflib.SequenceMatcher(None, text.casefold(), o.casefold()).ratio() > 0.6
                                                     for o in old):
            entry = {"scene": scene_id, "note": text, "at": now(), "uses": 0}
            mem.setdefault("pets", {}).setdefault(pet, []).append(entry)
            notes.append({"pet": pet, **entry})
    for pet, lst in mem.get("pets", {}).items():   # retired callbacks leave; six live notes per pet
        mem["pets"][pet] = [o for o in lst if o.get("uses", 0) < CALLBACK_USES][-6:]
    save_memory(mem)
    return notes


def mark_callback(memory: dict, slug: str, note: str, run_id: str) -> None:
    """Count a callback in the in-scene memory and on disk, so the joke fades after CALLBACK_USES scenes."""
    disk = load_memory()
    for mem in (memory, disk):
        for n in mem.get("pets", {}).get(slug, []):
            if n["note"] == note:
                n["uses"], n["lastUsed"] = n.get("uses", 0) + 1, run_id
                break
    save_memory(disk)


def record_habits(history: list[dict], run_id: str = "") -> None:
    """Cross-scene tics: each pet's last eight line openings, and which content words it used in which of its last
    four scenes. Repeats become 'start differently' / 'find a fresh image' hints (15 Nov: Rokoko's three-quarter
    waltz, Atech's kettle and NVIDIA's ten thousand threads came back run after run)."""
    mem, names = load_memory(), name_words()
    for slug in dict.fromkeys(h["slug"] for h in history):
        lines = [h["text"] for h in history if h["slug"] == slug]
        for t in lines:
            first = interjection(t) or opener(t)
            if first and first not in names:
                lst = mem.setdefault("openers", {}).setdefault(slug, [])
                lst.append(first)
                del lst[:-8]
        if run_id:
            log = mem.setdefault("sceneLog", {}).setdefault(slug, [])
            if run_id not in log:
                log.append(run_id)
                del log[:-4]
            words = mem.setdefault("words", {}).setdefault(slug, {})
            for w in re.findall(r"\w+", TAG.sub("", " ".join(lines)).casefold()):
                if len(w) >= 5 and not w.isdigit() and w[:5] not in {n[:5] for n in names}:
                    e = words.setdefault(w[:5], {"w": w, "in": []})
                    if run_id not in e["in"]:
                        e["in"] = (e["in"] + [run_id])[-4:]
            for st in [st for st, e in words.items() if not set(e["in"]) & set(log)]:
                del words[st]
    save_memory(mem)


record_openers = record_habits   # older name used by tests and notes


def rebuild_memory() -> dict:
    """Notes: keep the newest of any near-duplicates per pet. Habits: replay every complete scene receipt in time order."""
    mem = load_memory()
    for pet, lst in mem.get("pets", {}).items():
        kept: list[dict] = []
        for n in reversed(lst):
            if not any(difflib.SequenceMatcher(None, n["note"].casefold(), k["note"].casefold()).ratio() > 0.6 for k in kept):
                kept.append(n)
        mem["pets"][pet] = list(reversed(kept))
    for k in ("openers", "sceneLog", "words"):
        mem.pop(k, None)
    save_memory(mem)
    runs = []
    for f in SCENE_EVIDENCE.glob("scene-*.json"):
        r = json.loads(f.read_text())
        if r.get("complete"):
            runs.append((r.get("finishedAt", ""), r["runId"], r["turns"]))
    for _, run_id, turns in sorted(runs):
        record_habits([{"slug": t["slug"], "text": t["text"]} for t in turns], run_id)
    return load_memory()


def worn_words(slug: str, memory: dict) -> list[str]:
    """Content words this pet used in two or more of its last four scenes, most used first."""
    log = set(memory.get("sceneLog", {}).get(slug, []))
    words = memory.get("words", {}).get(slug, {})
    signature = {w[:5] for cp in characters().get(slug, {}).get("catchphrases", []) for w in re.findall(r"\w+", cp.casefold())}
    hits = sorted(((len(set(e["in"]) & log), e["w"]) for st, e in words.items() if st not in signature), reverse=True)
    return [w for n, w in hits if n >= 2][:6]   # catchphrases keep their own once-per-scene budget


# ------------------------------------------------------------------- scene ---
def scene_metrics(history: list[dict]) -> dict:
    import persona_lab
    names = [pv.persona(s)["name"] for s in pv.all_pet_slugs()]
    base = persona_lab.slop_metrics([{"line": h["text"], "name": h["name"]} for h in history], names)
    n = len(history) or 1
    rewrites = [h for h in history if (h.get("critic") or {}).get("verdict") == "rewrite" and h["text"] != h["draft"]["line"]]
    slugs, duet = [h["slug"] for h in history], 0
    for i in range(len(slugs)):
        j = i
        while j + 1 < len(slugs) and len(set(slugs[i:j + 2])) <= 2:
            j += 1
        duet = max(duet, j - i + 1 if len(set(slugs[i:j + 1])) == 2 else 0)
    return {**base,
            "longestDuet": duet,
            "callbacks": sum(bool(h.get("callbackNote")) for h in history),
            "nonSequiturLines": sum(any("non-sequitur" in p or "does not react" in p for p in h.get("problems", [])) for h in history),
            "exclamationOpeners": sum(bool(interjection(h["text"])) and interjection(h["text"]) not in name_words() for h in history),
            "maxLineShare": round(max((slugs.count(s) for s in set(slugs)), default=0) / n, 3),
            "linesWithOpenProblems": sum(bool(h.get("problems")) for h in history),
            "openProblems": sorted({p for h in history for p in h.get("problems", [])}),
            "criticRewriteRate": round(len(rewrites) / n, 3),
            "directorFallbackRate": round(sum(h["director"]["by"] in ("rule",) for h in history[1:]) / max(1, n - 1), 3),
            "movesUsed": sorted({h["move"] for h in history}),
            "speakers": len({h["slug"] for h in history})}


def run_scene(scene_id: str, *, audio: bool, run_id: str, use_critic: bool = True, seed: int = 7, icloud: bool = True,
              remember_after: bool = True) -> dict:
    scene, key, rng = load("scenes.json")["scenes"][scene_id], pv.read_key(), random.Random(seed)
    memory, learned = load_memory(), pv.load_learned()
    tts_order, prefer = pv.model_order(learned, "tts", pv.DEFAULT_TTS_MODELS, None), learned.get("ttsVariant") or {}
    run_dir = pv.RUNS_DIR / run_id
    (run_dir / "turns").mkdir(parents=True, exist_ok=True)
    meta_file = run_dir / "run.json"
    if not meta_file.exists():
        meta_file.write_text(json.dumps({"runId": run_id, "kind": "scene", "scene": scene_id, "speakers": scene["cast"],
                                         "languageMode": "own", "startedAt": now(), "audio": audio, "openerText": None}, indent=1))
    history, counts = [], {s: 0 for s in scene["cast"]}
    for i in range(scene["turns"]):
        tf, wf = run_dir / "turns" / f"{i:03d}.json", run_dir / "turns" / f"{i:03d}.wav"
        if tf.exists():
            done = json.loads(tf.read_text())
            if done.get("status") == "ok" and (not audio or wf.exists()):
                history.append(done)
                counts[done["slug"]] += 1
                continue
        log: list = []
        d = direct(scene, history, counts, scene["turns"] - i, key, log, rng)
        slug, p = d["next"], pv.persona(d["next"])
        turn = {"turn": i, "turnId": f"{run_id}.t{i:03d}", "slug": slug, "name": p["name"], "speaker": p["id"], "speakerSlug": slug,
                "speakerName": p["name"], "to": None, "toName": None, "mustAddressNext": False,
                "inReplyTo": history[-1]["turnId"] if history else None, "move": d["move"], "director": d,
                "mindEvents": log, "ttsEvents": [], "voice": voice_for(slug),
                "envelope": {"protocol": "junction.pet-collaboration/v1+voice", "from": p["id"], "to": None,
                             "mode": "live-model-synthetic-dialogue", "hostAuthorization": False, "externalEffects": False}}
        try:
            prev_audio = (run_dir / "turns" / f"{i - 1:03d}.wav").read_bytes() if audio and i else None
            w = write_turn(scene, slug, d["move"], history, prev_audio, memory, key, log, use_critic)
            if history:
                prev = history[-1]
                heard = w["heard"] if audio and w["heard"] else prev["text"]
                prev["heardText"], prev["heardBy"] = heard, slug
                (run_dir / "turns" / f"{prev['turn']:03d}.json").write_text(json.dumps(prev, ensure_ascii=False, indent=1))
                turn.update({"heardFrom": prev["slug"], "heard": w["heard"] if audio else "", "heardLanguage": w["heardLanguage"],
                             "heardAccuracy": pv.heard_accuracy(prev.get("ttsSpoken") or prev["text"], w["heard"]) if audio else None})
            turn.update({"text": w["line"], "heardText": w["line"], "voiceDirection": w["voiceDirection"], "style": w["voiceDirection"],
                         "language": w["language"], "draft": w["draft"], "critic": w["critic"], "problems": w["problems"],
                         "respondsTo": w["respondsTo"], "callbackNote": w["callbackNote"],
                         "mindModel": w["writer"], "mindLatencyS": w["writerLatencyS"]})
            if w["callbackNote"]:
                mark_callback(memory, slug, w["callbackNote"], run_id)
            if audio:
                spoken = speak_line(slug, w["line"], w["voiceDirection"], key, tts_order, turn["ttsEvents"], prefer)
                wf.write_bytes(spoken["wav"])
                turn.update({"voice": spoken["voiceUsed"], "ttsModel": spoken["model"], "ttsVariant": spoken["variant"],
                             "ttsLatencyS": spoken["latency"], "ttsSpoken": spoken.get("spoken"), "ttsFidelity": spoken.get("fidelity"),
                             "audioSeconds": pv.wav_seconds(spoken["wav"]), "audioSha256": pv.sha256(spoken["wav"])})
            turn["status"] = "ok"
        except pv.ProviderError as e:
            turn.update({"status": "failed", "error": e.record("n/a")})
        tf.write_text(json.dumps(turn, ensure_ascii=False, indent=1))
        print(f"[{i:02d}] {turn['status']:6} {p['name']:<12} {d['move']:<16} {turn.get('text', '')[:80]}"
              + (f"  ⚠ {turn['problems']}" if turn.get("problems") else ""), flush=True)
        if turn["status"] != "ok":
            break
        history.append(turn)
        counts[slug] += 1
    complete = len(history) == scene["turns"]
    notes = []
    if complete and remember_after:
        record_habits(history, run_id)
        try:
            notes = remember(scene_id, scene, history, key, [])
        except pv.ProviderError:
            notes = []
    commit, _ = pv.source_commit()
    report = {"schema": "junction.pet-voice.scene/v2", "runId": run_id, "scene": scene_id, "audio": audio, "finishedAt": now(),
              "source": {"repository": "SalesSquad/junction-pets", "commit": commit}, "writers": WRITERS, "critic": use_critic,
              "complete": complete, "metrics": scene_metrics(history) if history else {}, "memoryNotes": notes,
              "turns": [{k: h.get(k) for k in ("turn", "name", "slug", "language", "move", "text", "voiceDirection", "respondsTo",
                                               "callbackNote", "director", "draft", "critic", "problems", "heard", "heardAccuracy",
                                               "voice", "ttsModel", "ttsFidelity")} for h in history]}
    SCENE_EVIDENCE.mkdir(parents=True, exist_ok=True)
    (SCENE_EVIDENCE / f"{run_id}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    if audio and complete:
        pv.finalize(run_dir, history, write_evidence=True, icloud=icloud)
        pv.cmd_learn(argparse.Namespace(no_registry=False))
    return report


def as_text(history: list[dict]) -> str:
    return "\n".join(f"{t['name']} ({t['language']}): {t['text']}" for t in history)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="play one or more scenes (comma list or 'all')")
    r.add_argument("scenes")
    r.add_argument("--text-only", action="store_true", help="no audio: fast iteration while TTS quota is out")
    r.add_argument("--no-critic", action="store_true")
    r.add_argument("--tag", default=datetime.now(timezone.utc).strftime("%Y%m%dt%H%Mz"))
    r.add_argument("--seed", type=int, default=7)
    r.add_argument("--no-icloud", action="store_true")
    r.add_argument("--no-memory", action="store_true", help="do not write continuity notes after the scene")
    dv = sub.add_parser("design-voices", help="create each pet's own Gemini voice (Voice design)")
    dv.add_argument("--pets", default="all")
    dv.add_argument("--force", action="store_true")
    dv.add_argument("--disliked", action="store_true", help="redesign the voices the owner rated 👎, using their notes")
    vs = sub.add_parser("voice-script", help="voice a fixed transcript into a run folder (baselines, voice A/B)")
    vs.add_argument("script", help="JSON: {lines: [{slug|name, text, direction?}]}")
    vs.add_argument("--run-id", required=True)
    vs.add_argument("--prebuilt", action="store_true", help="prebuilt voices only (Live fallback allowed)")
    vs.add_argument("--models", default="", help="comma list of TTS models to use, in order")
    m = sub.add_parser("memory", help="print continuity notes and habits")
    m.add_argument("--rebuild", action="store_true",
                   help="drop near-duplicate notes and rebuild opener/word habits from scene-evidence/ in time order")
    args = ap.parse_args(argv)
    if args.cmd == "voice-script":
        spec = json.loads(Path(args.script).read_text())
        by_name = {pv.persona(s)["name"].casefold(): s for s in pv.all_pet_slugs()}
        lines = [{**ln, "slug": ln.get("slug") or by_name[ln["name"].casefold()]} for ln in spec["lines"]]
        voice_script(lines, args.run_id, args.prebuilt, [m for m in args.models.split(",") if m] or None)
        return 0
    if args.cmd == "memory":
        if args.rebuild:
            rebuild_memory()
        print(json.dumps(load_memory(), ensure_ascii=False, indent=1))
        return 0
    if args.cmd == "design-voices":
        if args.disliked:
            slugs = [s for s, v in taste().get("voiceRating", {}).items() if v == "down"]
        else:
            slugs = pv.all_pet_slugs() if args.pets == "all" else [pv.resolve_slug(s) for s in args.pets.split(",")]
        print(json.dumps(design_voices(slugs, args.force or args.disliked), indent=1))
        return 0
    ids = list(load("scenes.json")["scenes"]) if args.scenes == "all" else args.scenes.split(",")
    summary = {}
    for sid in ids:
        rid = f"scene-{sid}-{'text' if args.text_only else 'voice'}-{args.tag}".lower()
        print(f"== {sid} ({rid})", flush=True)
        rep = run_scene(sid, audio=not args.text_only, run_id=rid, use_critic=not args.no_critic, seed=args.seed,
                        icloud=not args.no_icloud, remember_after=not args.no_memory)
        summary[sid] = {"complete": rep["complete"], **{k: rep["metrics"].get(k) for k in (
            "templateRate", "questionEndRate", "meanWords", "shortLineRate", "actingTagsUsed", "linesWithOpenProblems", "criticRewriteRate", "speakers")}}
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0 if all(v["complete"] for v in summary.values()) else 3


if __name__ == "__main__":
    sys.exit(main())
