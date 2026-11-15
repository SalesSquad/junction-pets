"""Independent re-read and check of the v2 writer slices and of WRITER_INSTRUCTIONS.md.

Run from the project root:
    PYTHONDONTWRITEBYTECODE=1 scribe/.venv/bin/python data/scribe/v2/slices/_validate_slices.py

Reads the twelve slice files from disk (it does not import the builder), checks every spec
against scribe/sample.py, scribe/prompts.py and scribe/verify.py, and checks that the example
notes and the detector claims in WRITER_INSTRUCTIONS.md hold when executed. Appends one line to
runs/v2-data.jsonl. Exit code 1 if any check fails.
"""

import collections
import datetime as dt
import hashlib
import json
import pathlib
import re
import socket
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "scribe"))

import pyarrow.parquet as pq  # noqa: E402
import sample as S  # noqa: E402
from prompts import canonicalise, parse_output  # noqa: E402
from verify import DATE_RE, accept, code_check  # noqa: E402

KEYS = [
    "slice", "n", "part", "id", "kind", "focus", "style", "note_date", "facts_fi", "date_strings",
    "wording", "facts", "distractors", "ground_truth", "date_forms", "distractor_forms",
    "split_hint", "sampler", "synthetic",
]  # fmt: skip
STYLES = {"lähetekirje", "käyntimerkintä", "hoitajan puhelinmerkintä", "loppulausunnon ote"}
FOCUS_RULES = {  # focus -> (types that must be present, types that must be absent)
    "referral_sent_and_received": ({"REFERRAL_SENT", "REFERRAL_RECEIVED"}, set()),
    "referral_sent_only": ({"REFERRAL_SENT"}, {"REFERRAL_RECEIVED", "SPECIALIST_VISIT"}),
    "referral_received_only": ({"REFERRAL_RECEIVED"}, {"REFERRAL_SENT"}),
    "first_contact_and_physician_assessment": ({"FIRST_CONTACT", "PHYSICIAN_ASSESSMENT"}, {"SPECIALIST_VISIT"}),
    "physician_assessment_and_specialist_visit": ({"PHYSICIAN_ASSESSMENT", "SPECIALIST_VISIT"}, {"FIRST_CONTACT"}),
    "first_contact_physician_assessment_and_specialist_visit": (
        {"FIRST_CONTACT", "PHYSICIAN_ASSESSMENT", "SPECIALIST_VISIT"},
        set(),
    ),
    "single_first_contact": ({"FIRST_CONTACT"}, {"PHYSICIAN_ASSESSMENT", "SPECIALIST_VISIT"}),
    "single_physician_assessment": ({"PHYSICIAN_ASSESSMENT"}, {"FIRST_CONTACT", "SPECIALIST_VISIT"}),
    "single_specialist_visit": ({"SPECIALIST_VISIT"}, {"FIRST_CONTACT", "PHYSICIAN_ASSESSMENT"}),
}
SEED_V1, SEED_PILOT = 20261114, 77020261
failures = []


def check(ok, message):
    if not ok:
        failures.append(message)
    return ok


def sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


def probe_note(spec):
    """A mechanical note that contains every date string once, padded past 60 words."""
    parts = [f"Kohta {x} kirjattu." for x in spec["date_strings"]]
    text = " ".join(parts)
    while len(text.split()) < 70:
        text += " Vointi vakaa."
    return text


