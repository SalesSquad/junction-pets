"""TEST FIXTURE ONLY. Not the prompt of any trained adapter.

A stand-in prompt module for the expression output format, so the serve tests
can exercise that path. A real expression-format adapter must be served with
the prompt module it was trained with (serve/client.py --prompts).
"""

from sample import ROUTES, TYPES


def messages(row):
    return [
        {
            "role": "system",
            "content": 'Extract completed cancer-pathway events only. Return only JSON {"entry_route":...,"events":[{"type":...,"expression":"<date wording copied from the note>"}]}. Event types: '
            + ", ".join(TYPES)
            + ". Routes: "
            + ", ".join(ROUTES)
            + ". Copy each date expression exactly as written; do not calculate dates.",
        },
        {
            "role": "user",
            "content": f"Note date: {row['note_date']}\n{row['note_text']}",
        },
    ]
