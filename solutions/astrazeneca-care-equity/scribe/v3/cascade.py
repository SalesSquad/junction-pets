"""Cascade at inference: the student proposes events and a person confirms every one. A note may be pre-filled for
one-click confirmation only when the error among pre-filled notes stays at or below a target on validation notes;
every other note needs editing.

  scribe/.venv/bin/python scribe/v3/cascade.py prepare
      choose ONE student by validation exact match, write the judge inputs and the plan (no request is sent)
  scribe/judges/run.py --in data/scribe/v3/cascade/pairs-jev-v1.jsonl ...        (commands are in plan-v1.json)
  scribe/.venv/bin/python scribe/v3/cascade.py record --judge jev|decisions --summary <run.py stdout file>
  scribe/.venv/bin/python scribe/v3/cascade.py analyse
      thresholds and the logistic fit on validation notes only (asserted), report on the two test sets
  --resolve A' (default) | A | off    before any outcome is scored or any judge input is written, the student's
      prediction goes through the relative-date resolver (scribe/v3/resolve.py, frozen in
      data/scribe/v4/resolver/freeze.json), as in the product client. The outcome is then exact match of the resolved
      prediction. Resolved runs write their own *-v2-resolved-<arm> files; "--resolve off" is the recorded v1 analysis.

Signals: the student's confidence (mean token log-probability), a judge score built from Jev's answers, their
logistic combination, and on a hash-chosen subset the same with OpenAI Decisions. For each signal the threshold is
the one with the largest validation coverage whose observed validation error among accepted notes is at most the
target. These are EMPIRICAL thresholds on 310 synthetic validation notes, not guarantees.

All notes are SYNTHETIC (simulated pathways, model-written notes). Nothing here is for clinical use.
"""

import argparse
import datetime as dt
import json
import math
import random
import socket
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import ROOT, order_key, read_jsonl, save_json, sha256_file, share, wilson, write_jsonl  # noqa: E402

import resolve as date_resolve  # noqa: E402  (relative-date rule; standard library only)

sys.path.insert(0, str(ROOT / "scribe/judges"))
import core  # noqa: E402  (request bodies only, to check and size the inputs; this file sends nothing)

STUDENT = ROOT / "data/scribe/v3/student"
DATASET = ROOT / "data/scribe/v3/dataset"
JUDGES = ROOT / "data/scribe/v3/judges"
OUT = ROOT / "data/scribe/v3/cascade"
RUNLOG = ROOT / "runs/cascade-v3.jsonl"
COMPARE = STUDENT / "compare-v1.json"
PREREG = STUDENT / "preregistration.json"
PLAN = OUT / "plan-v1.json"
PAIRS = dict(jev=OUT / "pairs-jev-v1.jsonl", decisions=OUT / "pairs-decisions-v1.jsonl")
ANSWERS = dict(jev=OUT / "answers-jev-v1.jsonl", decisions=OUT / "answers-decisions-v1.jsonl")
RUNS = dict(jev=OUT / "run-jev-v1.json", decisions=OUT / "run-decisions-v1.json")
NOTES = OUT / "notes-v1.jsonl"
RESULT = OUT / "cascade-v1.json"
RESULTS_MD = OUT / "RESULTS.md"
RESOLVE_ARMS = ("A'", "A", "off")
RESOLVE = "off"  # on import: the v1 file set; the command line sets --resolve (default A', the product arm chosen on
# validation in data/scribe/v4/resolver/reproduce-v1.json) through use_resolver(), which also switches the file set
RESOLVER_FREEZE = ROOT / "data/scribe/v4/resolver/freeze.json"


def use_resolver(arm):
    """Select the resolver arm; a resolved run reads and writes its own file set, so v1 files stay as recorded."""
    global RESOLVE, PLAN, PAIRS, ANSWERS, RUNS, NOTES, RESULT, RESULTS_MD
    if arm not in RESOLVE_ARMS:
        raise SystemExit(f"--resolve must be one of {RESOLVE_ARMS}")
    RESOLVE = arm
    if arm == "off":
        return
    tag = "v2-resolved-" + ("Aprime" if arm == "A'" else arm)
    PLAN = OUT / f"plan-{tag}.json"
    PAIRS = dict(jev=OUT / f"pairs-jev-{tag}.jsonl", decisions=OUT / f"pairs-decisions-{tag}.jsonl")
    ANSWERS = dict(jev=OUT / f"answers-jev-{tag}.jsonl", decisions=OUT / f"answers-decisions-{tag}.jsonl")
    RUNS = dict(jev=OUT / f"run-jev-{tag}.json", decisions=OUT / f"run-decisions-{tag}.json")
    NOTES = OUT / f"notes-{tag}.jsonl"
    RESULT = OUT / f"cascade-{tag}.json"
    RESULTS_MD = OUT / f"RESULTS-{tag}.md"


def resolver_record():
    """What resolved the predictions; the frozen hashes are checked before use."""
    if RESOLVE == "off":
        return dict(arm="off")
    freeze = json.loads(RESOLVER_FREEZE.read_text())
    now_sha = {f: sha256_file(ROOT / f) for f in freeze["files"]}
    if now_sha != freeze["files"]:
        raise SystemExit(f"resolver files changed since {rel(RESOLVER_FREEZE)}")
    return dict(arm=RESOLVE, rule=date_resolve.RULE, freeze=rel(RESOLVER_FREEZE), frozen_at_utc=freeze["frozen_at_utc"],
                files=freeze["files"], applied="to every parsed student prediction before its outcome is scored and before "
                "any judge input is written; outcome = exact match of the resolved prediction")

TEST_GROUPS = ("test_nemotron", "test_haiku")
ALPHA_PCT = (5, 10)  # target error among accepted notes, percent
MIN_ACCEPTED = 20  # a validation threshold must accept at least this many notes (then one error is 5%)
BOOT = 2000
SEED = 20261114
L2 = 1.0  # ridge on the standardised logistic weights (not on the intercept)
DEC_MAX_PER_SPLIT = 120
DEC_SALT = "scribe-v3-cascade-decisions"
OPENAI_STEP_TOKENS = 300_000  # hard cap for this step, added to the shared ledger's committed tokens
OPENAI_PLAN_SHARE = 0.9  # the subset is sized so that the estimate stays under 90 % of the cap
TYPESAFE_STEP_USD = 1.00
JEV_USD_PER_MTOK = 0.042  # owner's price, scribe/judges/core.py
DEC_USD_PER_MTOK_INPUT = 0.10  # Decisions guide list rate as read by an earlier step (scribe/judges/RESULTS.md)
CONF_FLOOR = 1e-12


def now():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rel(p):
    return str(Path(p).resolve().relative_to(ROOT))


def log(step, command, inputs=None, outputs=None, metrics=None, cost_usd=0.0, status="ok", **kw):
    """One JSON line per executed step in runs/cascade-v3.jsonl."""
    rec = dict(ts=now(), step=step, host=socket.gethostname(), command=command, inputs=inputs, outputs=outputs,
               metrics=metrics, cost_usd=cost_usd, status=status, **kw)
    RUNLOG.parent.mkdir(parents=True, exist_ok=True)
    with RUNLOG.open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def r4(x):
    return None if x is None else round(x, 4)


def nearest_rank(xs, q):
    s = sorted(xs)
    return s[max(0, math.ceil(q * len(s)) - 1)] if s else None


# ---- the leak guard --------------------------------------------------------------------------------------------


def assert_validation_only(notes, test_ids, what):
    """Raise AssertionError when a test note (by split or by id) reaches a fit or a threshold. Not an `assert`
    statement, so it also holds under `python -O`."""
    bad = [n["id"] for n in notes if n.get("split") != "val" or n["id"] in test_ids]
    if bad:
        raise AssertionError(f"{what}: {len(bad)} test note(s) reached a validation-only step, e.g. {bad[0][:16]}")


# ---- threshold, logistic fit, risk-coverage --------------------------------------------------------------------


