"""Bearer-key guard for every path of the vLLM server except the health check.

vLLM v0.29.0 checks `VLLM_API_KEY` only on paths that start with /v1, /v2, /inference or /cohere
(vllm/entrypoints/serve/middleware/authenticate.py, read in the version-2 review). Other routes of
the same server, among them POST /invocations (which runs generation), /tokenize, /detokenize,
/metrics, /load, /version, /docs and /openapi.json, answer without a key. This middleware closes
that gap: it requires `Authorization: Bearer <key>` on every HTTP and websocket request whose path
is not in OPEN_PATHS, and it fails closed (refuses everything but OPEN_PATHS) when no key is set.

serve/entrypoint.sh loads it with vLLM's `--middleware guard.BearerGuard` and puts this file's
directory on PYTHONPATH whenever a key is required. It was tested with a fake ASGI app
(serve/tests/test_guard.py); it has not been run inside a live vLLM server.

Standard library only. Research artefact; the scribe is not a medical device.
"""

from __future__ import annotations

import hmac
import json
import os

OPEN_PATHS = frozenset({"/health", "/ping"})  # the platform health check must work without a key


class BearerGuard:
    """ASGI middleware. `app` is the next application; the key defaults to $VLLM_API_KEY."""

    def __init__(self, app, key: str | None = None, open_paths=OPEN_PATHS):
        self.app = app
        self.key = (os.environ.get("VLLM_API_KEY", "") if key is None else key).encode()
        self.open_paths = frozenset(open_paths)

    def allowed(self, scope) -> bool:
        if scope.get("path") in self.open_paths:
            return True
        if not self.key:
            return False  # fail closed: a guard without a key lets nothing through
        for name, value in scope.get("headers") or []:
            if name.lower() == b"authorization":
                return hmac.compare_digest(value, b"Bearer " + self.key)
        return False

    async def __call__(self, scope, receive, send):
        kind = scope.get("type")
        if kind not in ("http", "websocket") or self.allowed(scope):
            await self.app(scope, receive, send)
            return
        if kind == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        body = json.dumps({"error": {"message": "missing or wrong bearer key", "type": "unauthorized"}}).encode()
        await send({"type": "http.response.start", "status": 401,
                    "headers": [(b"content-type", b"application/json"), (b"www-authenticate", b"Bearer"),
                                (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
