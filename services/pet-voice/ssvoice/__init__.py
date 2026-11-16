"""SalesSquad shared voice layer: Gemini and OpenAI speech behind one router, a per-machine quota ledger and an audio
cache. Stdlib only. Source: SalesSquad/agents voice/ssvoice (consumers carry a vendored copy, see vendor.py)."""
from .errors import ProviderError
from .route import model_order, route_filter, speak

VERSION = "0.1.0"
__all__ = ["ProviderError", "model_order", "route_filter", "speak", "VERSION"]
