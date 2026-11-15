"""Vague-time gate: find vague or approximate Finnish time expressions in a note.

POST HOC: designed after the stress results were seen (the Gemma 3 1B reader invented precise dates for every vague
phrase of the stress set). The lexicon below was written from general Finnish, listed explicitly, before this module
read any stress note text. Only the two example phrases of the task brief ('pari viikkoa sitten', 'viime kuussa') were
known from the stress set. SYNTHETIC notes only; research artefact, not a medical device.

What the gate does: a note in which find_vague() finds at least one span goes to 'needs editing' instead of being
pre-filled for one-click confirmation. It never changes an extracted event and never confirms anything. A person
confirms every extracted event either way.

What counts as vague: a time expression whose day cannot be read off the text (a week, a season, a holiday, a part of a
month, 'a couple of weeks ago'), or a time quantity that is explicitly approximate ('noin kaksi viikkoa', 'reilu
viikko', '2-3 viikkoa'), or a statement that the date is not known. Exact relative phrasings ('3 viikkoa sitten',
'kolme päivää sitten', 'toissapäivänä', 'eilen') and month strings ('maaliskuussa 2025') are not vague.

Standard library only. Usage:

    from rule import find_vague, is_vague
    find_vague("Oireet alkoivat pari viikkoa sitten.")  # -> [{'category': 'vague_quantity', 'phrase': 'pari viikkoa', ...}]
"""

from __future__ import annotations

import re

RULE_VERSION = "fi-vague-time-v1"

# ---- word lists (explicit) --------------------------------------------------------------------------------------

# Time units in the case forms clinical free text uses; abbreviations included.
UNITS = (
    "päivä", "päivää", "päivän", "päiviä", "päivien", "pv", "pvä", "pvää", "pvn",
    "vrk", "vuorokausi", "vuorokautta", "vuorokauden", "vuorokausia",
    "viikko", "viikkoa", "viikon", "viikkoja", "viikkojen", "vk", "vko", "vkoa", "vkon",
    "kuukausi", "kuukautta", "kuukauden", "kuukausia", "kuukausien", "kk", "kk:n", "kuu", "kuuta", "kuita",
    "vuosi", "vuotta", "vuoden", "vuosia", "vuosien",
)
PLURAL_UNITS = ("päiviä", "viikkoja", "kuukausia", "kuita", "vuosia", "vuorokausia")

# Cardinal number words 1-12 (nominative, genitive, partitive).
NUMBER_WORDS = (
    "yksi", "yhden", "yhtä", "kaksi", "kahden", "kahta", "kolme", "kolmen", "kolmea", "neljä", "neljän", "neljää",
    "viisi", "viiden", "viittä", "kuusi", "kuuden", "kuutta", "seitsemän", "seitsemää", "kahdeksan", "kahdeksaa",
    "yhdeksän", "yhdeksää", "kymmenen", "kymmentä", "yksitoista", "yhdentoista", "yhtätoista", "kaksitoista",
    "kahdentoista", "kahtatoista",
)
HALVES = ("puoli", "puolen", "puolta", "puolitoista", "puolentoista")

# Quantities that are vague in themselves: 'a couple', 'a few', 'several', 'many'.
VAGUE_QUANTITIES = (
    "pari", "parin", "paria", "muutama", "muutaman", "muutamaa", "muutamia", "muutamien", "jokunen", "jonkun",
    "joitakin", "joitain", "jonkin", "useita", "useamman", "useampi", "useampia", "usean", "monta", "monia", "monen",
    "lukuisia", "kymmeniä", "kymmenien",
)

# Words that make the following time quantity approximate.
APPROX_WORDS = (
    "noin", "suunnilleen", "suurin piirtein", "suurinpiirtein", "arviolta", "arvion mukaan", "likimain", "likimäärin",
    "lähes", "melkein", "vajaa", "vajaat", "vajaan", "vajaata", "reilu", "reilut", "reilun", "reilua", "runsas",
    "runsaat", "runsaan", "runsasta", "yli", "alle", "ainakin", "vähintään", "korkeintaan", "enintään", "kenties",
    "ehkä", "mahdollisesti", "luultavasti", "todennäköisesti", "ilmeisesti", "parisen", "kolmisen", "nelisen",
    "viitisen", "kuutisen", "seitsemisen", "kahdeksisen", "yhdeksisen", "kymmenisen", "puolisen", "kymmenkunta",
    "kymmenkunnan",
)
APPROX_SYMBOLS = ("~", "n.", "ca.", "ca", "c.")

