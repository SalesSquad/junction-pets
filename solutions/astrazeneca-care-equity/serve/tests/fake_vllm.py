"""A small stand-in for the vLLM OpenAI-compatible server, for unit tests only.

It answers GET /health, GET /v1/models and POST /v1/chat/completions on
127.0.0.1 with the response shape read from vLLM v0.29.0
(vllm/entrypoints/openai/chat_completion/protocol.py): choices[0].message.content,
choices[0].finish_reason and choices[0].logprobs.content[i] = {token, logprob,
bytes, top_logprobs}. It runs no model: each answer is scripted per note.

Like vLLM, /health needs no key and /v1/* needs "Authorization: Bearer <key>".
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

API_KEY = "unit-test-key-not-a-secret"


def tokenise(text, size=3):
    """Cut text into pseudo-tokens of `size` characters (whole characters, never split bytes)."""
    return [text[i : i + size] for i in range(0, len(text), size)]


def logprob_items(text, total_logprob=-0.01, token_logprobs=None, size=3, end_token="<end_of_turn>"):
    """OpenAI-style logprobs content for `text`.

    By default total_logprob is spread evenly, so exp(sum) == exp(total_logprob).
    An end-of-turn token with log-probability 0 is appended, as a server may do.
    """
    tokens = tokenise(text, size)
    if token_logprobs is None:
        token_logprobs = [total_logprob / len(tokens)] * len(tokens) if tokens else []
    if len(token_logprobs) != len(tokens):
        raise ValueError(f"{len(tokens)} tokens but {len(token_logprobs)} log-probabilities")
    items = [
        {"token": t, "logprob": lp, "bytes": list(t.encode("utf-8")), "top_logprobs": []}
        for t, lp in zip(tokens, token_logprobs)
    ]
    if end_token:
        items.append({"token": end_token, "logprob": 0.0, "bytes": list(end_token.encode()), "top_logprobs": []})
    return items


class FakeVLLM:
    """Scripted server. `answers` maps the user message content to a reply spec:

    {"content": str, "total_logprob": float, "token_logprobs": [...],
     "finish_reason": "stop", "logprobs": True, "status": 200, "body": {...}}
    A callable `responder(payload) -> spec` overrides the lookup.
    """

    def __init__(self, answers=None, responder=None, models=("gemma-base", "pathway-scribe"),
                 api_key=API_KEY, fail_first=0, fail_status=503):
        self.answers = answers or {}
        self.responder = responder
        self.models = list(models)
        self.api_key = api_key
        self.fail_first = fail_first
        self.fail_status = fail_status
        self.requests = []
        self.paths = []
        self._lock = threading.Lock()
        self._server = None
        self._thread = None

    # -- lifecycle ---------------------------------------------------------- #
    def start(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def _send(self, status, body, content_type="application/json", extra=None):
                raw = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(raw)))
                for key, value in (extra or {}).items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(raw)

            def _authorised(self):
                if fake.api_key is None:
                    return True
                return self.headers.get("Authorization") == "Bearer " + fake.api_key

            def do_GET(self):
                with fake._lock:
                    fake.paths.append(("GET", self.path))
                if self.path == "/health":
                    return self._send(200, b"", "text/plain")
                if self.path == "/v1/models":
                    if not self._authorised():
                        return self._send(401, {"error": "Unauthorized"})
                    return self._send(200, {"object": "list", "data": [
                        {"id": m, "object": "model", "owned_by": "vllm"} for m in fake.models]})
                return self._send(404, {"error": "not found"})

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length)
                with fake._lock:
                    fake.paths.append(("POST", self.path))
                if self.path != "/v1/chat/completions":
                    return self._send(404, {"error": "not found"})
                if not self._authorised():
                    return self._send(401, {"error": "Unauthorized"})
                with fake._lock:
                    if fake.fail_first > 0:
                        fake.fail_first -= 1
                        return self._send(fake.fail_status, {"error": "replica starting"}, extra={"Retry-After": "0"})
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except ValueError:
                    return self._send(400, {"error": "body is not JSON"})
                with fake._lock:
                    fake.requests.append(
                        {"payload": payload, "authorization": self.headers.get("Authorization"),
                         "content_type": self.headers.get("Content-Type")}
                    )
                if payload.get("model") not in fake.models:
                    return self._send(404, {"error": f"model {payload.get('model')!r} does not exist"})
                if fake.responder is not None:
                    spec = fake.responder(payload)
                else:
                    user = [m["content"] for m in payload["messages"] if m["role"] == "user"][-1]
                    spec = fake.answers.get(user)
                if spec is None:
                    return self._send(400, {"error": "no scripted answer for this note"})
                if spec.get("status", 200) != 200:
                    return self._send(spec["status"], spec.get("body", {"error": "scripted failure"}))
                if "body" in spec:
                    return self._send(200, spec["body"])
                content = spec["content"]
                choice = {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "logprobs": None,
                    "finish_reason": spec.get("finish_reason", "stop"),
                    "stop_reason": None,
                }
                if payload.get("logprobs") and spec.get("logprobs", True):
                    choice["logprobs"] = {
                        "content": spec.get("items")
                        or logprob_items(content, spec.get("total_logprob", -0.01), spec.get("token_logprobs"))
                    }
                return self._send(200, {
                    "id": "chatcmpl-fake",
                    "object": "chat.completion",
                    "created": 0,
                    "model": payload["model"],
                    "choices": [choice],
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                })

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self._thread.start()
        return self.base_url

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def stop(self):
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._thread.join(timeout=5)
            self._server = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()