def check_spec(spec, where):
    ok = True
    ok &= check(list(spec) == KEYS, f"{where}: keys {list(spec)}")
    note = dt.date.fromisoformat(spec["note_date"])
    truth = spec["ground_truth"]
    ok &= check(dt.date(2024, 1, 1) <= note <= dt.date(2026, 12, 31), f"{where}: note date")
    ok &= check(spec["style"] in STYLES and spec["synthetic"] is True, f"{where}: style/synthetic")
    ok &= check(re.fullmatch(r"[0-9a-f]{64}", spec["id"]) is not None, f"{where}: id format")
    try:
        ok &= check(canonicalise(truth) == truth, f"{where}: ground truth not canonical")
        ok &= check(
            parse_output(json.dumps(truth, ensure_ascii=False, separators=(",", ":"))) == truth,
            f"{where}: ground truth does not survive prompts.parse_output",
        )
    except Exception as exc:  # canonicalise raises on a schema error
        ok &= check(False, f"{where}: canonicalise {exc!r}")
    facts, distractors = spec["facts"], spec["distractors"]
    events = sorted(
        [{k: f[k] for k in ["type", "date", "precision"]} for f in facts],
        key=lambda e: (e["date"], e["type"]),
    )
    ok &= check(events == truth["events"], f"{where}: events differ from facts")
    ok &= check(spec["date_forms"] == [f["form"] for f in facts], f"{where}: date_forms")
    ok &= check(len(spec["distractor_forms"]) == len(distractors), f"{where}: distractor_forms")
    strings = [x["expression"] for x in facts + distractors]
    ok &= check(spec["date_strings"] == strings and len(set(strings)) == len(strings), f"{where}: date_strings")
    previous = None
    for f in facts:
        d = dt.date.fromisoformat(f["date"])
        ok &= check(S.parse_date(f["expression"], note) == (d, f["precision"]), f"{where}: parse {f['expression']}")
        ok &= check(S.render(d, note, f["form"]) == f["expression"], f"{where}: render {f['expression']}")
        ok &= check(f["meaning"] == S.FIN[S.TYPES.index(f["type"])], f"{where}: meaning")
        ok &= check(0 <= (note - d).days <= 400, f"{where}: {f['expression']} outside 0..400 days before note")
        ok &= check((f["precision"] == "MONTH") == (f["form"] == "month"), f"{where}: precision/form")
        if previous:
            ok &= check(previous[0] < d, f"{where}: dates not strictly increasing")
            ok &= check(S.TYPES.index(previous[1]) < S.TYPES.index(f["type"]), f"{where}: not in pathway order")
        previous = (d, f["type"])
    for x, form in zip(distractors, spec["distractor_forms"]):
        d = dt.date.fromisoformat(x["date"])
        ok &= check(S.parse_date(x["expression"], note)[0] == d, f"{where}: distractor parse {x['expression']}")
        ok &= check(S.render(d, note, form) == x["expression"], f"{where}: distractor render {x['expression']}")
        kind = x["kind"]
        if kind == "birth":
            ok &= check(1940 <= d.year <= 1995, f"{where}: birth year")
        elif kind.startswith("future"):
            ok &= check(d > note, f"{where}: future date is not after the note date")
        elif kind in ("vaccination", "earlier"):
            ok &= check((note - d).days >= 420, f"{where}: {kind} date too close")
        elif kind == "ordinary":
            ok &= check(d < note, f"{where}: ordinary date not before the note date")
        else:
            ok &= check(False, f"{where}: unknown distractor kind {kind}")
    # Writer-facing lines: first line is the route, every date string closes exactly one line.
    lines = spec["facts_fi"]
    route_fi = S.ROUTES[truth["entry_route"]]
    first = ("asiointipaikka: " if spec["kind"] == "no_event" else "syöpäpolun tuloreitti: ") + route_fi
    ok &= check(lines[0] == first, f"{where}: route line {lines[0]!r}")
    dated = [line for line in lines[1:] if not line.startswith("ilman päivämäärää: ")]
    ok &= check(
        len(dated) == len(strings) and all(line.endswith(": " + s) for line, s in zip(dated, strings)),
        f"{where}: facts_fi lines do not carry the date strings in order",
    )
    stripped = [line[: -len(s)] for line, s in zip(dated, strings)] + [lines[0]]
    stripped += [line for line in lines[1:] if line.startswith("ilman päivämäärää: ")] + spec["wording"]
    ok &= check(not any(re.search(r"\d", t) for t in stripped), f"{where}: digit in writer-facing text")
    ok &= check(not any(DATE_RE.search(t) for t in stripped), f"{where}: date-like wording in writer-facing text")
    # The v1 code check must find every date string and nothing else in a mechanical note.
    probe = code_check(dict(facts=facts, distractors=distractors, note_text=probe_note(spec)))
    ok &= check(probe["ok"], f"{where}: v1 code_check on probe note {probe}")
    kind = spec["kind"]
    types = {f["type"] for f in facts}
    if kind == "standard":
        row = S.sample(spec["sampler"]["index"], seed=spec["sampler"]["seed"])
        same = (
            row["id"] == spec["id"]
            and row["facts"] == facts
            and row["distractors"] == distractors
            and row["note_date"] == spec["note_date"]
            and row["style"] == spec["style"]
            and row["target_json"] == json.dumps(truth, ensure_ascii=False, separators=(",", ":"))
            and row["split"] == spec["split_hint"]
        )
        ok &= check(same, f"{where}: does not reproduce from scribe/sample.py")
        ok &= check(1 <= len(facts) <= 4, f"{where}: event count")
    elif kind == "careful":
        need, forbid = FOCUS_RULES[spec["focus"]]
        ok &= check(need <= types and not (forbid & types), f"{where}: focus {spec['focus']} has {sorted(types)}")
        ok &= check(1 <= len(facts) <= 4, f"{where}: event count")
        ok &= check(all(f["precision"] == "DAY" for f in facts if f["type"] in need), f"{where}: focus event not DAY")
        ok &= check(spec["id"] == sha(truth), f"{where}: id is not the ground-truth hash")
        ok &= check(len(spec["wording"]) >= 3, f"{where}: wording missing")
    elif kind == "no_event":
        ok &= check(not facts and not truth["events"], f"{where}: no_event has events")
        ok &= check(1 <= len(distractors) <= 2 and distractors[0]["kind"] == "ordinary", f"{where}: dated items")
    else:
        ok &= check(False, f"{where}: unknown kind {kind}")
    if kind != "no_event":
        ok &= check(spec["id"] == sha(truth), f"{where}: id is not the ground-truth hash")
    return ok