def select_threshold(notes, scores, alpha_pct, test_ids, min_accepted=MIN_ACCEPTED):
    """Largest-coverage threshold on validation: accept a note when its score is >= t (a None score never accepts).
    Feasible when at least `min_accepted` notes are accepted and 100*wrong <= alpha_pct*accepted (exact integers)."""
    assert_validation_only(notes, test_ids, "threshold selection")
    if len(scores) != len(notes):
        raise ValueError("scores and notes differ in length")
    pairs = sorted(((s, bool(n["outcome"])) for n, s in zip(notes, scores) if s is not None), key=lambda x: -x[0])
    best, best_any, acc, wrong, i = None, None, 0, 0, 0
    while i < len(pairs):
        t = pairs[i][0]
        while i < len(pairs) and pairs[i][0] == t:
            acc += 1
            wrong += not pairs[i][1]
            i += 1
        if 100 * wrong <= alpha_pct * acc:
            best_any = dict(threshold=t, accepted=acc, wrong=wrong)
            if acc >= min_accepted:
                best = dict(best_any)
    n = len(notes)
    if best is None:
        why = (f"no threshold accepts at least {min_accepted} of {n} validation notes with observed error <= {alpha_pct}%"
               + (f"; the largest set within the error target had {best_any['accepted']} note(s)" if best_any else
                  "; not even the single highest-scored note was correct"))
        return dict(threshold=None, n=n, reason=why, alpha_pct=alpha_pct, min_accepted=min_accepted)
    return dict(best, n=n, coverage=best["accepted"] / n, error=best["wrong"] / best["accepted"], alpha_pct=alpha_pct,
                min_accepted=min_accepted)


def _sigmoid(z):
    if z >= 0:
        return 1 / (1 + math.exp(-z))
    e = math.exp(z)
    return e / (1 + e)


def _solve(a, b):
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[p] = m[p], m[c]
        if abs(m[c][c]) < 1e-15:
            raise ValueError("singular system in the logistic fit")
        for r in range(c + 1, n):
            f = m[r][c] / m[c][c]
            for k in range(c, n + 1):
                m[r][k] -= f * m[c][k]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        x[r] = (m[r][n] - sum(m[r][k] * x[k] for k in range(r + 1, n))) / m[r][r]
    return x


def fit_logistic(notes, features, test_ids, l2=L2, iters=100):
    """Ridge logistic regression of exact match on standardised features (Newton). Notes lacking a feature are left
    out of the fit (they go to a person). Validation notes only (asserted)."""
    assert_validation_only(notes, test_ids, "logistic fit")
    rows = [n for n in notes if all(n["features"].get(f) is not None for f in features)]
    if len(rows) < 2:
        raise ValueError("too few notes to fit")
    xs = [[n["features"][f] for f in features] for n in rows]
    ys = [1.0 if n["outcome"] else 0.0 for n in rows]
    mean = [statistics.fmean(c) for c in zip(*xs)]
    sd = [statistics.pstdev(c) or 1.0 for c in zip(*xs)]
    zs = [[1.0] + [(x - mu) / s for x, mu, s in zip(r, mean, sd)] for r in xs]
    d = len(features) + 1
    w = [0.0] * d
    it = 0
    for it in range(1, iters + 1):
        g = [0.0] * d
        h = [[0.0] * d for _ in range(d)]
        for z, y in zip(zs, ys):
            p = _sigmoid(sum(a * b for a, b in zip(w, z)))
            r, v = p - y, p * (1 - p)
            for a in range(d):
                g[a] += r * z[a]
                va = v * z[a]
                for b in range(a, d):
                    h[a][b] += va * z[b]
        for a in range(d):
            for b in range(a):
                h[a][b] = h[b][a]
        for a in range(1, d):
            g[a] += l2 * w[a]
            h[a][a] += l2
        step = _solve(h, g)
        w = [wi - si for wi, si in zip(w, step)]
        if max(abs(s) for s in step) < 1e-10:
            break
    return dict(features=list(features), mean=mean, sd=sd, weights=w, l2=l2, n=len(rows), positives=int(sum(ys)),
                iterations=it)


def logit(model, feats):
    """Linear predictor of the fitted model (monotone in the probability, no saturation ties); None if a feature is
    missing."""
    if any(feats.get(f) is None for f in model["features"]):
        return None
    return model["weights"][0] + sum(
        w * (feats[f] - mu) / s for w, f, mu, s in zip(model["weights"][1:], model["features"], model["mean"], model["sd"]))


def aurc(outcomes, scores):
    """Area under the risk-coverage curve: mean over k = 1..n of the error among the k highest-scored notes, in
    expectation over random tie-breaking. None scores rank last (they go to a person)."""
    n = len(outcomes)
    groups = {}
    for o, s in zip(outcomes, scores):
        key = -math.inf if s is None else s
        g = groups.setdefault(key, [0, 0])
        g[0] += 1
        g[1] += not o
    total, kb, eb = 0.0, 0, 0
    for key in sorted(groups, reverse=True):
        ng, eg = groups[key]
        for j in range(1, ng + 1):
            total += (eb + j * eg / ng) / (kb + j)
        kb += ng
        eb += eg
    return total / n if n else None


def aurc_optimal(outcomes):
    n, c = len(outcomes), sum(bool(o) for o in outcomes)
    return sum(max(0, k - c) / k for k in range(1, n + 1)) / n if n else None


# ---- the judge score -------------------------------------------------------------------------------------------


def judge_score(res):
    """min over predicted events of P(event stated) x (1 - P(unlisted event)); 0 when the judge's route choice
    differs from the student's route. None for an error or an incomplete answer. No events: min over nothing = 1."""
    if not isinstance(res, dict) or res.get("error"):
        return None
    p, n = res.get("probabilities") or {}, res.get("n_events")
    if not isinstance(n, int):
        return None
    need = [f"event_{i}" for i in range(n)] + ["unlisted"]
    if any(isinstance(p.get(k), bool) or not isinstance(p.get(k), (int, float)) for k in need):
        return None
    if res.get("route_choice") != res.get("claimed_route"):
        return 0.0
    return min((p[f"event_{i}"] for i in range(n)), default=1.0) * (1.0 - p["unlisted"])


def student_feature(conf):
    """-ln(-mean token log-probability): larger is more confident. Used only inside the logistic combinations."""
    return -math.log(max(-conf, CONF_FLOOR))


# ---- student choice and the per-note table ---------------------------------------------------------------------


def candidates():
    out = []
    for d in sorted(p for p in STUDENT.iterdir() if p.is_dir()):
        res = d / "result.json"
        tests = [d / "eval-test.json"] if (d / "eval-test.json").exists() else sorted(d.glob("*test_nemotron+test_haiku*.json"))
        if not res.exists() or not tests:
            continue
        m = json.loads(res.read_text())["val"]["metrics"]
        k, n = sum(bool(x) for x in m["outcomes"]), len(m["outcomes"])
        lo, hi = wilson(k, n)
        out.append(dict(run=d.name, k=k, n=n, exact_match=k / n, wilson95=[lo, hi], val_file=rel(res), test_file=rel(tests[0])))
    return out


def choose_student(cands, primary):
    """Highest validation exact match; but when the pre-registered primary and that run lie within each other's
    Wilson 95 % intervals, the primary."""
    top = max(cands, key=lambda c: (c["exact_match"], c["run"]))
    prim = next((c for c in cands if c["run"] == primary), None)
    within = bool(prim) and prim is not top and (top["wilson95"][0] <= prim["exact_match"] <= top["wilson95"][1]) and (
        prim["wilson95"][0] <= top["exact_match"] <= prim["wilson95"][1])
    if prim is top:
        return prim, f"{top['run']} has the highest validation exact match and is the pre-registered primary"
    if within:
        return prim, (
            f"highest validation exact match is {top['run']} ({top['k']}/{top['n']}); the pre-registered primary "
            f"{prim['run']} ({prim['k']}/{prim['n']}) and it lie within each other's Wilson 95% intervals, so the rule "
            f"prefers the primary")
    return top, f"{top['run']} has the highest validation exact match and the primary is not within its interval"


def primary_run():
    comp = json.loads(COMPARE.read_text())
    prim = [c["run"] for c in comp["comparisons"] if str(c.get("what", "")).startswith("primary")]
    pre = json.loads(PREREG.read_text())["primary"]["run"]
    if len(prim) != 1 or prim[0] != pre:
        raise SystemExit(f"compare-v1.json primary {prim} differs from the pre-registration {pre}")
    return prim[0]


def parquet(split):
    import pyarrow.parquet as pq

    return {r["id"]: r for r in pq.read_table(DATASET / f"{split}.parquet").to_pylist()}


def judgeable(pred):
    if not isinstance(pred, dict):
        return False, "prediction did not parse"
    if not isinstance(pred.get("entry_route"), str) or not isinstance(pred.get("events"), list):
        return False, "prediction lacks entry_route or events"
    for e in pred["events"]:
        if not isinstance(e, dict) or e.get("type") not in core.ENGLISH or (e.get("precision") or "DAY") not in ("DAY", "MONTH"):
            return False, "event type or precision outside the schema"
        try:
            dt.date.fromisoformat(e["date"])
        except (KeyError, TypeError, ValueError):
            return False, "event date is not an ISO date"
    return True, ""


