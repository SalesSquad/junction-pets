import re

from sample import MONTHS, ROUTES

DATE_RE = re.compile(
    r"\b(?:19|20)\d{2}\b|\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[./]\d{1,2}[./](?:\d{2,4})?|\b\d+\.?\s*(?:päivää|päivän|viikkoa|viikon|kuukautta|kuukauden)\s+(?:sitten|aiemmin|kuluttua)|\b(?:\d{1,2}\.\s*)?(?:"
    + "|".join(MONTHS)
    + r")kuu\w*(?:\s+\d{4})?|\b(?:eilen|tänään|huomenna|toissapäivänä|viime viikolla|viime kuussa)\b",
    re.I,
)


def code_check(row):
    text = row["note_text"]
    missing = []
    for f in row["facts"] + row["distractors"]:
        s = f["expression"]
        pattern = r"(?<!\w)" + re.escape(s) + r"(?!\w)"
        if not re.search(pattern, text):
            missing.append(s)
        text = re.sub(pattern, " DATE ", text)
    extra = DATE_RE.findall(text)
    return dict(
        ok=not missing and not extra and 60 <= len(row["note_text"].split()) <= 140,
        missing=missing,
        extra=extra,
        words=len(row["note_text"].split()),
    )


ENGLISH = {
    "SYMPTOM_ONSET_REPORTED": "reported onset of cancer-related symptoms",
    "FIRST_CONTACT": "first contact with healthcare about cancer-related symptoms",
    "PHYSICIAN_ASSESSMENT": "physician assessment on the cancer pathway",
    "REFERRAL_SENT": "cancer referral sent",
    "REFERRAL_RECEIVED": "cancer referral received",
    "SPECIALIST_VISIT": "cancer specialist visit",
    "DIAGNOSIS": "cancer diagnosis confirmed",
    "MDT_DECISION": "multidisciplinary team treatment decision",
    "TREATMENT_START": "cancer treatment started",
}


def questions(row, strict=False):
    q = {}
    prefix = (
        "Does the note explicitly and unambiguously establish that "
        if strict
        else "According to the note, is it true that "
    )
    for i, f in enumerate(row["facts"]):
        q[f"event_{i}"] = {
            "type": "noul",
            "instructions": prefix
            + f"{f['meaning']} ({ENGLISH[f['type']]}) took place {f['expression']}, given note date {row['note_date']}? Require the actual event, not a plan or negation.",
        }
    q["unlisted"] = {
        "type": "noul",
        "instructions": ("Scrutinize all dated statements. " if strict else "")
        + "Does the note describe any completed dated cancer-pathway event NOT in expected_events? Birth, vaccination and future plans do not count. Event types include symptom onset, first contact, physician assessment, referral sent/received, specialist visit, diagnosis, MDT decision and treatment start.",
    }
    for i, f in enumerate(row["distractors"]):
        q[f"distractor_{i}"] = {
            "type": "noul",
            "instructions": prefix
            + f"the date {f['expression']} ({f['meaning']}) is presented as a completed cancer-pathway event rather than a birth date, unrelated visit or future plan?",
        }
    if strict:
        for i, f in enumerate(row["facts"]):
            q[f"event_{i}"]["instructions"] = (
                f"Read only the source note. Is there clear affirmative textual evidence of a completed {f['meaning']} ({ENGLISH[f['type']]}) at '{f['expression']}', interpreted relative to {row['note_date']}? Reject future plans, hypothetical wording, negation, or a date attached to another activity. Expected facts are not evidence."
            )
        q["unlisted"]["instructions"] = (
            "Can you identify at least one affirmative completed cancer-pathway event with a stated date that is absent from the expected event/date pairs? Count extra event types even at an already listed date. Exclude birth dates, unrelated care and future plans. Inspect the source note, not assumptions about the expected list."
        )
        for i, f in enumerate(row["distractors"]):
            q[f"distractor_{i}"]["instructions"] = (
                f"Would extraction of an actual completed cancer-pathway event anchored to '{f['expression']}' be supported by the source note? This date is expected to be {f['meaning']}; assess the note's wording rather than trusting that expectation."
            )
    q["route"] = {
        "type": "noul",
        "instructions": ("Strictly scrutinize the source. " if strict else "")
        + f"Does the note itself explicitly establish cancer-pathway entry via {ROUTES[row['entry_route']]} ({row['entry_route']})? Being a customer of a service alone does not establish entry via it. Absence of a stated route means no; do not infer from expected labels.",
    }
    return q


def accept(p, strict=False):
    if not any(k.startswith("event_") for k in p) or "unlisted" not in p:
        return False
    if any(not 0 <= v <= 1 for v in p.values()):
        return False
    return all(
        v >= (0.9 if strict else 0.8)
        if k.startswith("event_") or k == "route"
        else v < (0.2 if strict else 0.5)
        for k, v in p.items()
    )
