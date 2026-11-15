"""Build the SAMA pathway-scribe v2 writer slices. Ground truth only: no model call, no network.

Run from the project root:
    PYTHONDONTWRITEBYTECODE=1 scribe/.venv/bin/python data/scribe/v2/slices/_build_slices.py

Imports (never edits) scribe/sample.py, scribe/generate.py, scribe/prompts.py and scribe/verify.py.
generate.py builds its teacher prompt inline inside Pipeline.one, which cannot be called without a
teacher request and a cache write, so its fact-line logic (one "meaning: expression" line per event
and per distractor, plus the explicit entry route) is mirrored in writer_lines() below.

Everything written here is SYNTHETIC ground truth. Nothing is for clinical use.
"""

import collections
import datetime as dt
import hashlib
import json
import pathlib
import random
import socket
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "scribe"))

import generate  # noqa: E402  imported for its ROUTES and sample bindings; not edited, not executed
import sample as S  # noqa: E402
from prompts import canonicalise  # noqa: E402

assert generate.sample is S.sample and generate.ROUTES is S.ROUTES

SEED_V1 = 20261114  # scribe/sample.py default; v1 used SEED_V1 + cache index
SEED_PILOT = 77020261  # runs/train.jsonl step haiku_sample_tuples
SEED_V2 = SEED_V1 + 1_000_000
SEEDS = {
    "standard": SEED_V2,  # sample(i, seed=SEED_V2) -> random.Random(SEED_V2 + i)
    "careful": SEED_V2 + 100_000,  # random.Random(SEEDS["careful"] + j)
    "no_event": SEED_V2 + 200_000,  # random.Random(SEEDS["no_event"] + j)
    "slicing": SEED_V2 + 300_000,  # deal into slices, shuffle inside each slice
}
N_STANDARD, N_NO_EVENT, N_CAREFUL, N_SLICES, PER_SLICE = 900, 150, 150, 12, 100
DAY_FORMS = ["numeric", "long", "no_year", "days", "weeks"]
STYLES = ["lähetekirje", "käyntimerkintä", "hoitajan puhelinmerkintä", "loppulausunnon ote"]

# Who is on the referring side, by entry route: who may answer a first contact, and the physician.
# One answering party is fixed per specification (by its id), so that a writer is not handed "A tai B".
ACTOR = {
    "PUBLIC_PRIMARY": (
        ["terveyskeskuksen hoitaja", "terveyskeskuksen ajanvaraus", "terveysaseman sairaanhoitaja"],
        "terveyskeskuslääkäri",
    ),
    "OCCUPATIONAL": (["työterveyshoitaja", "työterveyshuollon ajanvaraus"], "työterveyslääkäri"),
    "PRIVATE": (
        ["yksityisen lääkäriaseman hoitaja", "yksityisen lääkäriaseman ajanvaraus"],
        "yksityisen lääkäriaseman yleislääkäri",
    ),
    "EMERGENCY": (["päivystyksen hoitaja", "päivystysapu"], "päivystävä lääkäri"),
    "SCREENING": (["seulontayksikön hoitaja", "seulontayksikön ajanvaraus"], "seulontayksikön lääkäri"),
}


def actors(route, ident):
    options, physician = ACTOR[route]
    return options[int(ident[-4:], 16) % len(options)], physician


# Explanations are in English on purpose: in a twelve-note pilot the writer pasted the earlier Finnish
# explanations into six notes word for word. An English explanation cannot be pasted into a Finnish note.
GLOSS = {
    "SYMPTOM_ONSET_REPORTED": "the patient's own report of when the symptoms behind the cancer suspicion began",
    "FIRST_CONTACT": "the patient got in touch for the first time; answered by: {contact}; no physician examined the patient then",
    "PHYSICIAN_ASSESSMENT": "examined and assessed by: {physician}; not a nurse, not the treating specialist in specialised care",
    "REFERRAL_SENT": "the referring physician wrote the referral and SENT it to specialised care; this is not its arrival",
    "REFERRAL_RECEIVED": "the referral ARRIVED at the specialised-care unit and was registered there; this is not its sending and not the patient getting a referral",
    "SPECIALIST_VISIT": "the patient attended the appointment of the treating specialist in specialised care",
    "DIAGNOSIS": "the cancer diagnosis was confirmed",
    "MDT_DECISION": "the multidisciplinary meeting decided on treatment",
    "TREATMENT_START": "the first cancer treatment started",
}


def gloss(event_type, route, ident):
    contact, physician = actors(route, ident)
    return GLOSS[event_type].format(contact=contact, physician=physician)


def writer_lines(ident, route, facts, distractors, context=()):
    """generate.py logic: the entry route, then one 'meaning: expression' line per dated fact."""
    lines = [f"syöpäpolun tuloreitti: {S.ROUTES[route]}"]
    lines += [f"{f['meaning']} [{gloss(f['type'], route, ident)}]: {f['expression']}" for f in facts]
    for d in distractors:
        note = "has not happened yet" if d["kind"].startswith("future") else "not a pathway event"
        lines.append(f"{d['meaning']} [{note}]: {d['expression']}")
    lines += [f"ilman päivämäärää: {c}" for c in context]
    return lines


def sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


def split_hint(ident):
    bucket = int(ident[:8], 16) % 11  # same rule as scribe/sample.py
    return "test" if bucket < 2 else "val" if bucket == 2 else "train"


def month_end(d):
    return (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)


def sequence_problem(facts, distractors, note):
    """None if the dated facts are exact, strictly chronological and separately detectable."""
    expressions = [x["expression"] for x in facts + distractors]
    if len(set(expressions)) != len(expressions):
        return "duplicate_expression"
    previous = None
    for f in facts:
        d, p = S.parse_date(f["expression"], note)
        if (d.isoformat(), p) != (f["date"], f["precision"]):
            return "parse_mismatch"
        if not 0 <= (note - d).days <= 400:
            return "outside_400_days"
        if previous is not None:
            if not previous[0] < d:
                return "chronology_not_strict"
            if previous[1] == "MONTH" and not month_end(previous[0]) < d:
                return "month_overlaps_next_event"
        previous = (d, p)
    for x in distractors:
        if S.parse_date(x["expression"], note)[0].isoformat() != x["date"]:
            return "distractor_parse_mismatch"
    return None


def make_spec(kind, focus, ident, style, note, route, facts, distractors, distractor_forms, facts_fi, wording, sampler):
    events = sorted(
        [{k: f[k] for k in ["type", "date", "precision"]} for f in facts],
        key=lambda e: (e["date"], e["type"]),
    )
    truth = dict(entry_route=route, events=events)
    assert canonicalise(truth) == truth
    return dict(
        id=ident,
        kind=kind,
        focus=focus,
        style=style,
        note_date=note.isoformat(),
        facts_fi=facts_fi,
        date_strings=[x["expression"] for x in facts + distractors],
        wording=wording,
        facts=facts,
        distractors=distractors,
        ground_truth=truth,
        date_forms=[f["form"] for f in facts],
        distractor_forms=distractor_forms,
        split_hint=split_hint(ident),
        sampler=sampler,
        synthetic=True,
    )


# ---------------------------------------------------------------- standard: scribe/sample.py as is


def build_standard(taken):
    out, skipped, i = [], collections.Counter(), 0
    while len(out) < N_STANDARD:
        row = S.sample(i, seed=SEEDS["standard"])
        i += 1
        note = dt.date.fromisoformat(row["note_date"])
        truth = dict(entry_route=row["entry_route"], events=row["events"])
        assert row["id"] == sha(truth)
        if row["id"] in taken:
            skipped["ground_truth_already_used"] += 1
            continue
        problem = sequence_problem(row["facts"], row["distractors"], note)
        if problem:
            skipped[problem] += 1
            continue
        taken.add(row["id"])
        out.append(
            make_spec(
                "standard",
                "sampler_v1",
                row["id"],
                row["style"],
                note,
                row["entry_route"],
                row["facts"],
                row["distractors"],
                ["numeric"] * len(row["distractors"]),  # sample.py renders every distractor numerically
                writer_lines(row["id"], row["entry_route"], row["facts"], row["distractors"]),
                [],
                dict(source="sample.py", seed=SEEDS["standard"], index=i - 1),
            )
        )
    return out, dict(indices_drawn=i, skipped=dict(skipped))


# ---------------------------------------------------------------- shared date helpers


def dated(r, date, note, forms):
    """Pick a date form like sample.py does and return (date, form, precision, expression)."""
    form = r.choice(forms)
    if form == "weeks":
        weeks = round((note - date).days / 7)
        if weeks < 2:  # "1 viikkoa sitten" is not Finnish
            form = "days"
        else:
            date = note - dt.timedelta(days=weeks * 7)
    if form == "days" and (note - date).days < 2:  # "1 päivää sitten" is not Finnish
        form = "numeric"
    if form == "no_year" and date.year != note.year:
        form = "numeric"
    if form == "month":
        date = date.replace(day=1)
    return date, form, "MONTH" if form == "month" else "DAY", S.render(date, note, form)


def event_fact(r, event_type, date, note, forms):
    date, form, precision, expression = dated(r, date, note, forms)
    return dict(
        type=event_type,
        date=date.isoformat(),
        precision=precision,
        expression=expression,
        form=form,
        meaning=S.FIN[S.TYPES.index(event_type)],
    )


def other_date(r, kind, meaning, date, note, forms):
    date, form, _, expression = dated(r, date, note, forms)
    return dict(kind=kind, expression=expression, date=date.isoformat(), meaning=meaning), form


BIRTH_YEARS = {"OCCUPATIONAL": (1960, 1995), "SCREENING": (1952, 1976)}  # working age; screening age


def birth_date(r, years=(1940, 1995)):  # default range is the one scribe/sample.py uses
    return dt.date(r.randint(*years), r.randint(1, 12), r.randint(1, 28))


def future_forms(date, note):
    return ["numeric", "long"] + (["no_year"] if date.year == note.year else [])


# ---------------------------------------------------------------- careful wording

