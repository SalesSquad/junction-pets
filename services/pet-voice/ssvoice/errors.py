"""One error type for every provider, with what the router needs: status, code, retry hint, per-day quota flag."""
from __future__ import annotations

import json
import re


class ProviderError(Exception):
    def __init__(self, status: int, code: str | None, message: str, retry_after: float | None = None, daily: bool = False):
        super().__init__(f"{status} {code}: {message}")
        self.status, self.code, self.message, self.retry_after, self.daily = status, code or "", message, retry_after, daily

    def record(self, model: str) -> dict:
        return {"model": model, "status": self.status, "code": self.code, "daily": self.daily,
                "retryAfter": self.retry_after, "message": self.message[:200]}


def parse_error(status: int, raw: bytes) -> ProviderError:
    """Gemini error JSON -> ProviderError; per-day quota violations set `daily`, RetryInfo sets `retry_after`."""
    try:
        info = json.loads(raw.decode("utf-8", "replace")).get("error", {})
    except (ValueError, AttributeError):
        info = {}
    retry, daily = None, False
    for d in info.get("details") or []:
        kind = d.get("@type", "")
        if kind.endswith("RetryInfo"):
            m = re.match(r"([\d.]+)s", str(d.get("retryDelay", "")))
            retry = float(m.group(1)) if m else None
        if kind.endswith("QuotaFailure"):
            for v in d.get("violations") or []:
                if "perday" in (str(v.get("quotaId", "")) + str(v.get("quotaMetric", ""))).lower():
                    daily = True
    return ProviderError(status, info.get("status"), str(info.get("message") or "")[:400], retry, daily)
