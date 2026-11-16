"""Which model speaks: free first, paid last, private data never to the data-sharing project, cached audio reused.

Model names in an order list: a Gemini TTS model ("gemini-3.8-flash-tts"), a Live model ("live:<model>", prebuilt
voices only, separate quota), an OpenAI paid model ("openai:<model>") or an OpenAI shared-project model
("openai-shared:<model>", text only, `privacy="public"` only). Whatever learning says, the order is always
free Gemini -> shared OpenAI -> paid OpenAI, and models in a per-day cooldown (learned or in the machine's ledger)
are tried after the ones that are not.
"""
from __future__ import annotations

import time

from . import cache, config, gemini, ledger, openai_api as oa
from .audio import heard_accuracy, normalize_audio
from .errors import ProviderError

EXHAUSTED = config.EXHAUSTED
PAID, SHARED = "openai:", "openai-shared:"
OPENAI_PREFIXES = (PAID, SHARED)


def route_filter(models: list[str], privacy: str = "private") -> list[str]:
    """Drop every OpenAI model when gemini-only is on, and the data-sharing project unless the request is public."""
    out = list(models)
    if config.gemini_only():
        out = [m for m in out if not m.startswith(OPENAI_PREFIXES)]
    if privacy != "public":
        out = [m for m in out if not m.startswith(SHARED)]
    return out


def gemini_only_failure(what: str) -> ProviderError:
    return ProviderError(0, "GEMINI_ONLY_EXHAUSTED", f"--gemini-only: every Gemini {what} route failed or is exhausted; "
                         "OpenAI fallback is disabled, so this run stops here (wait for quota reset or drop --gemini-only)")


def model_order(learned: dict, kind: str, defaults: list[str], override: list[str] | None, privacy: str = "private") -> list[str]:
    """Learned order first, then untried defaults; cooling models (learned or ledger) go last within their tier."""
    if override:
        return route_filter(override, privacy)
    learned_order = (learned.get("modelOrder") or {}).get(kind) or []
    order = learned_order + [m for m in defaults if m not in learned_order]
    now = config.now()
    cooling = {m for m, until in (learned.get("cooldownUntil") or {}).items() if until > now} | set(ledger.cooldowns())
    ordered = [m for m in order if m not in cooling] + [m for m in order if m in cooling]
    free = [m for m in ordered if not m.startswith(OPENAI_PREFIXES)]
    return route_filter(free + [m for m in ordered if m.startswith(SHARED)] + [m for m in ordered if m.startswith(PAID)], privacy)


def _voice_in(model: str, voice: str, openai_voice: str | None) -> str:
    return (openai_voice or oa.voice_for(voice)) if model.startswith(PAID) else voice


def speak(text: str, voice: str, style: str, key: str, models: list[str], log: list, prefer: dict | None = None,
          openai_voice: str | None = None, *, privacy: str = "private", fresh: bool = False) -> dict:
    """Synthesize `text`: reuse cached audio from any allowed model, else walk the models and request variants.
    Returns {wav, model, variant, latency, mime, [openaiVoice], [spoken, fidelity], [cached]}."""
    allowed = [m for m in route_filter(models, privacy) if not m.startswith(SHARED)]  # speech is never complimentary
    if not fresh:
        for model in allowed:
            if model in EXHAUSTED:
                continue
            hit = cache.get(cache.key("tts", model, text, _voice_in(model, voice, openai_voice), style))
            if hit:
                wav, meta = hit
                return {**meta, "wav": wav, "latency": 0.0, "cached": True}
    out = _synthesize(text, voice, style, key, allowed, log, prefer, openai_voice)
    if out.get("fidelity") is None or out["fidelity"] >= 0.8:  # never cache a Live take that paraphrased the line
        meta = {k: v for k, v in out.items() if k != "wav"}
        cache.put(cache.key("tts", out["model"], text, _voice_in(out["model"], voice, openai_voice), style), out["wav"], meta)
    return out


def _synthesize(text: str, voice: str, style: str, key: str, models: list[str], log: list, prefer: dict | None,
                openai_voice: str | None) -> dict:
    for model in models:
        if model in EXHAUSTED:
            continue
        if model.startswith(PAID):
            ov, t0 = openai_voice or oa.voice_for(voice), time.monotonic()
            try:
                wav = oa.speak(text, ov, style, model.removeprefix(PAID))
            except ProviderError as e:
                log.append(e.record(model))
                if e.daily or e.code in ("NO_KEY", "OPENAI_CAP"):
                    EXHAUSTED.add(model)
                continue
            return {"wav": wav, "model": model, "variant": "openai-speech", "latency": round(time.monotonic() - t0, 2),
                    "mime": "audio/wav", "openaiVoice": ov}
        if model.startswith("live:"):
            # Live models sometimes *answer* the line instead of reading it (fidelity 0.19 on 14 Nov).
            # Check what was actually said; re-voice once with a stricter frame before accepting.
            best = None
            for variant, script in (("live-recite", text),
                                    ("live-recite-strict", f"Read exactly this text aloud and say nothing else:\n\n{text}")):
                t0 = time.monotonic()
                try:
                    wav, said = gemini.live_speak(script, voice, style, key, model.removeprefix("live:"))
                except ProviderError as e:
                    log.append(e.record(model))
                    break
                fid = heard_accuracy(text, said) if said else None
                attempt = {"wav": wav, "model": model, "variant": variant, "latency": round(time.monotonic() - t0, 2),
                           "mime": "audio/pcm", "spoken": said, "fidelity": fid}
                if fid is None or fid >= 0.8:
                    return attempt
                log.append({"model": model, "status": 200, "code": "LOW_FIDELITY", "daily": False, "retryAfter": None,
                            "message": f"{variant} fidelity {fid}"})
                if best is None or fid > (best["fidelity"] or 0):
                    best = attempt
            if best:
                return best
            continue
        variants = gemini.tts_variants(text, voice, style)
        if prefer and prefer.get(model):
            variants.sort(key=lambda v: v[0] != prefer[model])
        for name, body in variants:
            try:
                resp, latency = gemini.call(model, body, key, log, timeout=90)
                raw, mime = gemini.extract_audio(resp)
                wav = normalize_audio(raw, mime)
                return {"wav": wav, "model": model, "variant": name, "latency": round(latency, 2), "mime": mime}
            except ProviderError as e:
                if e.status == 400:
                    continue          # request shape not accepted by this model: try next variant
                break                 # quota, outage, timeout, no audio: next model
    if config.gemini_only():
        raise gemini_only_failure("TTS")
    raise ProviderError(0, "TTS_UNAVAILABLE", "no TTS model produced audio")
