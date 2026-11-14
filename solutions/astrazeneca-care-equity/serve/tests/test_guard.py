"""serve/guard.py with a fake ASGI app: which paths need the bearer key. Standard library only."""

import asyncio
import unittest

import support  # noqa: F401  (puts serve/ on sys.path)
from guard import BearerGuard


async def inner(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def call(guard, path, auth=None, kind="http"):
    sent = []
    headers = [(b"host", b"x")] + ([(b"authorization", auth)] if auth is not None else [])

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(message):
        sent.append(message)

    asyncio.run(guard({"type": kind, "path": path, "headers": headers}, receive, send))
    return sent


def status(sent):
    return sent[0].get("status") if sent and sent[0]["type"] == "http.response.start" else sent[0]


class Guard(unittest.TestCase):
    def test_every_path_but_health_needs_the_key(self):
        g = BearerGuard(inner, key="secret-key")
        # the routes the review found open in vLLM 0.29.0, plus the ones vLLM guards itself
        for path in ("/invocations", "/tokenize", "/detokenize", "/metrics", "/load", "/version", "/docs",
                     "/openapi.json", "/generative_scoring", "/scale_elastic_ep", "/v1/chat/completions", "/v1/models"):
            self.assertEqual(status(call(g, path)), 401, path)
            self.assertEqual(status(call(g, path, b"Bearer wrong")), 401, path)
            self.assertEqual(status(call(g, path, b"Bearer secret-key")), 200, path)
        for path in ("/health", "/ping"):
            self.assertEqual(status(call(g, path)), 200, path)

    def test_fails_closed_without_a_key(self):
        g = BearerGuard(inner, key="")
        self.assertEqual(status(call(g, "/v1/models", b"Bearer ")), 401)
        self.assertEqual(status(call(g, "/health")), 200)

    def test_websocket_is_closed_without_the_key(self):
        g = BearerGuard(inner, key="secret-key")
        sent = call(g, "/v1/realtime", kind="websocket")
        self.assertEqual(sent, [{"type": "websocket.close", "code": 1008}])

    def test_lifespan_passes_through(self):
        seen = []

        async def app(scope, receive, send):
            seen.append(scope["type"])

        g = BearerGuard(app, key="k")
        asyncio.run(g({"type": "lifespan"}, None, None))
        self.assertEqual(seen, ["lifespan"])

    def test_key_from_environment(self):
        import os
        old = os.environ.get("VLLM_API_KEY")
        os.environ["VLLM_API_KEY"] = "env-key"
        try:
            g = BearerGuard(inner)
        finally:
            if old is None:
                del os.environ["VLLM_API_KEY"]
            else:
                os.environ["VLLM_API_KEY"] = old
        self.assertEqual(status(call(g, "/invocations", b"Bearer env-key")), 200)


if __name__ == "__main__":
    unittest.main()
