"""Forward-phrase rule: copy a radiologist's written follow-up recommendation and compute its due date.

Rule-based, standard library only, no model. SAMA never decides what follow-up is due: it copies
what the radiologist wrote and does calendar arithmetic. A due date is computed only when a line
names exactly one forward interval ("3 kk kuluttua", "kuuden kuukauden päästä", "vuoden kuluttua")
or exactly one calendar day ("15.3.2026"). Everything else that mentions follow-up goes to a
person: ranges, approximate or conditional wording, a month without a day, a decimal interval,
two time expressions, an attributive interval next to a backward reference, a recommendation
without a time, or a "no follow-up" statement next to a time or a recommendation verb. Past
calendar dates are comparisons with earlier imaging and are ignored. An explicit "ei jatkotoimia" (no further action) gives NONE.

Written from general Finnish before the 60 test lines in reports.py existed; its sha256 is logged
in runs/ship-safetynet.jsonl (step 1). It does not use or modify scribe/v3/resolve.py or lexicon.py.
"""
from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

RULE_VERSION = 'forward-v1'
DUE_DATE, PERSON, NONE = 'DUE_DATE', 'PERSON', 'NONE'
OUTCOMES = (DUE_DATE, PERSON, NONE)

# Genitive number words used before a time unit ("kolmen kuukauden kuluttua").
NUMBER_WORDS = {
    'yhden': 1, 'kahden': 2, 'kolmen': 3, 'neljän': 4, 'viiden': 5, 'kuuden': 6,
    'seitsemän': 7, 'kahdeksan': 8, 'yhdeksän': 9, 'kymmenen': 10,
    'yhdentoista': 11, 'kahdentoista': 12, 'kahdeksantoista': 18,
}
_WORDS = '|'.join(sorted(NUMBER_WORDS, key=len, reverse=True))

# Unit spellings mapped to (calendar unit, multiplier).
UNITS = {
    'kk': ('month', 1), 'kuukauden': ('month', 1), 'kuukautta': ('month', 1), 'kuuk': ('month', 1),
    'viikon': ('day', 7), 'viikkoa': ('day', 7), 'vk': ('day', 7), 'vko': ('day', 7),
    'vuoden': ('month', 12), 'vuotta': ('month', 12), 'v': ('month', 12),
    'päivän': ('day', 1), 'päivää': ('day', 1), 'pv': ('day', 1), 'vrk': ('day', 1),
}
_UNITS = '|'.join(sorted((re.escape(u) for u in UNITS), key=len, reverse=True))
# A bare genitive unit means one of it ("vuoden kuluttua" = in a year); abbreviations need a number.
BARE_ONE = {'kuukauden', 'viikon', 'vuoden'}
FORWARD = r'(?:kuluttua|päästä|kuluessa|sisällä)'
CONTROL_NOUN = r'(?:kontrolli|seuranta|uusinta)'

_NUM = rf'(?:(?P<num>\d{{1,2}})|(?P<word>{_WORDS})|(?P<half>puolen))'
# "3 kk kuluttua", "3 kk:n päästä", "kuuden kuukauden kuluttua", "vuoden kuluttua", "puolen vuoden päästä"
INTERVAL = re.compile(rf'(?<![\w.,/-])(?:{_NUM}\s*)?(?P<unit>{_UNITS})\.?(?::n)?\s+{FORWARD}(?!\w)')
# "3 kk:n kontrolli-TT", "kuuden kuukauden seuranta" (attributive form, number required)
ATTRIBUTIVE = re.compile(rf'(?<![\w.,/-]){_NUM}\s*(?P<unit>{_UNITS})\.?(?::n)?\s+{CONTROL_NOUN}')
_ANYNUM = rf'(?:\d{{1,2}}|{_WORDS})'
RANGE = re.compile(rf'(?<![\w.,])({_ANYNUM})\s*(?:-|tai|–)\s*({_ANYNUM})\s*(?:{_UNITS})(?!\w)')
DECIMAL = re.compile(rf'\d+[.,]\d+\s*(?:{_UNITS})(?:\.|:n)?\s+(?:{FORWARD}|{CONTROL_NOUN})')
ABS_DATE = re.compile(r'(?<![\d.])(\d{1,2})\.(\d{1,2})\.(\d{4})(?!\d)')
MONTHS = ('tammikuu', 'helmikuu', 'maaliskuu', 'huhtikuu', 'toukokuu', 'kesäkuu', 'heinäkuu',
          'elokuu', 'syyskuu', 'lokakuu', 'marraskuu', 'joulukuu')
