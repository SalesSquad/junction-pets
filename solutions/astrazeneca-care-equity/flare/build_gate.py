"""Comparability gate, final step: FLARE result + plain-Python central reference -> data/flare/gate-v1.json.

SYNTHETIC data only. Usage (from the solution folder):
  flare/.venv/bin/python flare/build_gate.py

1. Central reference in plain Python, from paths independent of the FLARE site code where they exist:
   - referral to treatment from the central pipeline's data/eventlog/sample-intervals.parquet
     (diagnostic + treatment interval of complete episodes), not from the raw events the sites read;
   - scribe statistics pooled from data/flare/gate-sites/ and cross-checked against the stored
     runs/diagnose/notes-*.jsonl and intervals-*.json files.
2. Equivalence of FLARE (data/flare/fedstats-gate-p12.json) against that reference: counts equal, mean and SD
   within 1e-6, share within 42 days equal, suppressed sets identical.
3. The gate rule (flare/gate.py) per county x scribe arm. Missed share comes from FLARE; median bias is
   computed here in plain Python (FLARE-ready, not run in FLARE).
4. A real-data chip from the Syöpä 2024 stage-completeness figures (areas only).
If the FLARE output is missing, every column is computed here and labelled "FLARE-ready, not run in FLARE".
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import pyarrow.parquet as pq  # noqa: E402

from gate import (ARMS, BIAS_LIMIT_DAYS, COUNTIES, MIN_COUNT, MISSED_LIMIT, RTT_EDGE_DAYS, RTT_THRESHOLD_DAYS,  # noqa: E402
                  RULE_LABEL, THRESHOLD_LABEL, gate, log_days, mean_sd, median_bias)

TOL = 1e-6
FL = ROOT / "data/flare/fedstats-gate-p12.json"
META = ROOT / "data/flare/fedstats-gate-p12.meta.json"
OUT = ROOT / "data/flare/gate-v1.json"
NOT_RUN = "FLARE-ready, not run in FLARE"
SITES = ROOT / "data/flare/gate-sites"

# Which FLARE feature answers which question: (dataset, feature)
FEATURES = {"rtt": ("rtt", "log_days_rtt"), "complete": ("rtt_record", "rtt_complete"), "open": ("rtt_record", "rtt_open")}
for _a in ARMS:
    FEATURES[f"{_a}_missed"] = (f"scribe_{_a}_events", f"{_a}_missed")
    FEATURES[f"{_a}_err"] = (f"scribe_{_a}_intervals", f"{_a}_err_days")
    FEATURES[f"{_a}_gt3"] = (f"scribe_{_a}_intervals", f"{_a}_err_gt3")
    FEATURES[f"{_a}_lt3"] = (f"scribe_{_a}_intervals", f"{_a}_err_lt_m3")

SOURCES = {
    "oecd": dict(name="OECD/EU Country Cancer Profile Finland 2025", page=19,
                 url="https://cancer-inequalities.jrc.ec.europa.eu/sites/default/files/docs/ccp2025/ec-oecd-fi-2024-1666-en.pdf",
                 reopened_utc="2026-11-14T22:56Z"),
    "stm": dict(name="STM, Hoitotakuu (treatment guarantee), page updated 29 Oct 2026", url="https://stm.fi/hoitotakuu",
                reopened_utc="2026-11-14T22:56Z"),
    "stage": dict(name="Syöpäjärjestöt news item, 17 Jun 2026, on the Finnish Cancer Registry report Syöpä 2024",
                  url="https://www.syopajarjestot.fi/uutinen/syovan-levinneisyystiedoissa-suuria-alueellisia-eroja-suomessa/",
                  reopened_utc="2026-11-14T22:56Z"),
}


def central_rtt():
    """Per county: complete RTT days, started and open counts, from the central pipeline's interval table."""
    out = {c: dict(days=[], started=0, open=0) for c in COUNTIES}
    for r in pq.read_table(ROOT / "data/eventlog/sample-intervals.parquet").to_pylist():
        o = out[r["county"]]
        if r["censored_primary_care"] or r["days_primary_care"] is None:  # no REFERRAL_SENT recorded
            continue
        o["started"] += 1
        d_ok = not r["censored_diagnostic"] and r["days_diagnostic"] is not None
        t_ok = not r["censored_treatment"] and r["days_treatment"] is not None
        if d_ok and t_ok:
            o["days"].append(r["days_diagnostic"] + r["days_treatment"])
        elif r["censored_treatment"]:
            o["open"] += 1
    return out