def note_row(ident, split, group, outcome, conf, rec, meta):
    pred = rec.get("prediction")
    ok, why = judgeable(pred)
    return dict(id=ident, split=split, group=group, outcome=bool(outcome), confidence=None if conf is None else float(conf),
                parsed=isinstance(pred, dict), judgeable=ok, not_judgeable_reason=why, prediction=pred,
                note_date=meta["note_date"], kind=meta["kind"])


def same_conf(a, b):
    return (a is None and b is None) or (a is not None and b is not None and abs(a - b) <= 1e-12)


def resolve_note(rec, meta, stored_outcome, arm):
    """Resolve one stored prediction before scoring. Returns (record with the resolved prediction, outcome)."""
    gold = json.loads(meta["target_json"])
    pred = rec.get("prediction")
    if bool(stored_outcome) != (pred == gold):
        raise SystemExit(f"stored outcome of {meta['id']} is not exact match of its prediction")
    if arm == "off":
        return rec, stored_outcome
    try:
        fixed = date_resolve.repair(pred, meta["note_text"], meta["note_date"], arm)
    except (KeyError, TypeError, AttributeError):  # a malformed prediction stays as it is (and is not judgeable)
        fixed = pred
    return dict(rec, prediction=fixed, prediction_unresolved=pred), fixed == gold


def build_notes(run, arm=None):
    """Per-note outcomes, confidences and predictions of the chosen run, checked against the dataset files.

    arm (default: the --resolve setting) resolves relative dates in each prediction before its outcome is scored."""
    arm = RESOLVE if arm is None else arm
    d = STUDENT / run
    m = json.loads((d / "result.json").read_text())["val"]["metrics"]
    recs = {r["id"]: r for r in json.loads((d / "val-records.json").read_text())}
    meta = parquet("val")
    if set(m["ids"]) != set(meta) or set(recs) != set(meta) or len(m["ids"]) != len(meta):
        raise SystemExit("validation ids differ between result.json, val-records.json and val.parquet")
    notes = []
    for i, ident in enumerate(m["ids"]):
        if not same_conf(recs[ident]["confidence"], m["confidences"][i]):
            raise SystemExit(f"confidence mismatch for {ident}")
        group = "val_haiku" if "haiku" in meta[ident]["writer"] else "val_nemotron"
        rec, outcome = resolve_note(recs[ident], meta[ident], m["outcomes"][i], arm)
        notes.append(note_row(ident, "val", group, outcome, m["confidences"][i], rec, meta[ident]))
    ev = json.loads((d / "eval-test.json").read_text())
    for g in TEST_GROUPS:
        s = ev["splits"][g]
        mm = s["metrics"]
        recs = {r["id"]: r for r in s["records"]}
        meta = parquet(g)
        if set(mm["ids"]) != set(meta) or set(recs) != set(meta) or len(mm["ids"]) != len(meta):
            raise SystemExit(f"{g} ids differ between eval-test.json and {g}.parquet")
        for i, ident in enumerate(mm["ids"]):
            if not same_conf(recs[ident]["confidence"], mm["confidences"][i]):
                raise SystemExit(f"confidence mismatch for {ident}")
            rec, outcome = resolve_note(recs[ident], meta[ident], mm["outcomes"][i], arm)
            notes.append(note_row(ident, "test", g, outcome, mm["confidences"][i], rec, meta[ident]))
    val_ids = {n["id"] for n in notes if n["split"] == "val"}
    test_ids = {n["id"] for n in notes if n["split"] == "test"}
    if val_ids & test_ids or len(val_ids) + len(test_ids) != len(notes):
        raise SystemExit("validation and test notes overlap or repeat")
    return notes


def ledgers():
    oa = json.loads((JUDGES / "usage-openai.json").read_text())
    ts = json.loads((JUDGES / "usage-typesafe.json").read_text())
    return dict(openai=oa, typesafe=ts)


# ---- prepare ---------------------------------------------------------------------------------------------------


def tokens_per_char():
    """Decisions tokens per character of the JSON request body, over the cached benchmark requests."""
    rows = read_jsonl(JUDGES / "pairs-v1.jsonl")
    ratios = []
    for r in rows:
        events = [dict(type=e["type"], date=e["date"], precision=e.get("precision") or "DAY") for e in r["events"]]
        body = core.decisions_body(r["note_text"], r["note_date"], events)
        p = JUDGES / "cache/decisions" / f"{core.request_hash(body)}.json"
        if p.exists():
            u = json.loads(p.read_text())["usage"]
            ratios.append((u["input_tokens"] + u["output_tokens"]) / len(json.dumps(body, ensure_ascii=False)))
    return dict(requests=len(ratios), mean=statistics.fmean(ratios), max=max(ratios))


def cmd_prepare(_args):
    OUT.mkdir(parents=True, exist_ok=True)
    cands = candidates()
    prim = primary_run()
    chosen, why = choose_student(cands, prim)
    run = chosen["run"]
    if not (STUDENT / run / "eval-test.json").exists():
        raise SystemExit(f"{run} has no eval-test.json")
    notes = build_notes(run)
    texts = {}
    for split in ("val",) + TEST_GROUPS:
        texts.update({k: v["note_text"] for k, v in parquet(split).items()})
    policy = core.load_policy(core.POLICY)
    qset = policy["jev_question_set"]
    tpc = tokens_per_char()
    pairs = []
    est = {}
    for n in notes:
        if not n["judgeable"]:
            continue
        p = n["prediction"]
        events = [dict(type=e["type"], date=e["date"], precision=e.get("precision") or "DAY") for e in p["events"]]
        core.jev_body(texts[n["id"]], n["note_date"], events, qset)  # raises on anything the judge could not be asked
        body = core.decisions_body(texts[n["id"]], n["note_date"], events)
        est[n["id"]] = math.ceil(len(json.dumps(body, ensure_ascii=False)) * tpc["max"])
        pairs.append(dict(id=n["id"], note_text=texts[n["id"]], note_date=n["note_date"], entry_route=p["entry_route"],
                          events=events, split=n["split"], group=n["group"]))
    write_jsonl(PAIRS["jev"], pairs)
    val_order = sorted((x for x in pairs if x["split"] == "val"), key=lambda x: order_key(x["id"], DEC_SALT))
    test_order = sorted((x for x in pairs if x["split"] == "test"), key=lambda x: order_key(x["id"], DEC_SALT))
    plan_tokens = int(OPENAI_STEP_TOKENS * OPENAI_PLAN_SHARE)
    k = min(DEC_MAX_PER_SPLIT, len(val_order), len(test_order))
    while k > 0 and sum(est[x["id"]] for x in val_order[:k] + test_order[:k]) > plan_tokens:
        k -= 1
    subset = val_order[:k] + test_order[:k]
    write_jsonl(PAIRS["decisions"], subset)
    led = ledgers()
    oa_committed = led["openai"]["tokens"] + led["openai"]["reserved_tokens"]
    ts_committed_usd = (led["typesafe"]["tokens"] + led["typesafe"]["reserved_tokens"]) * core.TYPESAFE_USD_PER_TOKEN
    oa_limit = oa_committed + OPENAI_STEP_TOKENS
    ts_limit = round(ts_committed_usd + TYPESAFE_STEP_USD, 6)
    counts = {}
    for n in notes:
        c = counts.setdefault(n["group"], dict(notes=0, parsed=0, judgeable=0))
        c["notes"] += 1
        c["parsed"] += n["parsed"]
        c["judgeable"] += n["judgeable"]
    plan = dict(
        schema="scribe-v3-cascade-plan-v1",
        synthetic=True,
        not_for_clinical_use=True,
        written_utc=now(),
        resolver=resolver_record(),
        written_before_any_judge_answer=True,
        student=dict(chosen=run, rule="highest validation exact match; prefer the pre-registered primary of "
                     "compare-v1.json when it and the highest run lie within each other's Wilson 95% intervals; test "
                     "results are never read for the choice", primary=prim, why=why, candidates=cands),
        counts=counts,
        jev=dict(pairs=rel(PAIRS["jev"]), rows=len(pairs), question_set=qset,
                 note="every note whose prediction parsed; notes whose prediction did not parse go to a person and are not asked"),
        decisions=dict(pairs=rel(PAIRS["decisions"]), per_split=k, rows=len(subset),
                       val_groups={g: sum(x["group"] == g for x in subset) for g in ("val_nemotron", "val_haiku")},
                       test_groups={g: sum(x["group"] == g for x in subset) for g in TEST_GROUPS},
                       order=f"sha256('{DEC_SALT}|' + id) ascending, within validation and within the pooled test notes",
                       size_rule=f"largest K <= {DEC_MAX_PER_SPLIT} per split whose estimated tokens stay <= {plan_tokens} "
                                 f"({OPENAI_PLAN_SHARE:.0%} of the {OPENAI_STEP_TOKENS} cap)",
                       estimated_tokens=sum(est[x["id"]] for x in subset),
                       tokens_per_char=tpc,
                       estimate="ceil(characters of the JSON request body x the maximum tokens-per-character over the "
                                "cached benchmark Decisions requests)"),
        ledgers_before=dict(openai=led["openai"], typesafe=led["typesafe"], openai_committed=oa_committed,
                            typesafe_committed_usd=ts_committed_usd),
        limits=dict(max_tokens_openai=oa_limit, max_usd_typesafe=ts_limit,
                    meaning="run.py limits are cumulative ledger limits; these equal the committed amount before this "
                            f"step plus {OPENAI_STEP_TOKENS} OpenAI tokens and USD {TYPESAFE_STEP_USD:.2f} TypeSafe"),
        commands=dict(
            jev=f"scribe/.venv/bin/python scribe/judges/run.py --in {rel(PAIRS['jev'])} --out {rel(ANSWERS['jev'])} "
                f"--judges jev --max-usd-typesafe {ts_limit} --max-tokens-openai {oa_limit}",
            decisions=f"scribe/.venv/bin/python scribe/judges/run.py --in {rel(PAIRS['decisions'])} --out "
                      f"{rel(ANSWERS['decisions'])} --judges decisions --max-usd-typesafe {ts_limit} --max-tokens-openai {oa_limit}"),
        design=dict(alpha_pct=list(ALPHA_PCT), min_accepted=MIN_ACCEPTED, bootstrap=BOOT, seed=SEED, l2=L2),
    )
    save_json(PLAN, plan)
    log("prepare", f"scribe/.venv/bin/python scribe/v3/cascade.py --resolve \"{RESOLVE}\" prepare",
        inputs=[c["val_file"] for c in cands] + [rel(STUDENT / run / "eval-test.json"), rel(COMPARE), rel(PREREG),
                "data/scribe/v3/dataset/{val,test_nemotron,test_haiku}.parquet", rel(core.POLICY)],
        outputs=[rel(PLAN), rel(PAIRS["jev"]), rel(PAIRS["decisions"])],
        metrics=dict(student=run, jev_rows=len(pairs), decisions_rows=len(subset), decisions_per_split=k,
                     decisions_estimated_tokens=plan["decisions"]["estimated_tokens"], counts=counts,
                     openai_ledger_tokens_before=led["openai"]["tokens"], typesafe_ledger_usd_before=led["typesafe"].get("cost_usd")),
        cost_usd=0.0)
    print(json.dumps(dict(student=run, why=why, jev_rows=len(pairs), decisions_per_split=k,
                          decisions_estimated_tokens=plan["decisions"]["estimated_tokens"], limits=plan["limits"]), indent=1))


