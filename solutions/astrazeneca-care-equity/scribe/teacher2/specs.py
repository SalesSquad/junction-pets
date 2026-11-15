"""Teaching round 2: specifications (answer keys only; no model call, no network).

Reuses, without editing them, scribe/sample.py and the version-2 specification builders in
data/scribe/v2/slices/_build_slices.py, with NEW seeds. Everything is SYNTHETIC; not for clinical use.

Curricula (share of the 1,600 target):
  hard_standard     30%  sample.py tuples with >=2 relative date strings, >=2 distractor dates, 1 month date
  careful           25%  the version-2 wording traps (referral sent/received; contact/physician/specialist)
  no_event          15%  half non-cancer look-alikes, half cancer history without a dated pathway event
  long_multi_visit  15%  6..9 events, told out of chronological order
  terse             15%  telegraphic style with Finnish clinical abbreviations
"""

import collections
import datetime as dt
import importlib.util
import json
import pathlib
import random
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "scribe"))

import sample as S  # noqa: E402


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "v2_build_slices", ROOT / "data/scribe/v2/slices/_build_slices.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # defines functions only; main() is not called
    return module


B = _load_builder()

OUT = ROOT / "data/scribe/v3/teacher"
V2_DATASET = ROOT / "data/scribe/v2/dataset"
V2_FILES = ("train", "val", "test_nemotron", "test_haiku", "rejected")

SEED_V3 = 20261114 + 3_000_000  # v1: 20261114+i, pilot: 77020261+i, v2: 21261114 .. 21661113
SEEDS = {
    "hard_standard": SEED_V3,  # sample(i, seed) -> random.Random(seed + i), i < 900_000
    "careful": SEED_V3 + 1_000_000,
    "no_event": SEED_V3 + 1_100_000,
    "cancer_history": SEED_V3 + 1_200_000,
    "long_multi_visit": SEED_V3 + 1_300_000,
    "terse": SEED_V3 + 1_400_000,
    "order": SEED_V3 + 1_500_000,
}
TARGET = {"hard_standard": 480, "careful": 400, "no_event": 240, "long_multi_visit": 240, "terse": 240}
CURRICULA = tuple(TARGET)
RELATIVE = ("days", "weeks")

W_LONG = [
    "This is a summary that covers several visits. Tell the dated facts in exactly the order in which they are listed, which is deliberately NOT chronological. Do not re-sort them into time order and do not number them.",
    "Because the order is not chronological, the verb and the actor next to each date string must make clear on their own what happened on that date.",
]
W_TERSE = [
    "Telegraphic clinical style: short fragments separated by full stops or semicolons; drop verbs and filler words where a clinician would.",
    "Use common Finnish clinical abbreviations where they fit (for example pot., anam., tk, tth, esh, pkl, yleisl., erik.lääk., lab, rtg, jatkoh., kontr., yt.). Never abbreviate, shorten or alter a date string.",
    "Even in fragments, each date string must stand right next to the words that say what happened then, and the entry service must be named.",
]
W_HISTORY = [
    "The patient's background includes a cancer that was treated in the past and is over. Mention it as history WITHOUT any date, year, age or duration, and do not narrate any step of that old pathway (no referral, specialist appointment, confirmation of diagnosis, team decision or start of treatment as an event).",
    "This contact and every dated line are ordinary non-cancer care: no current suspicion of cancer, no new finding, no further investigations.",
    "Say clearly in which service the contact takes place (the given asiointipaikka).",
]
CANCERS = [
    "rintasyöpä",
    "eturauhassyöpä",
    "paksusuolisyöpä",
    "ihomelanooma",
    "kilpirauhassyöpä",
    "kohdunrunkosyöpä",
    "munuaissyöpä",
    "virtsarakon syöpä",
    "lymfooma",
    "kivessyöpä",
]
HISTORY_CATEGORIES = ("vaccination", "prescription_renewal", "dental_check", "minor_or_checkup")


def v2_ids():
    """Every id in any file of data/scribe/v2/dataset (train, val, both tests, rejected)."""
    import pyarrow.parquet as pq

    ids = set()
    for name in V2_FILES:
        ids |= set(pq.read_table(V2_DATASET / f"{name}.parquet", columns=["id"]).column("id").to_pylist())
    return ids


