import datetime as dt
import hashlib
import json
import random
import re

MONTHS = [
    "tammi",
    "helmi",
    "maalis",
    "huhti",
    "touko",
    "kesä",
    "heinä",
    "elo",
    "syys",
    "loka",
    "marras",
    "joulu",
]
TYPES = [
    "SYMPTOM_ONSET_REPORTED",
    "FIRST_CONTACT",
    "PHYSICIAN_ASSESSMENT",
    "REFERRAL_SENT",
    "REFERRAL_RECEIVED",
    "SPECIALIST_VISIT",
    "DIAGNOSIS",
    "MDT_DECISION",
    "TREATMENT_START",
]
FIN = [
    "oireiden alku",
    "ensimmäinen yhteydenotto terveydenhuoltoon",
    "lääkärin arvio",
    "lähetteen lähettäminen",
    "lähetteen vastaanottaminen",
    "erikoislääkärikäynti",
    "syöpädiagnoosin vahvistaminen",
    "moniammatillinen hoitopäätös",
    "syöpähoidon aloitus",
]
ROUTES = {
    "PUBLIC_PRIMARY": "julkinen perusterveydenhuolto",
    "OCCUPATIONAL": "työterveyshuolto",
    "PRIVATE": "yksityinen terveydenhuolto",
    "EMERGENCY": "päivystys",
    "SCREENING": "seulonta",
}
FORMS = ["numeric", "long", "no_year", "days", "weeks", "month"]


def render(date, note, form):
    if form == "numeric":
        return f"{date.day}.{date.month}.{date.year}"
    if form == "long":
        return f"{date.day}. {MONTHS[date.month - 1]}kuuta {date.year}"
    if form == "no_year":
        if date.year != note.year:
            raise ValueError("year mismatch")
        return f"{date.day}.{date.month}."
    if form == "days":
        return f"{(note - date).days} päivää sitten"
    if form == "weeks":
        if (note - date).days % 7:
            raise ValueError("not whole weeks")
        return f"{(note - date).days // 7} viikkoa sitten"
    if form == "month":
        return f"{MONTHS[date.month - 1]}kuussa {date.year}"
    raise ValueError(form)


def parse_date(s, note):
    for i, m in enumerate(MONTHS, 1):
        a = re.fullmatch(r"(\d+)\. " + m + r"kuuta (\d{4})", s)
        if a:
            return dt.date(int(a[2]), i, int(a[1])), "DAY"
        a = re.fullmatch(m + r"kuussa (\d{4})", s)
        if a:
            return dt.date(int(a[1]), i, 1), "MONTH"
    a = re.fullmatch(r"(\d+) (päivää|viikkoa) sitten", s)
    if a:
        return note - dt.timedelta(
            days=int(a[1]) * (7 if a[2] == "viikkoa" else 1)
        ), "DAY"
    a = re.fullmatch(r"(\d+)\.(\d+)\.(\d{4})?", s)
    if a:
        return dt.date(int(a[3]) if a[3] else note.year, int(a[2]), int(a[1])), "DAY"
    raise ValueError(s)


def sample(i, seed=20261114):
    r = random.Random(seed + i)
    note = dt.date(2024, 1, 1) + dt.timedelta(days=r.randrange(1096))
    inds = sorted(r.sample(range(9), r.randint(1, 4)))
    offsets = sorted(
        [v * 35 + r.randrange(4) for v in r.sample(range(1, 11), len(inds))],
        reverse=True,
    )
    facts = []
    for ix, offset in zip(inds, offsets):
        date = note - dt.timedelta(days=offset)
        form = r.choice(FORMS)
        if form == "weeks":
            date = note - dt.timedelta(days=max(7, round(offset / 7) * 7))
        if form == "no_year" and date.year != note.year:
            form = "numeric"
        if form == "month":
            date = date.replace(day=1)
        facts.append(
            dict(
                type=TYPES[ix],
                date=date.isoformat(),
                precision="MONTH" if form == "month" else "DAY",
                expression=render(date, note, form),
                form=form,
                meaning=FIN[ix],
            )
        )
    distractors = []
    for kind in r.sample(["birth", "vaccination", "future"], r.randint(0, 2)):
        date = (
            dt.date(r.randint(1940, 1995), r.randint(1, 12), r.randint(1, 28))
            if kind == "birth"
            else note + dt.timedelta(days=r.randint(10, 100))
            if kind == "future"
            else note - dt.timedelta(days=r.randint(450, 900))
        )
        distractors.append(
            dict(
                kind=kind,
                expression=render(date, note, "numeric"),
                date=date.isoformat(),
                meaning={
                    "birth": "syntymäaika",
                    "vaccination": "aiempi syöpään liittymätön rokotuskäynti",
                    "future": "tuleva, vielä toteutumaton kontrolliaika",
                }[kind],
            )
        )
    events = sorted(
        [{k: f[k] for k in ["type", "date", "precision"]} for f in facts],
        key=lambda e: (e["date"], e["type"]),
    )
    route = r.choice(list(ROUTES))
    target = dict(entry_route=route, events=events)
    ident = hashlib.sha256(json.dumps(target, sort_keys=True).encode()).hexdigest()
    bucket = int(ident[:8], 16) % 11
    split = "test" if bucket < 2 else "val" if bucket == 2 else "train"
    return dict(
        id=ident,
        split=split,
        note_date=note.isoformat(),
        style=r.choice(
            [
                "lähetekirje",
                "käyntimerkintä",
                "hoitajan puhelinmerkintä",
                "loppulausunnon ote",
            ]
        ),
        entry_route=route,
        events=events,
        facts=facts,
        distractors=distractors,
        date_forms=[f["form"] for f in facts],
        target_json=json.dumps(target, ensure_ascii=False, separators=(",", ":")),
        synthetic=True,
    )
