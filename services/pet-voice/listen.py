#!/usr/bin/env python3
"""Blind listening page + taste learning.

build   Make a self-contained page folder (index.html + audio/*.mp3 + key.json) that plays
        scene pairs as X/Y in random order and voice pairs as A/B, and saves the owner's
        choices to the artifact's database (`db` capability; localStorage + copy fallback).
ingest  Turn exported ratings + the private key into learned/taste.json: which system won,
        liked/disliked lines per pet, preferred voice per pet and free-text notes. The scene
        engine reads taste.json on every line (scene.system_prompt) and voice_for() honours
        the voice preference — that is how the owner's ear trains the pets.
"""
from __future__ import annotations

import argparse
import html
import json
import random
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pet_voice as pv

HERE = Path(__file__).resolve().parent
TASTE_FILE = HERE / "learned" / "taste.json"


EXT = "mp3"   # artifact pages serve .mp3 as their own media; .m4a is refused (15 Nov)


def m4a(src: Path, dst: Path) -> None:
    """Encode a WAV for the page: MP3 64 kb/s with ffmpeg (the name stays for older callers)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-loglevel", "error", "-y", "-i", str(src), "-codec:a", "libmp3lame",
                    "-b:a", "64k", str(dst)], check=True, capture_output=True, timeout=120)


def load_run(run_id: str) -> list[dict]:
    turns = []
    for f in sorted((pv.RUNS_DIR / run_id / "turns").glob("*.json")):
        t = json.loads(f.read_text())
        if t.get("status") == "ok" and f.with_suffix(".wav").exists():
            turns.append(t)
    return turns


def build(scene_pairs: list[tuple[str, str, str, str, str]], voice_pairs: list[tuple[str, str, Path, str, Path, str]],
          out: Path, seed: int, samples: list[tuple[str, Path]] | None = None) -> dict:
    """scene_pairs: (pair_id, title, setup, runA_label:runA, runB_label:runB); voice_pairs: (pet, text, wavA, labelA, wavB, labelB);
    samples: (pet, wav) — one designed-voice sample per pet, rated 👍/👎 with an optional note."""
    rng = random.Random(seed)
    if out.exists():
        shutil.rmtree(out)
    (out / "audio").mkdir(parents=True)
    manifest = {"scenes": [], "voices": [], "samples": []}
    key = {"createdAt": datetime.now(timezone.utc).isoformat(), "scenes": {}, "voices": {}}
    for pet, wav in samples or []:
        rel = f"audio/sample-{pet}.{EXT}"
        m4a(wav, out / rel)
        manifest["samples"].append({"id": f"sample-{pet}", "pet": pet, "name": pv.persona(pet)["name"],
                                    "language": pv.load_voices()[pet]["language"], "audio": rel})
    for pair_id, title, setup, a, b in scene_pairs:
        arms = [tuple(a.split(":", 1)), tuple(b.split(":", 1))]
        rng.shuffle(arms)
        entry = {"id": pair_id, "title": title, "setup": setup, "versions": {}}
        for letter, (label, run_id) in zip("XY", arms):
            turns = load_run(run_id)
            lines = []
            for t in turns:
                rel = f"audio/{pair_id}-{letter}-{t['turn']:03d}.{EXT}"
                m4a(pv.RUNS_DIR / run_id / "turns" / f"{t['turn']:03d}.wav", out / rel)
                lines.append({"turn": t["turn"], "name": t.get("speakerName") or t.get("name"), "slug": t.get("speakerSlug") or t.get("slug"),
                              "language": t.get("language"), "text": t["text"], "audio": rel})
            full = out / "audio" / f"{pair_id}-{letter}.wav"
            full.write_bytes(pv.concat_wavs([(pv.RUNS_DIR / run_id / "turns" / f"{t['turn']:03d}.wav").read_bytes() for t in turns], 0.35))
            m4a(full, full.with_suffix(f".{EXT}"))
            full.unlink()
            entry["versions"][letter] = {"audio": f"audio/{pair_id}-{letter}.{EXT}", "lines": lines}
            key["scenes"].setdefault(pair_id, {})[letter] = {"label": label, "run": run_id}
        manifest["scenes"].append(entry)
    for pet, text, wav_a, label_a, wav_b, label_b in voice_pairs:
        opts = [(label_a, wav_a), (label_b, wav_b)]
        rng.shuffle(opts)
        item = {"id": f"voice-{pet}", "pet": pet, "name": pv.persona(pet)["name"], "text": text, "options": {}}
        for letter, (label, wav) in zip("AB", opts):
            rel = f"audio/voice-{pet}-{letter}.{EXT}"
            m4a(wav, out / rel)
            item["options"][letter] = rel
            key["voices"].setdefault(pet, {})[letter] = label
        manifest["voices"].append(item)
    (out / "index.html").write_text(PAGE.replace("__MANIFEST__", json.dumps(manifest, ensure_ascii=False).replace("</", "<\\/")))
    (out / "key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1))  # private: never published
    return {"scenes": len(manifest["scenes"]), "voices": len(manifest["voices"]), "samples": len(manifest["samples"]),
            "files": len(list((out / "audio").iterdir()))}


def ingest(ratings: list[dict], key: dict, manifest_lines: dict) -> dict:
    """ratings: [{id, choice, reasons, note, lines?:{turnKey: up|down}}]; returns the new taste.json content."""
    try:
        taste = json.loads(TASTE_FILE.read_text())
    except (OSError, ValueError):
        taste = {"schema": "junction.pet-voice.taste/v1", "pets": {}, "systems": {}, "voicePreference": {}, "notes": []}
    seen = taste.setdefault("ingested", {})   # id -> the rating's `at`: the page db keeps every rating, so re-ingesting is a no-op
    for r in ratings:
        rid, choice = r.get("id", ""), r.get("choice")
        stamp = r.get("at") or json.dumps(r, sort_keys=True, ensure_ascii=False)
        if seen.get(rid) == stamp:
            continue
        seen[rid] = stamp
        if rid in key.get("scenes", {}) and choice in ("X", "Y", "tie"):
            arms = key["scenes"][rid]
            if choice == "tie":
                for v in arms.values():
                    taste["systems"].setdefault(v["label"], {"wins": 0, "ties": 0, "losses": 0})["ties"] += 1
            else:
                win, lose = arms[choice]["label"], arms["Y" if choice == "X" else "X"]["label"]
                taste["systems"].setdefault(win, {"wins": 0, "ties": 0, "losses": 0})["wins"] += 1
                taste["systems"].setdefault(lose, {"wins": 0, "ties": 0, "losses": 0})["losses"] += 1
        if rid.startswith("voice-") and choice in ("A", "B"):
            pet = rid.removeprefix("voice-")
            taste["voicePreference"][pet] = key.get("voices", {}).get(pet, {}).get(choice)
        if rid.startswith("sample-"):
            # Designed-voice samples: 👎 sends the pet back to its prebuilt voice until the voice is redesigned with
            # the owner's note (scene.design_voices reads voiceNotes); the note stays with the pet, not the global notes.
            pet = rid.removeprefix("sample-")
            if choice in ("up", "down"):
                taste.setdefault("voiceRating", {})[pet] = choice
            note = str(r.get("note") or "").strip()
            if note:
                notes = taste["pets"].setdefault(pet, {"liked": [], "disliked": []}).setdefault("voiceNotes", [])
                if note not in notes:
                    notes.append(note[:300])
            continue
        for line_key, verdict in (r.get("lines") or {}).items():
            line = manifest_lines.get(line_key)
            if line and verdict in ("up", "down"):
                bucket = taste["pets"].setdefault(line["slug"], {"liked": [], "disliked": []})["liked" if verdict == "up" else "disliked"]
                if line["text"] not in bucket:
                    bucket.append(line["text"])
                    del bucket[:-6]
        note = str(r.get("note") or "").strip()
        if note and note not in taste["notes"]:
            taste["notes"].append(note[:300])
        for reason in r.get("reasons") or []:
            taste.setdefault("reasons", {}).setdefault(reason, 0)
            taste["reasons"][reason] += 1
    taste["updatedAt"] = datetime.now(timezone.utc).isoformat()
    TASTE_FILE.parent.mkdir(parents=True, exist_ok=True)
    TASTE_FILE.write_text(json.dumps(taste, ensure_ascii=False, indent=1) + "\n")
    return taste


PAGE = r"""<!DOCTYPE html>
<html lang="fi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Junction pets — sokkokuuntelu</title>
<style>
:root{--bg:#0e1013;--card:#171a1f;--ink:#eceef2;--mute:#9aa1ad;--line:#262a31;--accent:#8fb3ff;--good:#7bd88f;--bad:#ff8a80}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 -apple-system,BlinkMacSystemFont,"Inter",system-ui,sans-serif}
main{max-width:820px;margin:0 auto;padding:28px 18px 80px}h1{font-size:26px;margin:0 0 6px;letter-spacing:-.01em}
h2{font-size:15px;text-transform:uppercase;letter-spacing:.08em;color:var(--mute);margin:36px 0 12px}
.lead{color:var(--mute);margin:0 0 8px}.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px;margin:14px 0}
.setup{color:var(--mute);font-size:14px;margin:4px 0 14px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media(max-width:620px){.pair{grid-template-columns:1fr}}
.ver{border:1px solid var(--line);border-radius:12px;padding:12px}.ver b{font-size:20px}audio{width:100%;margin:8px 0}
button{font:inherit;color:var(--ink);background:#22262d;border:1px solid var(--line);border-radius:999px;padding:8px 14px;cursor:pointer}
button.on{background:var(--accent);color:#0b0d10;border-color:var(--accent)}.row{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}
.chip{font-size:13px;padding:5px 10px}textarea{width:100%;margin-top:10px;background:#111318;color:var(--ink);border:1px solid var(--line);border-radius:10px;padding:10px;font:inherit;min-height:60px}
details{margin-top:8px}summary{cursor:pointer;color:var(--accent);font-size:14px}.ln{display:grid;grid-template-columns:1fr auto;gap:8px;align-items:center;padding:8px 0;border-top:1px solid var(--line)}
.ln small{color:var(--mute)}.ln audio{margin:4px 0 0}.thumbs button{padding:4px 9px}.status{position:fixed;bottom:14px;left:50%;transform:translateX(-50%);background:#22262d;border:1px solid var(--line);border-radius:999px;padding:6px 14px;font-size:13px;color:var(--mute)}
</style></head><body><main>
<h1>Junction pets — sokkokuuntelu</h1>
<p class="lead">Kuuntele kohtaukset. X ja Y ovat eri järjestelmien versioita satunnaisessa järjestyksessä — et näe kumpi on kumpi. Valintasi opettavat petit. Kaikki äänet ovat tekoälyn (Gemini) tuottamia.</p>
<h2>Kohtaukset</h2><div id="scenes"></div>
<h2 class="vsec">Äänet</h2><p class="lead vsec">Sama repliikki kahdella äänellä. Kumpi sopii hahmolle paremmin?</p><div id="voices"></div>
<h2 class="ssec">Jokaisen petin oma ääni</h2><p class="lead ssec">Gemini Voice designilla tehty ääni jokaiselle petille. 👍 pitää, 👎 vaihtaa takaisin vanhaan ääneen kunnes ääni suunnitellaan uudelleen — kirjoita mitä haluaisit toisin.</p><div id="samples"></div>
<div class="status" id="status">Ladataan…</div>
<div class="card" id="fallback" hidden><p class="lead">Tallennus tietokantaan ei ole käytössä tässä näkymässä. Kopioi tulokset ja liitä ne Claudelle.</p><button id="copy">Kopioi tulokset</button></div>
</main>
<script>
const M = __MANIFEST__;
const REASONS = ["persoonallisempi","luontevampi","hauskempi","ääni sopii","vähemmän AI-maista","selkeämpi"];
const state = {}; let db = null;
const $ = (t, a = {}, ...k) => { const e = document.createElement(t); for (const [n, v] of Object.entries(a)) { if (n === "on") e.addEventListener("click", v); else if (n === "html") e.innerHTML = v; else e.setAttribute(n, v); } k.flat().forEach(c => e.append(c)); return e; };
const status = m => document.getElementById("status").textContent = m;
function local() { try { return JSON.parse(localStorage.getItem("pet-ratings") || "{}"); } catch (e) { return {}; } }
async function save(id) {
  const r = { ...state[id], id, at: new Date().toISOString() };
  try { localStorage.setItem("pet-ratings", JSON.stringify({ ...local(), [id]: r })); } catch (e) {}
  if (!db) { status("Tallennettu tähän selaimeen"); return; }
  try { await db.doc("ratings/" + id).set(r); status("Tallennettu ✓"); } catch (e) { status("Tallennus epäonnistui — käytä Kopioi"); document.getElementById("fallback").hidden = false; }
}
function choiceRow(id, opts) {
  const row = $("div", { class: "row" });
  opts.forEach(([val, label]) => row.append($("button", { "data-v": val, on: e => { state[id] = { ...(state[id] || {}), choice: val }; row.querySelectorAll("button").forEach(b => b.classList.toggle("on", b.dataset.v === val)); save(id); } }, label)));
  return row;
}
function reasonRow(id) {
  const row = $("div", { class: "row" });
  REASONS.forEach(r => row.append($("button", { class: "chip", on: e => { const s = state[id] = state[id] || {}; s.reasons = s.reasons || []; const i = s.reasons.indexOf(r); i < 0 ? s.reasons.push(r) : s.reasons.splice(i, 1); e.target.classList.toggle("on", i < 0); save(id); } }, r)));
  return row;
}
function render() {
  const sc = document.getElementById("scenes");
  M.scenes.forEach(s => {
    const pair = $("div", { class: "pair" });
    ["X", "Y"].forEach(L => {
      const v = s.versions[L], det = $("details", {}, $("summary", {}, "Repliikit"));
      v.lines.forEach(l => {
        const k = `${s.id}-${L}-${l.turn}`, th = $("div", { class: "thumbs row" });
        [["up", "👍"], ["down", "👎"]].forEach(([val, ic]) => th.append($("button", { on: e => { const st = state[s.id] = state[s.id] || {}; st.lines = st.lines || {}; st.lines[k] = val; th.querySelectorAll("button").forEach(b => b.classList.remove("on")); e.target.classList.add("on"); save(s.id); } }, ic)));
        det.append($("div", { class: "ln" }, $("div", {}, $("small", {}, `${l.name} · ${l.language}`), $("div", {}, l.text), $("audio", { controls: "", preload: "none", src: l.audio })), th));
      });
      pair.append($("div", { class: "ver" }, $("b", {}, L), $("audio", { controls: "", preload: "none", src: v.audio }), det));
    });
    const note = $("textarea", { placeholder: "Mikä toimi, mikä ei? (vapaaehtoinen)" });
    note.addEventListener("change", () => { state[s.id] = { ...(state[s.id] || {}), note: note.value }; save(s.id); });
    sc.append($("div", { class: "card" }, $("b", {}, s.title), $("div", { class: "setup" }, s.setup), pair,
      choiceRow(s.id, [["X", "X parempi"], ["tie", "Yhtä hyvät"], ["Y", "Y parempi"]]), reasonRow(s.id), note));
  });
  const vo = document.getElementById("voices");
  M.voices.forEach(v => vo.append($("div", { class: "card" }, $("b", {}, v.name), $("div", { class: "setup" }, `“${v.text}”`),
    $("div", { class: "pair" }, ...["A", "B"].map(L => $("div", { class: "ver" }, $("b", {}, L), $("audio", { controls: "", preload: "none", src: v.options[L] })))),
    choiceRow(v.id, [["A", "A sopii paremmin"], ["B", "B sopii paremmin"]]))));
  if (!M.voices.length) document.querySelectorAll(".vsec").forEach(e => e.hidden = true);
  if (!(M.samples || []).length) document.querySelectorAll(".ssec").forEach(e => e.hidden = true);
  const sa = document.getElementById("samples");
  (M.samples || []).forEach(v => {
    const note = $("input", { placeholder: "Mitä toisin? (vapaaehtoinen)", style: "width:100%;margin-top:8px;background:#111318;color:var(--ink);border:1px solid var(--line);border-radius:10px;padding:8px;font:inherit" });
    note.addEventListener("change", () => { state[v.id] = { ...(state[v.id] || {}), note: note.value }; save(v.id); });
    sa.append($("div", { class: "card" }, $("b", {}, v.name), $("small", { style: "color:var(--mute);margin-left:8px" }, v.language),
      $("audio", { controls: "", preload: "none", src: v.audio }), choiceRow(v.id, [["up", "👍 sopii"], ["down", "👎 ei sovi"]]), note));
  });
  document.getElementById("copy").addEventListener("click", async () => { try { await navigator.clipboard.writeText(JSON.stringify(Object.values({ ...local(), ...state }))); status("Kopioitu"); } catch (e) { status("Kopiointi estetty"); } });
}
render();
status("Valmis — valintasi tallentuvat");
(async () => {
  const timer = setTimeout(() => { if (!db) { status("Tallennus vain tähän selaimeen"); document.getElementById("fallback").hidden = false; } }, 10000);
  try { db = window.claude && await window.claude.use("db"); } catch (e) { db = null; }
  clearTimeout(timer);
  if (!db) { document.getElementById("fallback").hidden = false; status("Tallennus vain tähän selaimeen"); }
})();
</script></body></html>
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--spec", required=True, help="JSON: {scenes:[[id,title,setup,'label:run','label:run']], voices:[[pet,text,wavA,labelA,wavB,labelB]]}")
    b.add_argument("--out", required=True)
    b.add_argument("--seed", type=int, default=20261115)
    i = sub.add_parser("ingest")
    i.add_argument("--ratings", required=True, help="JSON list exported from the page or the artifact db")
    i.add_argument("--key", required=True)
    i.add_argument("--manifest-dir", required=True, help="the built page folder (for line texts)")
    args = ap.parse_args(argv)
    if args.cmd == "build":
        spec = json.loads(Path(args.spec).read_text())
        voices = [(p, t, Path(a), la, Path(bb), lb) for p, t, a, la, bb, lb in spec.get("voices", [])]
        samples = [(p, Path(w)) for p, w in spec.get("samples", [])]
        print(json.dumps(build([tuple(s) for s in spec["scenes"]], voices, Path(args.out), args.seed, samples), indent=1))
        return 0
    page = (Path(args.manifest_dir) / "index.html").read_text()
    manifest = json.loads(page.split("const M = ", 1)[1].split(";\nconst REASONS", 1)[0].replace("<\\/", "</"))
    lines = {f"{s['id']}-{L}-{l['turn']}": l for s in manifest["scenes"] for L, v in s["versions"].items() for l in v["lines"]}
    raw = json.loads(Path(args.ratings).read_text())
    ratings = [r.get("data", r) for r in (raw if isinstance(raw, list) else raw.get("documents", []))]
    taste = ingest(ratings, json.loads(Path(args.key).read_text()), lines)
    print(json.dumps({"systems": taste.get("systems"), "voicePreference": taste.get("voicePreference"), "notes": len(taste.get("notes", []))},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