NOT_YET_SPECIALIST = "the patient has not yet been to a specialist's appointment"
BARE_VISIT = "Never a bare 'käynti', 'vastaanotto' or 'kontakti': for every dated contact the reader must be able to tell who received the patient."
NO_PATIENT_GOT = "Never 'potilas sai lähetteen' or 'lähete tehty', and never a referral without a verb that shows sending or arrival."
W_CONTACT = "First contact: the patient got in touch personally (a telephone call, an electronic message or a walk-in to a nurse) and was answered by: {contact}. No physician examined the patient on that date."
W_PHYSICIAN = "Physician's assessment: the patient was examined and assessed by: {physician}. It is not a nurse's contact and not the appointment of the treating specialist in specialised care."
W_SPECIALIST = "Specialist appointment: the patient attended the appointment of the treating specialist in specialised care. Name the specialty or the clinic (onkologi, kirurgi, urologi, hematologi, keuhkolääkäri, gynekologi, ...)."
FUTURE_SPECIALIST = ("future_specialist", "tuleva, vielä toteutumaton erikoislääkärin vastaanottoaika")
EARLY = ["SYMPTOM_ONSET_REPORTED"]
LATE = ["DIAGNOSIS", "MDT_DECISION", "TREATMENT_START"]
REFERRALS = ["REFERRAL_SENT", "REFERRAL_RECEIVED"]

# name, count, focus event types, optional extra event types, styles, wording, future distractor, context
FOCI = [
    dict(
        name="referral_sent_and_received",
        count=30,
        types=REFERRALS,
        extras=EARLY + ["FIRST_CONTACT", "PHYSICIAN_ASSESSMENT", "SPECIALIST_VISIT"] + LATE,
        styles=["loppulausunnon ote", "käyntimerkintä", "hoitajan puhelinmerkintä"],
        wording=[
            "Perspective: a specialised-care unit, or a summary that knows both dates of the referral.",
            "Two separate acts on two dates: the referring physician SENT the referral, and the referral ARRIVED in specialised care and was registered there. The verb at each date string must show the direction (sending: 'lähetti', 'lähti', 'lähetetty', 'toimitettu'; arrival: 'saapui', 'tuli', 'vastaanotettu', 'kirjattu saapuneeksi').",
            NO_PATIENT_GOT,
        ],
    ),
    dict(
        name="referral_sent_only",
        count=22,
        types=["REFERRAL_SENT"],
        extras=EARLY + ["FIRST_CONTACT", "PHYSICIAN_ASSESSMENT"],
        styles=["lähetekirje", "käyntimerkintä", "hoitajan puhelinmerkintä"],
        wording=[
            "Perspective: the referring unit (the physician or a nurse of the entry service).",
            "Say that the referring physician wrote the referral and sent it to specialised care on the given date ('lähetin lähetteen', 'lähete lähti', 'lähete lähetetty', 'lähete toimitettu', ...).",
            "Do not say or imply that the referral has arrived, been received, processed or accepted in specialised care. " + NO_PATIENT_GOT,
        ],
        future=FUTURE_SPECIALIST,
        context=("specialised care has not yet sent any word about how the referral is being handled", 0.6),
    ),
    dict(
        name="referral_received_only",
        count=23,
        types=["REFERRAL_RECEIVED"],
        extras=EARLY + ["SPECIALIST_VISIT"] + LATE,
        styles=["käyntimerkintä", "loppulausunnon ote", "hoitajan puhelinmerkintä"],
        wording=[
            "Perspective: the specialised-care unit that received the referral.",
            "Say that the referral arrived at the unit or was registered as received there on the given date ('lähete saapunut', 'lähete tullut', 'lähete vastaanotettu', 'lähete kirjattu saapuneeksi', ...).",
            "Do not say when the referral was written or sent. " + NO_PATIENT_GOT,
        ],
    ),
    dict(
        name="first_contact_and_physician_assessment",
        count=15,
        types=["FIRST_CONTACT", "PHYSICIAN_ASSESSMENT"],
        extras=EARLY + ["REFERRAL_SENT"],
        styles=STYLES,
        wording=[
            "The first contact and the physician's assessment are two separate events on two dates.",
            W_CONTACT,
            W_PHYSICIAN,
            BARE_VISIT,
        ],
        future=FUTURE_SPECIALIST,
        context=(NOT_YET_SPECIALIST, 0.5),
    ),
    dict(
        name="physician_assessment_and_specialist_visit",
        count=15,
        types=["PHYSICIAN_ASSESSMENT", "SPECIALIST_VISIT"],
        extras=EARLY + REFERRALS + LATE,
        styles=STYLES,
        wording=[
            "The physician's assessment and the specialist appointment are two separate events on two dates.",
            W_PHYSICIAN,
            W_SPECIALIST,
            BARE_VISIT,
        ],
    ),
    dict(
        name="first_contact_physician_assessment_and_specialist_visit",
        count=15,
        types=["FIRST_CONTACT", "PHYSICIAN_ASSESSMENT", "SPECIALIST_VISIT"],
        extras=EARLY + REFERRALS + LATE,
        styles=STYLES,
        wording=[
            "The first contact, the physician's assessment and the specialist appointment are three separate events on three dates.",
            W_CONTACT,
            W_PHYSICIAN,
            W_SPECIALIST,
            BARE_VISIT,
        ],
    ),
    dict(
        name="single_first_contact",
        count=10,
        types=["FIRST_CONTACT"],
        extras=EARLY,
        styles=["hoitajan puhelinmerkintä", "käyntimerkintä"],
        wording=[
            "The note has exactly one dated contact, and it is the first contact.",
            W_CONTACT,
            BARE_VISIT,
        ],
        future=("future_physician", "tuleva, vielä toteutumaton lääkärin vastaanottoaika"),
        context=("the patient has not yet been seen by a physician", 1.0),
        last_offset=(3, 21),  # still waiting for a physician: the contact is recent
    ),
    dict(
        name="single_physician_assessment",
        count=10,
        types=["PHYSICIAN_ASSESSMENT"],
        extras=EARLY + ["REFERRAL_SENT"],
        styles=["käyntimerkintä", "lähetekirje", "hoitajan puhelinmerkintä"],
        wording=[
            "The note has exactly one dated contact, and it is the physician's assessment.",
            W_PHYSICIAN,
            BARE_VISIT,
        ],
        future=FUTURE_SPECIALIST,
        context=(NOT_YET_SPECIALIST, 0.6),
    ),
    dict(
        name="single_specialist_visit",
        count=10,
        types=["SPECIALIST_VISIT"],
        extras=EARLY + ["REFERRAL_RECEIVED"] + LATE,
        styles=["käyntimerkintä", "loppulausunnon ote", "hoitajan puhelinmerkintä"],
        wording=[
            "The note has exactly one dated contact, and it is the specialist appointment.",
            W_SPECIALIST,
            "Do not describe it as an assessment by the physician of the entry service. " + BARE_VISIT,
        ],
    ),
]
SHORT_GAPS = {
    ("REFERRAL_SENT", "REFERRAL_RECEIVED"): (1, 14),
    ("FIRST_CONTACT", "PHYSICIAN_ASSESSMENT"): (1, 28),
    ("PHYSICIAN_ASSESSMENT", "REFERRAL_SENT"): (1, 10),
    ("REFERRAL_RECEIVED", "SPECIALIST_VISIT"): (5, 45),
}