MONTH_STEMS = ("tammi", "helmi", "maalis", "huhti", "touko", "kesä", "heinä", "elo", "syys", "loka", "marras", "joulu")

# Fixed phrases, by category. Each entry is a regular expression over lower-cased text with single spaces.
PHRASES = {
    # indefinite or recent past, without a quantity
    "indefinite_past": (
        "hiljattain", "äskettäin", "vastikään", "taannoin", "aikoinaan", "jokin aika sitten", "jonkin aikaa sitten",
        "jokunen aika sitten", "vähän aikaa sitten", "jonkin aikaa", "hetki sitten", "tovi sitten", "kauan sitten",
        "pitkä aika sitten", "aikoja sitten", "viime aikoina", "viime aikojen", "lähiaikoina", "lähipäivinä",
        "lähiviikkoina", "lähikuukausina", "jo pitkään", "pidemmän aikaa", "pitkän aikaa", "pidempään", "jo kauan",
        "jo vuosia", "jo viikkoja", "jo kuukausia", "jo päiviä", "jossain vaiheessa", "jossakin vaiheessa",
        "jonain päivänä", "jonakin päivänä", "eräänä päivänä", "yhtenä päivänä",
        r"(?:viime|viimeisinä|viimeisten|viimeisien|kuluneina|kuluneiden|edellisinä|edellisten)"
        r" (?:päivinä|päivien|viikkoina|viikkojen|kuukausina|kuukausien|vuosina|vuosien)",
        r"joskus (?:viime|edellisen|edellisenä|toissa|tämän|kuluvan|ensi|alku\w*|loppu\w*|keväällä|kesällä|syksyllä"
        r"|talvella|\w+kuussa|\w+kuun)",
    ),
    # a week, month or year relative to the note, without a day
    "relative_period": (
        r"(?:viime|edellisellä|toissa|tällä|ensi|kuluvalla|samalla) viikolla",
        r"toissaviikolla",
        r"(?:viime|edellisen|toissa|tämän|ensi|kuluvan|saman) viikon (?:aikana|alussa|lopussa|lopulla|puolivälissä"
        r"|alkupuolella|loppupuolella|puolella)",
        r"(?:viime )?viikonloppuna", r"(?:viime )?viikonlopun aikana",
        r"(?:viime|edellisessä|toissa|tässä|ensi|kuluvassa|samassa) kuussa",
        r"(?:viime|edellisen|toissa|tämän|ensi|kuluvan|saman) kuun (?:aikana|alussa|lopussa|lopulla|puolivälissä"
        r"|alkupuolella|loppupuolella|vaihteessa|puolella)",
        r"(?:viime|edellisenä|toissa|tänä|ensi|kuluvana|samana) vuonna",
        r"(?:viime|edellisen|toissa|tämän|ensi|kuluvan|saman) vuoden (?:aikana|alussa|lopussa|lopulla|puolivälissä"
        r"|alkupuolella|loppupuolella|puolella|keväällä|kesällä|syksyllä|talvella)",
    ),
    # part of a month, week or year
    "part_of_period": (
        "alkuvuodesta", "alkuvuonna", "loppuvuodesta", "loppuvuonna", "keskivuodesta",
        r"vuoden (?:alussa|lopussa|lopulla|alkupuolella|loppupuolella|puolivälissä|vaihteessa|vaihteen)",
        "vuodenvaihteessa", "vuodenvaihteen", "alkukuusta", "loppukuusta",
        r"kuun (?:alussa|lopussa|lopulla|puolivälissä|alkupuolella|loppupuolella|vaihteessa|vaihteen)",
        "kuunvaihteessa", "kuunvaihteen", "alkuviikosta", "loppuviikosta",
        r"viikon (?:alussa|lopussa|lopulla|puolivälissä|alkupuolella|loppupuolella)", "viikonvaihteessa",
        r"(?:" + "|".join(MONTH_STEMS) + r")kuun (?:alussa|lopussa|lopulla|puolivälissä|alkupuolella|loppupuolella"
        r"|vaihteessa|tienoilla|paikkeilla|korvilla)",
        r"(?:alku|loppu)puol(?:ella|elle|iskolla|iskossa)",
    ),
    # seasons
    "season": (
        r"(?:alku|loppu|keski|myöhä|varhais)?(?:keväällä|kesällä|syksyllä|talvella|keväänä|kesänä|syksynä|talvena"
        r"|keväästä|kesästä|syksystä|talvesta)",
        r"(?:kevät|syys)talve(?:lla|sta)",
        r"(?:kevään|kesän|syksyn|talven) (?:aikana|alussa|lopussa|lopulla|mittaan|kuluessa|puolivälissä"
        r"|alkupuolella|loppupuolella|korvilla|tienoilla)",
    ),
    # holidays and holiday seasons
    "holiday": (
        r"(?:kesä|hiihto|syys|joulu|talvi|kevät)?loma(?:lla|n aikana|n jälkeen|n alussa|n lopulla)",
        r"ennen (?:lomaa|joulua|pääsiäistä|juhannusta|vappua|pyhiä)",
        r"(?:joulun|pääsiäisen|juhannuksen|vapun|pyhien|uudenvuoden|loppiaisen) (?:alla|aikaan|aikana|tienoilla"
        r"|tienoolla|jälkeen|korvilla|paikkeilla|pyhinä|välipäivinä)",
        "jouluna", "pääsiäisenä", "juhannuksena", "vappuna", "uutenavuotena", "loppiaisena", "välipäivinä",
    ),
    # 'around' words after a time word
    "around": (
        "tienoilla", "tienoolla", "tienoille", "tienoissa", "paikkeilla", "paikkeille", "paikkeissa", "korvilla",
        "korville", "hujakoilla", "hujakoille", "tietämillä", "tietämissä",
        r"(?:samoihin|niihin|noihin|näihin) aikoihin", "samoin tienoin",
    ),
    # the date itself is said to be unknown or recalled
    "date_unknown": (
        r"(?:ei|en|eikä) (?:[\w,]+ ){0,2}(?:muista|muistanut|muistaa|tiedä|tiennyt|osaa sanoa|osannut sanoa"
        r"|osaa tarkentaa|osannut tarkentaa)[\s,]+(?:[\w,]+ ){0,3}(?:tarkka\w*|tarkasti|tarkemmin|milloin"
        r"|ajankoh\w*|päivä\w*|päivämäär\w*)",
        r"tarkk\w* (?:päivä\w*|ajankoh\w*|aika\w*) (?:[\w,]+ ){0,2}(?:ei|epäselv\w*|tuntemat\w*|avoi\w*|epävarm\w*)",
        r"(?:päivämäärä|päivämäärästä|ajankohta|ajankohdasta|alkamisajankohta|alkamisajankohdasta) (?:[\w,]+ ){0,2}"
        r"(?:epäselv\w*|epävarm\w*|tuntemat\w*|ei tiedossa|ei ole tiedossa)",
        r"(?:epäselvä|epävarma|tuntematon) (?:ajankohta|päivämäärä|päivä)",
        "muistaakseen", "muistelee", "muistelisi",
    ),
}