MONTH_ONLY = re.compile(rf'(?:\b(?:{"|".join(MONTHS)})(?:ssa|n|ta)?\b|(?<![\d.])\d{{1,2}}/\d{{4}}\b)')
VAGUE = re.compile(
    r'\b(?:noin|n\.(?=\s*\d)|suunnilleen|arviolta|parin|muutaman|joidenkin|myöhemmin|lähiaikoina|'
    r'tarvittaessa|harki\w*|kliinisen tilanteen mukaan|kliinisin perustein|tarpeen mukaan|'
    r'oireiden mukaan|aikanaan|sopivana ajankohtana|myöhemmässä vaiheessa|mikäli|jos|aikaisintaan|'
    r'viimeistään ennen|ehkä|mahdollisesti)(?!\w)')
BACKWARD = re.compile(r'\b(?:edellinen|edellisen|edellisessä|aiempi|aiemman|aiemmassa|aiemmin|sitten)\b')
NO_FOLLOWUP = re.compile(
    r'\b(?:ei (?:jatkotoimia|jatkotoimenpiteitä|jatkotutkimuksia|kontrollitarvetta|seurantatarvetta|'
    r'tarvetta (?:kontrollille|seurannalle|jatkotutkimuksille|jatkotoimille)|'
    r'vaadi (?:jatkotoimia|seurantaa|kontrollia|jatkotutkimuksia)|'
    r'edellytä (?:jatkotoimia|seurantaa|kontrollia)|aihetta (?:kontrolliin|seurantaan|jatkotoimiin))|'
    r'(?:kontrollia|seurantaa|jatkotoimia|jatkotutkimuksia) ei tarvita)\b')
RECOMMENDATION = re.compile(
    r'(?:kontrolli|seuranta|seurann|uusinta|jatkotutki|jatkoselvit|jatkokuva|lähete|'
    r'konsultaatio|suositel|suositus|ohjataan)')
# Next to an explicit "no follow-up", only an explicit recommendation verb or a time is a conflict.
EXPLICIT_RECOMMENDATION = re.compile(r'(?:suositel|suositus|ohjataan|lähete)')
SENTENCE_END = re.compile(r'(?<=[.!?])\s+(?=[A-ZÅÄÖ])')


def normalise(text: str) -> str:
    """Lower-case and map dashes and odd spaces one character to one, so offsets stay valid."""
    table = {'–': '-', '—': '-', '−': '-', ' ': ' ', ' ': ' ', ' ': ' '}
    return ''.join(table.get(c, c) for c in text).lower()


def add_months(d: date, n: int) -> date:
    """Calendar month addition; the day is clamped to the last day of the target month."""
    y, m = divmod(d.month - 1 + n, 12)
    year, month = d.year + y, m + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def due_from(report_date: date, n: int, unit: str) -> date:
    kind, mult = UNITS[unit]
    return add_months(report_date, n * mult) if kind == 'month' else report_date + timedelta(days=n * mult)


def _count(m: re.Match) -> int | None:
    if m.group('num'):
        return int(m.group('num'))
    if m.group('word'):
        return NUMBER_WORDS[m.group('word')]
    if m.group('half'):
        return None  # handled by the caller: "puolen vuoden" is six months
    return 1 if m.group('unit') in BARE_ONE else 0