def site_scribe():
    return {c: json.loads((SITES / f"county={c}" / "scribe.json").read_text()) for c in COUNTIES}


def stored_crosscheck(scribe):
    """Rebuild per-county raw missed counts and raw / resolver interval errors from the stored diagnose files."""
    asg = json.loads((SITES / "assignment.json").read_text())["note_to_county"]
    miss = defaultdict(lambda: [0, 0])
    for line in (ROOT / "runs/diagnose/notes-C-270m-all-v2data.jsonl").read_text().splitlines():
        n = json.loads(line)
        c = asg[n["id"][:12]]
        if "parse_failure" in n["cats"]:
            miss[c][0] += n["n_gold"]
            miss[c][1] += n["n_gold"]
            continue
        for e in n["events"]:
            miss[c][0] += e["status"] not in ("exact", "date_wrong", "precision_only")
            miss[c][1] += 1
    raw = json.loads((ROOT / "runs/diagnose/intervals-C-270m-all-v2data.json").read_text())
    res = json.loads((ROOT / "runs/diagnose/intervals-C-270m-all-v2data-resolved.json").read_text())
    errs = {a: defaultdict(list) for a in ARMS}
    aligned = len(raw) == len(res)
    for a_row, r_row in zip(raw, res):
        aligned &= a_row.get("types") == r_row.get("types") and a_row.get("true_days") == r_row.get("true_days")
        for arm, row in (("raw", a_row), ("resolver", r_row)):
            if row.get("found"):
                errs[arm][asg[a_row["note"]]].append(row["err"])
    ok_miss = all(miss[c] == [sum(e["missed"] for e in scribe[c]["arms"]["raw"]["events"]), len(scribe[c]["arms"]["raw"]["events"])] for c in COUNTIES)
    ok_err = {arm: all(sorted(errs[arm][c]) == sorted(q["err"] for q in scribe[c]["arms"][arm]["intervals"]) for c in COUNTIES) for arm in ARMS}
    return dict(raw_missed_equal_stored_notes=ok_miss, raw_interval_errors_equal_stored=ok_err["raw"],
                resolver_interval_errors_equal_stored=ok_err["resolver"], stored_interval_files_aligned=aligned,
                files=["runs/diagnose/notes-C-270m-all-v2data.jsonl", "runs/diagnose/intervals-C-270m-all-v2data.json",
                       "runs/diagnose/intervals-C-270m-all-v2data-resolved.json"],
                note="no stored per-note event file exists for the resolver arm; its events are checked through the pooled exact-note total (651/700) in gate_prep.py")


def central_values(rtt, scribe):
    """{(county, key): list of feature values} exactly as the site builds them."""
    vals = {}
    for c in COUNTIES:
        vals[(c, "rtt")] = [log_days(x) for x in rtt[c]["days"]]
        vals[(c, "complete")] = [1.0] * len(rtt[c]["days"]) + [0.0] * (rtt[c]["started"] - len(rtt[c]["days"]))
        vals[(c, "open")] = [1.0] * rtt[c]["open"] + [0.0] * (rtt[c]["started"] - rtt[c]["open"])
        for arm in ARMS:
            a = scribe[c]["arms"][arm]
            errs = [float(q["err"]) for q in a["intervals"]]
            vals[(c, f"{arm}_missed")] = [float(e["missed"]) for e in a["events"]]
            vals[(c, f"{arm}_err")] = errs
            vals[(c, f"{arm}_gt3")] = [float(x > 3) for x in errs]
            vals[(c, f"{arm}_lt3")] = [float(x < -3) for x in errs]
    return vals


def flare_cell(fl, key, site):
    ds, f = FEATURES[key]
    g = lambda s: fl.get(f, {}).get(s, {}).get(site, {}).get(ds)  # noqa: E731
    return dict(count=g("count"), mean=g("mean"), sd=g("stddev"), hist=g("histogram"))


