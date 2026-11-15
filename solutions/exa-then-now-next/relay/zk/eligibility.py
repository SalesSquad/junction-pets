#!/usr/bin/env python3
"""Eligibility proofs over a private amount, built on Kättely's Ristretto255 range proofs.

Statement: 0 <= value <= threshold, without revealing value.
  C  = value*G + r*H                    (Pedersen commitment, published)
  P1 = range proof that C opens to [0, 2^bits)
  P2 = range proof that threshold*G - C (= (threshold-value)*G - r*H) opens to [0, 2^bits)
Both proofs are bound to a caller context (claim, receiver, mandate) so they cannot be replayed elsewhere.

stdin JSON -> stdout JSON. Commands: prove | verify. The secret value and blinding never leave this process.
Limits: the commitment is self-attested by the holder. Binding it to an issuer (bank or tax authority
signature over the same commitment) is required before an institution should rely on it.
"""
import json, os, sys

sys.path.insert(0, os.environ.get("KATTELY_PATH", os.path.expanduser("~/Developer/kattely-ref-20261114")))
from kattely.crypto import primitives as p  # noqa: E402
from kattely.crypto import rangeproof as rp  # noqa: E402

SCHEME = "kattely-pedersen-bitor-v1/le-threshold"


def ctx(context, part):
    return {**context, "statement": "0<=value<=threshold", "part": part}


def prove(req):
    value, threshold, bits, context = int(req["value"]), int(req["threshold"]), int(req.get("bits", 32)), req["context"]
    if not 0 <= value <= threshold < 2 ** bits:
        return {"ok": False, "error": "value is not within [0, threshold]; no proof can be produced"}
    r = p.scalar_random()
    c = p.commitment(value, r)
    low = rp.prove_range(value, r, ctx(context, "nonneg"), bits)
    high = rp.prove_range(threshold - value, (-r) % p.ORDER, ctx(context, "le"), bits)
    return {"ok": True, "proof": {"scheme": SCHEME, "commitment": c.hex(), "threshold": threshold, "bits": bits, "context": context, "low": low, "high": high}}


def verify(req):
    pr = req["proof"]
    try:
        if pr.get("scheme") != SCHEME:
            return {"ok": True, "valid": False, "reason": "unknown scheme"}
        bits, threshold = int(pr["bits"]), int(pr["threshold"])
        c = p.point_decode(pr["commitment"])
        complement = p.sub(p.base(threshold), c).hex()
        valid = rp.verify_range(pr["commitment"], pr["low"], ctx(pr["context"], "nonneg"), bits) and rp.verify_range(complement, pr["high"], ctx(pr["context"], "le"), bits)
        return {"ok": True, "valid": bool(valid)}
    except Exception as e:  # malformed proofs are invalid, never errors that leak
        return {"ok": True, "valid": False, "reason": type(e).__name__}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    req = json.load(sys.stdin)
    out = prove(req) if cmd == "prove" else verify(req) if cmd == "verify" else {"ok": False, "error": "usage: eligibility.py prove|verify"}
    json.dump(out, sys.stdout)
