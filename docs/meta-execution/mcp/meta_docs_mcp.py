#!/usr/bin/env python3
"""Bounded anonymous reads of Meta's official public documentation MCP.

This helper never configures credentials or changes the user's Codex home.
It accepts only the two public documentation-search tools.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import re
import time
import urllib.error
import urllib.request

ENDPOINT = "https://mcp.developer.meta.com/wearables"
SOURCE_COMMIT = "bbae597cd1c748cd29b9375a1624a8d75b1c9e14"
README_BLOB = "98547c399efd5c4ec0b3654716ffa37173d09919"
PUBLIC_TOOLS = ("search_dat_docs", "search_webapps_docs")
MAX_RESPONSE_BYTES = 1024 * 1024


class PublicDocsClient:
    def __init__(self) -> None:
        self.protocol = "2025-11-25"
        self.session = None
        self.next_id = 1
        self.requests = []

    def request(self, method: str, params: dict | None = None,
                notification: bool = False) -> dict:
        payload = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        request_id = None
        if not notification:
            request_id = self.next_id
            self.next_id += 1
            payload["id"] = request_id
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": self.protocol,
        }
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        req = urllib.request.Request(
            ENDPOINT, data=json.dumps(payload).encode("utf-8"),
            headers=headers, method="POST",
        )
        started = time.monotonic()
        with urllib.request.urlopen(req, timeout=30) as response:
            self.session = response.headers.get("Mcp-Session-Id") or self.session
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise RuntimeError("response exceeds bounded size")
            content_type = response.headers.get("Content-Type", "")
            self.requests.append({
                "method": method, "httpStatus": response.status,
                "durationMs": round((time.monotonic() - started) * 1000),
                "contentType": content_type,
                "responseSha256": hashlib.sha256(raw).hexdigest(),
            })
        if not raw.strip():
            return {}
        text = raw.decode("utf-8")
        if "text/event-stream" in content_type:
            events = []
            for block in text.replace("\r\n", "\n").split("\n\n"):
                data = "\n".join(line[5:].lstrip() for line in block.splitlines()
                                 if line.startswith("data:"))
                if data and data != "[DONE]":
                    events.append(json.loads(data))
            result = next((x for x in events if x.get("id") == request_id), {})
        else:
            result = json.loads(text)
        if result.get("error"):
            raise RuntimeError("MCP JSON-RPC error: " + json.dumps(result["error"])[:500])
        if not notification and result.get("id") != request_id:
            raise RuntimeError("MCP response id mismatch or missing result")
        return result.get("result", {})

    def initialize(self) -> tuple[dict, list[dict]]:
        info = self.request("initialize", {
            "protocolVersion": self.protocol, "capabilities": {},
            "clientInfo": {"name": "chibi-meta-docs-bootstrap", "version": "0.1.0"},
        })
        self.protocol = info["protocolVersion"]
        self.request("notifications/initialized", notification=True)
        tools = self.request("tools/list", {})["tools"]
        return info["serverInfo"], tools

    def search(self, tool: str, query: str, max_results: int) -> dict:
        if tool not in PUBLIC_TOOLS:
            raise ValueError("Only public documentation-search tools are allowed")
        result = self.request("tools/call", {
            "name": tool, "arguments": {"query": query, "max_results": max_results},
        })
        text = "\n".join(c.get("text", "") for c in result.get("content", [])
                         if c.get("type") == "text")
        if result.get("isError"):
            raise RuntimeError("Documentation search returned isError")
        raw = json.dumps(result, ensure_ascii=False, sort_keys=True).encode("utf-8")
        urls = list(dict.fromkeys(re.findall(r"https?://[^\s\"<>\])]+", text)))
        return {
            "tool": tool, "query": query, "maxResults": max_results,
            "resultIsError": bool(result.get("isError", False)),
            "resultSha256": hashlib.sha256(raw).hexdigest(),
            "responseCharacters": len(text), "sourceUrls": urls[:12],
            "publicExcerpt": text[:1800],
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tool", choices=PUBLIC_TOOLS, default="search_dat_docs")
    parser.add_argument("--query", required=True)
    parser.add_argument("--max-results", type=int, choices=range(1, 4), default=2)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--also-web-query")
    args = parser.parse_args()
    client = PublicDocsClient()
    server, available = client.initialize()
    names = [tool["name"] for tool in available]
    if args.tool not in names:
        raise RuntimeError("Requested documentation tool is unavailable")
    searches = [client.search(args.tool, args.query, args.max_results)]
    if args.also_web_query:
        searches.append(client.search("search_webapps_docs", args.also_web_query,
                                      args.max_results))
    receipt = {
        "schemaVersion": 1, "workId": "META-MCP-20261114",
        "checkedAtUtc": datetime.now(timezone.utc).isoformat(),
        "executor": "ChatGPT hosted session exec_command",
        "platform": platform.system(), "pythonVersion": platform.python_version(),
        "endpoint": ENDPOINT, "authentication": "anonymous; no Authorization header",
        "source": {
            "repository": "meta/meta-wearables-dat-ios",
            "commit": SOURCE_COMMIT, "readmeBlob": README_BLOB,
        },
        "server": {"name": server.get("name"), "version": server.get("version")},
        "protocolVersion": client.protocol,
        "availableToolNames": names,
        "requests": client.requests, "searches": searches,
        "qualification": {
            "publicDocumentationMcp": True, "developerAccountAccess": False,
            "glassesRuntime": False, "chibiHostRuntime": False,
            "globalClientConfigChanged": False,
        },
    }
    serialized = json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(serialized, encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
