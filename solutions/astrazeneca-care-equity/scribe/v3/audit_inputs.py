"""Audit inputs for eight independent auditors: 240 round-2 notes in eight slices of 30.

  scribe/.venv/bin/python scribe/v3/audit_inputs.py

Sample, fixed by SHA-256("scribe-v3-audit|" + id): the first 160 notes the rule accepted and the first 80
that passed the code check but were rejected by the rule (all of them when fewer exist). The 240 are then
ordered by SHA-256("scribe-v3-audit-shuffle|" + id) and cut into slices, so every slice mixes both groups.
A slice item holds audit_id, note_date, note_text and the claimed answer only; the status is in key.json.
All text is SYNTHETIC. Nothing here is for clinical use.
"""

import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import AUDIT, CANDIDATES, GATE, ROOT, log, now, order_key, read_jsonl, save_json, sha256_file  # noqa: E402

N_ACCEPTED, N_REJECTED, SLICES, PER_SLICE = 160, 80, 8, 30
SALT, SALT_SHUFFLE, SALT_ID = "scribe-v3-audit", "scribe-v3-audit-shuffle", "scribe-v3-audit-id"
WRITER_INSTRUCTIONS = ROOT / "data/scribe/v2/WRITER_INSTRUCTIONS.md"
VERDICTS = ("stated", "wrong_date", "wrong_type", "not_stated", "ambiguous")


def section(text, start, end):
    """The lines of WRITER_INSTRUCTIONS.md from the heading `start` up to the heading `end` (exclusive)."""
    a = text.index(start)
    b = text.index(end, a)
    return text[a:b].rstrip() + "\n"


