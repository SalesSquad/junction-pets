"""TEST FIXTURE ONLY. Shaped like the interface scribe/v2/data_iface.py expects from
scribe/v2/data_tools.py (expression_messages, EXPRESSION_SCHEMA, resolve_expression), with a
deliberately different event key ("when") to prove that serve/client.py takes the prompt, the
schema and the date resolver from the training-side module when it offers them."""

import datetime

from sample import ROUTES, TYPES, parse_date

EXPRESSION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["entry_route", "events"],
    "properties": {
        "entry_route": {"enum": list(ROUTES)},
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["type", "when"],
                "properties": {"type": {"enum": list(TYPES)}, "when": {"type": "string", "minLength": 1}},
            },
        },
    },
}


def expression_messages(row):
    return [
        {"role": "system", "content": 'Return JSON {"entry_route":...,"events":[{"type":...,"when":"<date wording>"}]}.'},
        {"role": "user", "content": f"Note date: {row['note_date']}\n{row['note_text']}"},
    ]


def resolve_expression(obj, note_date):
    note = datetime.date.fromisoformat(note_date)
    events = []
    for event in obj["events"]:
        date, precision = parse_date(event["when"], note)
        events.append({"type": event["type"], "date": date.isoformat(), "precision": precision})
    return {"entry_route": obj["entry_route"], "events": events}
