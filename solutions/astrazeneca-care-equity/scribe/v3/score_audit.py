"""Score the auditors' files of the round-2 audit.

  scribe/.venv/bin/python scribe/v3/score_audit.py [--audit-dir data/scribe/v3/audit] [--out <audit-dir>/audit-v1.json]

Reads <audit-dir>/out/slice-XX.json (the auditors), <audit-dir>/slice-XX.json (the notes) and <audit-dir>/key.json.

A verdict is DISCARDED, and counted, when
  - its quote is not an exact substring of its note (quote_not_in_note), or
  - it is stated / wrong_date / wrong_type / ambiguous, or an unlisted event marked present, with an empty quote
    (quote_missing), or
  - the verdict word is not one of the five (invalid_verdict).
A note is scored only when every claimed event has exactly one kept verdict and the unlisted-event answer is
kept; otherwise it is left out of every share and counted under notes_not_scored.

Per scored note:
  wrong_label     at least one wrong_date, wrong_type or not_stated verdict, or an unlisted event present
  ambiguity_only  no wrong label and at least one ambiguous verdict
  clean           every claimed event stated, no unlisted event
route_ok == false is reported separately (route_not_ok); it is not part of wrong_label.

Shares are given with numerator, denominator and a Wilson 95% interval, separately for the notes the rule
accepted and rejected, the same split by read-back consistency, and the two crossed.
All text is SYNTHETIC. Nothing here is for clinical use.
"""

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import AUDIT, log, now, save_json, share  # noqa: E402

VERDICTS = ("stated", "wrong_date", "wrong_type", "not_stated", "ambiguous")
WRONG = ("wrong_date", "wrong_type", "not_stated")
NEEDS_QUOTE = ("stated", "wrong_date", "wrong_type", "ambiguous")


def check_verdict(verdict, quote, note_text):
    """None when the verdict is kept, otherwise the reason it is discarded."""
    if verdict not in VERDICTS:
        return "invalid_verdict"
    if not isinstance(quote, str):
        return "quote_missing" if verdict in NEEDS_QUOTE else None
    if quote and quote not in note_text:
        return "quote_not_in_note"
    if not quote and verdict in NEEDS_QUOTE:
        return "quote_missing"
    return None


def score_item(answer, note_text, n_events):
    """Classify one audited note. Returns dict(scored, label, kinds, route_ok, discarded: Counter, verdicts: int)."""
    discarded, kinds, n_verdicts = collections.Counter(), collections.Counter(), 0
    complete = True
    seen = {}
    events = answer.get("events")
    if not isinstance(events, list):
        events, complete = [], n_events == 0 and events is None
    for pos, e in enumerate(events):
        if not isinstance(e, dict):
            complete = False
            continue
        n_verdicts += 1
        index = e.get("index", pos)
        reason = check_verdict(e.get("verdict"), e.get("quote", ""), note_text)
        if reason:
            discarded[reason] += 1
            continue
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < n_events or index in seen:
            discarded["bad_index"] += 1
            continue
        seen[index] = e["verdict"]
    if len(seen) != n_events:
        complete = False
    un = answer.get("unlisted_event")
    unlisted = None
    if isinstance(un, dict) and isinstance(un.get("present"), bool):
        n_verdicts += 1
        if un["present"]:
            q = un.get("quote", "")
            if not isinstance(q, str) or not q:
                discarded["quote_missing"] += 1
            elif q not in note_text:
                discarded["quote_not_in_note"] += 1
            else:
                unlisted = True
        else:
            unlisted = False
    if unlisted is None:
        complete = False
    route_ok = answer.get("route_ok") if isinstance(answer.get("route_ok"), bool) else None
    out = dict(scored=complete, label=None, kinds=kinds, route_ok=route_ok, discarded=discarded, verdicts=n_verdicts)
    if not complete:
        return out
    for v in seen.values():
        kinds[v] += 1
    if unlisted:
        kinds["unlisted_event"] += 1
    if unlisted or any(v in WRONG for v in seen.values()):
        out["label"] = "wrong_label"
    elif any(v == "ambiguous" for v in seen.values()):
        out["label"] = "ambiguity_only"
    else:
        out["label"] = "clean"
    return out


def group_report(items):
    """items: list of (key entry, score). Shares over the scored notes of the group."""
    scored = [s for _, s in items if s is not None and s["scored"]]
    n = len(scored)
    kinds = collections.Counter()
    for s in scored:
        for k in s["kinds"]:
            kinds[k] += 1  # notes with at least one verdict of this kind
    route_known = [s for s in scored if s["route_ok"] is not None]
    return dict(
        notes_in_sample=len(items),
        notes_scored=n,
        notes_not_scored=len(items) - n,
        wrong_label=share(sum(s["label"] == "wrong_label" for s in scored), n),
        ambiguity_only=share(sum(s["label"] == "ambiguity_only" for s in scored), n),
        clean=share(sum(s["label"] == "clean" for s in scored), n),
        route_not_ok=share(sum(s["route_ok"] is False for s in route_known), len(route_known)),
        wrong_label_or_route_not_ok=share(sum(s["label"] == "wrong_label" or s["route_ok"] is False for s in scored), n),
        clean_strict=share(sum(s["label"] == "clean" and s["route_ok"] is not False for s in scored), n),
        notes_with_at_least_one={k: kinds.get(k, 0) for k in ("wrong_date", "wrong_type", "not_stated", "unlisted_event", "ambiguous")},
    )