def _sentence(original: str, start: int, end: int) -> str:
    """Copy, verbatim, the sentence of the original line that contains [start, end)."""
    bounds = [0] + [m.end() for m in SENTENCE_END.finditer(original)] + [len(original)]
    for a, b in zip(bounds, bounds[1:]):
        if a <= start < b or (start == b == len(original)):
            return original[a:max(b, end)].strip()
    return original.strip()


def _times(t: str, report_date: date):
    """All forward time expressions: (start, end, due_date, n, unit, kind)."""
    found = []
    for rx, kind in ((INTERVAL, 'interval'), (ATTRIBUTIVE, 'attributive')):
        for m in rx.finditer(t):
            unit = m.group('unit')
            n = _count(m)
            if m.group('half'):
                if UNITS[unit] != ('month', 12):
                    continue
                n, unit = 6, 'kk'
            if not n:
                continue
            if any(m.start() < e and s < m.end() for s, e, *_ in found):
                continue
            found.append((m.start(), m.end(), due_from(report_date, n, unit), n, unit, kind))
    for m in ABS_DATE.finditer(t):
        try:
            d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            d = None
        if d is not None and d < report_date:
            continue  # a past date is a comparison with earlier imaging, never a forward recommendation
        found.append((m.start(), m.end(), d, None, None, 'calendar_date'))
    return sorted(found)


def read(line: str, report_date: date) -> dict:
    """Apply the rule to one report line. Returns a dict; it never raises on text."""
    t = normalise(line)
    out = dict(outcome=None, due_date=None, interval=None, matched_phrase=None, span=None,
               recommendation_text=None, reason=None, rule_version=RULE_VERSION)

    def person(reason, span=None):
        s = span or (0, len(line))
        out.update(outcome=PERSON, reason=reason, span=list(span) if span else None,
                   matched_phrase=line[s[0]:s[1]] if span else None,
                   recommendation_text=_sentence(line, *s) if span else line.strip())
        return out

    times = _times(t, report_date)
    stop = NO_FOLLOWUP.search(t)
    rec_text = NO_FOLLOWUP.sub(' ', t)
    rec = RECOMMENDATION.search(rec_text)
    if stop:
        if times or RANGE.search(t) or EXPLICIT_RECOMMENDATION.search(rec_text):
            return person('no_followup_and_followup_both_written', (stop.start(), stop.end()))
        out.update(outcome=NONE, reason='explicit_no_followup', span=[stop.start(), stop.end()],
                   matched_phrase=line[stop.start():stop.end()],
                   recommendation_text=_sentence(line, stop.start(), stop.end()))
        return out
    for rx, reason in ((RANGE, 'range'), (DECIMAL, 'decimal_interval'), (MONTH_ONLY, 'month_without_day'),
                       (VAGUE, 'vague_or_conditional')):
        m = rx.search(t)
        if m:
            return person(reason, (m.start(), m.end()))
    if any(x[5] == 'attributive' for x in times) and BACKWARD.search(t):
        m = BACKWARD.search(t)  # "edellinen 3 kk:n kontrolli" may describe a past scan
        return person('backward_reference', (m.start(), m.end()))
    if len(times) > 1:
        return person('several_time_expressions', (times[0][0], times[-1][1]))
    if len(times) == 1:
        s, e, due, n, unit, kind = times[0]
        if due is None:
            return person('invalid_calendar_date', (s, e))
        out.update(outcome=DUE_DATE, due_date=due.isoformat(), span=[s, e], matched_phrase=line[s:e],
                   interval=None if kind == 'calendar_date' else dict(n=n, unit=UNITS[unit][0], multiplier=UNITS[unit][1]),
                   recommendation_text=_sentence(line, s, e), reason=kind)
        return out
    if rec:
        return person('recommendation_without_time', (rec.start(), rec.end()))
    out.update(outcome=NONE, reason='no_recommendation_found', recommendation_text=None)
    return out