def equivalence(fl, vals, rtt, edge_index):
    cells, failed, sup_c, sup_f = 0, [], [], []
    max_mean = max_sd = max_share = 0.0
    for c in COUNTIES:
        for key in FEATURES:
            cells += 1
            x = vals[(c, key)]
            m, sd = mean_sd(x)
            central_sup = len(x) < MIN_COUNT
            fc = flare_cell(fl, key, c)
            flare_sup = fc["count"] is not None and fc["mean"] is None
            if central_sup:
                sup_c.append(f"{c}|{key}")
            if flare_sup:
                sup_f.append(f"{c}|{key}")
            ok = fc["count"] == len(x)
            if not central_sup and fc["mean"] is not None:
                dm, ds_ = abs(fc["mean"] - m), abs(fc["sd"] - sd)
                max_mean, max_sd = max(max_mean, dm), max(max_sd, ds_)
                ok &= dm <= TOL and ds_ <= TOL
            if key == "rtt" and fc["hist"]:
                within_f = sum(b[2] for b in fc["hist"][:edge_index])
                share_c = sum(1 for d in rtt[c]["days"] if d <= RTT_THRESHOLD_DAYS) / len(rtt[c]["days"])
                max_share = max(max_share, abs(within_f / sum(b[2] for b in fc["hist"]) - share_c))
                ok &= sum(b[2] for b in fc["hist"]) == len(x) and within_f / len(x) == share_c
            if not ok:
                failed.append(f"{c}|{key}")
    return dict(cells=cells, cells_ok=cells - len(failed), cells_failed=failed, suppressed_central=sup_c, suppressed_flare=sup_f,
                suppressed_sets_identical=sorted(sup_c) == sorted(sup_f), max_abs_diff_mean=max_mean, max_abs_diff_sd=max_sd,
                max_abs_diff_share_within_42=max_share, tolerance=TOL,
                success=not failed and sorted(sup_c) == sorted(sup_f))


