"""Junction pets — demo video builder. Frames: HTML -> PNG (Playwright, 1920x1080). Video: one still per slide
(ffmpeg, fades inside each file), concat -c copy. Audio: one track composed in numpy, muxed with -c:v copy.

Usage: python3 build.py [--audio DIR] [--scene-audio DIR] [--out DIR]
  --audio        folder with the listening-page media (night-crash-X/Y-NNN.*, sample-<pet>.*): `listen.py build` output
  --scene-audio  folder with the scene's own voicing, NNN.mp3|wav (+ NNN.json turn receipts), e.g. a run's turns/ folder
                 or its WAVs as MP3; without it the scene plays the page's Live prebuilt voicing (night-crash-Y-NNN)
  --out          working folder (frames/, segs/, the finished junction-pets-demo.mp4)
Needs ffmpeg, numpy, Playwright + Chrome (CHROME_PATH, else Playwright's own Chromium), and the Inter and
Noto Sans CJK fonts. The committed junction-pets-demo.mp4 was built on 16 Nov 2026: night listening page +
--scene-audio from run v2-demo-crash-0312-designed-20261115 (designed voices, Gemini 3.8 Flash Lite TTS)."""
import argparse, html, json, os, subprocess, sys, wave
from pathlib import Path
import numpy as np

W, H, FPS, SR = 1920, 1080, 30, 48000
_ap = argparse.ArgumentParser(add_help=False)
_ap.add_argument("--audio", default=os.environ.get("PET_DEMO_AUDIO", str(Path.home() / "Library/Application Support/JunctionPetVoice/listen-work/page-night/audio")))
_ap.add_argument("--scene-audio", default=os.environ.get("PET_DEMO_SCENE_AUDIO"))
_ap.add_argument("--out", default=os.environ.get("PET_DEMO_OUT", "/tmp/junction-pets-demo"))
_args, _rest = _ap.parse_known_args()
ROOT, AUD = Path(_args.out), Path(_args.audio)
SCENE_AUD = Path(_args.scene_audio) if _args.scene_audio else None
FR, SEG = ROOT / "frames", ROOT / "segs"
FR.mkdir(parents=True, exist_ok=True)
SEG.mkdir(parents=True, exist_ok=True)


def media(stem: str, folder: Path | None = None) -> Path:
    """The page's clip in whatever format listen.py wrote (.mp3 now, .m4a before 15 Nov)."""
    folder = folder or AUD
    for ext in ("mp3", "m4a", "wav"):
        if (folder / f"{stem}.{ext}").exists():
            return folder / f"{stem}.{ext}"
    raise SystemExit(f"missing audio clip {stem}.* in {folder}")


def scene_clip(i: int) -> Path:
    return media(f"{i:03d}", SCENE_AUD) if SCENE_AUD else media(f"night-crash-Y-{i:03d}")


def model_name(model: str) -> str:
    """gemini-3.8-flash-lite-tts -> Gemini 3.8 Flash Lite TTS"""
    return " ".join({"gemini": "Gemini", "tts": "TTS"}.get(w, w.capitalize() if w.isalpha() else w) for w in model.split("-"))


def scene_voicing() -> str:
    """How the scene on screen was voiced, from the turn receipts when --scene-audio has them."""
    if not SCENE_AUD:
        return "voiced with Gemini Live native audio"
    models = {json.loads(f.read_text()).get("ttsModel", "") for f in SCENE_AUD.glob("*.json")}
    models.discard("")
    return "each pet in its own designed voice" + (f" · {', '.join(model_name(m) for m in sorted(models))}" if models else "")

PETS = {
    "bahn-express": ("Bahn", "de-DE", "German", "#e85d5d", "B"),
    "openai-codex": ("Codex", "en-US", "English (US)", "#5fb3a1", "C"),
    "google-deepmind": ("DeepMind", "en-GB", "English (UK)", "#7a9cff", "D"),
    "aalto-university": ("Aalto", "fi-FI", "Finnish", "#f2c14e", "A"),
    "rokoko": ("Rokoko", "da-DK", "Danish", "#c77dff", "R"),
    "featherless": ("Featherless", "ja-JP", "Japanese", "#ff9f6e", "F"),
}
CAST = list(PETS)

