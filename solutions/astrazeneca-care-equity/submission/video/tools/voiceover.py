"""Generate the English narration with ElevenLabs, one take per segment, timed to the video.

Reads the segments from tools/cues.mjs (via `node -e`), asks ElevenLabs text-to-speech with
character timestamps, speeds a take up (at most 1.2x) when it would overrun its window, then writes:
  tools/vo/<seg>.mp3          one take per segment
  tools/vo-timing.json        caption cues placed where each line is actually spoken
  assets/voiceover-slot.m4a   the full 119 s narration track the composition plays
The voice is synthetic (ElevenLabs); the key is read from ~/.config/elevenlabs/.env and never printed.
    python3 tools/voiceover.py [--voice Sarah]
"""
import argparse, base64, json, os, pathlib, subprocess, sys, urllib.request

HERE = pathlib.Path(__file__).resolve().parent
VIDEO = HERE.parent
LEAD, TAIL, MODEL = 0.3, 0.35, "eleven_multilingual_v2"
SAY = {"Nemotron": "Nee-mo-tron"}  # how the voice should pronounce a word; captions keep the real spelling


def say(line):
    for k, v in SAY.items():
        line = line.replace(k, v)
    return line

def key():
    k = os.environ.get("ELEVENLABS_API_KEY")
    if k: return k
    for line in (pathlib.Path.home() / ".config/elevenlabs/.env").read_text().splitlines():
        if line.strip().startswith("ELEVENLABS_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("no ELEVENLABS_API_KEY")

def api(path, body=None):
    req = urllib.request.Request("https://api.elevenlabs.io" + path, data=json.dumps(body).encode() if body else None,
                                 headers={"xi-api-key": key(), "Content-Type": "application/json"}, method="POST" if body else "GET")
    try:
        with urllib.request.urlopen(req, timeout=180) as r: return json.loads(r.read())
    except urllib.error.HTTPError as e: sys.exit(f"ElevenLabs HTTP {e.code}: {e.read()[:300].decode(errors='replace')}")

def segments():
    js = "import('./tools/cues.mjs').then(m=>console.log(JSON.stringify({segments:m.segments,total:m.TOTAL})))"
    return json.loads(subprocess.run(["node", "-e", js], cwd=VIDEO, capture_output=True, text=True, check=True).stdout)

def tts(voice_id, text, speed):
    r = api(f"/v1/text-to-speech/{voice_id}/with-timestamps?output_format=mp3_44100_128",
            {"text": text, "model_id": MODEL, "voice_settings": {"stability": 0.55, "similarity_boost": 0.75, "style": 0.0, "speed": speed}})
    al = r["alignment"]
    return base64.b64decode(r["audio_base64"]), al["character_start_times_seconds"], al["character_end_times_seconds"]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--voice", default="Sarah"); a = ap.parse_args()
    voice = next(v for v in api("/v1/voices")["voices"] if v["name"].lower().startswith(a.voice.lower()))
    data = segments(); out_cues, report, chars = [], [], 0
    (HERE / "vo").mkdir(exist_ok=True)
    for seg in data["segments"]:
        if not seg["lines"]: continue
        spoken = [say(l) for l in seg["lines"]]  # pronunciation hints change only what is sent to the voice
        text = " ".join(spoken); chars += len(text)
        window = seg["end"] - seg["start"] - LEAD - TAIL
        speed = 1.0
        for attempt in range(3):
            audio, st, en = tts(voice["voice_id"], text, speed)
            dur = en[-1]
            if dur <= window or speed >= 1.2: break
            speed = min(1.2, round(speed * dur / window * 1.02, 3)); chars += len(text)
        (HERE / "vo" / f"{seg['id']}.mp3").write_bytes(audio)
        pos, starts = 0, []
        for line in spoken:
            starts.append(st[pos]); pos += len(line) + 1
        t0 = seg["start"] + LEAD
        for i, line in enumerate(seg["lines"]):
            s = t0 + starts[i]; e = t0 + (starts[i + 1] if i + 1 < len(starts) else dur)
            out_cues.append({"seg": seg["id"], "start": round(s, 2), "end": round(min(e, seg["end"] - 0.05), 2), "text": line})
        report.append({"seg": seg["id"], "window_s": round(window, 2), "spoken_s": round(dur, 2), "speed": speed, "fits": dur <= window})
    (HERE / "vo-timing.json").write_text(json.dumps({"voice": voice["name"], "model": MODEL, "synthetic_voice": True,
                                                    "segments": report, "cues": out_cues}, indent=1) + "\n")
    # one 119 s track: each take delayed to its segment start + LEAD, mixed, loudness-normalised
    total = data["total"]; inputs, filt = [], []
    takes = [s for s in data["segments"] if s["lines"]]
    for i, seg in enumerate(takes):
        inputs += ["-i", str(HERE / "vo" / f"{seg['id']}.mp3")]
        ms = int(round((seg["start"] + LEAD) * 1000)); filt.append(f"[{i}:a]adelay={ms}|{ms},aresample=48000[a{i}]")
    filt.append("".join(f"[a{i}]" for i in range(len(takes))) + f"amix=inputs={len(takes)}:normalize=0,apad,atrim=0:{total},loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[out]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(filt), "-map", "[out]",
                    "-ac", "2", "-c:a", "aac", "-b:a", "160k", str(VIDEO / "assets" / "voiceover-slot.m4a")], check=True)
    print(json.dumps({"voice": voice["name"], "characters_sent": chars, "segments": report}, indent=1))

if __name__ == "__main__":
    main()