def instructions(type_names, n_accepted_rejected):
    src = WRITER_INSTRUCTIONS.read_text()
    events = section(src, "### 3.5 Pathway events", "### 3.6 Dated items that are not events")
    table = "\n".join(line for line in events.splitlines() if line.startswith("|"))
    assert table.count("\n") == 10, "the event table of the writer instructions changed"
    non_events = section(src, "### 3.6 Dated items that are not events", "### 3.7 The moment of writing is not an event")
    non_events = "\n".join(non_events.splitlines()[1:]).strip()
    route = section(src, "### 3.4 Route", "### 3.5 Pathway events")
    route_names = route.split("\n\n")[1].strip()
    sys.path.insert(0, str(ROOT / "scribe"))
    from sample import ROUTES  # version 1, read only

    route_codes = "\n".join(f"| `{code}` | `{name}` |" for code, name in ROUTES.items())
    codes = "\n".join(f"| `{t}` | `{name}` |" for t, name in type_names.items())
    return f"""# Auditor instructions: SAMA pathway scribe, teaching round 2

Everything here is SYNTHETIC: invented Finnish clinical-style notes written by a language model from sampled
answer keys. No real patients. Nothing is for clinical use.

You are one of eight independent auditors. You check whether the claimed answer of each note is really what
the note says. Judge from the note alone.

## 1. Files

**Input.** `data/scribe/v3/audit/slice-XX.json` (XX = `01` .. `08`; you are given one). A JSON array of
{PER_SLICE} items:

```json
{{"audit_id": "a1b2c3d4e5f6",
 "note_date": "2026-04-30",
 "note_text": "<the note, Finnish, one string>",
 "claimed": {{"entry_route": "EMERGENCY",
             "events": [{{"index": 0, "type": "PHYSICIAN_ASSESSMENT", "date": "2025-09-30", "precision": "DAY"}},
                        {{"index": 1, "type": "REFERRAL_SENT", "date": "2025-11-01", "precision": "MONTH"}}]}}}}
```

`claimed.events` may be empty: the claim is then that the note states no dated cancer-pathway event at all.

**Do not open any other file** under `data/scribe/v3/` or `scribe/` (in particular not `key.json`, the
candidates, the judges' output or another auditor's output). Do not use a model or a tool to pre-label
the notes. Your verdicts must be your own reading of the note.

**Output.** `data/scribe/v3/audit/out/slice-XX.json` (create the `out` directory if needed; write no other
file and change no existing file). One JSON array with one object per item, in the order of the input, and
`audit_id` on every item:

```json
[
  {{"audit_id": "a1b2c3d4e5f6",
   "events": [
     {{"index": 0, "verdict": "stated", "quote": "Päivystävä lääkäri tutki ja arvioi potilasta 212 päivää sitten"}},
     {{"index": 1, "verdict": "wrong_type", "quote": "lähete saapui erikoissairaanhoitoon marraskuussa 2025"}}
   ],
   "unlisted_event": {{"present": false, "quote": ""}},
   "route_ok": true}}
]
```

UTF-8, valid JSON, nothing before `[` or after `]`. `events` has exactly one entry per claimed event, with
the same `index`. An optional `"comment"` string per item is allowed and is not scored.

## 2. Dates

Resolve every date expression against `note_date`:

| in the note | means |
| --- | --- |
| `3.2.2025`, `3. helmikuuta 2025` | 2025-02-03 |
| `3.2.` (no year) | that day and month in the year of `note_date` |
| `12 päivää sitten` | `note_date` minus 12 days |
| `8 viikkoa sitten` | `note_date` minus 56 days (8 x 7) |
| `helmikuussa 2025` | the calendar month 2025-02 |

A claimed event with `"precision": "MONTH"` and `"date": "2025-02-01"` claims **the month** February 2025,
not the first day of it; it is right when the note gives that month for that event. A claimed event with
`"precision": "DAY"` is right only when the note's expression resolves to exactly that day. Do the
arithmetic carefully (month lengths, leap years); a date that is off by one day is `wrong_date`.

## 3. The nine event types

Codes and their Finnish names:

| code | Finnish name |
| --- | --- |
{codes}

The definitions, copied from `data/scribe/v2/WRITER_INSTRUCTIONS.md` (section 3.5; written for the writers of
version 2, so "the note must make clear that" is the definition, and the "never" column lists wordings that do
NOT establish the event):

{table}

Dated items that are not pathway events (same source, section 3.6):

{non_events}

The moment of writing (`note_date`) is not an event. A plan, a booked or future appointment, a negation or a
hedge (`ilmeisesti`, `noin`) does not state an event.

## 4. Verdict per claimed event

Give exactly one verdict for every claimed event:

| verdict | when | quote |
| --- | --- | --- |
| `stated` | the note states that an event of this type happened on this date (this month for `MONTH`) | the passage that states it, including the date expression |
| `wrong_date` | the note states an event of this type, but its date resolves to another day (or another month) | the passage with the date expression the note really gives |
| `wrong_type` | the note has this date, but what happened then is another kind of event or not a pathway event (referral arrived instead of sent, a nurse instead of a physician, a plan instead of a completed act, ...) | the passage that shows what the note really says at that date |
| `not_stated` | the note states no such event: neither this type at another date nor this date with another event | empty string |
| `ambiguous` | a careful reader cannot decide between `stated` and one of the others (the verb does not show sent or received, it is unclear who assessed, the date could belong to two events, ...) | the passage that is unclear |

Use `ambiguous` only for a real doubt about the note, not to avoid the date arithmetic.

**The quote** is an exact substring of `note_text`: copied character for character, including punctuation,
capital letters and spaces, with no ellipsis, no added quotation marks and nothing left out in the middle.
Keep it short (one clause or sentence, at most about 200 characters) and make sure it contains the evidence.
A verdict whose quote is not an exact substring of the note is discarded by the scorer, and so is a
`stated`, `wrong_date`, `wrong_type` or `ambiguous` verdict with an empty quote. If you can run code, check
`quote in note_text` for every quote before saving.

## 5. `unlisted_event`

`{{"present": true, "quote": "..."}}` when the note states a completed, dated cancer-pathway event (one of the
nine types) that is **not** in the claimed list: its type or its resolved date differs from every claimed
entry. The quote is an exact substring that shows the event and its date. Otherwise
`{{"present": false, "quote": ""}}`.

Do not count: birth dates, vaccinations and other care unrelated to cancer, future or booked appointments,
pathway steps mentioned without any date, and the event you already marked `wrong_date` or `wrong_type`
(that one is the same statement of the note, counted once).

## 6. `route_ok`

| code | Finnish name |
| --- | --- |
{route_codes}

From `data/scribe/v2/WRITER_INSTRUCTIONS.md` (section 3.4): {route_names}

`route_ok` is `true` when the note says that the patient came onto the cancer pathway through the claimed
service. For an item with an empty event list it is `true` when the contact described in the note takes
place in the claimed service. Otherwise `false`.

## 7. Before saving

- {PER_SLICE} objects, each with the `audit_id` of its item, in input order.
- One verdict per claimed event, each one of: {", ".join(f"`{v}`" for v in VERDICTS)}.
- Every non-empty quote is an exact substring of its note.
- You judged the note, not the plausibility of the claim: a claim can be perfectly plausible and still not be
  what the note says.

The sample holds {n_accepted_rejected} notes in eight slices; which notes a gate accepted is not shown to you.
"""