def cmd_record(args):
    """Log one finished run.py call (its printed summary was saved to a file) with the ledgers before and after."""
    plan = json.loads(PLAN.read_text())
    s = json.loads(Path(args.summary).read_text())
    led = ledgers()
    j = args.judge
    if j == "jev":
        cost = s["tokens_this_run"]["jev"] * core.TYPESAFE_USD_PER_TOKEN
    else:
        cost = 0.0  # Decisions is counted in tokens; the list-rate USD is in cascade-v1.json
    status = "ok" if not any(s["errors"].values()) else "partial"
    log(f"judge_{j}", plan["commands"][j], inputs=[plan[j]["pairs"]], outputs=[rel(ANSWERS[j]), rel(args.summary)],
        metrics=dict(rows=s["rows"], errors=s["errors"], stats=s["stats"], tokens_this_run=s["tokens_this_run"],
                     seconds=s["seconds"], ledger_after={"openai" if j == "decisions" else "typesafe": led["openai" if j == "decisions" else "typesafe"]}),
        cost_usd=cost, status=status)
    print(status, json.dumps(s["tokens_this_run"]))


# ---- analyse ---------------------------------------------------------------------------------------------------


def answers(judge):
    p = ANSWERS[judge]
    if not p.exists():
        return {}
    return {r["id"]: (r.get("judges") or {}).get(judge) for r in read_jsonl(p)}


def evaluate(notes, scores, threshold):
    """Coverage and error among accepted notes at a fixed threshold."""
    acc = [n for n, s in zip(notes, scores) if threshold is not None and s is not None and s >= threshold]
    wrong = sum(not n["outcome"] for n in acc)
    return dict(coverage=share(len(acc), len(notes)), error_among_accepted=share(wrong, len(acc)))


def boot_indices(n, label):
    rng = random.Random(f"{SEED}|{label}")
    return [[rng.randrange(n) for _ in range(n)] for _ in range(BOOT)]


def paired_boot(notes, acc_x, acc_b, idx):
    """Percentile 95 % intervals of coverage(x) - coverage(base) and error(x) - error(base) over paired resamples."""
    wrong = [not n["outcome"] for n in notes]
    dc, de, skipped = [], [], 0
    nn = len(notes)
    for ix in idx:
        ax = ab = wx = wb = 0
        for i in ix:
            if acc_x[i]:
                ax += 1
                wx += wrong[i]
            if acc_b[i]:
                ab += 1
                wb += wrong[i]
        dc.append((ax - ab) / nn)
        if ax and ab:
            de.append(wx / ax - wb / ab)
        else:
            skipped += 1
    out = dict(coverage_difference95=[r4(nearest_rank(dc, 0.025)), r4(nearest_rank(dc, 0.975))])
    out["error_difference95"] = [r4(nearest_rank(de, 0.025)), r4(nearest_rank(de, 0.975))] if de else None
    out["resamples"] = len(idx)
    out["resamples_without_error_difference"] = skipped
    return out


def signal_scores(notes, signal, models):
    if signal == "student":
        return [n["confidence"] if n["parsed"] and n["confidence"] is not None else None for n in notes]
    if signal in ("jev", "decisions"):
        return [n["features"].get(signal) for n in notes]
    return [logit(models[signal], n["features"]) if n["parsed"] else None for n in notes]


COMBOS = {"student+jev": ("student", "jev"), "student+jev+decisions": ("student", "jev", "decisions")}


def pipeline_bootstrap(val, test, test_ids):
    """Resample validation AND test notes, refit the logistic model and re-choose every threshold on the resampled
    validation notes, then measure pooled test coverage. Includes the noise of the threshold choice itself; a
    resample without a feasible threshold counts as coverage 0 (every note goes to a person)."""
    rng = random.Random(f"{SEED}|pipeline")
    sigs = ("student", "jev", "student+jev")
    diffs = {(s, a): [] for s in sigs[1:] for a in ALPHA_PCT}
    ediffs = {(s, a): [] for s in sigs[1:] for a in ALPHA_PCT}
    errs = {(s, a): [] for s in sigs for a in ALPHA_PCT}
    infeasible = {(s, a): 0 for s in sigs for a in ALPHA_PCT}
    for _ in range(BOOT):
        vb = [val[rng.randrange(len(val))] for _ in range(len(val))]
        tb = [test[rng.randrange(len(test))] for _ in range(len(test))]
        models = {"student+jev": fit_logistic(vb, COMBOS["student+jev"], test_ids)}
        cov, err = {}, {}
        for s in sigs:
            vs, ts = signal_scores(vb, s, models), signal_scores(tb, s, models)
            for a in ALPHA_PCT:
                th = select_threshold(vb, vs, a, test_ids)["threshold"]
                if th is None:
                    infeasible[(s, a)] += 1
                    cov[(s, a)], err[(s, a)] = 0.0, None
                else:
                    acc = [n for n, x in zip(tb, ts) if x is not None and x >= th]
                    cov[(s, a)] = len(acc) / len(tb)
                    err[(s, a)] = sum(not n["outcome"] for n in acc) / len(acc) if acc else None
                if err[(s, a)] is not None:
                    errs[(s, a)].append(err[(s, a)])
        for s in sigs[1:]:
            for a in ALPHA_PCT:
                diffs[(s, a)].append(cov[(s, a)] - cov[("student", a)])
                if err[(s, a)] is not None and err[("student", a)] is not None:
                    ediffs[(s, a)].append(err[(s, a)] - err[("student", a)])
    out = {}
    for s in sigs:
        for a in ALPHA_PCT:
            e = errs[(s, a)]
            rec = dict(test_error_among_accepted95=[r4(nearest_rank(e, 0.025)), r4(nearest_rank(e, 0.975))] if e else None,
                       resamples_with_no_threshold=infeasible[(s, a)])
            if s != "student":
                d, ed = diffs[(s, a)], ediffs[(s, a)]
                rec.update(coverage_difference_vs_student95=[r4(nearest_rank(d, 0.025)), r4(nearest_rank(d, 0.975))],
                           mean_coverage_difference=r4(statistics.fmean(d)),
                           error_difference_vs_student95=[r4(nearest_rank(ed, 0.025)), r4(nearest_rank(ed, 0.975))] if ed else None,
                           resamples_with_error_difference=len(ed))
            out.setdefault(s, {})[f"{a}pct"] = rec
    return dict(resamples=BOOT, seed=f"{SEED}|pipeline", by_signal=out,
                note="validation and test resampled together; logistic fit and thresholds re-chosen each time; pooled test; "
                     "a resample without a feasible threshold counts as coverage 0 and has no error")