def check_instructions():
    """Execute what WRITER_INSTRUCTIONS.md claims: its examples and its detector statements."""
    path = ROOT / "data/scribe/v2/WRITER_INSTRUCTIONS.md"
    if not path.exists():
        return dict(present=False)
    text = path.read_text()
    blocks = re.findall(r"<!-- example-(spec|output) -->\s*```json\n(.*?)\n```", text, re.S)
    specs = [json.loads(b) for tag, b in blocks if tag == "spec"]
    outputs = [json.loads(b) for tag, b in blocks if tag == "output"]
    check(len(specs) == len(outputs) and len(specs) >= 3, "instructions: example blocks")
    examples = []
    for spec, output in zip(specs, outputs):
        check(isinstance(output, list) and len(output) == 1 and set(output[0]) == {"id", "note_text"}, "instructions: output shape")
        check(output[0]["id"] == spec["id"], "instructions: example id")
        note = dt.date.fromisoformat(spec["note_date"])
        for f in spec["facts"]:
            check(S.parse_date(f["expression"], note) == (dt.date.fromisoformat(f["date"]), f["precision"]), f"instructions: example date {f['expression']}")
        for x in spec["distractors"]:
            check(S.parse_date(x["expression"], note)[0].isoformat() == x["date"], f"instructions: example distractor {x['expression']}")
        check(canonicalise(spec["ground_truth"]) == spec["ground_truth"], "instructions: example truth")
        result = code_check(dict(facts=spec["facts"], distractors=spec["distractors"], note_text=output[0]["note_text"]))
        check(result["ok"], f"instructions: example note fails code_check {result}")
        check(not re.search(r"\d", re.sub("|".join(re.escape(s) for s in spec["date_strings"]), "", output[0]["note_text"])), "instructions: digit outside date strings in example")
        examples.append(dict(kind=spec["kind"], words=result["words"], ok=result["ok"]))

    def detector(sentence, expression=None):
        row = dict(facts=[dict(expression=expression)] if expression else [], distractors=[], note_text=sentence + " " + "Vointi vakaa. " * 35)
        return code_check(row)

    claims = {  # sentence -> does the v1 code check reject it (missing or extra date)?
        "capitalised month string is missing": not detector("Marraskuussa 2025 hoito aloitettiin.", "marraskuussa 2025")["ok"],
        "lower-case month string passes": detector("Hoito aloitettiin marraskuussa 2025.", "marraskuussa 2025")["ok"],
        "leading zero is missing and extra": not detector("Käynti 03.02.2025.", "3.2.2025")["ok"],
        "added year after no_year string is rejected": not detector("Käynti 3.2.2025.", "3.2.")["ok"],
        "no_year string at sentence end passes": detector("Käynti oli 3.2. Vointi hyvä.", "3.2.")["ok"],
        "tänään is extra": bool(detector("Potilas soitti tänään.")["extra"]),
        "eilen is extra": bool(detector("Potilas soitti eilen.")["extra"]),
        "viime viikolla is extra": bool(detector("Potilas soitti viime viikolla.")["extra"]),
        "bare year is extra": bool(detector("Leikattu vuonna 2019.")["extra"]),
        "bare month name is extra": bool(detector("Oireet alkoivat maaliskuun alussa.")["extra"]),
        "kuluttua is extra": bool(detector("Kontrolli 2 viikon kuluttua.")["extra"]),
        "decimal at sentence end is extra": bool(detector("Hb oli 13.5.")["extra"]),
        "clock time at sentence end is extra": bool(detector("Soitto klo 14.30.")["extra"]),
        "weekday is NOT detected": not detector("Potilas soitti maanantaina.")["extra"],
        "duration is NOT detected": not detector("Yskää on ollut kolmen viikon ajan.")["extra"],
        "59 words fail": not code_check(dict(facts=[], distractors=[], note_text="sana " * 59))["ok"],
        "60 words pass": code_check(dict(facts=[], distractors=[], note_text="sana " * 60))["ok"],
        "140 words pass": code_check(dict(facts=[], distractors=[], note_text="sana " * 140))["ok"],
        "141 words fail": not code_check(dict(facts=[], distractors=[], note_text="sana " * 141))["ok"],
        "v1 accept() is false without an event": not accept({"unlisted": 0.01, "distractor_0": 0.01, "route": 0.99}),
        "v1 accept() is true with an event": accept({"event_0": 0.99, "unlisted": 0.01, "distractor_0": 0.01, "route": 0.99}),
    }
    for name, holds in claims.items():
        check(holds, f"instructions: claim does not hold: {name}")
    return dict(present=True, sha256=hashlib.sha256(text.encode()).hexdigest(), bytes=len(text.encode()), examples=examples, detector_claims_checked=len(claims), detector_claims_true=sum(claims.values()))


