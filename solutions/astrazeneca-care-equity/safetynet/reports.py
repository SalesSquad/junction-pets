"""SYNTHETIC Finnish radiology report lines with follow-up recommendations, rendered by code templates.

Not real reports and not written by a model. Each line is a finding sentence plus a recommendation
sentence, and carries its gold label from the template: DUE_DATE with the date a person would
compute from what the radiologist wrote, PERSON (a range, approximate, vague or conditional wording,
a month without a day, two recommendations, or a recommendation without a time) or NONE (an
explicit "no further action"). The gold date uses its own month arithmetic, not safetynet.rule.

Written after safetynet/rule.py was frozen (runs/ship-safetynet.jsonl step 1), by the same step,
so a score on these lines measures the rule against its own template family, not real reports.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

SEED = 20261115
GOLD_OUTCOMES = ('DUE_DATE', 'PERSON', 'NONE')

LUNG_FINDINGS = [
    'Oikean yläkeuhkon {k} mm kiinteä kyhmy.',
    'Vasemman alalohkon {k} mm osittain kiinteä kyhmy.',
    'Oikean keskilohkon {k} mm mattalasimuutos.',
    'Keuhkoissa useita alle {k} mm kyhmyjä.',
    'Vasemman yläkeuhkon {k} mm kyhmy, joka on ennallaan verrattuna 12 kk sitten otettuun TT:hen.',
    'Oikean alalohkon {k} mm kyhmy on kasvanut 1 mm verrattuna {past} tutkimukseen.',
]
OTHER_FINDINGS = [
    'Maksassa {k} mm epäselvä leesio.',
]
# Findings for "no further action" lines: benign or resolved, so the synthetic text stays plausible.
BENIGN_FINDINGS = [
    'Kalkkeutunut {k} mm granulooma, ennallaan verrattuna 12 kk sitten otettuun TT:hen.',
    'Aiemmin todettu {k} mm kyhmy on hävinnyt verrattuna {past} tutkimukseen.',
    'Keuhkoissa ei kyhmyjä eikä infiltraatteja.',
    'Intrapulmonaalinen {k} mm imusolmuke, hyvänlaatuisen näköinen.',
]
WORDS = {3: 'kolmen', 6: 'kuuden', 9: 'yhdeksän', 12: 'kahdentoista', 2: 'kahden'}


def _gold_months(d: date, n: int) -> date:
    """Independent of safetynet.rule: step month by month and clamp the day."""
    year, month = d.year, d.month
    for _ in range(n):
        month += 1
        if month == 13:
            year, month = year + 1, 1
    last = (date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)).day
    return date(year, month, min(d.day, last))


def _fi(d: date) -> str:
    return f'{d.day}.{d.month}.{d.year}'


def _templates():
    """(family, gold_outcome, recommendation template, gold(n) -> (kind, value) or None, parameter list)."""
    m = lambda n: ('months', n)
    w = lambda n: ('days', 7 * n)
    return [
        ('digits_kk', 'DUE_DATE', 'Suositellaan kontrolli-TT {n} kk kuluttua.', m, [3, 6, 12, 3, 6]),
        ('digits_kuukauden', 'DUE_DATE', 'Kontrolli-TT {n} kuukauden kuluttua.', m, [3, 6, 12, 9]),
        ('number_words', 'DUE_DATE', 'Seuranta-TT {word} kuukauden kuluttua.', m, [3, 6, 9, 12]),
        ('weeks', 'DUE_DATE', 'Kontrollikuvaus {n} viikon kuluttua.', w, [4, 6, 8]),
        ('years_bare', 'DUE_DATE', 'Uusinta-TT vuoden kuluttua.', lambda n: ('months', 12), [1]),
        ('years_digits', 'DUE_DATE', 'Kontrolli-TT {n} vuoden kuluttua.', lambda n: ('months', 12 * n), [2]),
        ('years_words', 'DUE_DATE', 'Seuranta-TT {word} vuoden päästä.', lambda n: ('months', 12 * n), [2]),
        ('half_year', 'DUE_DATE', 'Kontrolli-TT puolen vuoden kuluttua.', lambda n: ('months', 6), [1, 1]),
        ('kk_n_paasta', 'DUE_DATE', 'Kontrolli-TT {n} kk:n päästä.', m, [3, 6, 12]),
        ('attributive', 'DUE_DATE', 'Suositellaan {n} kk:n kontrolli-TT.', m, [3, 6, 12]),
        ('calendar_date', 'DUE_DATE', 'Kontrolli-TT {date}.', lambda n: ('days', n), [45, 120, 200]),
        ('range_digits', 'PERSON', 'Kontrolli-TT {a}–{b} kk kuluttua.', None, [(3, 6), (6, 12), (3, 6), (6, 12)]),
        ('range_words', 'PERSON', 'Seuranta-TT {wa} tai {wb} kuukauden kuluttua.', None, [(3, 6), (6, 12)]),
        ('approximate', 'PERSON', 'Kontrolli-TT {q} {n} kk kuluttua.', None, [('noin', 3), ('n.', 6), ('noin', 12)]),
        ('vague', 'PERSON', '{text}', None, ['Kontrolli harkinnan mukaan.', 'Jatkotutkimukset kliinisen tilanteen mukaan.',
                                             'Seuranta-TT myöhemmin.', 'Kontrolli-TT parin kuukauden kuluttua.']),
        ('conditional', 'PERSON', '{text}', None, ['Mikäli kliinisesti aiheellista, kontrolli-TT 3 kk kuluttua.',
                                                   'Jos oireet jatkuvat, uusintakuvaus.']),
        ('month_only', 'PERSON', 'Kontrolli-TT {month}.', None, [1]),
        ('two_recommendations', 'PERSON', '{text}', None, ['Kontrolli-TT 3 kk kuluttua ja ultraäänitutkimus 6 kk kuluttua.',
                                                           'Kontrolli-TT 6 kk kuluttua; lisäksi vatsan TT 12 kk kuluttua.']),
        ('no_time', 'PERSON', '{text}', None, ['Suositellaan jatkoselvittelyä keuhkopoliklinikalla.', 'Suositellaan kontrolli-TT:tä.']),
        ('ei_jatkotoimia', 'NONE', 'Ei jatkotoimia.', None, [1, 1, 1, 1]),
        ('ei_kontrollitarvetta', 'NONE', 'Ei kontrollitarvetta.', None, [1, 1]),
        ('kontrollia_ei_tarvita', 'NONE', 'Kontrollia ei tarvita.', None, [1, 1]),
        ('ei_seurantatarvetta', 'NONE', 'Ei seurantatarvetta.', None, [1, 1]),
    ]


MONTH_NAMES = ['tammikuussa', 'helmikuussa', 'maaliskuussa', 'huhtikuussa', 'toukokuussa', 'kesäkuussa',
               'heinäkuussa', 'elokuussa', 'syyskuussa', 'lokakuussa', 'marraskuussa', 'joulukuussa']


def render(seed: int = SEED, start: date = date(2025, 1, 1), days: int = 365, prefix: str = 'SYN-RAD',
           lung_share: float = 0.85, end_of_month_every: int = 7) -> list[dict]:
    """Render one line per template parameter (60 with the defaults). Deterministic for a seed."""
    rng = random.Random(seed)
    rows = []
    for family, outcome, tpl, gold, params in _templates():
        for p in params:
            i = len(rows)
            report = start + timedelta(days=rng.randrange(days))
            if end_of_month_every and i % end_of_month_every == 3:
                # Force some month-end report dates to exercise day clamping (31 Jan + 1 month).
                report = date(report.year, report.month, 1) + timedelta(days=40)
                report = report.replace(day=1) - timedelta(days=1)
            past = report - timedelta(days=rng.randrange(150, 400))
            pool = BENIGN_FINDINGS if outcome == 'NONE' else LUNG_FINDINGS if rng.random() < lung_share else OTHER_FINDINGS
            finding = rng.choice(pool).format(k=rng.choice([4, 5, 6, 7, 8, 9, 11]), past=_fi(past))
            fields = dict(n=p if isinstance(p, int) else None, word=WORDS.get(p) if isinstance(p, int) else None)
            gold_due = None
            if family == 'calendar_date':
                gold_due = report + timedelta(days=p)
                fields['date'] = _fi(gold_due)
            elif outcome == 'DUE_DATE':
                kind, value = gold(p)
                gold_due = _gold_months(report, value) if kind == 'months' else report + timedelta(days=value)
            if family in ('range_digits', 'range_words'):
                fields.update(a=p[0], b=p[1], wa=WORDS[p[0]], wb=WORDS[p[1]])
            if family == 'approximate':
                fields.update(q=p[0], n=p[1])
            if isinstance(p, str):
                fields['text'] = p
            if family == 'month_only':
                target = _gold_months(report, 3)
                fields['month'] = f'{MONTH_NAMES[target.month - 1]} {target.year}'
            text = f'{finding} {tpl.format(**fields)}'
            rows.append(dict(line_id=f'{prefix}-{i + 1:03d}', report_date=report.isoformat(), text=text,
                             family=family, gold_outcome=outcome,
                             gold_due_date=gold_due.isoformat() if gold_due else None,
                             language='fi', synthetic=True))
    return rows


if __name__ == '__main__':
    import json
    for r in render():
        print(json.dumps(r, ensure_ascii=False))