def cost_block(rows, judge):
    rs = [r for r in rows if r and not r.get("error")]
    distinct = {r["request_sha256"]: r for r in rs}
    if not distinct:
        return None
    if judge == "jev":
        toks = [r["usage"]["input_tokens"] + r["usage"]["output_tokens"] for r in distinct.values()]
        usd_per_tok = JEV_USD_PER_MTOK / 1e6
        price = "USD 0.042 per million tokens (input + output), owner's price in scribe/judges/core.py"
    else:
        toks = [r["usage"]["input_tokens"] for r in distinct.values()]
        usd_per_tok = DEC_USD_PER_MTOK_INPUT / 1e6
        price = ("USD 0.10 per million input tokens, output not charged: the Decisions guide list rate as read by an "
                 "earlier step (scribe/judges/RESULTS.md); not a bill")
    lat = [r["latency_s"] for r in distinct.values()]
    per = statistics.fmean(toks)
    return dict(
        distinct_requests=len(distinct),
        paid_in_this_step=sum(not r.get("cached") for r in distinct.values()),
        tokens_counted=sum(toks),
        output_tokens=sum(r["usage"]["output_tokens"] for r in distinct.values()),
        tokens_per_note=r4(per),
        tokens_per_1000_notes=round(per * 1000),
        usd_per_1000_notes=r4(per * 1000 * usd_per_tok),
        price=price,
        latency_s_p50=nearest_rank(lat, 0.5),
        latency_s_p95=nearest_rank(lat, 0.95),
        latency_note=f"wall time of single requests while up to {12 if judge == 'jev' else 8} were in flight; nearest-rank percentiles",
    )


