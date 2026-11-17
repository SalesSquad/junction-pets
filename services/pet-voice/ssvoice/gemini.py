"""Google Gemini speech: TTS (prebuilt and designed voices), Live native audio, Voice design, plus the raw request
with bounded retries that text callers use. Every HTTP/WebSocket request is counted in the ledger."""
from __future__ import annotations

import base64
import json
import os
import re
import struct
import subprocess
import time
import urllib.error
import urllib.request

from . import config, ledger
from .audio import SAMPLE_RATE, pcm_to_wav
from .errors import ProviderError, parse_error

API = "https://generativelanguage.googleapis.com/v1beta"
# The owner's personal Gemini key on the MBP (Junction-named, see docs/gemini-junction.md). SSVOICE_GEMINI_KEYCHAIN
# ("service|account") points at another Keychain item; SSVOICE_GEMINI_API_KEY supplies a key directly.
KEYCHAIN_SERVICE = "com.salessquad.junction.gemini"
KEYCHAIN_ACCOUNT = "Junction-2026-Gemini-Agent-Mesh"
LIVE_PATH = "/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
PREBUILT_VOICES = ["Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Orus", "Aoede", "Callirrhoe", "Autonoe",
                   "Enceladus", "Iapetus", "Umbriel", "Algieba", "Despina", "Erinome", "Algenib", "Rasalgethi",
                   "Laomedeia", "Achernar", "Alnilam", "Schedar", "Gacrux", "Pulcherrima", "Achird",
                   "Zubenelgenubi", "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat"]
FEMALE_VOICES = {"Zephyr", "Kore", "Leda", "Aoede", "Callirrhoe", "Autonoe", "Despina", "Erinome", "Laomedeia", "Achernar",
                 "Gacrux", "Pulcherrima", "Vindemiatrix", "Sulafat"}


def read_key() -> str:
    """The key stays in process memory; it is never printed or written."""
    given = (config.env("GEMINI_API_KEY") or "").strip()
    if len(given) >= 20:
        return given
    service, _, account = (config.env("GEMINI_KEYCHAIN") or f"{KEYCHAIN_SERVICE}|{KEYCHAIN_ACCOUNT}").partition("|")
    try:
        r = subprocess.run(["/usr/bin/security", "find-generic-password", "-s", service, "-a", account, "-w"],
                           capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        raise SystemExit("KEYCHAIN_ACCESS_UNAVAILABLE")
    key = r.stdout.strip()
    if r.returncode != 0 or len(key) < 20:
        raise SystemExit("KEYCHAIN_ACCESS_NOT_AUTHORIZED_OR_NOT_FOUND")
    return key


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # never follow redirects with the key header
        return None


def _request(url: str, body: dict, key: str, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"x-goog-api-key": key, "content-type": "application/json"}, method="POST")
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        raise parse_error(e.code, e.read())
    except TimeoutError:
        raise ProviderError(0, "TIMEOUT", f"no response within {timeout:.0f}s")
    except urllib.error.URLError as e:
        if isinstance(e.reason, TimeoutError):
            raise ProviderError(0, "TIMEOUT", f"no response within {timeout:.0f}s")
        raise ProviderError(0, "NETWORK", type(e.reason).__name__)
    except OSError as e:
        raise ProviderError(0, "NETWORK", type(e).__name__)


def post(model: str, body: dict, key: str, timeout: float = 150) -> dict:
    """One generateContent request, counted in the ledger under the model's name."""
    try:
        resp = _request(f"{API}/models/{model}:generateContent", body, key, timeout)
    except ProviderError as e:
        ledger.record(model, False, error=e)
        raise
    usage = resp.get("usageMetadata") or {}
    ledger.record(model, True, tokens=int(usage.get("totalTokenCount") or 0))
    return resp


def api_post(path: str, body: dict, key: str, timeout: float = 120) -> dict:
    """Any other v1beta POST (e.g. `voices` for Voice design), counted as gemini-api:<path>."""
    label = f"gemini-api:{path.split('/')[0]}"
    try:
        resp = _request(f"{API}/{path}", body, key, timeout)
    except ProviderError as e:
        ledger.record(label, False, error=e)
        raise
    ledger.record(label, True)
    return resp