# ---- regular expressions ----------------------------------------------------------------------------------------


def _alts(words):
    """Bare alternation of literal words, longest first; a space in a word matches any run of white space."""
    return "|".join(re.escape(w).replace(r"\ ", r"\s+") for w in sorted(words, key=len, reverse=True))


def _alt(words):
    return "(?:" + _alts(words) + ")"


_B, _E = r"(?<!\w)", r"(?!\w)"
UNIT = _alt(UNITS)
NUMBER = r"(?:\d+(?:[.,]\d+)?|" + _alts(NUMBER_WORDS) + ")"
QUANTITY = r"(?:" + NUMBER + "|" + _alts(HALVES) + r"|pari|parin|paria)"
QUANTITIES = r"(?:" + QUANTITY + r"(?:\s*-\s*" + QUANTITY + r")?\s+){0,2}"
SYMBOL = r"(?:~|(?<!\w)(?:" + "|".join(re.escape(s) for s in APPROX_SYMBOLS) + "))"
_NOT_FREQUENCY = r"(?!\s+(?:välein|välin|välillä))"  # 'parin päivän välein' is a frequency, not a date

PATTERNS = [
    # 'noin kaksi viikkoa', 'reilu viikko', 'yli kolme kuukautta', 'kolmisen viikkoa', 'ehkä viikko sitten'
    ("approximate_quantity", re.compile(_B + _alt(APPROX_WORDS) + r"\s+" + QUANTITIES + UNIT + _E + _NOT_FREQUENCY)),
    # 'n. 2 vk', '~2 vk', 'ca 3 kk'
    ("approximate_quantity",
     re.compile(SYMBOL + r"\s*(?:" + QUANTITY + r"(?:\s*-\s*" + QUANTITY + r")?\s*){0,2}" + UNIT + _E + _NOT_FREQUENCY)),
    # 'pari viikkoa', 'muutama päivä', 'useita kuukausia', 'muutaman viime viikon'
    ("vague_quantity",
     re.compile(_B + _alt(VAGUE_QUANTITIES) + r"\s+(?:(?:viime|viimeisen|viimeisten|edellisen|edellisten|kuluneen"
                r"|kuluneiden|" + NUMBER + r")\s+)?" + UNIT + _E + _NOT_FREQUENCY)),
    # 'puoli vuotta', 'puolitoista viikkoa'
    ("vague_quantity", re.compile(_B + _alt(HALVES) + r"\s+" + UNIT + _E + _NOT_FREQUENCY)),
    # ranges: '2-3 viikkoa', 'kaksi-kolme viikkoa', 'kaksi tai kolme viikkoa', 'kaksi kolme viikkoa'
    ("range", re.compile(_B + QUANTITY + r"\s*(?:-|/|\.\.|…)\s*" + QUANTITY + r"\s*" + UNIT + _E)),
    ("range", re.compile(_B + QUANTITY + r"\s+tai\s+" + QUANTITY + r"\s+" + UNIT + _E)),
    ("range", re.compile(_B + r"(?:" + _alts(NUMBER_WORDS) + r"|pari|parin)\s+" + _alt(NUMBER_WORDS) + r"\s+" + UNIT + _E)),
    # 'viikko pari', 'viikon-parin', 'viikko tai kaksi', 'päivä tai pari'
    ("range", re.compile(_B + UNIT + r"(?:\s*-\s*(?:pari|parin|kaksi|kahden)|\s+(?:pari|parin)"
                         r"|\s+tai\s+(?:pari|parin|kaksi|kahden|toinen|toisen|kolme|kolmen))" + _E)),
    # plural unit without a number: 'viikkoja sitten', 'kuukausia aiemmin'
    ("vague_quantity",
     re.compile(_B + _alt(PLURAL_UNITS) + r"\s+(?:sitten|aiemmin|aikaisemmin|takaperin|ennen)" + _E)),
]
for _category, _phrases in PHRASES.items():
    for _p in _phrases:
        PATTERNS.append((_category, re.compile(_B + _p.replace(" ", r"\s+") + _E)))