def build_careful(taken):
    plan = [f for f in FOCI for _ in range(f["count"])]
    assert len(plan) == N_CAREFUL
    out, rejected, attempts_total = [], collections.Counter(), 0
    for j, focus in enumerate(plan):
        r = random.Random(SEEDS["careful"] + j)
        for attempt in range(1, 2001):
            attempts_total += 1
            note = dt.date(2024, 1, 1) + dt.timedelta(days=r.randrange(1096))
            route = r.choice(list(S.ROUTES))
            style = r.choice(focus["styles"])
            n_extra = r.randint(0, min(2, 4 - len(focus["types"]), len(focus["extras"])))
            types = sorted(focus["types"] + r.sample(focus["extras"], n_extra), key=S.TYPES.index)
            offsets = [r.randint(*focus.get("last_offset", (3, 120)))]  # days before the note, latest event first
            for pair in reversed(list(zip(types, types[1:]))):
                offsets.append(offsets[-1] + r.randint(*SHORT_GAPS.get(pair, (7, 75))))
            offsets.reverse()
            facts = [
                event_fact(
                    r,
                    t,
                    note - dt.timedelta(days=o),
                    note,
                    DAY_FORMS if t in focus["types"] else S.FORMS,
                )
                for t, o in zip(types, offsets)
            ]
            distractors, distractor_forms = [], []
            for kind in r.sample(["birth", "vaccination", "future"], r.randint(0, 2)):
                if kind == "birth":
                    item = other_date(r, kind, "syntymäaika", birth_date(r, BIRTH_YEARS.get(route, (1940, 1995))), note, ["numeric"])
                elif kind == "vaccination":
                    item = other_date(
                        r,
                        kind,
                        "aiempi syöpään liittymätön rokotuskäynti",
                        note - dt.timedelta(days=r.randint(450, 900)),
                        note,
                        ["numeric", "long"],
                    )
                else:
                    date = note + dt.timedelta(days=r.randint(10, 100))
                    kind, meaning = focus.get(
                        "future", ("future", "tuleva, vielä toteutumaton kontrolliaika")
                    )
                    item = other_date(r, kind, meaning, date, note, future_forms(date, note))
                distractors.append(item[0])
                distractor_forms.append(item[1])
            draw = r.random()  # always drawn so the stream does not depend on the branch
            context = []
            if "context" in focus and draw < focus["context"][1]:
                # A booked specialist appointment contradicts "no word from the hospital yet".
                if not (
                    focus["name"] == "referral_sent_only"
                    and any(d["kind"] == "future_specialist" for d in distractors)
                ):
                    context.append(focus["context"][0])
            problem = sequence_problem(facts, distractors, note)
            if not problem and min((note - dt.date.fromisoformat(f["date"])).days for f in facts) < 2:
                problem = "too_close_to_note_date"
            if problem:
                rejected[problem] += 1
                continue
            events = sorted(
                [{k: f[k] for k in ["type", "date", "precision"]} for f in facts],
                key=lambda e: (e["date"], e["type"]),
            )
            ident = sha(dict(entry_route=route, events=events))  # same id rule as scribe/sample.py
            if ident in taken:
                rejected["ground_truth_already_used"] += 1
                continue
            taken.add(ident)
            contact, physician = actors(route, ident)
            spec = make_spec(
                "careful",
                focus["name"],
                ident,
                style,
                note,
                route,
                facts,
                distractors,
                distractor_forms,
                writer_lines(ident, route, facts, distractors, context),
                [w.format(contact=contact, physician=physician) for w in focus["wording"]],
                dict(source="build_careful", seed=SEEDS["careful"], index=j, attempt=attempt),
            )
            out.append(spec)
            break
        else:
            raise RuntimeError(f"no valid careful spec for index {j}")
    return out, dict(attempts=attempts_total, rejected=dict(rejected))