def call(model: str, body: dict, key: str, log: list, attempts: int = 6, max_wait: float = 75,
         timeout: float = 60) -> tuple[dict, float]:
    """POST with bounded retry: honours RetryInfo on per-minute 429s, backs off on 5xx/network.
    A timeout is not retried: a model that stalls is skipped and learning demotes it."""
    for i in range(attempts):
        t0 = time.monotonic()
        try:
            return post(model, body, key, timeout), time.monotonic() - t0
        except ProviderError as e:
            log.append(e.record(model))
            if e.daily:
                config.EXHAUSTED.add(model)
            last = i == attempts - 1
            if e.status == 429 and not e.daily and not last:
                time.sleep(min(max_wait, (e.retry_after or 5 * 2 ** i) + 1))
                continue
            if e.status in (0, 500, 502, 503, 504) and e.code != "TIMEOUT" and not last:
                time.sleep(3 * 2 ** i)
                continue
            raise
    raise ProviderError(0, "EXHAUSTED", "retries exhausted")


# ------------------------------------------------------------------ TTS ---
def tts_variants(text: str, voice: str, style: str) -> list[tuple[str, dict]]:
    """Request shapes in the order newer models accept them; a designed voice id only works in the first."""
    current = {"contents": [{"role": "user", "parts": [{"text": text, "speech_metadata": {"style": style}}]}],
               "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"voiceConfig": {"voice": voice}}}}
    prebuilt = {"contents": [{"role": "user", "parts": [{"text": text, "speech_metadata": {"style": style}}]}],
                "generationConfig": {"responseModalities": ["AUDIO"],
                                     "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
    legacy = {"contents": [{"role": "user", "parts": [{"text": f"Say in a {style} way: {text}"}]}],
              "generationConfig": {"responseModalities": ["AUDIO"],
                                   "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
    return [("speech_metadata+voice", current), ("speech_metadata+prebuilt", prebuilt), ("legacy-style-prefix", legacy)]


def extract_audio(resp: dict) -> tuple[bytes, str]:
    for cand in resp.get("candidates") or []:
        for part in (cand.get("content") or {}).get("parts") or []:
            data = part.get("inlineData") or part.get("inline_data")
            if data and data.get("data"):
                return base64.b64decode(data["data"]), data.get("mimeType") or data.get("mime_type") or ""
    reason = ((resp.get("candidates") or [{}])[0]).get("finishReason")
    raise ProviderError(200, "NO_AUDIO", f"finishReason={reason}")


def design_voice(description: str, language: str, key: str, *, display_name: str, model: str = "gemini-3.8-flash-tts",
                 gender: str | None = None) -> dict:
    """Gemini Voice design: one sentence in, a stored voice out (`voice_...` id). Works while TTS is daily-capped.
    Designed ids are accepted only by the 3.8 TTS models (flash and flash-lite), as of 15-16 Nov 2026."""
    voice = {"model": model, "type": "prompted", "display_name": display_name, "language_code": language,
             "prompted": {"input": description}}
    if gender:
        voice["gender"] = gender
    return api_post("voices", {"store": True, "voice": voice}, key)


# ----------------------------------------------------------------- Live ---
class MiniWebSocket:
    """Just enough RFC 6455 client for the Gemini Live API (TLS, masked text frames, ping/pong, close)."""

    def __init__(self, host: str, path: str, headers: dict, timeout: float):
        import socket
        import ssl
        raw = socket.create_connection((host, 443), timeout=timeout)
        self.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
        self.buf = b""
        nonce = base64.b64encode(os.urandom(16)).decode()
        req = (f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {nonce}\r\nSec-WebSocket-Version: 13\r\n"
               + "".join(f"{k}: {v}\r\n" for k, v in headers.items()) + "\r\n")
        self.sock.sendall(req.encode())
        while b"\r\n\r\n" not in self.buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ProviderError(0, "NETWORK", "websocket handshake closed")
            self.buf += chunk
        head, self.buf = self.buf.split(b"\r\n\r\n", 1)
        status = int(head.split(b" ", 2)[1])
        if status != 101:
            raise ProviderError(status, "WS_HANDSHAKE", head.split(b"\r\n", 1)[0].decode(errors="replace"))

    def _exact(self, n: int) -> bytes:
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ProviderError(0, "NETWORK", "websocket closed")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def _frame(self, opcode: int, payload: bytes) -> None:
        n, mask = len(payload), os.urandom(4)
        head = bytes([0x80 | opcode]) + (bytes([0x80 | n]) if n < 126 else bytes([0xFE]) + struct.pack(">H", n)
                                          if n < 65536 else bytes([0xFF]) + struct.pack(">Q", n))
        keystream = (mask * (n // 4 + 1))[:n]
        body = (int.from_bytes(payload, "big") ^ int.from_bytes(keystream, "big")).to_bytes(n, "big") if n else b""
        self.sock.sendall(head + mask + body)

    def send(self, text: str) -> None:
        self._frame(0x1, text.encode())

    def recv(self) -> str:
        message = b""
        while True:
            b1, b2 = self._exact(2)
            n = b2 & 0x7F
            n = struct.unpack(">H", self._exact(2))[0] if n == 126 else struct.unpack(">Q", self._exact(8))[0] if n == 127 else n
            if b2 & 0x80:
                self._exact(4)
            data, op = self._exact(n), b1 & 0x0F
            if op == 0x8:
                reason = data[2:].decode(errors="replace")[:300]
                quota = "quota" in reason.lower() or "exhausted" in reason.lower()
                raise ProviderError(429 if quota else 400, "WS_CLOSED", reason, daily=quota)
            if op == 0x9:
                self._frame(0xA, data)
                continue
            if op == 0xA:
                continue
            message += data
            if b1 & 0x80:
                return message.decode()

    def close(self) -> None:
        try:
            self._frame(0x8, struct.pack(">H", 1000))
            self.sock.close()
        except OSError:
            pass


def live_speak(text: str, voice: str, style: str, key: str, model: str, timeout: float = 60) -> tuple[bytes, str]:
    """Voice a line through the Gemini Live API (native audio). Separate quota from the TTS models; prebuilt voices only.
    Returns (wav, what the model actually said) so fidelity to the script can be measured."""
    label = f"live:{model}"
    try:
        wav, said = _live(text, voice, style, key, model, timeout)
    except ProviderError as e:
        ledger.record(label, False, error=e)
        raise
    ledger.record(label, True)
    return wav, said


def _live(text: str, voice: str, style: str, key: str, model: str, timeout: float) -> tuple[bytes, str]:
    try:
        ws = MiniWebSocket("generativelanguage.googleapis.com", LIVE_PATH, {"x-goog-api-key": key}, timeout)
    except TimeoutError:
        raise ProviderError(0, "TIMEOUT", "live connect timeout")
    except OSError as e:
        raise ProviderError(0, "NETWORK", f"live connect: {type(e).__name__}")
    try:
        ws.send(json.dumps({"setup": {
            "model": f"models/{model}",
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}},
            "systemInstruction": {"parts": [{"text": "You are a text-to-speech voice. Read the user's message aloud exactly as "
                                             f"written, word for word, in its own language, with a {style} delivery. Do not "
                                             "answer it, translate it, add or omit anything."}]},
            "outputAudioTranscription": {}}}))
        first = json.loads(ws.recv())
        if "setupComplete" not in first:
            raise ProviderError(400, "LIVE_SETUP", json.dumps(first)[:200])
        ws.send(json.dumps({"clientContent": {"turns": [{"role": "user", "parts": [{"text": text}]}], "turnComplete": True}}))
        pcm, said, rate = [], [], SAMPLE_RATE
        while True:
            msg = json.loads(ws.recv())
            content = msg.get("serverContent") or {}
            for part in (content.get("modelTurn") or {}).get("parts") or []:
                data = part.get("inlineData") or {}
                if data.get("data"):
                    pcm.append(base64.b64decode(data["data"]))
                    m = re.search(r"rate=(\d+)", data.get("mimeType", ""))
                    rate = int(m.group(1)) if m else rate
            if (content.get("outputTranscription") or {}).get("text"):
                said.append(content["outputTranscription"]["text"])
            if content.get("turnComplete") or msg.get("goAway"):
                break
        if not pcm:
            raise ProviderError(200, "NO_AUDIO", "live turn returned no audio")
        return pcm_to_wav(b"".join(pcm), rate), "".join(said).strip()
    except TimeoutError:
        raise ProviderError(0, "TIMEOUT", f"live: no response within {timeout:.0f}s")
    except (ValueError, IndexError, OSError) as e:
        raise ProviderError(0, "NETWORK", f"live: {type(e).__name__}")
    finally:
        ws.close()
