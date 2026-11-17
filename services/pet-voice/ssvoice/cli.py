"""python3 -m ssvoice status | say | settings | cache-prune | vendor  (run from voice/ or with voice/ on PYTHONPATH)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import cache, config, ledger, openai_api as oa, route, vendor
from .errors import ProviderError

DEFAULT_TTS = ["gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts", "gemini-3.1-flash-tts-preview",
               "gemini-2.5-flash-preview-tts", "live:gemini-2.5-flash-native-audio-latest"]


def cmd_status(args) -> int:
    """Keys present (never their values), today's ledger, cooling models, cache size, settings."""
    print(json.dumps({"ledger": ledger.summary(), "cache": cache.stats(), "geminiOnly": config.gemini_only(),
                      "openaiKeys": {p: bool(oa.read_key(p)) for p in ("paid", "shared")},
                      "openaiShared": {"tokensToday": oa.shared_tokens_today(), "budget": oa.shared_budget(),
                                       "paidSharesData": oa.paid_shares_data()},
                      "settings": config.settings()}, ensure_ascii=False, indent=1))
    return 0


def cmd_settings(args) -> int:
    """This machine's non-secret settings: pointers to Keychain items and switches, never keys."""
    if args.action != "show" and (not args.name or (args.action == "set" and args.value is None)):
        raise SystemExit("usage: settings set NAME VALUE | settings unset NAME | settings show")
    try:
        if args.action == "set":
            data = config.set_setting(args.name, args.value)
        elif args.action == "unset":
            data = config.set_setting(args.name, None)
        else:
            data = config.settings()
    except ValueError as e:
        raise SystemExit(str(e))
    print(json.dumps({"path": str(config.settings_path()), "settings": data}, ensure_ascii=False, indent=1))
    return 0


def cmd_say(args) -> int:
    from . import gemini
    models = args.models.split(",") if args.models else route.model_order({}, "tts", DEFAULT_TTS, None, args.privacy)
    log: list = []
    try:
        out = route.speak(args.text, args.voice, args.style, gemini.read_key(), models, log, privacy=args.privacy,
                          fresh=args.fresh)
    except ProviderError as e:
        print(json.dumps({"ok": False, "error": e.record("route"), "log": log}, ensure_ascii=False, indent=1))
        return 1
    Path(args.out).write_bytes(out["wav"])
    print(json.dumps({"ok": True, "out": args.out, **{k: v for k, v in out.items() if k != "wav"}, "log": log},
                     ensure_ascii=False, indent=1))
    return 0


def cmd_cache_prune(args) -> int:
    print(json.dumps(cache.prune(args.max_mb), indent=1))
    return 0


def cmd_vendor(args) -> int:
    result = vendor.check(Path(args.target)) if args.check else vendor.vendor(Path(args.target))
    print(json.dumps(result, indent=1))
    return 0 if result.get("ok", True) else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ssvoice", description="SalesSquad shared voice layer")
    ap.add_argument("--gemini-only", action="store_true", help="never call OpenAI")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    s = sub.add_parser("say")
    s.add_argument("text")
    s.add_argument("--voice", default="Kore", help="prebuilt name or a designed voice_... id")
    s.add_argument("--style", default="natural, warm")
    s.add_argument("--models", help="comma-separated order; default: free Gemini TTS, then Live")
    s.add_argument("--privacy", choices=["private", "public"], default="private")
    s.add_argument("--fresh", action="store_true", help="skip the cache")
    s.add_argument("--out", default="say.wav")
    s.set_defaults(fn=cmd_say)
    st = sub.add_parser("settings", help="e.g. settings set OPENAI_SHARED_KEYCHAIN 'OpenAI API Key|openai'")
    st.add_argument("action", choices=["show", "set", "unset"])
    st.add_argument("name", nargs="?")
    st.add_argument("value", nargs="?")
    st.set_defaults(fn=cmd_settings)
    p = sub.add_parser("cache-prune")
    p.add_argument("--max-mb", type=float)
    p.set_defaults(fn=cmd_cache_prune)
    v = sub.add_parser("vendor")
    v.add_argument("target", help="folder that gets ssvoice/ (e.g. services/pet-voice)")
    v.add_argument("--check", action="store_true")
    v.set_defaults(fn=cmd_vendor)
    args = ap.parse_args(argv)
    if args.gemini_only:
        config.set_gemini_only()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