def cmd_analyse(_args):
    plan = json.loads(PLAN.read_text())
    if (plan.get("resolver") or dict(arm="off"))["arm"] != RESOLVE:
        raise SystemExit(f"{rel(PLAN)} was prepared with another resolver arm than --resolve {RESOLVE}")
    run = plan["student"]["chosen"]
    notes = build_notes(run)
    jev, dec = answers("jev"), answers("decisions")
    dec_ids = {r["id"] for r in read_jsonl(PAIRS["decisions"])}
    for n in notes:
        n["features"] = dict(
            student=student_feature(n["confidence"]) if n["parsed"] and n["confidence"] is not None else None,
            jev=judge_score(jev.get(n["id"])) if n["judgeable"] else None,
            decisions=judge_score(dec.get(n["id"])) if n["id"] in dec_ids else None)
        n["in_decisions_subset"] = n["id"] in dec_ids
    val = [n for n in notes if n["split"] == "val"]
    test = [n for n in notes if n["split"] == "test"]
    test_ids = {n["id"] for n in test}
    if {n["id"] for n in val} & test_ids:
        raise AssertionError("validation and test overlap")

    # all notes: student, jev, student+jev (fit and thresholds on validation only)
    models = {"student+jev": fit_logistic(val, COMBOS["student+jev"], test_ids)}
    full_sigs = ("student", "jev", "student+jev")
    thresholds = {}
    for s in full_sigs:
        vs = signal_scores(val, s, models)
        for a in ALPHA_PCT:
            thresholds[(s, a)] = select_threshold(val, vs, a, test_ids)

    # Decisions subset: Decisions alone, three-way, and student alone re-thresholded on the subset
    have_dec = sum(n["features"]["decisions"] is not None for n in notes)
    vsub = [n for n in val if n["in_decisions_subset"]]
    tsub = [n for n in test if n["in_decisions_subset"]]
    sub_sigs = ()
    if have_dec and vsub and tsub:
        models["student+jev+decisions"] = fit_logistic(vsub, COMBOS["student+jev+decisions"], test_ids)
        sub_sigs = ("student@subset", "decisions", "student+jev+decisions")
        for s in sub_sigs:
            base = "student" if s == "student@subset" else s
            vs = signal_scores(vsub, base, models)
            for a in ALPHA_PCT:
                thresholds[(s, a)] = select_threshold(vsub, vs, a, test_ids)

    def scores_for(sig, ns):
        return signal_scores(ns, "student" if sig == "student@subset" else sig, models)

    # test report
    groups = {g: [n for n in test if n["group"] == g] for g in TEST_GROUPS}
    groups["test_pooled"] = test
    report = dict(all_notes={}, decisions_subset={})
    for section, sigs, base_list, sets in (
        ("all_notes", full_sigs, ("student",), groups),
        ("decisions_subset", full_sigs + sub_sigs if sub_sigs else (), ("student", "student@subset"),
         {g: [n for n in tsub if n["group"] == g] for g in TEST_GROUPS} | {"test_pooled": tsub}),
    ):
        for gname, ns in sets.items():
            if not ns or not sigs:
                continue
            idx = boot_indices(len(ns), f"{section}|{gname}")
            acc = {}
            for s in sigs:
                sc = scores_for(s, ns)
                for a in ALPHA_PCT:
                    th = thresholds[(s, a)]["threshold"]
                    acc[(s, a)] = [th is not None and x is not None and x >= th for x in sc]
            outs = [n["outcome"] for n in ns]
            sc_all = {s: scores_for(s, ns) for s in sigs}
            boot_aurc = {s: [aurc([outs[i] for i in ix], [sc_all[s][i] for i in ix]) for ix in idx] for s in sigs}
            for s in sigs:
                sc = sc_all[s]
                block = report[section].setdefault(s, {})
                block.setdefault("aurc", {})[gname] = r4(aurc(outs, sc))
                if s != "student":
                    d = [x - y for x, y in zip(boot_aurc[s], boot_aurc["student"])]
                    block.setdefault("aurc_difference_vs_student", {})[gname] = dict(
                        difference=r4(aurc(outs, sc) - aurc(outs, sc_all["student"])),
                        paired_bootstrap95=[r4(nearest_rank(d, 0.025)), r4(nearest_rank(d, 0.975))])
                for a in ALPHA_PCT:
                    th = thresholds[(s, a)]
                    e = dict(evaluate(ns, sc, th["threshold"]), threshold=th["threshold"])
                    if th["threshold"] is None:
                        e["no_threshold"] = th["reason"]
                    for b in base_list:
                        if b == s or (section == "all_notes" and b != "student"):
                            continue
                        if th["threshold"] is None or thresholds[(b, a)]["threshold"] is None:
                            e[f"vs_{b}"] = None
                            continue
                        diff = (sum(acc[(s, a)]) - sum(acc[(b, a)])) / len(ns)
                        e[f"vs_{b}"] = dict(coverage_difference=r4(diff), **paired_boot(ns, acc[(s, a)], acc[(b, a)], idx))
                    block.setdefault(f"{a}pct", {})[gname] = e
        for gname, ns in sets.items():
            if ns:
                outs = [n["outcome"] for n in ns]
                report[section].setdefault("_reference", {})[gname] = dict(
                    notes=len(ns), exact_match=share(sum(outs), len(outs)),
                    aurc_random_order=r4(1 - sum(outs) / len(outs)), aurc_best_possible_order=r4(aurc_optimal(outs)))

    validation = {}
    for (s, a), th in thresholds.items():
        validation.setdefault(s, {})[f"{a}pct"] = {k: (r4(v) if isinstance(v, float) and k != "threshold" else v)
                                                   for k, v in th.items()}
    pipe = pipeline_bootstrap(val, test, test_ids)

    # judges: answered, errors, cost, latency
    judge_stats = {}
    for j, ans, asked in (("jev", jev, [n for n in notes if n["judgeable"]]), ("decisions", dec, [n for n in notes if n["in_decisions_subset"]])):
        rows = [ans.get(n["id"]) for n in asked]
        errs = [r.get("error") for r in rows if r and r.get("error")]
        judge_stats[j] = dict(
            asked=len(asked), answered=sum(1 for r in rows if r and not r.get("error")), missing=sum(r is None for r in rows),
            errors=len(errs), error_kinds=sorted({e.split(":")[0] for e in errs}),
            route_disagrees_with_student=sum(1 for r in rows if r and not r.get("error") and r.get("route_choice") != r.get("claimed_route")),
            question_set=sorted({r.get("question_set") for r in rows if r and not r.get("error")}),
            cost=cost_block(rows, j))
    led = ledgers()
    before = plan["ledgers_before"]
    spent = dict(
        openai_tokens_ledger_difference=led["openai"]["tokens"] - before["openai"]["tokens"],
        openai_committed_difference=(led["openai"]["tokens"] + led["openai"]["reserved_tokens"]) - before["openai_committed"],
        typesafe_tokens_ledger_difference=led["typesafe"]["tokens"] - before["typesafe"]["tokens"],
        typesafe_usd_ledger_difference=r4((led["typesafe"]["tokens"] - before["typesafe"]["tokens"]) * core.TYPESAFE_USD_PER_TOKEN),
        note="ledger differences include any other process that used the same shared ledgers during this step")
    if judge_stats["decisions"]["cost"]:
        spent["decisions_usd_list_rate_this_step"] = r4(spent["openai_tokens_ledger_difference"] * DEC_USD_PER_MTOK_INPUT / 1e6)

    def logistic_record(m):
        return dict(m, fitted_on="validation notes only (asserted)",
                    feature_definitions=dict(student="-ln(-mean token log-probability)", jev="Jev judge score",
                                             decisions="Decisions judge score"),
                    note="weights are on standardised features (mean/sd of the fitting notes); the cascade ranks by the linear predictor")

    counts = {}
    for n in notes:
        c = counts.setdefault(n["group"], dict(notes=0, exact_match=0, parsed=0, judgeable=0, jev_score=0, decisions_score=0))
        c["notes"] += 1
        c["exact_match"] += n["outcome"]
        c["parsed"] += n["parsed"]
        c["judgeable"] += n["judgeable"]
        c["jev_score"] += n["features"]["jev"] is not None
        c["decisions_score"] += n["features"]["decisions"] is not None

    result = dict(
        schema="scribe-v3-cascade-v1",
        synthetic=True,
        not_for_clinical_use=True,
        generated_utc=now(),
        resolver=resolver_record(),
        question="At the same target error among notes pre-filled for one-click confirmation, does adding an independent judge let more notes be pre-filled than the student's own confidence?",
        student=plan["student"],
        inputs={rel(p): sha256_file(p) for p in [STUDENT / run / "result.json", STUDENT / run / "val-records.json",
                                                   STUDENT / run / "eval-test.json", PLAN, PAIRS["jev"], PAIRS["decisions"],
                                                   ANSWERS["jev"], ANSWERS["decisions"], core.POLICY] if p.exists()},
        design=dict(
            targets_pct=list(ALPHA_PCT),
            threshold_rule=(f"on validation notes only: accept a note when its score >= t; t is the value with the largest "
                            f"validation coverage whose observed error among accepted notes is <= the target, with at least "
                            f"{MIN_ACCEPTED} accepted notes; otherwise no threshold is set"),
            empirical_not_guaranteed="the thresholds are chosen on 310 synthetic validation notes (the subset ones on fewer); the error on new notes can be higher",
            coverage_denominator="every note in the set, including notes whose prediction did not parse (they always go to a person)",
            signals=dict(
                student="mean token log-probability of the student's answer (higher = more confident)",
                jev="judge score from Jev: min over predicted events of P(event stated) x (1 - P(unlisted event)); 0 when Jev's route choice differs from the student's route",
                decisions="the same judge score from OpenAI Decisions (question set v1), on the subset only",
                **{"student+jev": "ridge logistic regression of exact match on (student, jev), fitted on validation notes",
                   "student+jev+decisions": "ridge logistic regression on (student, jev, decisions), fitted on the validation part of the subset",
                   "student@subset": "student confidence alone with its threshold re-chosen on the validation part of the subset (like-for-like control)"}),
            leak_guard="assert_validation_only() raises before any fit or threshold sees a note whose split is not 'val' or whose id is a test id; unit-tested in scribe/v3/tests/test_cascade.py",
            bootstrap=f"paired percentile bootstrap over test notes, {BOOT} resamples, seed '{SEED}|<section>|<set>'; thresholds held fixed, so it omits the noise of choosing them (see pipeline_bootstrap)",
            jev_question_set=plan["jev"]["question_set"],
            decisions_subset=plan["decisions"],
            unparsed="notes whose prediction did not parse are not sent to a judge and are never accepted by any signal",
        ),
        counts=counts,
        logistic={k: logistic_record(m) for k, m in models.items()},
        validation_in_sample=validation,
        test=report,
        pipeline_bootstrap=pipe,
        judges=judge_stats,
        ledgers=dict(before=before, after=led, this_step=spent,
                     caps=dict(openai_tokens=OPENAI_STEP_TOKENS, typesafe_usd=TYPESAFE_STEP_USD, limits_passed=plan["limits"])),
    )
    result["verdict"] = verdict(result)
    save_json(RESULT, result)
    write_jsonl(NOTES, [dict(id=n["id"], split=n["split"], group=n["group"], kind=n["kind"], outcome=n["outcome"],
                             parsed=n["parsed"], judgeable=n["judgeable"], confidence=n["confidence"],
                             jev_score=n["features"]["jev"], decisions_score=n["features"]["decisions"],
                             in_decisions_subset=n["in_decisions_subset"],
                             combo_student_jev_logit=r4(logit(models["student+jev"], n["features"])) if n["parsed"] else None)
                        for n in notes])
    RESULTS_MD.write_text(render_md(result))
    log("analyse", f"scribe/.venv/bin/python scribe/v3/cascade.py --resolve \"{RESOLVE}\" analyse",
        inputs=list(result["inputs"]), outputs=[rel(RESULT), rel(NOTES), rel(RESULTS_MD)],
        metrics=dict(verdict=result["verdict"]["lines"], judges={j: {k: v for k, v in s.items() if k != "cost"} for j, s in judge_stats.items()}),
        cost_usd=0.0)
    print("\n".join(result["verdict"]["lines"]))


# ---- plain-English verdict and RESULTS.md ----------------------------------------------------------------------


def pct(x):
    return "n/a" if x is None else f"{100 * x:.1f}%"


def pp(x):
    return "n/a" if x is None else f"{100 * x:+.1f} points"


def ci_pp(x):
    return "n/a" if not x else f"{100 * x[0]:+.1f} to {100 * x[1]:+.1f} points"


def frac_s(sh):
    return f"{sh['numerator']}/{sh['denominator']} ({pct(sh['share'])})" if sh["denominator"] else f"0/{sh['denominator']}"


def noise_words(ci):
    if not ci:
        return "n/a"
    if ci[1] < 0:
        return "lower, outside noise"
    if ci[0] > 0:
        return "higher, outside noise"
    return "within noise"


def includes0(x):
    return bool(x) and x[0] <= 0 <= x[1]


NAMES = {"student": "student confidence alone", "jev": "Jev alone", "student+jev": "student + Jev (logistic)",
         "decisions": "Decisions alone", "student+jev+decisions": "student + Jev + Decisions (logistic)",
         "student@subset": "student alone, threshold from the subset"}


