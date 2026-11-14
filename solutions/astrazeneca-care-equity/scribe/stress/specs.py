"""Stress set v1 (NVIDIA_OPTIONS.md step 5): answer keys (specifications) only. No model call, no network.

New seeds. Reuses, without editing them, scribe/sample.py (the existing sampler: note date, event types, offsets,
date forms, distractors, route, style) and the version-2 specification helpers in
data/scribe/v2/slices/_build_slices.py (writer lines, glosses, no-event scenarios).

What is new is the date phrasing of the LAST pathway fact(s):
  heldout   Finnish number words 7..12 ("kahdeksan päivää sitten", "yksitoista viikkoa sitten") or "toissapäivänä"
  vague     "pari viikkoa sitten", "viime kuussa", ... : no single exact day; the right outcome is "send to a person"
  standard  the six forms of scribe/sample.py, unchanged
and the lengths: standard (60-140 words), terse (25-49), long (110-260), plus no-event notes.

Everything is SYNTHETIC; not for clinical use. A person confirms every extracted event. These notes are an
evaluation set: no training script may read data/scribe/stress/.
"""

import collections
import datetime as dt
import hashlib
import importlib.util
import json
import pathlib
import random
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(ROOT / "scribe"), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import phrases as P  # noqa: E402
import sample as S  # noqa: E402
from prompts import canonicalise  # noqa: E402