# ---------------------------------------------------------------- no pathway event

P, O, PR, E, SC = "PUBLIC_PRIMARY", "OCCUPATIONAL", "PRIVATE", "EMERGENCY", "SCREENING"
VISIT = ["käyntimerkintä", "hoitajan puhelinmerkintä"]
ACUTE = ["käyntimerkintä", "loppulausunnon ote"]
AUTUMN = {10, 11, 12, 1}  # the main date of a seasonal item must fall in these months
# category -> (count, earlier-date meaning, future-date meaning, [(what the date is, routes, styles[, months])])
NO_EVENT = {
    "vaccination": (
        30,
        "edellinen, jo annettu rokoteannos",
        "tuleva, vielä toteutumaton seuraava rokoteannos",
        [
            ("kausi-influenssarokotus", [P, O, PR], VISIT, AUTUMN),
            ("jäykkäkouristus-kurkkumätärokotteen tehosteannos", [P, O, PR], VISIT),
            ("koronarokotteen tehosteannos", [P, O, PR], VISIT, AUTUMN),
            ("puutiaisaivotulehdusrokotteen annos", [P, O, PR], VISIT),
            ("A-hepatiittirokotus ulkomaanmatkaa varten", [P, O, PR], VISIT),
            ("B-hepatiittirokotesarjan annos", [P, O, PR], VISIT),
            ("pneumokokkirokotus", [P, PR], VISIT),
            ("vyöruusurokotus", [P, PR], VISIT),
            ("MPR-rokotteen tehosteannos", [P, O, PR], VISIT),
            ("jäykkäkouristusrokotteen tehosteannos haavan hoidon yhteydessä", [E], ACUTE),
        ],
    ),
    "prescription_renewal": (
        30,
        "edellinen, jo toteutunut lääkityksen seurantakäynti",
        "tuleva, vielä toteutumaton lääkityksen seurantakäynti",
        [
            ("verenpainelääkkeen reseptin uusiminen", [P, O, PR], VISIT),
            ("kilpirauhaslääkkeen reseptin uusiminen", [P, O, PR], VISIT),
            ("astman hoitolääkkeen reseptin uusiminen", [P, O, PR], VISIT),
            ("kolesterolilääkkeen reseptin uusiminen", [P, O, PR], VISIT),
            ("allergialääkkeen reseptin uusiminen", [P, O, PR], VISIT),
            ("migreenilääkkeen reseptin uusiminen", [P, O, PR], VISIT),
            ("närästyslääkkeen reseptin uusiminen", [P, O, PR], VISIT),
            ("nivelrikon kipulääkkeen reseptin uusiminen", [P, O, PR], VISIT),
        ],
    ),
    "dental_check": (
        25,
        "edellinen, jo toteutunut hammastarkastus",
        "tuleva, vielä toteutumaton hammashoidon aika",
        [
            ("suun ja hampaiden määräaikaistarkastus", [P, PR], VISIT),
            ("hammaskiven poisto suuhygienistin vastaanotolla", [P, PR], VISIT),
            ("lohjenneen paikan uusiminen hammaslääkärin vastaanotolla", [P, PR], VISIT),
            ("hampaiden röntgenkuvaus ja tarkastus, ei hoidon tarvetta", [P, PR], VISIT),
            ("lohjenneen hampaan väliaikainen paikkaus hammaslääkäripäivystyksessä", [E], ACUTE),
        ],
    ),
    "minor_or_checkup": (
        20,
        "edellinen, jo toteutunut vastaava käynti",
        "tuleva, vielä toteutumaton kontrollikäynti",
        [
            ("nilkan nyrjähdyksen tutkiminen ja tukeminen", [E, O, PR], ACUTE),
            ("sormen viiltohaavan ompelu", [E, O], ACUTE),
            ("korvatulehduksen hoito antibioottikuurilla", [E, P, PR], ACUTE),
            ("virtsatietulehduksen hoito antibioottikuurilla", [E, P, O, PR], ACUTE),
            ("ajokorttia varten tehty terveystarkastus ja lääkärinlausunto", [P, O, PR], VISIT),
            ("määräaikainen työterveystarkastus", [O], VISIT),
            ("diabeteksen vuosikontrolli", [P, O, PR], VISIT),
            ("verenpaineen seurantakäynti hoitajan vastaanotolla", [P, O, PR], VISIT),
            ("ranteen venähdyksen tutkiminen ja lastoitus", [E], ACUTE),
            ("silmän sidekalvotulehduksen hoito silmätipoilla", [E, P, PR], ACUTE),
        ],
    ),
    "non_cancer_screening": (
        15,
        "edellinen, jo toteutunut vastaava seulontatutkimus",
        "tuleva, vielä toteutumaton vastaava seulontatutkimus",
        [
            ("diabeetikon silmänpohjakuvaus seulontana, ei muutoksia", [SC], VISIT),
            ("kuulon seulontatutkimus, tulos normaali", [SC], VISIT),
            ("luuntiheysmittaus osteoporoosin seulontana, tulos normaali", [SC], VISIT),
            ("vatsa-aortan seulontaultraääni, löydös normaali", [SC], VISIT),
            ("näön seulontatutkimus, näkö normaali", [SC], VISIT),
        ],
    ),
    # Each of these resembles one pathway step (named in the comment) but is plainly not cancer care.
    "non_cancer_lookalike": (
        30,
        "edellinen, jo toteutunut käynti saman vaivan vuoksi",
        "tuleva, vielä toteutumaton kontrollikäynti",
        [
            ("fysioterapialähetteen lähettäminen alaselkäkivun vuoksi", [P, O, PR], ["lähetekirje", "käyntimerkintä"]),  # referral sent
            ("lähetteen lähettäminen silmätautien poliklinikalle harmaakaihin vuoksi", [P, O, PR], ["lähetekirje", "käyntimerkintä"]),  # referral sent
            ("käynti ortopedin vastaanotolla polven nivelrikon vuoksi", [P, O, PR], VISIT),  # specialist visit
            ("käynti ihotautilääkärin vastaanotolla atooppisen ihottuman vuoksi", [P, PR], VISIT),  # specialist visit
            ("aikuistyypin diabeteksen toteaminen verikokeiden perusteella", [P, O, PR], VISIT),  # diagnosis
            ("kilpirauhasen vajaatoiminnan toteaminen ja tyroksiinihoidon aloitus", [P, O, PR], VISIT),  # diagnosis, treatment start
            ("verenpainelääkityksen aloitus", [P, O, PR], VISIT),  # treatment start
            ("umpilisäkkeen poisto päivystysleikkauksena", [E], ACUTE),  # treatment start
            ("ranteen murtuman toteaminen röntgenkuvasta ja kipsaus", [E], ACUTE),  # diagnosis
            ("ensimmäinen yhteydenotto jännitysniskan vuoksi, hoito-ohjeet annettu", [P, O, PR], VISIT),  # first contact
            ("lääkärin arvio olkapään kiertäjäkalvosinvaivasta", [P, O, PR], VISIT),  # physician assessment
            ("uniapneaepäilyn vuoksi tehdyn unirekisteröintilähetteen saapuminen keuhkosairauksien poliklinikalle", [P, O, PR], VISIT),  # referral received
            ("tenniskyynärpään oireiden alku potilaan kertomana", [P, O, PR], VISIT),  # symptom onset
        ],
    ),
}
W_NO_EVENT = [
    "This note has nothing to do with cancer: no cancer, tumour, suspicious finding, cancer screening or further investigations.",
    "Say clearly in which service the contact takes place (the given asiointipaikka).",
]
W_LOOKALIKE = "Keep the benign reason of the dated line explicit, so that it cannot be read as a cancer-pathway step."
W_FUTURE = "The upcoming appointment has not happened; do not write it as done."