def verdict(res):
    """Plain sentences built only from numbers in the result; the wording branches on the intervals."""
    lines = []
    allv = res["test"]["all_notes"]
    pipe = res["pipeline_bootstrap"]["by_signal"]
    for a in ALPHA_PCT:
        k = f"{a}pct"
        e = {s: allv[s][k]["test_pooled"] for s in ("student", "jev", "student+jev")}
        if any(x["threshold"] is None for x in e.values()):
            for s, x in e.items():
                if x["threshold"] is None:
                    lines.append(f"{a}% target: {NAMES[s]} has no validation threshold ({x['no_threshold']}).")
            continue
        cov = {s: x["coverage"] for s, x in e.items()}
        err = {s: x["error_among_accepted"] for s, x in e.items()}
        tci = {s: e[s]["vs_student"]["coverage_difference95"] for s in ("jev", "student+jev")}
        pci = {s: pipe[s][k]["coverage_difference_vs_student95"] for s in ("jev", "student+jev")}
        eci = {s: e[s]["vs_student"]["error_difference95"] for s in ("jev", "student+jev")}
        peci = {s: pipe[s][k]["error_difference_vs_student95"] for s in ("jev", "student+jev")}
        if all(includes0(tci[s]) and includes0(pci[s]) for s in tci):
            cov_word = "did not let measurably more notes be pre-filled for one-click confirmation: every coverage difference is within noise"
        elif all(includes0(pci[s]) for s in pci) and any(tci[s][0] > 0 for s in tci):
            cov_word = ("let more notes be pre-filled for one-click confirmation on these test notes (outside test-sampling noise), but the gain is within "
                        "noise once the thresholds are re-chosen on resampled validation notes")
        elif any(pci[s][0] > 0 for s in pci):
            cov_word = "let more notes be pre-filled for one-click confirmation, outside noise even when the thresholds are re-chosen"
        else:
            cov_word = "did not let more notes be pre-filled for one-click confirmation"
        lines.append(
            f"{a}% target, all 700 test notes: adding Jev {cov_word}. Pre-filled for one-click confirmation: {NAMES['student']} {frac_s(cov['student'])}, "
            f"Jev alone {frac_s(cov['jev'])}, student + Jev {frac_s(cov['student+jev'])}. Coverage difference vs the student: "
            f"Jev {pp(e['jev']['vs_student']['coverage_difference'])} (test bootstrap 95% {ci_pp(tci['jev'])}; with threshold re-choice "
            f"{ci_pp(pci['jev'])}), student + Jev {pp(e['student+jev']['vs_student']['coverage_difference'])} ({ci_pp(tci['student+jev'])}; "
            f"{ci_pp(pci['student+jev'])}).")
        held = [NAMES[s] for s in e if err[s]["share"] is not None and err[s]["share"] <= a / 100]
        missed = [NAMES[s] for s in e if err[s]["share"] is not None and err[s]["share"] > a / 100]
        hk = {s: allv[s][k]["test_haiku"]["error_among_accepted"] for s in e}
        nk = {s: allv[s][k]["test_nemotron"]["error_among_accepted"] for s in e}
        lines.append(
            f"{a}% target, error among the pre-filled notes (pooled test): student {frac_s(err['student'])}, Jev "
            f"{frac_s(err['jev'])}, student + Jev {frac_s(err['student+jev'])}. Difference vs the student, Jev: {ci_pp(eci['jev'])} "
            f"on these test notes ({noise_words(eci['jev'])}), {ci_pp(peci['jev'])} with threshold re-choice "
            f"({noise_words(peci['jev'])}); student + Jev: {ci_pp(eci['student+jev'])} ({noise_words(eci['student+jev'])}), "
            f"{ci_pp(peci['student+jev'])} ({noise_words(peci['student+jev'])}). The observed pooled test error was at or below the target for: {', '.join(held) or 'none'}; above it "
            f"for: {', '.join(missed) or 'none'}. Haiku-written test notes: student {frac_s(hk['student'])}, Jev "
            f"{frac_s(hk['jev'])}, student + Jev {frac_s(hk['student+jev'])} wrong among pre-filled; Nemotron-written: "
            f"{frac_s(nk['student'])}, {frac_s(nk['jev'])}, {frac_s(nk['student+jev'])}.")
    au = {s: allv[s]["aurc"]["test_pooled"] for s in ("student", "jev", "student+jev")}
    ad = {s: allv[s]["aurc_difference_vs_student"]["test_pooled"] for s in ("jev", "student+jev")}
    ref = res["test"]["all_notes"]["_reference"]["test_pooled"]
    lines.append(
        f"Ranking over all coverage levels (area under the risk-coverage curve, pooled test, lower is better): student "
        f"{au['student']}, Jev {au['jev']} (difference {ad['jev']['difference']:+.4f}, paired bootstrap 95% "
        f"{ad['jev']['paired_bootstrap95'][0]:+.4f} to {ad['jev']['paired_bootstrap95'][1]:+.4f}), student + Jev {au['student+jev']} "
        f"({ad['student+jev']['difference']:+.4f}; {ad['student+jev']['paired_bootstrap95'][0]:+.4f} to "
        f"{ad['student+jev']['paired_bootstrap95'][1]:+.4f}); random order {ref['aurc_random_order']}, best possible order "
        f"{ref['aurc_best_possible_order']}.")
    sub = res["test"]["decisions_subset"]
    if sub.get("decisions"):
        n_sub = sub["_reference"]["test_pooled"]["notes"]
        parts = []
        for a in ALPHA_PCT:
            k = f"{a}pct"
            d, d3, sj = sub["decisions"][k]["test_pooled"], sub["student+jev+decisions"][k]["test_pooled"], sub["student+jev"][k]["test_pooled"]
            s0 = sub["student"][k]["test_pooled"]
            dv = d.get("vs_student")
            parts.append(
                f"at {a}% Decisions alone {frac_s(d['coverage'])} vs student {frac_s(s0['coverage'])}"
                + (f" (difference {ci_pp(dv['coverage_difference95'])})" if dv else "")
                + f", three-way {frac_s(d3['coverage'])} vs student + Jev {frac_s(sj['coverage'])}")
        lines.append(f"Decisions, on the {n_sub} hash-chosen test notes of the subset (thresholds from "
                     f"{res['design']['decisions_subset']['per_split']} validation notes): " + "; ".join(parts) + ". AURC there: student "
                     f"{sub['student']['aurc']['test_pooled']}, Decisions {sub['decisions']['aurc']['test_pooled']}, student + Jev "
                     f"{sub['student+jev']['aurc']['test_pooled']}, three-way {sub['student+jev+decisions']['aurc']['test_pooled']}.")
    for j, st in res["judges"].items():
        c = st["cost"]
        if c:
            lines.append(f"{j}: {st['answered']}/{st['asked']} notes answered, {st['errors']} errors, USD {c['usd_per_1000_notes']} per "
                         f"1,000 notes ({c['tokens_per_note']} tokens per note), latency p50 {c['latency_s_p50']} s, p95 {c['latency_s_p95']} s.")
    return dict(lines=lines, computed_by="scribe/v3/cascade.py verdict() from the numbers in this file")


