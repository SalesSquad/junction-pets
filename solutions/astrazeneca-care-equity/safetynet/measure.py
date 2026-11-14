"""Score the frozen forward-phrase rule on the 60 SYNTHETIC report lines (safetynet.reports)."""
from __future__ import annotations

import math
from collections import Counter
from datetime import date

from . import rule
from .reports import render


def wilson(k: int, n: int, z: float = 1.96):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def score(lines: list[dict]) -> dict:
    rows, confusion = [], Counter()
    for x in lines:
        r = rule.read(x['text'], date.fromisoformat(x['report_date']))
        confusion[(x['gold_outcome'], r['outcome'])] += 1
        copied = all(s is None or s in x['text'] for s in (r['matched_phrase'], r['recommendation_text']))
        rows.append(dict(line_id=x['line_id'], family=x['family'], gold_outcome=x['gold_outcome'],
                         gold_due_date=x['gold_due_date'], outcome=r['outcome'], due_date=r['due_date'],
                         reason=r['reason'], matched_phrase=r['matched_phrase'], copied_verbatim=copied,
                         correct=(r['outcome'] == x['gold_outcome'] and r['due_date'] == x['gold_due_date'])))
    by = lambda g: [r for r in rows if r['gold_outcome'] == g]
    due, person, none = by('DUE_DATE'), by('PERSON'), by('NONE')
    exact = sum(r['outcome'] == 'DUE_DATE' and r['due_date'] == r['gold_due_date'] for r in due)
    to_person = [r for r in rows if r['outcome'] == 'PERSON']
    person_ok = sum(r['outcome'] == 'PERSON' for r in person)
    metrics = dict(
        lines=len(rows),
        gold_counts={g: len(by(g)) for g in rule.OUTCOMES},
        exact_due_date=dict(k=exact, n=len(due), share=round(exact / len(due), 4) if due else None, wilson95=wilson(exact, len(due))),
        sent_to_person_when_gold_person=dict(k=person_ok, n=len(person), share=round(person_ok / len(person), 4) if person else None, wilson95=wilson(person_ok, len(person))),
        gold_person_among_sent_to_person=dict(k=sum(r['gold_outcome'] == 'PERSON' for r in to_person), n=len(to_person)),
        none_correct=dict(k=sum(r['outcome'] == 'NONE' for r in none), n=len(none)),
        all_correct=dict(k=sum(r['correct'] for r in rows), n=len(rows)),
        errors=dict(
            wrong_due_date=sum(r['outcome'] == 'DUE_DATE' and r['due_date'] != r['gold_due_date'] for r in rows if r['gold_outcome'] == 'DUE_DATE'),
            invented_date_for_person_line=sum(r['outcome'] == 'DUE_DATE' for r in person),
            invented_date_for_none_line=sum(r['outcome'] == 'DUE_DATE' for r in none),
            missed_recommendation=sum(r['outcome'] == 'NONE' for r in due + person),
            due_line_sent_to_person=sum(r['outcome'] == 'PERSON' for r in due),
        ),
        copied_verbatim=dict(k=sum(r['copied_verbatim'] for r in rows), n=len(rows)),
        confusion=[dict(gold=g, rule=p, n=n) for (g, p), n in sorted(confusion.items())],
    )
    return dict(metrics=metrics, rows=rows)


def evaluate() -> dict:
    lines = render()
    return dict(rule_version=rule.RULE_VERSION, lines=lines, **score(lines))