def build_no_event(taken):
    plan = []
    for category, (count, _, _, scenarios) in NO_EVENT.items():
        plan += [(category, scenarios[k % len(scenarios)]) for k in range(count)]
    assert len(plan) == N_NO_EVENT
    out, rejected, attempts_total = [], collections.Counter(), 0
    for j, (category, scenario) in enumerate(plan):
        statement, routes, styles = scenario[:3]
        months = scenario[3] if len(scenario) > 3 else None
        _, earlier_meaning, future_meaning, _ = NO_EVENT[category]
        r = random.Random(SEEDS["no_event"] + j)
        for attempt in range(1, 2001):
            attempts_total += 1
            note = dt.date(2024, 1, 1) + dt.timedelta(days=r.randrange(1096))
            route = r.choice(routes)
            style = r.choice(styles)
            offset = r.randint(2, 21) if r.random() < 0.6 else r.randint(22, 380)
            items = [other_date(r, "ordinary", statement, note - dt.timedelta(days=offset), note, S.FORMS)]
            second = r.choice(["none", "none", "none", "birth", "future", "earlier"])
            if second == "birth":
                items.append(
                    other_date(r, second, "syntymäaika", birth_date(r, (1960, 1995) if route == O else (1940, 1995)), note, ["numeric"])
                )
            elif second == "future":
                date = note + dt.timedelta(days=r.randint(10, 180))
                items.append(other_date(r, second, future_meaning, date, note, future_forms(date, note)))
            elif second == "earlier":
                date = note - dt.timedelta(days=r.randint(450, 900))
                items.append(other_date(r, second, earlier_meaning, date, note, ["numeric", "long", "month"]))
            distractors = [x[0] for x in items]
            problem = sequence_problem([], distractors, note)
            if not problem and months and dt.date.fromisoformat(distractors[0]["date"]).month not in months:
                problem = "outside_season"
            if problem:
                rejected[problem] += 1
                continue
            # Empty ground truth cannot identify a note, so the id also covers the dated content.
            ident = sha(
                dict(
                    kind="no_event",
                    statement=statement,
                    entry_route=route,
                    note_date=note.isoformat(),
                    items=[[d["kind"], d["date"], d["expression"]] for d in distractors],
                )
            )
            if ident in taken:
                rejected["id_already_used"] += 1
                continue
            taken.add(ident)
            wording = list(W_NO_EVENT)
            if category == "non_cancer_lookalike":
                wording.append(W_LOOKALIKE)
            if second == "future":
                wording.append(W_FUTURE)
            spec = make_spec(
                "no_event",
                category,
                ident,
                style,
                note,
                route,
                [],
                distractors,
                [x[1] for x in items],
                [f"asiointipaikka: {S.ROUTES[route]}"]
                + [f"{d['meaning']}: {d['expression']}" for d in distractors],
                wording,
                dict(source="build_no_event", seed=SEEDS["no_event"], index=j, attempt=attempt),
            )
            out.append(spec)
            break
        else:
            raise RuntimeError(f"no valid no-event spec for index {j}")
    return out, dict(attempts=attempts_total, rejected=dict(rejected))