def read_part_table():
    """slice file name -> ([[first, last] x 4], total lines) as printed in WRITER_INSTRUCTIONS.md."""
    path = ROOT / "data/scribe/v2/WRITER_INSTRUCTIONS.md"
    if not path.exists():
        return {}
    out = {}
    row = re.compile(r"^\| `(slice-\d\d\.json)` \| (\d+)-(\d+) \| (\d+)-(\d+) \| (\d+)-(\d+) \| (\d+)-(\d+) \| (\d+) \|$", re.M)
    for m in row.finditer(path.read_text()):
        v = list(map(int, m.groups()[1:]))
        out[m.group(1)] = ([v[0:2], v[2:4], v[4:6], v[6:8]], v[8])
    return out


def main():
    files = sorted(HERE.glob("slice-*.json"))
    check([f.name for f in files] == [f"slice-{k:02d}.json" for k in range(1, 13)], "file names")
    specs, per_file, layout = [], {}, {}
    table = read_part_table()
    for k, path in enumerate(files, 1):
        raw = path.read_text()
        rows = json.loads(raw)
        check(isinstance(rows, list) and len(rows) == 100, f"{path.name}: not 100 specs")
        file_lines = raw.splitlines()
        # Layout promised to the writers: short lines, and the line ranges printed in the instructions.
        check(len(file_lines) < 2000 and max(map(len, file_lines)) < 1500, f"{path.name}: layout {len(file_lines)} lines, longest {max(map(len, file_lines))}")
        check(sum(line.startswith('{"slice":') for line in file_lines) == 100, f"{path.name}: spec start lines")
        ranges = table.get(path.name)
        if check(ranges is not None and ranges[1] == len(file_lines), f"{path.name}: missing or stale row in the line-range table"):
            for part, (a, b) in enumerate(ranges[0], 1):
                try:
                    chunk = json.loads("[" + "\n".join(file_lines[a - 1 : b]).rstrip(",") + "]")
                except ValueError:
                    chunk = None
                check(chunk == [r for r in rows if r["part"] == part] and chunk is not None and len(chunk) == 25, f"{path.name}: lines {a}-{b} are not exactly part {part}")
        layout[path.name] = dict(lines=len(file_lines), longest_line=max(map(len, file_lines)), part_lines=ranges[0] if ranges else None)
        for n, spec in enumerate(rows, 1):
            where = f"{path.name}#{n}"
            check(spec["slice"] == k and spec["n"] == n and spec["part"] == (n - 1) // 25 + 1, f"{where}: slice/n/part")
            check_spec(spec, where)
        kinds = collections.Counter(s["kind"] for s in rows)
        check(kinds["standard"] == 75 and {kinds["no_event"], kinds["careful"]} == {12, 13}, f"{path.name}: kind mix {dict(kinds)}")
        per_file[path.name] = dict(sha256=hashlib.sha256(raw.encode()).hexdigest(), bytes=len(raw.encode()), specs=len(rows), kinds=dict(kinds), parts=dict(collections.Counter(s["part"] for s in rows)), **layout[path.name])
        specs += rows
    ids = [s["id"] for s in specs]
    check(len(specs) == 1200 and len(set(ids)) == 1200, "1200 unique ids")
    kinds = collections.Counter(s["kind"] for s in specs)
    check(kinds == {"standard": 900, "no_event": 150, "careful": 150}, f"kind totals {dict(kinds)}")

    # Overlap with everything written before: ids and, independently, the ground-truth strings.
    v1_ids, v1_targets = set(), set()
    for split in ["train", "val", "test", "rejected"]:
        table = pq.read_table(ROOT / f"data/scribe/dataset-v1/{split}.parquet", columns=["id", "target_json"]).to_pylist()
        v1_ids |= {r["id"] for r in table}
        v1_targets |= {json.dumps(json.loads(r["target_json"]), sort_keys=True) for r in table}
    cache_files = sorted((ROOT / "data/scribe/cache").glob("*.json"))
    cache_ids = {json.loads(p.read_text())["id"] for p in cache_files}
    pilot_path = ROOT / "scribe/artifacts/haiku-writer/tuples.json"
    pilot_ids = {x["id"] for x in json.loads(pilot_path.read_text())} if pilot_path.exists() else set()
    targets = [json.dumps(s["ground_truth"], sort_keys=True) for s in specs]
    overlap = dict(
        ids_in_dataset_v1=len(set(ids) & v1_ids),
        ids_in_v1_cache=len(set(ids) & cache_ids),
        ids_in_haiku_pilot=len(set(ids) & pilot_ids),
        ground_truth_in_dataset_v1=len(set(targets) & v1_targets),
        duplicate_ground_truth_among_event_specs=sum(
            c - 1 for t, c in collections.Counter(t for s, t in zip(specs, targets) if s["kind"] != "no_event").items()
        ),
    )
    check(not any(overlap.values()), f"overlap {overlap}")

    # Seeds: every random.Random seed of v2 lies outside what v1 and the pilot used.
    max_cache_index = max(int(p.stem) for p in cache_files)
    used = [(SEED_V1, SEED_V1 + max_cache_index), (SEED_PILOT, SEED_PILOT + 10_000)]
    seeds = collections.defaultdict(set)
    for s in specs:
        seeds[s["sampler"]["source"]].add(s["sampler"]["seed"] + s["sampler"]["index"])
    seed_ranges = {k: [min(v), max(v)] for k, v in seeds.items()}
    for lo, hi in seed_ranges.values():
        check(all(hi < a or lo > b for a, b in used), f"seed range {lo}-{hi} overlaps an earlier run")
    check(len({s["sampler"]["seed"] for s in specs}) == 3, "three generator seeds")

    events = [e for s in specs for e in s["ground_truth"]["events"]]
    instructions = check_instructions()
    metrics = dict(
        files=len(files),
        specs=len(specs),
        unique_ids=len(set(ids)),
        kinds=dict(kinds),
        focus=dict(collections.Counter(f"{s['kind']}/{s['focus']}" for s in specs)),
        entry_route=dict(collections.Counter(s["ground_truth"]["entry_route"] for s in specs)),
        entry_route_no_event=dict(collections.Counter(s["ground_truth"]["entry_route"] for s in specs if s["kind"] == "no_event")),
        styles=dict(collections.Counter(s["style"] for s in specs)),
        events=len(events),
        event_types=dict(collections.Counter(e["type"] for e in events)),
        event_precision=dict(collections.Counter(e["precision"] for e in events)),
        events_per_spec=dict(sorted(collections.Counter(len(s["ground_truth"]["events"]) for s in specs).items())),
        event_date_forms=dict(collections.Counter(f for s in specs for f in s["date_forms"])),
        distractors=sum(len(s["distractors"]) for s in specs),
        distractor_kinds=dict(collections.Counter(d["kind"] for s in specs for d in s["distractors"])),
        date_strings=sum(len(s["date_strings"]) for s in specs),
        date_strings_per_spec=dict(sorted(collections.Counter(len(s["date_strings"]) for s in specs).items())),
        no_event_dates_per_spec=dict(sorted(collections.Counter(len(s["date_strings"]) for s in specs if s["kind"] == "no_event").items())),
        undated_context_lines=sum(line.startswith("ilman päivämäärää: ") for s in specs for line in s["facts_fi"]),
        split_hint=dict(collections.Counter(s["split_hint"] for s in specs)),
        overlap=overlap,
        earlier_ids_checked=dict(dataset_v1=len(v1_ids), v1_cache=len(cache_ids), haiku_pilot=len(pilot_ids)),
        seed_ranges=seed_ranges,
        seed_ranges_used_before=used,
        probe_notes_passing_v1_code_check=len(specs) - sum("v1 code_check" in f for f in failures),
        layout=dict(max_lines=max(v["lines"] for v in layout.values()), longest_line=max(v["longest_line"] for v in layout.values()), part_line_ranges_checked=sum(len(v["part_lines"] or []) for v in layout.values())),
        instructions=instructions,
        failures=len(failures),
    )
    status = "ok" if not failures else "error"
    line = dict(
        ts=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        step="validate_v2_slices",
        host=socket.gethostname(),
        command="PYTHONDONTWRITEBYTECODE=1 scribe/.venv/bin/python data/scribe/v2/slices/_validate_slices.py",
        inputs=dict(slices="data/scribe/v2/slices/slice-*.json", instructions="data/scribe/v2/WRITER_INSTRUCTIONS.md"),
        outputs=per_file,
        metrics=dict(metrics, first_failures=failures[:20]),
        cost_usd=0,
        status=status,
    )
    with (ROOT / "runs/v2-data.jsonl").open("a") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")
    print(json.dumps(dict(status=status, metrics=metrics, first_failures=failures[:20]), ensure_ascii=False, indent=1))
    sys.exit(0 if not failures else 1)


if __name__ == "__main__":
    main()
