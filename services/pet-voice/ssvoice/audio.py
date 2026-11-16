"""WAV helpers (stdlib only) and a language-agnostic "did the listener hear what was said" score."""
from __future__ import annotations

import difflib
import hashlib
import re
import struct
import unicodedata

SAMPLE_RATE = 24000


def pcm_to_wav(pcm: bytes, rate: int = SAMPLE_RATE, channels: int = 1, bits: int = 16) -> bytes:
    block = channels * bits // 8
    header = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVE"
    header += b"fmt " + struct.pack("<IHHIIHH", 16, 1, channels, rate, rate * block, block, bits)
    return header + b"data" + struct.pack("<I", len(pcm)) + pcm


def wav_pcm(wav: bytes) -> tuple[bytes, int, int, int]:
    """Return (pcm, rate, channels, bits) from any RIFF/WAVE, tolerating odd chunk sizes."""
    if wav[:4] != b"RIFF" or wav[8:12] != b"WAVE":
        raise ValueError("not a RIFF/WAVE file")
    pos, rate, channels, bits, pcm = 12, SAMPLE_RATE, 1, 16, None
    while pos + 8 <= len(wav):
        cid, size = wav[pos:pos + 4], struct.unpack("<I", wav[pos + 4:pos + 8])[0]
        body = wav[pos + 8:pos + 8 + size]
        if cid == b"fmt ":
            _, channels, rate, _, _, bits = struct.unpack("<HHIIHH", body[:16])
        elif cid == b"data":
            pcm = wav[pos + 8:] if size in (0, 0xFFFFFFFF) or pos + 8 + size > len(wav) else body
            break
        pos += 8 + size + (size & 1)
    if pcm is None:
        raise ValueError("no data chunk")
    return pcm, rate, channels, bits


def normalize_audio(raw: bytes, mime: str = "") -> bytes:
    """Gemini 3.8 returns WAV; older TTS returns headerless L16 PCM. Always produce a clean PCM WAV."""
    if raw[:4] == b"RIFF":
        pcm, rate, channels, bits = wav_pcm(raw)
        return pcm_to_wav(pcm, rate, channels, bits)
    m = re.search(r"rate=(\d+)", mime or "")
    return pcm_to_wav(raw, int(m.group(1)) if m else SAMPLE_RATE)


def wav_seconds(wav: bytes) -> float:
    pcm, rate, channels, bits = wav_pcm(wav)
    return round(len(pcm) / (rate * channels * bits / 8), 2)


def concat_wavs(wavs: list[bytes], gap: float = 0.5) -> bytes:
    pcm0, rate, channels, bits = wav_pcm(wavs[0])
    silence = b"\x00" * (int(rate * gap) * channels * bits // 8)
    out = []
    for w in wavs:
        pcm, r, c, b = wav_pcm(w)
        if (r, c, b) != (rate, channels, bits):
            raise ValueError(f"mixed audio formats {r}/{c}/{b} vs {rate}/{channels}/{bits}")
        out += [pcm, silence]
    return pcm_to_wav(b"".join(out), rate, channels, bits)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def heard_accuracy(said: str, heard: str) -> float | None:
    """Language-agnostic round-trip intelligibility: char similarity after NFKC + casefold, ignoring punctuation."""
    def norm(s: str) -> str:
        s = unicodedata.normalize("NFKC", s or "").casefold()
        return "".join(ch for ch in s if ch.isalnum())
    a, b = norm(said), norm(heard)
    if not a:
        return None
    return round(difflib.SequenceMatcher(None, a, b, autojunk=False).ratio(), 4)