def drop_collisions(specs, used):
    """(kept, dropped): drop a specification whose id is in `used` or repeats an earlier one."""
    kept, dropped, seen = [], [], set(used)
    for spec in specs:
        if spec["id"] in seen:
            dropped.append(spec)
        else:
            seen.add(spec["id"])
            kept.append(spec)
    return kept, dropped


def is_hard(row):
    forms = row["date_forms"]
    return sum(f in RELATIVE for f in forms) >= 2 and forms.count("month") == 1 and len(row["distractors"]) >= 2


def _standard(curriculum, focus, n, taken, accept, wording, limit=900_000):
    out, skipped, i = [], collections.Counter(), 0
    seed = SEEDS[curriculum]
    while len(out) < n and i < limit:
        row = S.sample(i, seed=seed)
        i += 1
        if not accept(row):
            skipped["not_in_curriculum"] += 1
            continue
        if row["id"] in taken:
            skipped["id_already_used"] += 1
            continue
        note = dt.date.fromisoformat(row["note_date"])
        problem = B.sequence_problem(row["facts"], row["distractors"], note)
        if problem:
            skipped[problem] += 1
            continue
        taken.add(row["id"])
        out.append(
            B.make_spec(
                "standard",
                focus,
                row["id"],
                row["style"],
                note,
                row["entry_route"],
                row["facts"],
                row["distractors"],
                ["numeric"] * len(row["distractors"]),
                B.writer_lines(row["id"], row["entry_route"], row["facts"], row["distractors"]),
                list(wording),
                dict(source="sample.py", seed=seed, index=i - 1),
            )
        )
    return out, dict(indices_drawn=i, skipped=dict(skipped))


def build_hard_standard(n, taken):
    return _standard("hard_standard", "hard_standard", n, taken, is_hard, [])


def build_terse(n, taken):
    return _standard("terse", "terse_abbreviations", n, taken, lambda row: True, W_TERSE)


def _scaled(counts, total):
    """Largest-remainder scaling of integer counts to a new total."""
    base = sum(counts)
    raw = [c * total / base for c in counts]
    out = [int(x) for x in raw]
    for k in sorted(range(len(raw)), key=lambda k: raw[k] - out[k], reverse=True)[: total - sum(out)]:
        out[k] += 1
    return out


def build_careful(n, taken):
    """Version 2's build_careful, with new seeds and its focus counts scaled to n."""
    saved = (B.FOCI, B.N_CAREFUL, dict(B.SEEDS))
    try:
        counts = _scaled([f["count"] for f in saved[0]], n)
        B.FOCI = [dict(f, count=c) for f, c in zip(saved[0], counts)]
        B.N_CAREFUL = n
        B.SEEDS["careful"] = SEEDS["careful"]
        return B.build_careful(taken)
    finally:
        B.FOCI, B.N_CAREFUL = saved[0], saved[1]
        B.SEEDS.clear()
        B.SEEDS.update(saved[2])


def build_lookalike(n, taken):
    """Version 2's build_no_event restricted to its non-cancer look-alike category, new seeds."""
    saved = (B.NO_EVENT, B.N_NO_EVENT, dict(B.SEEDS))
    try:
        _, earlier, future, scenarios = saved[0]["non_cancer_lookalike"]
        B.NO_EVENT = {"non_cancer_lookalike": (n, earlier, future, scenarios)}
        B.N_NO_EVENT = n
        B.SEEDS["no_event"] = SEEDS["no_event"]
        return B.build_no_event(taken)
    finally:
        B.NO_EVENT, B.N_NO_EVENT = saved[0], saved[1]
        B.SEEDS.clear()
        B.SEEDS.update(saved[2])