# ---------------------------------------------------------------- ids already used, slicing, log


def used_ids():
    import pyarrow.parquet as pq

    sources = {}
    v1 = set()
    for split in ["train", "val", "test", "rejected"]:
        v1 |= set(pq.read_table(ROOT / f"data/scribe/dataset-v1/{split}.parquet", columns=["id"]).column("id").to_pylist())
    sources["data/scribe/dataset-v1/*.parquet"] = v1
    cache = ROOT / "data/scribe/cache"
    sources["data/scribe/cache/*.json"] = {json.loads(p.read_text())["id"] for p in sorted(cache.glob("*.json"))}
    pilot = ROOT / "scribe/artifacts/haiku-writer/tuples.json"
    sources["scribe/artifacts/haiku-writer/tuples.json"] = (
        {x["id"] for x in json.loads(pilot.read_text())} if pilot.exists() else set()
    )
    max_cache_index = max((int(p.stem) for p in cache.glob("*.json")), default=-1)
    return sources, max_cache_index


def spec_lines(row):
    """One specification as a few short lines: tools that cut long lines must not lose anything."""
    j = lambda v: json.dumps(v, ensure_ascii=False)  # noqa: E731
    pairs = lambda keys: ", ".join(f"{j(k)}: {j(row[k])}" for k in keys)  # noqa: E731
    items = lambda values: ["  " + j(v) + ("," if i < len(values) - 1 else "") for i, v in enumerate(values)]  # noqa: E731
    lines = ["{" + pairs(["slice", "n", "part", "id", "kind", "focus", "style", "note_date"]) + ', "facts_fi": [']
    lines += items(row["facts_fi"])
    if row["wording"]:
        lines.append(' ], "date_strings": ' + j(row["date_strings"]) + ', "wording": [')
        lines += items(row["wording"])
        lines.append(' ], "facts": ' + j(row["facts"]) + ",")
    else:
        lines.append(' ], "date_strings": ' + j(row["date_strings"]) + ', "wording": [], "facts": ' + j(row["facts"]) + ",")
    lines.append(' "distractors": ' + j(row["distractors"]) + ",")
    lines.append(" " + pairs(["ground_truth", "date_forms", "distractor_forms", "split_hint", "sampler", "synthetic"]) + "}")
    return lines


def part_table(part_lines):
    """Markdown table of the line range of each part, pasted into WRITER_INSTRUCTIONS.md."""
    out = ["| slice | part 1 | part 2 | part 3 | part 4 | lines in file |", "| --- | --- | --- | --- | --- | --- |"]
    for name, (ranges, total) in part_lines.items():
        out.append(f"| `{name}` | " + " | ".join(f"{a}-{b}" for a, b in ranges) + f" | {total} |")
    return "\n".join(out)