def _load_builder():
    spec = importlib.util.spec_from_file_location("v2_build_slices", ROOT / "data/scribe/v2/slices/_build_slices.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # defines functions and tables only; main() is not called
    return module


B = _load_builder()

SET = "stress-v1"
OUT = ROOT / "data/scribe/stress"
# v1: 20261114+i; pilot: 77020261+i; v2: 21261114..21561114+j; v3 (teacher2): 23261114..24661114+i (< 25561114).
SEED = 20261114 + 8_000_000
SEEDS = {
    "standard": SEED,
    "terse": SEED + 100_000,
    "long": SEED + 200_000,
    "no_event": SEED + 300_000,
    "no_event_terse": SEED + 350_000,
    "phrasing": SEED + 400_000,  # random.Random(SEEDS["phrasing"] + k): phrase choices of the k-th sampler draw
    "order": SEED + 500_000,
}
# curriculum -> (code-check word bounds, target length given to the writer, max_tokens of a write call)
LENGTH = {
    "standard": ((60, 140), (80, 110), 650),
    "terse": ((25, 49), (30, 44), 400),
    "long": ((110, 260), (150, 220), 1200),
    "no_event": ((60, 140), (75, 105), 650),
    "no_event_terse": ((25, 49), (30, 44), 400),
}
TARGET = {"standard": 150, "terse": 70, "long": 50, "no_event": 35, "no_event_terse": 15}
CURRICULA = tuple(TARGET)
EVENT_CURRICULA = ("standard", "terse", "long")
SHARE = {"heldout": 0.55, "vague": 0.12}  # of the notes with events; the rest keep the six standard forms
HELDOUT_WEIGHTS = (("heldout_days_word", 0.35), ("heldout_weeks_word", 0.40), ("heldout_toissa", 0.25))
VAGUE_WEIGHTS = (
    ("pari viikkoa sitten", 0.30),
    ("viime kuussa", 0.25),
    ("muutama päivä sitten", 0.15),
    ("kuukausi sitten", 0.15),
    ("pari kuukautta sitten", 0.15),
)
SECOND_HELDOUT = 0.35  # chance that a held-out note also phrases the fact before the last one in number words

W_WORDS = (
    "Some date strings are written in words on purpose (for example '{example}'). Copy every date string exactly as "
    "given, in lower case and in the middle of a sentence: never at the start of a sentence, never in digits, never "
    "in another inflection, never more or less precise."
)
W_VAGUE = (
    "The time phrase '{phrase}' is deliberately vague. Keep it exactly that vague: give that fact no exact date, no "
    "number of days or weeks and no other time reference."
)
W_TERSE = [
    "Telegraphic clinical style: short fragments separated by full stops or semicolons; drop verbs and filler words where a clinician would.",
    "Use common Finnish clinical abbreviations where they fit (for example pot., anam., tk, tth, esh, pkl, yleisl., erik.lääk., lab, jatkoh., yt.). Never abbreviate, shorten or alter a date string, and never write a time abbreviation such as vk, pv, kk or vrk.",
    "Even in fragments, each date string must stand right next to the words that say what happened then, and the service must be named.",
]
W_LONG = [
    "Long note: describe the course in detail. Put plenty of neutral undated content (symptoms in general terms, current condition, functional ability, coping at home, counselling) between and around the dated facts.",
]


def sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def used_ids():
    """Every id in data/scribe/dataset-v1, v2/dataset, v3/dataset (all parquet files) and the v3 teacher specs."""
    import pyarrow.parquet as pq

    ids = set()
    files = []
    for folder in ("data/scribe/dataset-v1", "data/scribe/v2/dataset", "data/scribe/v3/dataset"):
        for path in sorted((ROOT / folder).glob("*.parquet")):
            ids |= set(pq.read_table(path, columns=["id"]).column("id").to_pylist())
            files.append(str(path.relative_to(ROOT)))
    for path in (ROOT / "data/scribe/v3/teacher/specs.jsonl", ROOT / "data/scribe/v3/dataset/round2.jsonl"):
        if path.exists():
            for line in path.read_text().splitlines():
                if line.strip():
                    row = json.loads(line)
                    if row.get("id"):
                        ids.add(row["id"])
            files.append(str(path.relative_to(ROOT)))
    return ids, files


def _weighted_order(r, weights):
    """All options, the first drawn by weight, the rest in a random order (fallbacks)."""
    names = [w[0] for w in weights]
    first = r.choices(names, weights=[w[1] for w in weights])[0]
    rest = [n for n in names if n != first]
    r.shuffle(rest)
    return [first] + rest


def interval(f):
    """(first day, last day) a fact can mean: a DAY date, a MONTH, or the window of a vague phrase."""
    if f.get("outcome") == "person":
        return dt.date.fromisoformat(f["window_start"]), dt.date.fromisoformat(f["window_end"])
    d = dt.date.fromisoformat(f["date"])
    return (d, P.month_end(d)) if f["precision"] == "MONTH" else (d, d)


def fits(facts, k, first, last, note):
    """Whether fact k may cover [first, last]: strictly after fact k-1, strictly before fact k+1, 0..400 days."""
    if not (0 <= (note - last).days and (note - first).days <= 400):
        return False
    if k > 0 and not interval(facts[k - 1])[1] < first:
        return False
    if k + 1 < len(facts) and not last < interval(facts[k + 1])[0]:
        return False
    return True


def problem(facts, distractors, note):
    """None if the facts are exact, strictly ordered and separately detectable; else the reason."""
    expressions = [x["expression"] for x in facts + distractors]
    if len(set(expressions)) != len(expressions):
        return "duplicate_expression"
    for f in facts:
        if f["family"] in P.STANDARD_FORMS:
            d, p = S.parse_date(f["expression"], note)
            if (d.isoformat(), p) != (f["date"], f["precision"]):
                return "parse_mismatch"
        elif f["family"] in P.HELDOUT_FAMILIES:
            if (note - dt.timedelta(days=P.heldout_days(f["expression"]))).isoformat() != f["date"]:
                return "heldout_arithmetic_mismatch"
    for k in range(len(facts)):
        first, last = interval(facts[k])
        if not fits(facts, k, first, last, note):
            return "chronology"
    for x in distractors:
        if x.get("form", "numeric") in P.STANDARD_FORMS and S.parse_date(x["expression"], note)[0].isoformat() != x["date"]:
            return "distractor_parse_mismatch"
    return None


def _set_heldout(f, family, offset, note):
    n = None if family == "heldout_toissa" else (offset if family == "heldout_days_word" else offset // 7)
    f.update(
        date=(note - dt.timedelta(days=offset)).isoformat(),
        precision="DAY",
        expression=P.render_heldout(family, n),
        form=family,
        family=family,
    )


def phrase_facts(plan, row, r):
    """The sampler's facts with the plan's phrasing applied to the last fact(s); (facts, reason-if-impossible)."""
    note = dt.date.fromisoformat(row["note_date"])
    facts = [dict(f, family=f["form"], outcome="date", window_start=None, window_end=None) for f in row["facts"]]
    last = len(facts) - 1
    if plan == "heldout":
        for family in _weighted_order(r, HELDOUT_WEIGHTS):
            options = [o for o in P.heldout_offsets(family) if fits(facts, last, note - dt.timedelta(days=o), note - dt.timedelta(days=o), note)]
            if options:
                _set_heldout(facts[last], family, r.choice(options), note)
                break
        else:
            return None, "heldout_does_not_fit"
        if last >= 1 and r.random() < SECOND_HELDOUT:
            options = [o for o in P.heldout_offsets("heldout_weeks_word") if fits(facts, last - 1, note - dt.timedelta(days=o), note - dt.timedelta(days=o), note)]
            if options:
                _set_heldout(facts[last - 1], "heldout_weeks_word", r.choice(options), note)
    elif plan == "vague":
        for phrase in _weighted_order(r, VAGUE_WEIGHTS):
            first, end, nominal, precision = P.vague_window(phrase, note)
            if fits(facts, last, first, end, note):
                facts[last].update(
                    date=nominal.isoformat(),
                    precision=precision,
                    expression=phrase,
                    form="vague",
                    family="vague",
                    outcome="person",
                    window_start=first.isoformat(),
                    window_end=end.isoformat(),
                )
                break
        else:
            return None, "vague_does_not_fit"
    elif plan != "standard":
        raise ValueError(plan)
    return facts, None


def _word_example(facts, distractors):
    for x in facts + distractors:
        if x.get("family", x.get("form")) in P.HELDOUT_FAMILIES + ("vague",):
            return x["expression"]
    return None


def make_spec(curriculum, plan, row, facts, sampler):
    distractors = [dict(d, form="numeric") for d in row["distractors"]]  # sample.py renders every distractor numerically
    events = sorted(
        [{k: f[k] for k in ("type", "date", "precision")} for f in facts if f["outcome"] == "date"],
        key=lambda e: (e["date"], e["type"]),
    )
    truth = canonicalise(dict(entry_route=row["entry_route"], events=events))
    vague = [
        dict(type=f["type"], phrase=f["expression"], window_start=f["window_start"], window_end=f["window_end"], nominal_date=f["date"], nominal_precision=f["precision"])
        for f in facts
        if f["outcome"] == "person"
    ]
    ident = sha(
        dict(
            set=SET,
            note_date=row["note_date"],
            entry_route=row["entry_route"],
            facts=[[f["type"], f["date"], f["precision"], f["expression"]] for f in facts],
            distractors=[[d["kind"], d["date"], d["expression"]] for d in distractors],
        )
    )
    wording = []
    example = _word_example(facts, distractors)
    if example:
        wording.append(W_WORDS.format(example=example))
    for v in vague:
        wording.append(W_VAGUE.format(phrase=v["phrase"]))
    wording += W_TERSE if curriculum == "terse" else W_LONG if curriculum == "long" else []
    families = [f["family"] for f in facts]
    return dict(
        id=ident,
        set=SET,
        kind="standard",
        curriculum=curriculum,
        phrase_plan=plan,
        focus=f"{curriculum}/{plan}",
        style=row["style"],
        note_date=row["note_date"],
        entry_route=row["entry_route"],
        facts_fi=B.writer_lines(ident, row["entry_route"], facts, distractors),
        date_strings=[x["expression"] for x in facts + distractors],
        wording=wording,
        facts=facts,
        distractors=distractors,
        ground_truth=truth,
        vague_events=vague,
        date_forms=families,
        has_heldout=any(f in P.HELDOUT_FAMILIES for f in families),
        has_vague=bool(vague),
        sampler=sampler,
        synthetic=True,
    )


def build_events(curriculum, n, taken):
    """n specifications of one event curriculum: heldout / vague / standard phrasing in the SHARE proportions."""
    n_held, n_vague = round(SHARE["heldout"] * n), round(SHARE["vague"] * n)
    plan = ["heldout"] * n_held + ["vague"] * n_vague + ["standard"] * (n - n_held - n_vague)
    random.Random(SEEDS["order"] + CURRICULA.index(curriculum)).shuffle(plan)
    out, skipped, i = [], collections.Counter(), 0
    seed = SEEDS[curriculum]
    for phrase_plan in plan:
        while True:
            if i >= 200_000:
                raise RuntimeError(f"sampler exhausted for {curriculum}")
            row = S.sample(i, seed=seed)
            r = random.Random(SEEDS["phrasing"] + CURRICULA.index(curriculum) * 10_000 + i)
            i += 1
            if curriculum == "terse" and (len(row["facts"]) > 2 or len(row["distractors"]) > 1):
                skipped["terse_needs_at_most_2_events_1_distractor"] += 1
                continue
            if curriculum == "long" and len(row["facts"]) < 3:
                skipped["long_needs_3_events"] += 1
                continue
            facts, why = phrase_facts(phrase_plan, row, r)
            if facts is None:
                skipped[why] += 1
                continue
            note = dt.date.fromisoformat(row["note_date"])
            why = problem(facts, [dict(d, form="numeric") for d in row["distractors"]], note)
            if why:
                skipped[why] += 1
                continue
            spec = make_spec(curriculum, phrase_plan, row, facts, dict(source="scribe/sample.py", seed=seed, index=i - 1))
            if spec["id"] in taken:
                skipped["id_already_used"] += 1
                continue
            taken.add(spec["id"])
            out.append(spec)
            break
    return out, dict(indices_drawn=i, skipped=dict(skipped), plan=dict(collections.Counter(plan)))


def build_no_event(curriculum, n, taken):
    """No pathway event: one ordinary non-cancer dated contact (B.NO_EVENT scenarios), half phrased held-out."""
    categories = list(B.NO_EVENT)
    out, rejected, attempts_total = [], collections.Counter(), 0
    base = SEEDS[curriculum]
    for j in range(n):
        category = categories[j % len(categories)]
        _, earlier_meaning, future_meaning, scenarios = B.NO_EVENT[category]
        scenario = scenarios[(j // len(categories)) % len(scenarios)]
        statement, routes, styles = scenario[:3]
        months = scenario[3] if len(scenario) > 3 else None
        heldout = j % 2 == 0
        r = random.Random(base + j)
        for attempt in range(1, 2001):
            attempts_total += 1
            note = dt.date(2024, 1, 1) + dt.timedelta(days=r.randrange(1096))
            route = r.choice(routes)
            style = r.choice(styles)
            if heldout:
                family = _weighted_order(r, HELDOUT_WEIGHTS)[0]
                offset = r.choice(P.heldout_offsets(family))
                f = dict(kind="ordinary", meaning=statement)
                _set_heldout(f, family, offset, note)
                ordinary = dict(kind="ordinary", expression=f["expression"], date=f["date"], meaning=statement, form=family)
            else:
                offset = r.randint(2, 21) if r.random() < 0.6 else r.randint(22, 380)
                item, form = B.other_date(r, "ordinary", statement, note - dt.timedelta(days=offset), note, S.FORMS)
                ordinary = dict(item, form=form)
            distractors = [ordinary]
            second = r.choice(["none", "none", "none", "birth", "future", "earlier"])
            if second == "birth":
                item, form = B.other_date(r, second, "syntymäaika", B.birth_date(r, (1960, 1995) if route == "OCCUPATIONAL" else (1940, 1995)), note, ["numeric"])
            elif second == "future":
                date = note + dt.timedelta(days=r.randint(10, 180))
                item, form = B.other_date(r, second, future_meaning, date, note, B.future_forms(date, note))
            elif second == "earlier":
                item, form = B.other_date(r, second, earlier_meaning, note - dt.timedelta(days=r.randint(450, 900)), note, ["numeric", "long", "month"])
            if second != "none":
                distractors.append(dict(item, form=form))
            why = problem([], distractors, note)
            if not why and months and dt.date.fromisoformat(ordinary["date"]).month not in months:
                why = "outside_season"
            if why:
                rejected[why] += 1
                continue
            ident = sha(
                dict(
                    set=SET,
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
            wording = list(B.W_NO_EVENT)
            if category == "non_cancer_lookalike":
                wording.append(B.W_LOOKALIKE)
            if second == "future":
                wording.append(B.W_FUTURE)
            example = _word_example([], distractors)
            if example:
                wording.insert(0, W_WORDS.format(example=example))
            if curriculum == "no_event_terse":
                wording += W_TERSE
            lines = [f"asiointipaikka: {S.ROUTES[route]}"]
            for d in distractors:
                tag = "has not happened yet" if d["kind"].startswith("future") else "not a pathway event"
                lines.append(f"{d['meaning']} [{tag}]: {d['expression']}")
            truth = canonicalise(dict(entry_route=route, events=[]))
            out.append(
                dict(
                    id=ident,
                    set=SET,
                    kind="no_event",
                    curriculum=curriculum,
                    phrase_plan="no_event_heldout" if heldout else "no_event_standard",
                    focus=f"{curriculum}/{category}",
                    style=style,
                    note_date=note.isoformat(),
                    entry_route=route,
                    facts_fi=lines,
                    date_strings=[d["expression"] for d in distractors],
                    wording=wording,
                    facts=[],
                    distractors=distractors,
                    ground_truth=truth,
                    vague_events=[],
                    date_forms=[],
                    has_heldout=False,
                    has_vague=False,
                    distractor_heldout=heldout,
                    sampler=dict(source="scribe/stress/specs.py build_no_event", seed=base, index=j, attempt=attempt, category=category),
                    synthetic=True,
                )
            )
            break
        else:
            raise RuntimeError(f"no valid no-event spec for index {j}")
    return out, dict(attempts=attempts_total, rejected=dict(rejected))


def interleave(groups):
    """One list in which every curriculum is spread evenly, so that a partial run stays balanced."""
    keyed = []
    for c, name in enumerate(CURRICULA):
        group = groups[name]
        for k, spec in enumerate(group):
            keyed.append(((k + 0.5) / max(1, len(group)), c, spec))
    keyed.sort(key=lambda t: t[:2])
    return [spec for _, _, spec in keyed]


def build_all(target=None):
    target = target or TARGET
    used, files = used_ids()
    taken = set(used)
    groups, report = {}, {}
    for name in CURRICULA:
        builder = build_events if name in EVENT_CURRICULA else build_no_event
        groups[name], report[name] = builder(name, target[name], taken)
        for spec in groups[name]:
            spec["writer_length"] = list(LENGTH[name][1])
            spec["word_bounds"] = list(LENGTH[name][0])
    specs = interleave(groups)
    ids = [s["id"] for s in specs]
    assert len(set(ids)) == len(ids) and not (set(ids) & used)
    with_events = [s for s in specs if s["kind"] == "standard"]
    summary = dict(
        set=SET,
        target=dict(target),
        built={name: len(groups[name]) for name in CURRICULA},
        specifications=len(specs),
        ids_checked_against=dict(files=files, ids=len(used), collisions=0),
        seeds=SEEDS,
        phrase_plan=dict(collections.Counter(s["phrase_plan"] for s in specs)),
        notes_with_heldout_fact=sum(s["has_heldout"] for s in specs),
        notes_with_vague_fact=sum(s["has_vague"] for s in specs),
        no_event_notes=sum(s["kind"] == "no_event" for s in specs),
        no_event_with_heldout_distractor=sum(bool(s.get("distractor_heldout")) for s in specs),
        fact_families=dict(collections.Counter(f["family"] for s in with_events for f in s["facts"])),
        events_per_note=dict(collections.Counter(len(s["facts"]) for s in with_events)),
        builders=report,
    )
    return specs, summary


def load_specs(path=None):
    path = path or OUT / "specs.jsonl"
    return [json.loads(line) for line in pathlib.Path(path).read_text().splitlines() if line.strip()]


def write_specs(specs, summary):
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "specs.jsonl"
    if target.exists():
        raise SystemExit(f"{target} exists; specifications are written once")
    with target.open("w") as f:
        for n, spec in enumerate(specs):
            f.write(json.dumps(dict(order=n, **spec), ensure_ascii=False) + "\n")
    (OUT / "specs-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n")