def build_cancer_history(n, taken):
    """No dated pathway event; an old, treated cancer is mentioned as undated history."""
    plan = []
    k = 0
    while len(plan) < n:
        category = HISTORY_CATEGORIES[k % len(HISTORY_CATEGORIES)]
        scenarios = B.NO_EVENT[category][3]
        plan.append((category, scenarios[(k // len(HISTORY_CATEGORIES)) % len(scenarios)]))
        k += 1
    out, rejected, attempts_total = [], collections.Counter(), 0
    for j, (category, scenario) in enumerate(plan):
        statement, routes, styles = scenario[:3]
        months = scenario[3] if len(scenario) > 3 else None
        _, earlier_meaning, future_meaning, _ = B.NO_EVENT[category]
        r = random.Random(SEEDS["cancer_history"] + j)
        for attempt in range(1, 2001):
            attempts_total += 1
            note = dt.date(2024, 1, 1) + dt.timedelta(days=r.randrange(1096))
            route = r.choice(routes)
            style = r.choice(styles)
            cancer = r.choice(CANCERS)
            offset = r.randint(2, 21) if r.random() < 0.6 else r.randint(22, 380)
            items = [B.other_date(r, "ordinary", statement, note - dt.timedelta(days=offset), note, S.FORMS)]
            second = r.choice(["none", "none", "birth", "future", "earlier"])
            if second == "birth":
                items.append(B.other_date(r, second, "syntymäaika", B.birth_date(r, (1940, 1975)), note, ["numeric"]))
            elif second == "future":
                date = note + dt.timedelta(days=r.randint(10, 180))
                items.append(B.other_date(r, second, future_meaning, date, note, B.future_forms(date, note)))
            elif second == "earlier":
                date = note - dt.timedelta(days=r.randint(450, 900))
                items.append(B.other_date(r, second, earlier_meaning, date, note, ["numeric", "long", "month"]))
            distractors = [x[0] for x in items]
            problem = B.sequence_problem([], distractors, note)
            if not problem and months and dt.date.fromisoformat(distractors[0]["date"]).month not in months:
                problem = "outside_season"
            if problem:
                rejected[problem] += 1
                continue
            ident = B.sha(  # the version-2 id rule for a note without events
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
            wording = list(W_HISTORY) + ([B.W_FUTURE] if second == "future" else [])
            history = (
                f"ilman päivämäärää: anamneesissa aiemmin hoidettu {cancer} "
                "(treated in the past, over; no date, year, age or duration of any kind)"
            )
            spec = B.make_spec(
                "no_event",
                "cancer_history_undated",
                ident,
                style,
                note,
                route,
                [],
                distractors,
                [x[1] for x in items],
                [f"asiointipaikka: {S.ROUTES[route]}"]
                + [f"{d['meaning']} [not a pathway event]: {d['expression']}" for d in distractors]
                + [history],
                wording,
                dict(source="teacher2.build_cancer_history", seed=SEEDS["cancer_history"], index=j, attempt=attempt, category=category),
            )
            out.append(spec)
            break
        else:
            raise RuntimeError(f"no valid cancer-history spec for index {j}")
    return out, dict(attempts=attempts_total, rejected=dict(rejected))


def build_long(n, taken):
    """Six to nine pathway events; the fact lines are listed (and must be told) out of time order."""
    styles = ["loppulausunnon ote", "lähetekirje", "käyntimerkintä"]
    out, rejected, attempts_total = [], collections.Counter(), 0
    for j in range(n):
        r = random.Random(SEEDS["long_multi_visit"] + j)
        for attempt in range(1, 4001):
            attempts_total += 1
            note = dt.date(2024, 1, 1) + dt.timedelta(days=r.randrange(1096))
            route = r.choice(list(S.ROUTES))
            style = r.choice(styles)
            types = sorted(r.sample(S.TYPES, r.randint(6, 9)), key=S.TYPES.index)
            offsets = [r.randint(3, 30)]
            for pair in reversed(list(zip(types, types[1:]))):
                offsets.append(offsets[-1] + r.randint(*B.SHORT_GAPS.get(pair, (7, 45))))
            offsets.reverse()
            facts = [B.event_fact(r, t, note - dt.timedelta(days=o), note, S.FORMS) for t, o in zip(types, offsets)]
            distractors, distractor_forms = [], []
            for kind in r.sample(["birth", "vaccination", "future"], r.randint(0, 2)):
                if kind == "birth":
                    item = B.other_date(r, kind, "syntymäaika", B.birth_date(r, B.BIRTH_YEARS.get(route, (1940, 1995))), note, ["numeric"])
                elif kind == "vaccination":
                    item = B.other_date(r, kind, "aiempi syöpään liittymätön rokotuskäynti", note - dt.timedelta(days=r.randint(450, 900)), note, ["numeric", "long"])
                else:
                    date = note + dt.timedelta(days=r.randint(10, 100))
                    item = B.other_date(r, "future", "tuleva, vielä toteutumaton kontrolliaika", date, note, B.future_forms(date, note))
                distractors.append(item[0])
                distractor_forms.append(item[1])
            order = list(range(len(facts)))
            r.shuffle(order)
            problem = B.sequence_problem(facts, distractors, note)
            if not problem and min((note - dt.date.fromisoformat(f["date"])).days for f in facts) < 2:
                problem = "too_close_to_note_date"
            if not problem and order == sorted(order):
                problem = "narration_order_is_chronological"
            if problem:
                rejected[problem] += 1
                continue
            events = sorted([{k: f[k] for k in ["type", "date", "precision"]} for f in facts], key=lambda e: (e["date"], e["type"]))
            ident = B.sha(dict(entry_route=route, events=events))  # same id rule as scribe/sample.py
            if ident in taken:
                rejected["id_already_used"] += 1
                continue
            taken.add(ident)
            told = [facts[k] for k in order]
            spec = B.make_spec(
                "standard",
                "long_multi_visit",
                ident,
                style,
                note,
                route,
                facts,
                distractors,
                distractor_forms,
                B.writer_lines(ident, route, told, distractors),
                list(W_LONG),
                dict(source="teacher2.build_long", seed=SEEDS["long_multi_visit"], index=j, attempt=attempt),
            )
            spec["narration_order"] = [f["type"] for f in told]
            out.append(spec)
            break
        else:
            raise RuntimeError(f"no valid long spec for index {j}")
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
    used = v2_ids()
    taken = set(used)
    groups, report = {}, {}
    groups["hard_standard"], report["hard_standard"] = build_hard_standard(target["hard_standard"], taken)
    groups["careful"], report["careful"] = build_careful(target["careful"], taken)
    half = target["no_event"] // 2
    lookalike, r1 = build_lookalike(half, taken)
    history, r2 = build_cancer_history(target["no_event"] - half, taken)
    groups["no_event"], report["no_event"] = lookalike + history, dict(lookalike=r1, cancer_history=r2)
    groups["long_multi_visit"], report["long_multi_visit"] = build_long(target["long_multi_visit"], taken)
    groups["terse"], report["terse"] = build_terse(target["terse"], taken)
    dropped_total = 0
    for name in CURRICULA:
        for spec in groups[name]:
            spec["curriculum"] = name
            spec["round"] = 2
        random.Random(SEEDS["order"] + CURRICULA.index(name)).shuffle(groups[name])
        groups[name], dropped = drop_collisions(groups[name], used)
        dropped_total += len(dropped)
    specs = interleave(groups)
    specs, dropped = drop_collisions(specs, used)
    dropped_total += len(dropped)
    assert len({s["id"] for s in specs}) == len(specs) and not ({s["id"] for s in specs} & used)
    summary = dict(
        target=dict(target),
        built={name: len(groups[name]) for name in CURRICULA},
        specifications=len(specs),
        v2_dataset_ids=len(used),
        dropped_by_final_collision_filter=dropped_total,
        seeds=SEEDS,
        builders=report,
    )
    return specs, summary


def write_specs(specs, summary):
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "specs.jsonl").open("w") as f:
        for n, spec in enumerate(specs):
            f.write(json.dumps(dict(order=n, **spec), ensure_ascii=False) + "\n")
    (OUT / "specs-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))


def load_specs():
    return [json.loads(line) for line in (OUT / "specs.jsonl").read_text().splitlines() if line.strip()]


if __name__ == "__main__":
    specs, summary = build_all()
    write_specs(specs, summary)
    print(json.dumps({k: summary[k] for k in ("target", "built", "specifications", "v2_dataset_ids", "dropped_by_final_collision_filter")}))