def render_md(res):
    s = res["student"]
    chosen = next(c for c in s["candidates"] if c["run"] == s["chosen"])
    d = res["design"]
    L = ["# Cascade at inference: does a judge let more notes be pre-filled for one-click confirmation?\n",
         f"Generated by `scribe/v3/cascade.py --resolve \"{RESOLVE}\" analyse`; every number is in `{rel(RESULT)}`. All notes are "
         "SYNTHETIC (simulated pathways, model-written notes). Nothing here is for clinical use or shows patient benefit, and a "
         "judge is a language model that gives a second opinion, not the truth.\n",
         "The idea: the student proposes events and a person confirms every one. A note may be pre-filled for one-click "
         "confirmation only if the error among pre-filled notes stays at a target; every other note needs editing. The thresholds below were chosen on validation notes and are empirical, not "
         "guarantees: on test they can, and here sometimes did, give a higher error than the target.\n",
         "## Answer\n"]
    L += [f"- {x}" for x in res["verdict"]["lines"]]
    L.append("")
    L.append("## How it was measured\n")
    cand = "; ".join(f"{c['run']} {c['k']}/{c['n']}" for c in s["candidates"])
    L.append(f"- Student: **{s['chosen']}**, validation exact match {chosen['k']}/{chosen['n']}. {s['why'][0].upper() + s['why'][1:]}. "
             f"Candidates on validation: {cand}. Test results played no part in the choice.")
    L.append(f"- Signals: student confidence = {d['signals']['student']}; Jev score = {d['signals']['jev']} (question set "
             f"{d['jev_question_set']}); student + Jev = {d['signals']['student+jev']}.")
    ds = d["decisions_subset"]
    L.append(f"- Decisions: {ds['per_split']} validation and {ds['per_split']} test notes, order {ds['order']}; size rule: {ds['size_rule']}.")
    L.append(f"- Threshold: {d['threshold_rule']}.")
    L.append(f"- {d['unparsed'][0].upper() + d['unparsed'][1:]}; coverage counts them in its denominator. Leak guard: {d['leak_guard']}.")
    L.append(f"- Intervals: Wilson 95% for shares; {d['bootstrap']}. The pipeline bootstrap resamples validation and test notes "
             "together and re-chooses thresholds each time.\n")
    L.append("## Test results, all 700 notes\n")
    L.append("| target | signal | set | pre-filled for one-click confirmation | error among pre-filled (Wilson 95%) | coverage vs student (95%) | error vs student (95%) |")
    L.append("|---|---|---|---|---|---|---|")
    for a in ALPHA_PCT:
        for sig in ("student", "jev", "student+jev"):
            for g in ("test_nemotron", "test_haiku", "test_pooled"):
                e = res["test"]["all_notes"][sig][f"{a}pct"][g]
                if e["threshold"] is None:
                    L.append(f"| {a}% | {sig} | {g} | no threshold | | | |")
                    continue
                r = e["error_among_accepted"]
                err = f"{frac_s(r)}; {pct(r['wilson95'][0])} to {pct(r['wilson95'][1])}" if r["denominator"] else "none pre-filled"
                v = e.get("vs_student")
                L.append(f"| {a}% | {sig} | {g} | {frac_s(e['coverage'])} | {err} | "
                         f"{(pp(v['coverage_difference']) + ' (' + ci_pp(v['coverage_difference95']) + ')') if v else '-'} | "
                         f"{ci_pp(v['error_difference95']) if v else '-'} |")
    L.append("")
    L.append("Pipeline bootstrap (pooled test, thresholds and fit re-chosen on resampled validation notes):\n")
    L.append("| target | signal | coverage vs student (95%) | error vs student (95%) | test error among pre-filled (95%) |")
    L.append("|---|---|---|---|---|")
    for a in ALPHA_PCT:
        for sig in ("student", "jev", "student+jev"):
            p = res["pipeline_bootstrap"]["by_signal"][sig][f"{a}pct"]
            L.append(f"| {a}% | {sig} | {ci_pp(p.get('coverage_difference_vs_student95')) if sig != 'student' else '-'} | "
                     f"{ci_pp(p.get('error_difference_vs_student95')) if sig != 'student' else '-'} | "
                     f"{pct(p['test_error_among_accepted95'][0])} to {pct(p['test_error_among_accepted95'][1])} |")
    L.append("")
    sub = res["test"]["decisions_subset"]
    if sub.get("decisions"):
        L.append(f"## Decisions subset ({sub['_reference']['test_pooled']['notes']} test notes, pooled)\n")
        L.append("| target | signal | pre-filled for one-click confirmation | error among pre-filled | coverage vs student (95%) | AURC |")
        L.append("|---|---|---|---|---|---|")
        for a in ALPHA_PCT:
            for sig in ("student", "student@subset", "jev", "student+jev", "decisions", "student+jev+decisions"):
                e = sub[sig][f"{a}pct"]["test_pooled"]
                if e["threshold"] is None:
                    L.append(f"| {a}% | {sig} | no threshold: {e['no_threshold']} | | | {sub[sig]['aurc']['test_pooled']} |")
                    continue
                v = e.get("vs_student")
                L.append(f"| {a}% | {sig} | {frac_s(e['coverage'])} | {frac_s(e['error_among_accepted'])} | "
                         f"{(pp(v['coverage_difference']) + ' (' + ci_pp(v['coverage_difference95']) + ')') if v else '-'} | "
                         f"{sub[sig]['aurc']['test_pooled']} |")
        L.append("")
        L.append("`student@subset` re-chooses the student's threshold on the same validation subset as Decisions (like-for-like).\n")
    L.append("## Validation thresholds (in-sample)\n")
    L.append("| signal | target | threshold | accepted / validation notes | wrong |")
    L.append("|---|---|---|---|---|")
    for sig, blk in res["validation_in_sample"].items():
        for k, th in blk.items():
            if th.get("threshold") is None:
                L.append(f"| {sig} | {k} | none: {th['reason']} | | |")
            else:
                L.append(f"| {sig} | {k} | {th['threshold']:.6g} | {th['accepted']}/{th['n']} | {th['wrong']} |")
    L.append("")
    L.append("## Ranking on test (area under the risk-coverage curve, lower is better)\n")
    ref = res["test"]["all_notes"]["_reference"]
    gs = ["test_nemotron", "test_haiku", "test_pooled"]
    L.append("| signal | " + " | ".join(gs) + " | difference vs student, pooled (95%) |")
    L.append("|---|---|---|---|---|")
    for sig in ("student", "jev", "student+jev"):
        blk = res["test"]["all_notes"][sig]
        dd = blk.get("aurc_difference_vs_student", {}).get("test_pooled")
        L.append(f"| {sig} | " + " | ".join(str(blk["aurc"][g]) for g in gs) + " | "
                 + (f"{dd['difference']:+.4f} ({dd['paired_bootstrap95'][0]:+.4f} to {dd['paired_bootstrap95'][1]:+.4f})" if dd else "-") + " |")
    L.append("| random order | " + " | ".join(str(ref[g]["aurc_random_order"]) for g in gs) + " | |")
    L.append("| best possible order | " + " | ".join(str(ref[g]["aurc_best_possible_order"]) for g in gs) + " | |")
    L.append("")
    L.append("## Cost and latency (measured in this step)\n")
    L.append("| judge | asked | answered | errors | tokens per note | USD per 1,000 notes | latency p50 s | latency p95 s |")
    L.append("|---|---|---|---|---|---|---|---|")
    for j, st in res["judges"].items():
        c = st["cost"] or {}
        L.append(f"| {j} | {st['asked']} | {st['answered']} | {st['errors']} | {c.get('tokens_per_note')} | {c.get('usd_per_1000_notes')} | "
                 f"{c.get('latency_s_p50')} | {c.get('latency_s_p95')} |")
    L.append("")
    for j, st in res["judges"].items():
        if st["cost"]:
            L.append(f"- {j}: {st['cost']['price']}; {st['cost']['latency_note']}.")
    sp = res["ledgers"]["this_step"]
    L.append(f"- Spent in this step (shared ledgers): OpenAI {sp['openai_tokens_ledger_difference']} tokens (cap "
             f"{res['ledgers']['caps']['openai_tokens']}); TypeSafe {sp['typesafe_tokens_ledger_difference']} tokens = USD "
             f"{sp['typesafe_usd_ledger_difference']} (cap USD {res['ledgers']['caps']['typesafe_usd']:.2f}).\n")
    L.append("## Limits\n")
    L.append("- Synthetic notes with model-written labels; the outcome is exact match of the whole answer, and the person who reviews is not modelled.")
    L.append("- One student and 310 validation notes (250 Nemotron-written, 60 Haiku-written); the test mix is 500 and 200, so the "
             "pooled test mix differs from validation. The thresholds were chosen in-sample on validation.")
    L.append("- The Decisions part rests on a small subset, and its thresholds on even fewer validation notes.")
    return "\n".join(L) + "\n"


def cmd_render(_args):
    """Rebuild the plain-English verdict and RESULTS.md from the stored result file only: no judge request, no rescoring.
    The question text is refreshed from the current wording; every number is read from the stored result."""
    result = json.loads(RESULT.read_text())
    result["question"] = ("At the same target error among notes pre-filled for one-click confirmation, does adding an "
                          "independent judge let more notes be pre-filled than the student's own confidence?")
    before = result.get("verdict", {}).get("lines")
    result["verdict"] = verdict(result)
    save_json(RESULT, result)
    RESULTS_MD.write_text(render_md(result))
    log("render", f"scribe/.venv/bin/python scribe/v3/cascade.py --resolve \"{RESOLVE}\" render", inputs=[rel(RESULT)],
        outputs=[rel(RESULT), rel(RESULTS_MD)], metrics=dict(verdict_lines=len(result["verdict"]["lines"]),
                                                             verdict_changed=before != result["verdict"]["lines"]), cost_usd=0.0)
    print("\n".join(result["verdict"]["lines"]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("prepare")
    r = sub.add_parser("record")
    r.add_argument("--judge", choices=("jev", "decisions"), required=True)
    r.add_argument("--summary", required=True)
    sub.add_parser("analyse")
    sub.add_parser("render")
    ap.add_argument("--resolve", choices=RESOLVE_ARMS, default="A'",
                    help="relative-date resolver arm applied before scoring (scribe/v3/resolve.py); off = recorded v1 analysis")
    a = ap.parse_args()
    use_resolver(a.resolve)
    dict(prepare=cmd_prepare, record=cmd_record, analyse=cmd_analyse, render=cmd_render)[a.cmd](a)


if __name__ == "__main__":
    main()