def log(step, command, inputs, outputs, metrics, status="ok"):
    line = dict(
        ts=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        step=step,
        host=socket.gethostname(),
        command=command,
        inputs=inputs,
        outputs=outputs,
        metrics=metrics,
        cost_usd=0,
        status=status,
    )
    with (ROOT / "runs/v2-data.jsonl").open("a") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def main():
    sources, max_cache_index = used_ids()
    taken = set().union(*sources.values())
    n_previous = len(taken)
    # Every random.Random seed used here must be new: outside v1 (SEED_V1 + cache index) and the pilot.
    ranges = {
        "v1": (SEED_V1, SEED_V1 + max(max_cache_index, 10_000)),
        "pilot": (SEED_PILOT, SEED_PILOT + 10_000),
    }
    for name, seed in SEEDS.items():  # each generator uses seeds in [seed, seed + 99_999]
        for lo, hi in ranges.values():
            assert seed > hi or seed + 99_999 < lo, name

    standard, standard_stats = build_standard(taken)
    careful, careful_stats = build_careful(taken)
    no_event, no_event_stats = build_no_event(taken)
    assert standard_stats["indices_drawn"] < 100_000
    specs = standard + careful + no_event
    assert len({s["id"] for s in specs}) == len(specs) == N_SLICES * PER_SLICE
    assert len(taken) == n_previous + len(specs)

    r = random.Random(SEEDS["slicing"])
    for group in (standard, careful, no_event):
        r.shuffle(group)
    files, part_lines = {}, {}
    position = collections.Counter()
    for k in range(N_SLICES):
        take = {"standard": 75, "no_event": 13 if k < 6 else 12, "careful": 12 if k < 6 else 13}
        chunk = []
        for name, group in (("standard", standard), ("no_event", no_event), ("careful", careful)):
            chunk += group[position[name] : position[name] + take[name]]
            position[name] += take[name]
        assert len(chunk) == PER_SLICE
        random.Random(SEEDS["slicing"] + k + 1).shuffle(chunk)
        rows = [dict(slice=k + 1, n=n + 1, part=n // 25 + 1, **spec) for n, spec in enumerate(chunk)]
        out_lines, ranges = ["["], []
        for row in rows:
            block = spec_lines(row)
            if row["n"] % 25 == 1:
                ranges.append([len(out_lines) + 1, None])  # 1-based line number of the part's first line
            block[-1] += "," if row["n"] < len(rows) else ""
            out_lines += block
            ranges[-1][1] = len(out_lines)
        out_lines.append("]")
        text = "\n".join(out_lines) + "\n"
        assert json.loads(text) == rows and [list(a) for a in json.loads(text)] == [list(a) for a in rows]
        path = HERE / f"slice-{k + 1:02d}.json"
        path.write_text(text)
        part_lines[path.name] = (ranges, len(out_lines))
        files[str(path.relative_to(ROOT))] = dict(
            sha256=hashlib.sha256(text.encode()).hexdigest(),
            bytes=len(text.encode()),
            specs=len(rows),
            kinds=dict(collections.Counter(row["kind"] for row in rows)),
            lines=len(out_lines),
            longest_line=max(map(len, out_lines)),
            part_lines=ranges,
        )
    assert position == {"standard": N_STANDARD, "no_event": N_NO_EVENT, "careful": N_CAREFUL}

    # Keep the line-range table of the writer instructions in step with the files just written.
    instructions = HERE.parent / "WRITER_INSTRUCTIONS.md"
    start, end = "<!-- part-lines:start -->", "<!-- part-lines:end -->"
    table_updated = False
    if instructions.exists() and start in instructions.read_text():
        doc = instructions.read_text()
        a, b = doc.index(start) + len(start), doc.index(end)
        instructions.write_text(doc[:a] + "\n" + part_table(part_lines) + "\n" + doc[b:])
        table_updated = True

    metrics = dict(
        specs=len(specs),
        kinds=dict(collections.Counter(s["kind"] for s in specs)),
        focus=dict(collections.Counter(f"{s['kind']}/{s['focus']}" for s in specs)),
        entry_route_by_kind={
            kind: dict(collections.Counter(s["ground_truth"]["entry_route"] for s in specs if s["kind"] == kind))
            for kind in ["standard", "careful", "no_event"]
        },
        events_total=sum(len(s["ground_truth"]["events"]) for s in specs),
        event_types=dict(collections.Counter(e["type"] for s in specs for e in s["ground_truth"]["events"])),
        events_per_spec=dict(collections.Counter(len(s["ground_truth"]["events"]) for s in specs)),
        event_date_forms=dict(collections.Counter(f for s in specs for f in s["date_forms"])),
        distractors_total=sum(len(s["distractors"]) for s in specs),
        styles=dict(collections.Counter(s["style"] for s in specs)),
        split_hint=dict(collections.Counter(s["split_hint"] for s in specs)),
        previously_used_ids_excluded={k: len(v) for k, v in sources.items()},
        previously_used_ids_union=n_previous,
        standard=standard_stats,
        careful=careful_stats,
        no_event=no_event_stats,
        instructions_line_table_updated=table_updated,
    )
    log(
        "build_v2_slices",
        "PYTHONDONTWRITEBYTECODE=1 scribe/.venv/bin/python data/scribe/v2/slices/_build_slices.py",
        dict(seeds=SEEDS, seed_v1=SEED_V1, seed_pilot=SEED_PILOT, v1_max_cache_index=max_cache_index),
        files,
        metrics,
    )
    print(json.dumps(dict(files=files, metrics=metrics), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