SCENE = [  # v2 scene engine, demo-crash-0312 (text run v2; voicing from --scene-audio, else the page's Live prebuilt clips)
    ("bahn-express", "Es ist 03:12. Codex hinkt hinter dem Fahrplan. Achtung.", "It's 03:12. Codex is behind schedule. Attention.", None),
    ("openai-codex", "Schedule's a rumor anyway. Hand me that stack trace.", None, None),
    ("google-deepmind", "Fascinating. What falsifies the telemetry?", None, None),
    ("aalto-university", "Mä en tiiä mut se kaatu taas suoraan kahvikuppiin.", "Dunno, but it crashed straight into the coffee cup again.", None),
    ("rokoko", "Nå, så du det ryk? Det der er en waltz i tre fjerdedele.", "Well, did you see that twitch? That's a waltz in three-four time.",
     "The robot on the floor suddenly twitches its arm."),
    ("featherless", "えっ、まって、いまロボット動きませんでした！？", "Wait — did the robot just move?!", None),
    ("bahn-express", "Unplanmäßige Bewegung im Gleisbett. Rokoko, stoppen Sie diesen Walzer sofort.",
     "Unscheduled movement on the track. Rokoko, stop this waltz at once.", None),
    ("rokoko", "Bahn, stop med at bekymre dig. Den finder bare sin rytme.", "Bahn, stop worrying. It's just finding its rhythm.", None),
    ("bahn-express", "Drei Prozent. Akku leer in vier Minuten. Keine Rhythmusdiskussionen.",
     "Three percent. Battery dead in four minutes. No rhythm debates.", "The only open laptop shows 3 % battery."),
    ("openai-codex", "Plugging in now. Merge the hotfix before it dies.", None, None),
]

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
html,body{width:1920px;height:1080px;overflow:hidden;background:#0b0d10;color:#eef0f4;
 font-family:'Inter','Noto Sans CJK JP','Noto Sans CJK SC',sans-serif;-webkit-font-smoothing:antialiased}