# A relative year next to a month string has month precision ('maaliskuussa viime vuonna'): not vague.
_MONTH_WORD = re.compile(r"(?<!\w)(?:" + "|".join(MONTH_STEMS) + r")kuussa(?!\w)")
_RELATIVE_YEAR = re.compile(r"(?:viime|edellisenä|toissa|tänä|ensi|kuluvana|samana)\s+vuonna")

_DASHES = str.maketrans({"–": "-", "—": "-", "−": "-", "‐": "-", "‑": "-", " ": " ",
                         " ": " "})


def normalise(text: str) -> str:
    """Lower case, dashes to '-', non-breaking spaces to ' '. Same length as the input, so spans map back."""
    return (text or "").translate(_DASHES).lower()


def find_vague(text: str) -> list[dict]:
    """All vague or approximate time expressions in `text`: [{category, phrase, start, end}], in text order,
    overlapping matches merged (the first category of the longest match is kept)."""
    low = normalise(text)
    hits = []
    for category, rx in PATTERNS:
        for m in rx.finditer(low):
            if category == "relative_period" and _RELATIVE_YEAR.fullmatch(m.group(0)):
                window = low[max(0, m.start() - 30):m.end() + 30]
                if _MONTH_WORD.search(window):
                    continue
            hits.append((m.start(), m.end(), category))
    hits.sort(key=lambda h: (h[0], -(h[1] - h[0])))
    merged = []
    for start, end, category in hits:
        if merged and start < merged[-1][1]:
            if end > merged[-1][1]:
                merged[-1] = (merged[-1][0], end, merged[-1][2])
            continue
        merged.append((start, end, category))
    return [{"category": c, "phrase": text[s:e], "start": s, "end": e} for s, e, c in merged]


def is_vague(text: str) -> bool:
    """True when the note should go to 'needs editing' because a time expression in it is vague or approximate."""
    return bool(find_vague(text))