def main():
    cands = {c["id"]: c for c in read_jsonl(CANDIDATES)}
    judged = read_jsonl(GATE / "judged.jsonl")
    acc = sorted((r for r in judged if r["pass"] is True), key=lambda r: order_key(r["id"], SALT))
    rej = sorted((r for r in judged if r["pass"] is False), key=lambda r: order_key(r["id"], SALT))
    assert all(cands[r["id"]]["code_check"]["passed"] for r in acc + rej)
    take = [(r, "accepted") for r in acc[:N_ACCEPTED]] + [(r, "rejected") for r in rej[:N_REJECTED]]
    take.sort(key=lambda x: order_key(x[0]["id"], SALT_SHUFFLE))
    assert len(take) == SLICES * PER_SLICE, f"{len(take)} notes available, {SLICES * PER_SLICE} wanted"

    type_names = {}
    for c in cands.values():
        for f in c["facts"]:
            type_names.setdefault(f["type"], f["meaning"])
    order = ["SYMPTOM_ONSET_REPORTED", "FIRST_CONTACT", "PHYSICIAN_ASSESSMENT", "REFERRAL_SENT", "REFERRAL_RECEIVED", "SPECIALIST_VISIT", "DIAGNOSIS", "MDT_DECISION", "TREATMENT_START"]
    assert set(type_names) == set(order), sorted(type_names)
    type_names = {t: type_names[t] for t in order}

    AUDIT.mkdir(parents=True, exist_ok=True)
    key, files = {}, {}
    for s in range(SLICES):
        items = []
        for r, status in take[s * PER_SLICE : (s + 1) * PER_SLICE]:
            c = cands[r["id"]]
            aid = order_key(r["id"], SALT_ID)[:12]
            assert aid not in key
            items.append(
                dict(
                    audit_id=aid,
                    note_date=c["note_date"],
                    note_text=c["note_text"],
                    claimed=dict(
                        entry_route=c["entry_route"],
                        events=[dict(index=i, type=e["type"], date=e["date"], precision=e["precision"]) for i, e in enumerate(c["events"])],
                    ),
                )
            )
            key[aid] = dict(
                id=r["id"],
                slice=s + 1,
                status=status,
                readback_consistent=c["readback"]["consistent"],
                curriculum=c["curriculum"],
                kind=c["kind"],
                n_events=len(c["events"]),
                repaired=c["repaired"],
            )
        name = f"slice-{s + 1:02d}.json"
        text = "[\n" + ",\n".join(json.dumps(i, ensure_ascii=False) for i in items) + "\n]\n"
        assert not re.search(r"accepted|rejected|readback|curriculum|\"pass\"", text), "a slice must not show the status"
        (AUDIT / name).write_text(text)
        files[name] = dict(
            items=len(items),
            accepted=sum(key[i["audit_id"]]["status"] == "accepted" for i in items),
            rejected=sum(key[i["audit_id"]]["status"] == "rejected" for i in items),
            sha256=sha256_file(AUDIT / name),
        )
    n_acc = sum(v["status"] == "accepted" for v in key.values())
    n_rej = sum(v["status"] == "rejected" for v in key.values())
    meta = dict(
        schemaVersion="scribe-audit-key-v1",
        generated=now(),
        synthetic=True,
        sample=dict(
            order="SHA-256('scribe-v3-audit|' + id) within each group; slices by SHA-256('scribe-v3-audit-shuffle|' + id)",
            accepted_by_rule=dict(sampled=n_acc, available=len(acc), wanted=N_ACCEPTED),
            code_check_pass_rejected_by_rule=dict(sampled=n_rej, available=len(rej), wanted=N_REJECTED),
            by_status_and_readback={
                f"{st}/{'consistent' if rb else 'inconsistent'}": n
                for (st, rb), n in sorted(collections.Counter((v["status"], bool(v["readback_consistent"])) for v in key.values()).items())
            },
            by_status_and_curriculum={
                f"{st}/{cu}": n for (st, cu), n in sorted(collections.Counter((v["status"], v["curriculum"]) for v in key.values()).items())
            },
        ),
        judged_sha256=sha256_file(GATE / "judged.jsonl"),
        candidates_sha256=sha256_file(CANDIDATES),
        slices=files,
        items=key,
    )
    save_json(AUDIT / "key.json", meta)
    (AUDIT / "INSTRUCTIONS.md").write_text(instructions(type_names, len(key)))
    log(
        "audit_inputs",
        inputs=["data/scribe/v3/gate/judged.jsonl", str(CANDIDATES.relative_to(ROOT)), str(WRITER_INSTRUCTIONS.relative_to(ROOT))],
        outputs=[f"data/scribe/v3/audit/{n}" for n in list(files) + ["key.json", "INSTRUCTIONS.md"]],
        metrics=dict(sample=meta["sample"], slices={n: {k: v for k, v in f.items() if k != "sha256"} for n, f in files.items()}),
        cost_usd=0,
        status="ok",
    )
    print(json.dumps(dict(sample=meta["sample"], slices={n: {k: v for k, v in f.items() if k != "sha256"} for n, f in files.items()}), indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
