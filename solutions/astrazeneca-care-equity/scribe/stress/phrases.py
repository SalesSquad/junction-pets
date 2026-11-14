"""Stress set v1: the date-phrase families and the generator's own date arithmetic. Standard library only.

SYNTHETIC notes only; not for clinical use. A person confirms every extracted event.

Families (NVIDIA_OPTIONS.md step 5):
  standard   the six forms of scribe/sample.py render(): numeric, long, no_year, days, weeks, month
  held-out   phrasings that no training note and no resolver lexicon contains (step 3 holds them out):
             Finnish number words seven to twelve + "päivää sitten" / "viikkoa sitten", and "toissapäivänä"
             (the day before yesterday)
  vague      phrases that name no single exact day ("pari viikkoa sitten", "viime kuussa", ...). The correct outcome
             is "send to a person"; they are scored separately (does a system invent a precise date?)

The held-out arithmetic below is the generator's own; it is deliberately NOT imported from scribe/v3/lexicon.py,
whose frozen version (data/scribe/v4/resolver/freeze.json) excludes these phrases.
"""

import calendar
import datetime as dt
import re

STANDARD_FORMS = ("numeric", "long", "no_year", "days", "weeks", "month")
HELDOUT_NUMBER_WORDS = {
    "seitsemän": 7,
    "kahdeksan": 8,
    "yhdeksän": 9,
    "kymmenen": 10,
    "yksitoista": 11,
    "kaksitoista": 12,
}
HELDOUT_UNITS = {"päivää": 1, "viikkoa": 7}
HELDOUT_ADVERBS = {"toissapäivänä": 2}
HELDOUT_FAMILIES = ("heldout_days_word", "heldout_weeks_word", "heldout_toissa")
# vague phrase -> nominal offset in days and the window of days it could mean; "viime kuussa" is the previous
# calendar month. The window only orders the facts of a specification; it is never an answer.
VAGUE = {
    "pari viikkoa sitten": dict(nominal_days=14, window_days=(10, 21)),
    "muutama päivä sitten": dict(nominal_days=4, window_days=(3, 6)),
    "kuukausi sitten": dict(nominal_days=30, window_days=(25, 35)),
    "pari kuukautta sitten": dict(nominal_days=60, window_days=(45, 75)),
    "viime kuussa": dict(calendar="previous_month"),
}
FAMILIES = STANDARD_FORMS + HELDOUT_FAMILIES + ("vague",)

_WORD_OF = {v: k for k, v in HELDOUT_NUMBER_WORDS.items()}


def render_heldout(family, n=None):
    """The held-out phrase: ("heldout_days_word", 8) -> "kahdeksan päivää sitten"; toissa -> "toissapäivänä"."""
    if family == "heldout_toissa":
        return "toissapäivänä"
    if n not in _WORD_OF:
        raise ValueError(f"held-out number words are 7..12, got {n!r}")
    unit = "päivää" if family == "heldout_days_word" else "viikkoa" if family == "heldout_weeks_word" else None
    if unit is None:
        raise ValueError(family)
    return f"{_WORD_OF[n]} {unit} sitten"


_HELDOUT_RE = re.compile(
    r"(" + "|".join(HELDOUT_NUMBER_WORDS) + r") (" + "|".join(HELDOUT_UNITS) + r") sitten"
)


def heldout_days(phrase):
    """The generator's own arithmetic: days before the note date that a held-out phrase means."""
    if phrase in HELDOUT_ADVERBS:
        return HELDOUT_ADVERBS[phrase]
    m = _HELDOUT_RE.fullmatch(phrase)
    if not m:
        raise ValueError(f"not a held-out phrase: {phrase!r}")
    return HELDOUT_NUMBER_WORDS[m[1]] * HELDOUT_UNITS[m[2]]


def heldout_offsets(family):
    """Every offset (days) a held-out family can express."""
    if family == "heldout_toissa":
        return [2]
    step = 1 if family == "heldout_days_word" else 7
    return [n * step for n in sorted(_WORD_OF)]


def previous_month(note):
    last = note.replace(day=1) - dt.timedelta(days=1)
    return last.replace(day=1), last


def vague_window(phrase, note):
    """(first possible day, last possible day, nominal date, nominal precision) of a vague phrase."""
    v = VAGUE[phrase]
    if v.get("calendar") == "previous_month":
        first, last = previous_month(note)
        return first, last, first, "MONTH"
    lo, hi = v["window_days"]
    return note - dt.timedelta(days=hi), note - dt.timedelta(days=lo), note - dt.timedelta(days=v["nominal_days"]), "DAY"


def month_end(d):
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


# A date or time reference that a specification did not declare. Applied after every declared date string has
# been masked. Extends scribe/verify.py DATE_RE (digits, years, month names, a few adverbs) with spelled-out
# numbers, singular units, vague quantifiers, weekdays and clinical time abbreviations.
_NUMBERS = (
    "yksi kaksi kolme neljä viisi kuusi seitsemän kahdeksan yhdeksän kymmenen yksitoista kaksitoista "
    "kahden kolmen neljän viiden kuuden seitsemän kahdeksan yhdeksän kymmenen "
    "pari parin muutama muutaman useita useamman monta monen puoli puolen"
).split()
UNDECLARED_RE = re.compile(
    "|".join(
        [
            r"\b(?:19|20)\d{2}\b",
            r"\b\d{4}-\d{2}-\d{2}\b",
            r"\b\d{1,2}[./]\d{1,2}[./](?:\d{2,4})?",
            r"\b\d+\.?\s*(?:päiv\w*|viik\w*|kuukau\w*|vuo\w*|vrk|pv\w*|vk\w*|vko|kk|v)\b",
            r"\b(?:" + "|".join(sorted(set(_NUMBERS), key=len, reverse=True)) + r")\s+(?:päiv\w*|viik\w*|kuukau\w*|vuo\w*|tun\w*)",
            r"\b(?:päivä|viikko|kuukausi|vuosi)\s+(?:sitten|aiemmin|sitte)\b",
            r"\b(?:tammi|helmi|maalis|huhti|touko|kesä|heinä|elo|syys|loka|marras|joulu)kuu\w*",
            r"\b(?:eilen|eilis\w*|tänään|huomenna|toissapäivänä|ylihuomenna|toissa\w*)\b",
            r"\b(?:viime|ensi|tällä|tässä|edellisellä|edellisessä|kuluneella|kuluneessa|kuluvalla|kuluvassa)\s+(?:viiko\w*|kuu\w*|vuon\w*|vuo\w*)",
            r"\b(?:maanantai|tiistai|keskiviikko|torstai|perjantai|lauantai|sunnuntai)\w*",
            r"\b(?:vk|pv|vrk|kk)\s+sitten\b",
        ]
    ),
    re.IGNORECASE,
)


def undeclared(text_with_declared_masked):
    """Date or time references left after masking; [] means none."""
    return [m.group(0) for m in UNDECLARED_RE.finditer(text_with_declared_masked)]
