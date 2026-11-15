import datetime
import json
import re

from sample import ROUTES, TYPES


def canonicalise(x):
    if set(x) != {"entry_route", "events"} or x["entry_route"] not in ROUTES:
        raise ValueError("schema/route")
    out = []
    for e in x["events"]:
        if (
            set(e) != {"type", "date", "precision"}
            or e["type"] not in TYPES
            or e["precision"] not in ["DAY", "MONTH"]
        ):
            raise ValueError("event schema")
        d = datetime.date.fromisoformat(e["date"])
        if e["date"] != d.isoformat() or (e["precision"] == "MONTH" and d.day != 1):
            raise ValueError("date")
        out.append(dict(type=e["type"], date=e["date"], precision=e["precision"]))
    return dict(
        entry_route=x["entry_route"],
        events=sorted(out, key=lambda e: (e["date"], e["type"])),
    )


def parse_output(s):
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s.strip())
    return canonicalise(json.loads(s))


def messages(row):
    return [
        {
            "role": "system",
            "content": 'Extract completed cancer-pathway events only. Return only canonical JSON {"entry_route":...,"events":[{"type":...,"date":"YYYY-MM-DD","precision":"DAY|MONTH"}]}. Event types: '
            + ", ".join(TYPES)
            + ". Routes: "
            + ", ".join(ROUTES)
            + ". Resolve relative dates against the note date; a missing year means note year. Month precision uses the first day. Ignore birth dates, unrelated visits and future appointments. Sort events by date then type. Do not infer undocumented events.",
        },
        {
            "role": "user",
            "content": f"Note date: {row['note_date']}\n{row['note_text']}",
        },
    ]