def score(audit_dir):
    audit_dir = Path(audit_dir)
    meta = json.loads((audit_dir / "key.json").read_text())
    key = meta["items"]
    notes = {}
    for f in sorted(audit_dir.glob("slice-*.json")):
        for item in json.loads(f.read_text()):
            notes[item["audit_id"]] = item
    assert set(notes) == set(key), "the slices and the key hold different audit ids"

    files, problems = {}, collections.Counter()
    answers = {}
    out_dir = audit_dir / "out"
    for f in sorted(out_dir.glob("slice-*.json")) if out_dir.exists() else []:
        try:
            data = json.loads(f.read_text())
            assert isinstance(data, list)
        except (json.JSONDecodeError, AssertionError):
            files[f.name] = dict(valid_json_array=False, items=0)
            problems["invalid_files"] += 1
            continue
        kept = 0
        for a in data:
            aid = a.get("audit_id") if isinstance(a, dict) else None
            if aid not in key:
                problems["items_with_unknown_audit_id"] += 1
            elif aid in answers:
                problems["duplicate_items"] += 1  # the first answer of an audit id counts
            else:
                answers[aid] = a
                kept += 1
        files[f.name] = dict(valid_json_array=True, items=len(data), items_used=kept)

    scores, discarded, n_verdicts = {}, collections.Counter(), 0
    for aid, a in answers.items():
        s = score_item(a, notes[aid]["note_text"], len(notes[aid]["claimed"]["events"]))
        scores[aid] = s
        discarded.update(s["discarded"])
        n_verdicts += s["verdicts"]

    def group(pred):
        return group_report([(k, scores.get(aid)) for aid, k in key.items() if pred(k)])

    def rb(k):
        return "consistent" if k["readback_consistent"] is True else "inconsistent"

    report = dict(
        schemaVersion="scribe-audit-v1",
        generated=now(),
        synthetic=True,
        audit_dir=str(audit_dir),
        definitions=dict(
            wrong_label="scored notes with at least one wrong_date, wrong_type or not_stated verdict, or an unlisted event",
            ambiguity_only="scored notes without a wrong label and with at least one ambiguous verdict",
            scored="every claimed event has one kept verdict and the unlisted-event answer is kept",
            discarded="a verdict whose quote is not an exact substring of its note, or that needs a quote and has none, is dropped",
            route_not_ok="route_ok == false; reported separately, not part of wrong_label",
            clean_strict="no wrong label, no unlisted event, no ambiguous verdict, and route_ok not false (the headline for a clean note)",
            wrong_label_or_route_not_ok="the headline problem share: wrong label or the note does not support the claimed route",
            interval="Wilson score interval, 95%",
        ),
        input=dict(
            items_in_key=len(key),
            items_answered=len(answers),
            items_missing=len(key) - len(answers),
            files=files,
            **{k: problems.get(k, 0) for k in ("invalid_files", "items_with_unknown_audit_id", "duplicate_items")},
        ),
        verdicts=dict(
            total=n_verdicts,
            discarded=sum(discarded.values()),
            discarded_quote_not_in_note=discarded.get("quote_not_in_note", 0),
            discarded_quote_missing=discarded.get("quote_missing", 0),
            discarded_invalid_verdict=discarded.get("invalid_verdict", 0),
            discarded_bad_index=discarded.get("bad_index", 0),
        ),
        by_status={st: group(lambda k, st=st: k["status"] == st) for st in ("accepted", "rejected")},
        by_readback={r: group(lambda k, r=r: rb(k) == r) for r in ("consistent", "inconsistent")},
        by_status_and_readback={
            f"{st}/{r}": group(lambda k, st=st, r=r: k["status"] == st and rb(k) == r)
            for st in ("accepted", "rejected")
            for r in ("consistent", "inconsistent")
        },
        by_status_and_curriculum={
            f"{st}/{c}": group(lambda k, st=st, c=c: k["status"] == st and k["curriculum"] == c)
            for st in ("accepted", "rejected")
            for c in sorted({k["curriculum"] for k in key.values()})
        },
        pooled_unweighted=group(lambda k: True),
        sampling=dict(
            note="the two statuses were sampled at very different rates, so pooled_unweighted is NOT a rate for the round-2 dataset; quote by_status",
            accepted=dict(sampled=sum(k["status"] == "accepted" for k in key.values()), available=meta.get("sample", {}).get("accepted_by_rule", {}).get("available")),
            rejected=dict(sampled=sum(k["status"] == "rejected" for k in key.values()), available=meta.get("sample", {}).get("code_check_pass_rejected_by_rule", {}).get("available")),
        ),
        auditor_note="the auditors were language-model readers (Claude Haiku) who saw the claimed labels, not humans",
    )
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--audit-dir", default=str(AUDIT))
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    report = score(a.audit_dir)
    out = Path(a.out) if a.out else Path(a.audit_dir) / "audit-v1.json"
    save_json(out, report)
    log(
        "score_audit",
        inputs=[a.audit_dir + "/out", a.audit_dir + "/key.json"],
        outputs=[str(out)],
        metrics=dict(input={k: v for k, v in report["input"].items() if k != "files"}, verdicts=report["verdicts"], by_status=report["by_status"]),
        cost_usd=0,
        status="ok" if report["input"]["items_missing"] == 0 else "partial",
    )
    print(json.dumps(dict(input={k: v for k, v in report["input"].items() if k != "files"}, verdicts=report["verdicts"], by_status=report["by_status"], by_readback=report["by_readback"]), indent=1))


if __name__ == "__main__":
    main()