def main():
    rtt = central_rtt()
    scribe = site_scribe()
    vals = central_values(rtt, scribe)
    cross = stored_crosscheck(scribe)
    meta = json.loads(META.read_text()) if META.exists() else {}
    fl = json.loads(FL.read_text()) if FL.exists() else None
    flare_ran = fl is not None and str(meta.get("run_status", "")).startswith("FINISHED")
    edge_index = meta.get("rtt_histogram_threshold_edge_index")
    eq = equivalence(fl, vals, rtt, edge_index) if flare_ran else None
    where_flare = "NVIDIA FLARE 2.9.1 simulator, 23 sites" if flare_ran and eq["success"] else NOT_RUN

    counties, national = [], dict(n=0, within=0, started=0, complete=0, open=0)
    summary = {a: dict(not_comparable=[], comparable=[]) for a in ARMS}
    decisions_agree = True
    for c in COUNTIES:
        days = rtt[c]["days"]
        within_c = sum(1 for d in days if d <= RTT_THRESHOLD_DAYS)
        if flare_ran and eq["success"]:
            fc = flare_cell(fl, "rtt", c)
            n, within = fc["count"], sum(b[2] for b in fc["hist"][:edge_index])
            complete_share = flare_cell(fl, "complete", c)["mean"]
            open_share = flare_cell(fl, "open", c)["mean"]
            started = flare_cell(fl, "complete", c)["count"]
        else:
            n, within = len(days), within_c
            started = rtt[c]["started"]
            complete_share = len(days) / started if started else None
            open_share = rtt[c]["open"] / started if started else None
        suppressed = n < MIN_COUNT
        national["n"] += 0 if suppressed else n
        national["within"] += 0 if suppressed else within
        national["started"] += started
        national["complete"] += len(days)
        national["open"] += rtt[c]["open"]
        row = dict(county=c, rtt=dict(n=n, within=within, share_within=None if suppressed else within / n, suppressed=suppressed),
                   completeness=dict(started=started, complete_share=complete_share, open_share=open_share,
                                     missing_share=None if complete_share is None else max(0.0, round(1 - complete_share - open_share, 12))),
                   notes=scribe[c]["notes"], writers=scribe[c]["writers"], scribe={})
        for arm in ARMS:
            a = scribe[c]["arms"][arm]
            missed_c = sum(e["missed"] for e in a["events"]) / len(a["events"]) if a["events"] else None
            if flare_ran and eq["success"]:
                missed = flare_cell(fl, f"{arm}_missed", c)["mean"]
                err = flare_cell(fl, f"{arm}_err", c)
                gt3, lt3 = flare_cell(fl, f"{arm}_gt3", c)["mean"], flare_cell(fl, f"{arm}_lt3", c)["mean"]
                mean_err, sd_err = err["mean"], err["sd"]
            else:
                missed = missed_c
                mean_err, sd_err = mean_sd([q["err"] for q in a["intervals"]])
                gt3 = sum(q["err"] > 3 for q in a["intervals"]) / len(a["intervals"]) if a["intervals"] else None
                lt3 = sum(q["err"] < -3 for q in a["intervals"]) / len(a["intervals"]) if a["intervals"] else None
            bias = median_bias(a["intervals"])
            bias = None if bias is None else float(bias)
            g = gate(bias, missed)
            decisions_agree &= g["comparable"] == gate(bias, missed_c)["comparable"]
            summary[arm]["comparable" if g["comparable"] else "not_comparable"].append(c)
            row["scribe"][arm] = dict(events=len(a["events"]), missed_share=missed, intervals=len(a["intervals"]),
                                      mean_signed_err_days=mean_err, sd_signed_err_days=sd_err,
                                      share_err_above_3=gt3, share_err_below_minus_3=lt3,
                                      median_bias_days=bias, exact_notes=a["exact_notes"],
                                      intervals_with_error=sum(1 for q in a["intervals"] if q["err"] != 0),
                                      nonzero_errors_days=sorted(q["err"] for q in a["intervals"] if q["err"] != 0) if not g["comparable"] else None,
                                      **g)
        counties.append(row)
    nat_share = national["within"] / national["n"]
    pooled = [d for c in COUNTIES for d in rtt[c]["days"]]
    nat_central = sum(1 for d in pooled if d <= RTT_THRESHOLD_DAYS) / len(pooled)
    flare_global = None
    if flare_ran and eq["success"]:
        gc = flare_cell(fl, "rtt", "Global")
        flare_global = dict(n=gc["count"], within=sum(b[2] for b in gc["hist"][:edge_index]))
        flare_global["equals_county_rows"] = flare_global == dict(n=national["n"], within=national["within"])

    out = dict(
        schema="sama-flare-gate-v1", synthetic=True, label="SYNTHETIC",
        generated_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        title="Comparability gate",
        lede=("Each county computes its referral-to-treatment clock where its data live; a county's figure is labelled "
              "'not comparable' when the way its dates were read would distort it. The figure itself stays visible."),
        clock=dict(name="Referral to treatment", start_event="REFERRAL_SENT", end_event="TREATMENT_START",
                   starts="when the referral is sent", threshold_days=RTT_THRESHOLD_DAYS, histogram_edge_days=RTT_EDGE_DAYS,
                   threshold_label=THRESHOLD_LABEL,
                   threshold_text=("42 days is a placeholder: the OECD/EU reports a six-week target from a suspected-cancer "
                                   "referral to the start of primary treatment. Finnish law lets specialised treatment start up "
                                   "to six months after the need is identified and names no cancer-specific limit."),
                   sources=[SOURCES["oecd"], SOURCES["stm"]], computed_in=where_flare),
        rule=dict(label=RULE_LABEL, bias_limit_days=BIAS_LIMIT_DAYS, missed_limit=MISSED_LIMIT,
                  text=(f"A county's cell is 'not comparable' when the scribe's median bias is above {BIAS_LIMIT_DAYS:g} days "
                        f"either way, or its missed-event share is above {MISSED_LIMIT:.0%}. Thresholds are placeholders."),
                  median_bias_definition=("median scribe-measured interval length minus median true length, days, over the "
                                          "county's within-note intervals whose two endpoints the scribe found"),
                  missed_definition="gold events not found with their correct type, divided by all gold events in the county's notes",
                  missed_share_computed_in=where_flare,
                  median_bias_computed_in=(f"plain Python on the same site partitions: {NOT_RUN} (medians are not among the "
                                           "statistics this job runs; FLARE's quantile statistic is an approximate T-digest and "
                                           "its package was not installed)"),
                  why_median_bias=("the median of per-interval errors is 0 for the raw scribe in most counties because its "
                                   "errors are two-sided, yet the county median moves by up to tens of days; the rule therefore "
                                   "tests the shift of the county median")),
        scribe_input=dict(run="C-270m-all-v2data (Gemma 3 270M LoRA)", notes=700, kind="SYNTHETIC notes",
                          arms=dict(raw="stored predictions as the scribe wrote them",
                                    resolver="the same predictions after the code relative-date resolver (runs/diagnose/resolve_relative.py)"),
                          exact_notes=json.loads((SITES / "assignment.json").read_text())["exact_notes"],
                          assignment="notes sorted by SHA-256 id; note k goes to county k mod 23 (SYNTHETIC, content-blind)",
                          scenario=("the SYNTHETIC event log's dates are structured fields; the gate asks what would happen if a "
                                    "county's dates were read from notes by this scribe")),
        counties=counties,
        national=dict(n=national["n"], within=national["within"], share_within=nat_share, share_within_central_pooled=nat_central,
                      started=national["started"], complete_share=national["complete"] / national["started"],
                      open_share=national["open"] / national["started"],
                      completeness_note=("the SYNTHETIC event log has no missing end dates; a started clock is either complete "
                                         "or still open at the administrative data cut"),
                      computed_from="unsuppressed county rows (FLARE's own national row is wrong when a county is suppressed)",
                      flare_global_row=flare_global),
        summary={a: dict(not_comparable=len(s["not_comparable"]), comparable=len(s["comparable"]), of=len(COUNTIES),
                         not_comparable_counties=s["not_comparable"]) for a, s in summary.items()},
        flare=dict(ran=flare_ran, run_status=meta.get("run_status"), nvflare=meta.get("nvflare"), sites=len(meta.get("sites", [])),
                   simulator_threads=meta.get("simulator_threads"), elapsed_seconds=meta.get("elapsed_seconds"),
                   precision=meta.get("precision"), privacy_filters=meta.get("privacy_filters"),
                   output="data/flare/fedstats-gate-p12.json" if flare_ran else None, equivalence=eq,
                   gate_decisions_identical_with_central_missed_share=decisions_agree),
        crosscheck_stored_files=cross,
        realData=dict(kind="PUBLISHED", question="Can this area see its cancer stage?",
                      rule="yes when stage is recorded for at least 70% of cancers, the stated aim", aim_pct=70,
                      areas=[dict(area="Whole country", pct=42, canSee=False),
                             dict(area="Pirkanmaa wellbeing services county", pct=72, canSee=True),
                             dict(area="Sisä-Suomi collaborative area (yhteistyöalue)", pct=60, canSee=False),
                             dict(area="Other areas, not named one by one in the source", pctRange=[33, 42], canSee=False)],
                      note="Published by area only. No value is given or invented for any SYNTHETIC county.",
                      source=SOURCES["stage"]),
        limits=[
            "All pathway and note data here are SYNTHETIC. Nothing was run on real notes or real patients.",
            "Simulation only: 23 FLARE sites on one Mac reading partitions of one folder; no network, provisioning or site approval.",
            "Notes are assigned to counties by a content-blind rule, so differences between counties in one arm are sampling noise of the same scribe on 30-31 notes, not county effects.",
            "The bias is estimated on 27-59 within-note intervals per county; a real gate would need a fixed audit sample per county.",
            "Both thresholds are placeholders, not validated limits; 42 days is a placeholder for the OECD/EU-reported target, not a Finnish legal limit.",
            "A person confirms every extracted event in SAMA; the gate labels figures, it does not replace that check.",
        ],
        files=dict(prep="flare/gate_prep.py", rule="flare/gate.py", site="flare/gate_stats.py", job="flare/run_gate.py",
                   build="flare/build_gate.py", render="web/flare.mjs", log="runs/ship-flare.jsonl"),
    )
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps(dict(flare_ran=flare_ran, equivalence=None if eq is None else {k: eq[k] for k in ("cells", "cells_ok", "success", "max_abs_diff_mean", "max_abs_diff_sd", "max_abs_diff_share_within_42")},
                          national_share_within_42=round(nat_share, 4), national_central=round(nat_central, 4),
                          summary={a: out["summary"][a]["not_comparable"] for a in ARMS},
                          not_comparable={a: out["summary"][a]["not_comparable_counties"] for a in ARMS},
                          crosscheck=cross, decisions_agree=decisions_agree)))


if __name__ == "__main__":
    main()