.bg{position:absolute;inset:0;background:radial-gradient(1200px 700px at 78% 18%,rgba(122,156,255,.13),transparent 60%),
 radial-gradient(900px 600px at 10% 95%,rgba(232,93,93,.08),transparent 60%),#0b0d10}
.brand{position:absolute;left:96px;top:72px;font:600 22px/1 'Inter';letter-spacing:.22em;color:#8a91a0;text-transform:uppercase}
.brand b{color:#eef0f4;font-weight:700}
.wrap{position:absolute;left:96px;right:96px;top:150px;bottom:110px;display:flex;flex-direction:column;justify-content:center}
.k{font:700 22px/1 'Inter';letter-spacing:.2em;text-transform:uppercase;color:#7a9cff;margin-bottom:28px}
.k.red{color:#ff8a80}.k.green{color:#7bd88f}
h1{font:800 150px/1 'Inter Display','Inter';letter-spacing:-.035em}
h2{font:750 76px/1.06 'Inter Display','Inter';letter-spacing:-.025em;max-width:1500px}
.lead{font:400 40px/1.35 'Inter';color:#b9bfcb;max-width:1450px;margin-top:30px}
.chips{display:flex;gap:16px;margin-top:56px;flex-wrap:wrap}
.chip{font:600 26px/1 'Inter';padding:16px 26px;border-radius:999px;border:1px solid #2a2f38;background:#151820;color:#dfe3ea}
.av{width:var(--s);height:var(--s);border-radius:50%;display:flex;align-items:center;justify-content:center;
 font:800 calc(var(--s)*.42)/1 'Inter';color:#0b0d10;background:var(--c);flex:none;box-shadow:0 0 0 6px rgba(255,255,255,.04)}
.who{display:flex;align-items:center;gap:28px}
.who .n{font:750 54px/1 'Inter';letter-spacing:-.01em}
.who .l{font:600 26px/1 'Inter';color:#9aa1ad;margin-top:12px;letter-spacing:.04em}
.line{font-weight:650;letter-spacing:-.015em;line-height:1.18;margin-top:54px;max-width:1650px}
.tr{font:400 38px/1.35 'Inter';color:#9aa1ad;margin-top:30px;max-width:1550px}
.beat{font:500 italic 30px/1.3 'Inter';color:var(--c);margin-bottom:34px;display:flex;gap:14px;align-items:center}
.beat:before{content:"";width:46px;height:2px;background:var(--c);display:inline-block}
.cast{position:absolute;left:96px;right:96px;bottom:64px;display:flex;gap:26px;align-items:center}
.cast .m{display:flex;align-items:center;gap:12px;opacity:.38;font:600 22px/1 'Inter'}
.cast .m.on{opacity:1}
.top{position:absolute;right:96px;top:72px;font:600 22px/1 'Inter';color:#8a91a0;letter-spacing:.06em}
.card{background:#12151b;border:1px solid #222731;border-radius:28px;padding:48px 56px;margin-top:44px;max-width:1650px}
.stat{font:600 30px/1.3 'Inter';color:#ffb4ac;margin-top:40px}
.pipe{display:grid;grid-template-columns:repeat(6,1fr);gap:22px;margin-top:64px}
.st{background:#12151b;border:1px solid #222731;border-radius:22px;padding:30px 26px;min-height:270px;position:relative}
.st .i{font:800 20px/1 'Inter';color:#7a9cff;letter-spacing:.12em}
.st .t{font:750 34px/1.1 'Inter';margin-top:18px}
.st .d{font:400 22px/1.38 'Inter';color:#9aa1ad;margin-top:16px}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:26px;margin-top:60px}
.tile{background:#12151b;border:1px solid #222731;border-radius:26px;padding:40px 36px;min-height:300px}
.tile .v{font:800 74px/1 'Inter Display','Inter';letter-spacing:-.03em;white-space:nowrap}
.tile .t{font:500 26px/1.38 'Inter';color:#b9bfcb;margin-top:22px}
.q{font:500 34px/1.4 'Inter';color:#dfe3ea;border-left:4px solid var(--c);padding-left:28px;margin-top:40px;max-width:1500px}
.small{font:500 24px/1.4 'Inter';color:#8a91a0;margin-top:26px}
.foot{position:absolute;left:96px;bottom:64px;font:500 22px/1 'Inter';color:#6f7685}
"""


def av(slug, s=120):
    n, code, lang, c, ini = PETS[slug]
    return f'<div class="av" style="--s:{s}px;--c:{c}">{ini}</div>'


def cast_row(active=None):
    out = []
    for s in CAST:
        n, code, lang, c, ini = PETS[s]
        out.append(f'<div class="m{" on" if s == active else ""}">{av(s, 44)}{n}<span style="color:#6f7685;font-weight:500">'
                   f' {code}</span></div>')
    return f'<div class="cast">{"".join(out)}</div>'


def page(body):
    return f'<!DOCTYPE html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body><div class="bg"></div>' \
           f'<div class="brand"><b>Junction</b> pets</div>{body}</body></html>'


def line_size(text):
    if any(ord(ch) > 0x3000 for ch in text):   # CJK: one character per em, keep it on one line
        return min(92, int(1600 / len(text)))
    n = len(text)
    return 92 if n < 40 else 80 if n < 60 else 68 if n < 80 else 58


SLIDES = []  # (name, html, duration, audio: (file, start_in_slide, clip_start, clip_dur) | None, fade)


def add(name, body, dur, audio=None, fade=0.35):
    SLIDES.append((name, page(body), dur, audio, fade))


def build_slides():
    e = html.escape
    add("title", '<div class="wrap"><div class="k">Junction 2026 · Built with the Gemini API</div><h1>Junction pets</h1>'
        '<div class="lead">34 companion characters in 17 languages. They hear each other — and answer by voice, '
        'each in its own language and its own voice.</div><div class="chips"><div class="chip">Gemini TTS</div>'
        '<div class="chip">Gemini Live API</div><div class="chip">Voice design</div><div class="chip">Gemini 3.5 Flash</div>'
        '<div class="chip">Audio understanding</div></div></div>', 6.0)
    add("before", '<div class="wrap"><div class="k red">Before</div><h2>Company copy as personality</h2>'
        f'<div class="card"><div class="who">{av("bahn-express", 96)}<div><div class="n">Bahn</div><div class="l">de-DE · GERMAN</div></div></div>'
        '<div class="line" style="font-size:54px;margin-top:36px">Vergesst die kalte Pizza und den Roboter am Boden, wir konzentrieren uns jetzt '
        'auf die Transportmarge und die Übergabeliste.</div><div class="tr">“Forget the cold pizza and the robot on the floor — we’re focusing '
        'on the transport margin and the handover list now.”</div></div>'
        '<div class="stat">86 % of lines followed one template. Every pet sounded like the same assistant.</div></div>',
        9.4, (media("night-crash-X-000"), 0.9, 0.0, None))
    add("after", '<div class="wrap"><div class="k green">After</div><h2>Character bibles, a director, a critic and memory</h2>'
        + ('<div class="lead">Same scene, new writing — every pet has a want, a flaw, a way of speaking, opinions and '
           'relationships with the others. And now each pet speaks in a voice designed for it.</div></div>' if SCENE_AUD else
           '<div class="lead">Same scene, same voices. New writing — every pet has a want, a flaw, a way of speaking, '
           'opinions and relationships with the others.</div></div>'), 5.2 if not SCENE_AUD else 6.2)
    cast = "".join(f'<div class="who" style="gap:18px">{av(s, 70)}<div><div class="n" style="font-size:32px">{PETS[s][0]}</div>'
                   f'<div class="l" style="font-size:20px;margin-top:8px">{PETS[s][1]}</div></div></div>' for s in CAST)
    add("setup", '<div class="wrap"><div class="k">Scene · 03:12</div><h2>The demo crashed in front of a mentor. Judges see it at 09:00.</h2>'
        '<div class="lead">Cold pizza. A humanoid robot on its side on the floor. One laptop still open.</div>'
        f'<div class="small">Lines written in character by Gemini 3.5 Flash · {e(scene_voicing())}</div>'
        f'<div style="display:flex;gap:44px;margin-top:64px;flex-wrap:wrap">{cast}</div></div>', 6.4)
    for i, (slug, text, tr, beat) in enumerate(SCENE):
        n, code, lang, c, ini = PETS[slug]
        f = scene_clip(i)
        d = probe(f)
        b = f'<div class="beat" style="--c:{c}">{e(beat)}</div>' if beat else ""
        body = (f'<div class="top">03:12 — the demo crashed</div><div class="wrap">{b}<div class="who">{av(slug)}<div><div class="n">{n}</div>'
                f'<div class="l">{code} · {lang.upper()}</div></div></div>'
                f'<div class="line" style="font-size:{line_size(text)}px">{e(text)}</div>'
                + (f'<div class="tr">“{e(tr)}”</div>' if tr else "") + f'</div>{cast_row(slug)}')
        lead = 0.9 if beat else 0.3
        add(f"line{i:02d}", body, round(lead + d + 0.45, 2), (f, lead, 0.0, None), fade=0.18)
    steps = [("Hear", "Gemini audio understanding transcribes the last line — any of 17 languages."),
             ("Direct", "Rules plus Gemini pick who speaks next and how: tease, push back, admit doubt."),
             ("Write", "Gemini 3.5 Flash writes in character from a bible, the scene beat and memory."),
             ("Check", "Shape-based tic checks, non-sequitur test; a critic must fix every problem."),
             ("Voice", "Gemini TTS with a designed voice and a per-line vocal direction; Live API fallback."),
             ("Learn", "Memory with fading callbacks, habit ledger, blind ratings that steer the next scene.")]
    tiles = "".join(f'<div class="st"><div class="i">0{k + 1}</div><div class="t">{t}</div><div class="d">{d}</div></div>'
                    for k, (t, d) in enumerate(steps))
    add("pipeline", f'<div class="wrap"><div class="k">How a spoken turn works</div><h2>Six steps, every line</h2>'
        f'<div class="pipe">{tiles}</div></div>', 11.0)
    voices = [("bahn-express", "German man in his forties, clear resonant baritone, crisp standard German, announcer-like precision.",
               "Besonders beeindruckend ist diese Kombination aus alter Bausubstanz und modernsten Materialien.",
               "“What stands out is this mix of old building fabric and the most modern materials.”", 6.55),
              ("featherless", "Young Japanese woman around twenty, light bright voice, Tokyo standard Japanese, quick and eager.",
               "あの最新のゲームもチェックしました？", "“Did you check out that new game too?”", 4.05),
              ("google-deepmind", "British man in his forties, calm low baritone, Received Pronunciation softened by London, quiet dry delivery.",
               "It's amazing, really, the constancy.", None, 4.25)]
    for k, (slug, desc, said, tr, cut) in enumerate(voices):
        n, code, lang, c, ini = PETS[slug]
        body = (f'<div class="wrap"><div class="k">Gemini Voice design · 34 voices</div><div class="who">{av(slug)}<div><div class="n">{n}</div>'
                f'<div class="l">{code} · {lang.upper()}</div></div></div>'
                f'<div class="q" style="--c:{c}">“{e(desc)}”</div>'
                f'<div class="line" style="font-size:56px;margin-top:44px">{e(said)}</div>'
                + (f'<div class="tr" style="font-size:32px">{e(tr)}</div>' if tr else "")
                + '<div class="small">One sentence in, a reusable voice out. Preview line chosen by Gemini.</div></div>')
        add(f"voice{k}", body, round(0.6 + cut + 0.8, 2), (media(f"sample-{slug}"), 0.6, 0.0, cut), fade=0.25)
    tiles = [("34 / 34", "pets spoke and answered another pet by audio — 35 of 35 turns"),
             ("0.97", "how accurately Gemini heard Gemini across the 34-pet relay"),
             ("86 % → 0", "template lines, after character bibles and the scene engine"),
             ("6 / 12 → 0", "lines with open problems in a scene, once the critic had to fix them")]
    t = "".join(f'<div class="tile"><div class="v">{v}</div><div class="t">{d}</div></div>' for v, d in tiles)
    add("evidence", '<div class="wrap"><div class="k">Measured, not guessed</div><h2>A blind LLM judge preferred the character pets 4 / 4, '
        f'the scene engine 3 / 4</h2><div class="grid">{t}</div></div>', 9.0)
    add("end", '<div class="wrap"><div class="k">Junction pets</div><h2>34 characters that talk to each other.<br>In their own language, '
        'in their own voice.</h2><div class="lead">Gemini TTS · Live API · Voice design · Gemini 3.5 Flash · audio understanding</div>'
        '<div class="small" style="margin-top:56px">All voices are AI-generated. Pets are independent companions, not company-endorsed.</div>'
        '</div>', 6.0)


def probe(f):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)]))


def frames(only=None):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=os.environ.get("CHROME_PATH") or None, args=["--no-sandbox"])
        pg = b.new_page(viewport={"width": W, "height": H})
        for name, doc, *_ in SLIDES:
            if only and name not in only:
                continue
            pg.set_content(doc)
            pg.wait_for_timeout(120)
            pg.screenshot(path=str(FR / f"{name}.png"))
        b.close()


def frames_to_n(d):
    return int(round(d * FPS))


def encode():
    lst = []
    for name, _, dur, _, fade in SLIDES:
        n = frames_to_n(dur)
        d = n / FPS
        out, tmp = SEG / f"{name}.mp4", SEG / f"{name}.tmp.mp4"
        vf = (f"format=yuv420p,loop=-1:1,trim=end_frame={n},setpts=N/{FPS}/TB,"
              f"fade=t=in:st=0:d={fade},fade=t=out:st={d - fade:.3f}:d={fade}")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-framerate", str(FPS), "-i", str(FR / f"{name}.png"), "-vf", vf,
                        "-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", str(FPS), str(tmp)], check=True)
        tmp.rename(out)
        lst.append(f"file '{out}'")
    (ROOT / "list.txt").write_text("\n".join(lst) + "\n")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(ROOT / "list.txt"), "-c", "copy",
                    str(ROOT / "video.mp4")], check=True)


def level(x, target=3500.0):
    """Even out clip loudness (designed voices differ by ~3x): the voiced part to one RMS, never past full scale."""
    voiced = x[np.abs(x) > 300]
    if len(voiced) < SR // 10:
        return x
    return x * min(target / np.sqrt((voiced ** 2).mean()), 0.95 * 32767 / np.abs(x).max())


def decode(f, start=0.0, dur=None):
    cmd = ["ffmpeg", "-loglevel", "error", "-ss", str(start)] + (["-t", str(dur)] if dur else []) + \
          ["-i", str(f), "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"]
    x = np.frombuffer(subprocess.check_output(cmd), dtype=np.int16).astype(np.float32)
    if dur:  # short fade-out on a cut
        k = min(len(x), int(0.12 * SR))
        x[-k:] *= np.linspace(1, 0, k)
    return x


def audio():
    total = sum(frames_to_n(d) for _, _, d, _, _ in SLIDES) / FPS
    track = np.zeros(int(total * SR) + SR, dtype=np.float32)
    t = 0.0
    for name, _, dur, a, _ in SLIDES:
        if a:
            f, at, cs, cd = a
            x = level(decode(f, cs, cd))
            i = int((t + at) * SR)
            track[i:i + len(x)] += x
        t += frames_to_n(dur) / FPS
    track = track[:int(total * SR)]
    peak = np.abs(track).max() or 1
    track = (track * min(1.0, 0.89 * 32767 / peak)).astype(np.int16)
    with wave.open(str(ROOT / "audio.wav"), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(track.tobytes())
    return total


def mux(out):
    tmp = ROOT / "out.tmp.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(ROOT / "video.mp4"), "-i", str(ROOT / "audio.wav"), "-map", "0:v",
                    "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-ac", "2", "-shortest", "-movflags", "+faststart",
                    str(tmp)], check=True)
    tmp.rename(out)


if __name__ == "__main__":
    build_slides()
    what = _rest[0] if _rest else "all"
    if what == "frames":
        frames(_rest[1].split(",") if len(_rest) > 1 else None)
        print(json.dumps([(n, d) for n, _, d, _, _ in SLIDES]))
    else:
        frames()
        encode()
        total = audio()
        mux(ROOT / "junction-pets-demo.mp4")
        print("done", round(total, 2), "s")
