"""Recompute every number used in submission/*.md from its source file and check the documents.

Run from the solution folder:
    scribe/.venv/bin/python submission/check_numbers.py            # human-readable report
    scribe/.venv/bin/python submission/check_numbers.py --json     # machine-readable summary

Checks:
1. each fact, recomputed from its source file, formats to the exact string the documents use;
2. that string occurs in every document listed for it;
3. no banned or retired wording, every document says SYNTHETIC, the deck states the language scope
   and the promise, every 42-day threshold is labelled a placeholder;
4. the video voice-over fits 120 s at 2.3 words a second; the Verda post fits 2,000 characters;
5. lists every pending placeholder and whether its file exists now.
External facts come from submission/evidence-v2.json (sources re-opened on 14 Nov 2026, 22:53-23:03
UTC) or data/evidence/literature-v1.json.
Exit code 1 on any failure. Reads only; writes nothing.
"""
import collections
import glob
import json
import math
import os
import re
import statistics
import sys

import pyarrow.parquet as pq

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUB = os.path.join(ROOT, "submission")
DOCS = ["DECK.md", "VIDEO_SCRIPT.md", "NVIDIA_FORM.md", "GEMMA_WRITEUP.md", "VERDA_DISCORD.md",
        "PATH_TO_SCALE.md", "ZERO_EURO_2027.md", "PATHWAY_CLOCK.md", "EXPORT_CHECKLIST.md"]
BANNED = ["auto-confirmed", "auto confirmed", "skips review", "skip review", "clinically accurate",
          "works on real notes", "hospital-grade", "hospital grade"]
# Retired wording: numbers and phrases BIG_PICTURE.md (revision 2) found wrong.
RETIRED = ["23 wellbeing services counties", "Kuitunen H", "207 days", "160 patients",
           "highest lung mortality", "deaths postponed a year (range", "the highest of the 23",
           "for the same model writing dates", "scribe that runs inside the"]
PROMISE = "wherever they live, whoever they are, however they enter care"
WORDS_PER_SECOND = 2.3
MAX_SECONDS = 120
NUM_WORDS = {3: "three", 6: "six"}

TEXT = {d: open(os.path.join(SUB, d), encoding="utf-8").read() for d in DOCS}
failures, facts = [], []


def J(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
        return json.load(fh)


def jsonl(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def r(x, nd):
    """Round half away from zero (the documents round like a person, not like banker's rounding)."""
    q = 10 ** nd
    return math.floor(abs(x) * q + 0.5) / q * (1 if x >= 0 else -1)


def f(x, nd):
    return f"{r(x, nd):.{nd}f}"


def thousands(n):
    return f"{int(n):,}"


def wilson(k, n, z=1.959963984540054):
    """Wilson 95% interval in percent, recomputed from k and n (not from a rounded stored bound)."""
    ph = k / n
    den = 1 + z * z / n
    mid = (ph + z * z / (2 * n)) / den
    half = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / den
    return f(100 * max(0.0, mid - half), 1) + "-" + f(100 * min(1.0, mid + half), 1)


def pct(k, n, nd=1):
    return f(100 * k / n, nd) + "%"


def fact(name, source, display, docs):
    facts.append((name, source, display, docs))
    for d in docs:
        if display not in TEXT[d]:
            failures.append(f"{d}: missing '{display}' ({name}, from {source})")


def same(name, got, want):
    if got != want:
        failures.append(f"source changed: {name}: file gives {got!r}, documents assume {want!r}")


ALL = DOCS
DECK, VIDEO, NV, GEM, VERDA, PTS, ZERO, CLOCK, EXP = DOCS

# --- external facts re-opened tonight (submission/evidence-v2.json) ----------------------------
ev = {x["id"]: x for x in J("submission/evidence-v2.json")["rows"]}
same("evidence rows have url and recheck", all(x.get("url") and x.get("rechecked") for x in ev.values()), True)
V = lambda i: ev[i]["values"]
s = V("oecd-2025-fi-survival-education")
fact("survival lower education", "evidence-v2 oecd survival", f"{s['lower_men']}-{s['lower_women']}%", [DECK, VIDEO])
fact("survival higher education", "evidence-v2 oecd survival", f"{s['higher_men']}-{s['higher_women']}%", [DECK, VIDEO])
b = V("oecd-2025-fi-breast-screening-gaps")
fact("breast by mother tongue", "evidence-v2 oecd breast", f"**{b['other_language']}%** against **{b['domestic_language']}%**", [DECK])
fact("breast by education", "evidence-v2 oecd breast", f"**{b['lower_education']}%** against **{b['higher_education']}%**", [DECK])
w = V("oecd-2025-fi-six-weeks")
same("six weeks = 42 days", w["weeks"] * 7, w["days_placeholder"])
fact("six weeks", "evidence-v2 oecd six weeks", f"**{NUM_WORDS[w['weeks']]} weeks**", [DECK, CLOCK])
fact("six-week spoken", "evidence-v2 oecd six weeks", f"{NUM_WORDS[w['weeks']]}-week target", [VIDEO])
fact("42-day placeholder", "evidence-v2 oecd six weeks", f"{w['days_placeholder']} days", [DECK, CLOCK])
h = V("stm-hoitotakuu")
for k, unit in (("assessment_weeks", "weeks"), ("tests_months", "months"), ("treatment_months", "months")):
    fact(f"law {k}", "evidence-v2 stm-hoitotakuu", f"**{h[k]} {unit}**", [DECK, CLOCK])
fact("law six months spoken", "evidence-v2 stm-hoitotakuu", f"up to {NUM_WORDS[h['treatment_months']]} months", [VIDEO])
st_ = V("syopajarjestot-2026-stage-completeness")
fact("stage national", "evidence-v2 syopajarjestot", f"**{st_['national']}%** of cancers", [DECK])
fact("stage national spoken", "evidence-v2 syopajarjestot", f"only {st_['national']} percent of cancers", [VIDEO])
fact("stage aim", "evidence-v2 syopajarjestot", f"at least {st_['aim']}%", [DECK])
fact("stage by area", "evidence-v2 syopajarjestot",
     f"{st_['pirkanmaa']}% in Pirkanmaa, {st_['sisa_suomi']}% in Sisä-Suomi and {st_['others_low']}-{st_['others_high']}%", [DECK, CLOCK])
same("only Pirkanmaa meets the stage aim", [k for k in ("pirkanmaa", "sisa_suomi", "others_high") if st_[k] >= st_["aim"]], ["pirkanmaa"])
law = V("stm-2026-proactive-care-law")
same("law date", law["in_force"], "2026-06-01")
fact("law in force", "evidence-v2 stm law", "1 June 2026", [DECK, ZERO])
li = V("lungimpact-2026")
same("LungIMPACT equal medians", li["median_days_ai"], li["median_days_usual"])
fact("LungIMPACT x-rays", "evidence-v2 lungimpact", thousands(li["xrays"]), [DECK, ZERO, VIDEO])
fact("LungIMPACT median", "evidence-v2 lungimpact", f"**{li['median_days_ai']} days**", [DECK, ZERO])
fact("LungIMPACT ratio", "evidence-v2 lungimpact", f"(ratio {li['ratio']}, {li['ci_low']}-{li['ci_high']})", [DECK])
ku = V("kuitunen-2026-route-medians-groups")
fact("route median public", "evidence-v2 kuitunen", f"**{ku['median_public']} days**", [DECK, CLOCK])
fact("route median fast", "evidence-v2 kuitunen", f"**{ku['median_fast']} days**", [DECK, CLOCK])
fact("route spoken", "evidence-v2 kuitunen", f"was {ku['median_public']} days through a public health centre appointment, and {ku['median_fast']} through", [VIDEO])
fact("route groups", "evidence-v2 kuitunen", f"{ku['n_public']} against {ku['n_fast']} patients, p = {ku['p']}", [DECK, VIDEO])
fact("route group total", "evidence-v2 kuitunen", f"{ku['n_public'] + ku['n_fast']} patients in the two route groups", [DECK])
fact("route medians gap", "evidence-v2 kuitunen", f"{ku['median_public'] - ku['median_fast']} days ({ku['median_public']} against {ku['median_fast']})", [DECK])
fact("route means gap", "evidence-v2 kuitunen", f"means by {ku['mean_public'] - ku['mean_fast']} ({ku['mean_public']} against {ku['mean_fast']})", [DECK])
raw_lit = open(os.path.join(ROOT, "data/evidence/literature-v1.json"), encoding="utf-8").read()
lit = {x["id"]: x for x in json.loads(raw_lit)["rows"]}
same("literature medians agree", (lit["kuitunen-2026-route-medians"]["value"], "127 public vs 76" in lit["kuitunen-2026-route-medians"]["unit"]),
     (ku["median_public"] - ku["median_fast"], True))
# The NHS-Galleri line was removed from the deck on 15 Nov 2026 (no named technologies in the "not yet" list).
y = V("yle-2025-helsinki-prebooking")
fact("pre-booking", "evidence-v2 yle", f"from **{y['before']}%** to about **{y['after']}%**", [DECK, ZERO])
tt = V("thl-ttp-person-level")
fact("TTP deadline", "evidence-v2 thl", f"by {max(tt['deadline_a'], tt['deadline_b'])[:4]} at the latest", [DECK, CLOCK, ZERO])
fact("no money year", "evidence-v2 stt", f"**{V('stt-2026-no-strategy-money-2027')['year']}**", [DECK, ZERO])
ai = V("eu-ai-act-dates")
same("AI Act dates", (ai["annex3"], ai["products"]), ("2027-12-02", "2028-08-02"))
fact("AI Act", "evidence-v2 ai act", "2 December 2027\nand 2 August 2028", [DECK])
c21 = V("stm-21-counties")
fact("21 counties", "evidence-v2 stm-21-counties", f"{c21['counties']} wellbeing services counties, Helsinki and Åland ({c21['areas_in_sama']} areas)", [DECK])
fl = V("filha-2026-found-by-chance")
fact("lung survival education men", "evidence-v2 filha", f"{fl['men_basic']}% against {fl['men_tertiary']}%", [DECK])
fact("lung survival education women", "evidence-v2 filha", f"{fl['women_basic']}% against {fl['women_tertiary']}%", [DECK])
ma = lit["masai-2025-workload"]
fact("MASAI workload", "literature-v1 masai", f"**{f(ma['value'], 0)}%**", [DECK])
same("MASAI detection ratio", "detection ratio 1.29 (1.09-1.51)" in ma["unit"], True)
fact("MASAI detection", "literature-v1 masai", "detection ratio of 1.29 (1.09-1.51)", [DECK])
vi = lit["virtanen-2011-selfsampling-fi"]
# The zero-euro pre-booking action is a cervical-screening change, so its gap is quoted with cervical figures.
cvl, cve = lit["oecd-2025-cervical-screening-language"]["figures"], lit["oecd-2025-cervical-screening-education"]["figures"]
fact("cervical by mother tongue", "literature-v1 oecd cervical language", f"**{cvl['nonDomesticLanguage']}%** against **{cvl['domesticLanguage']}%**", [DECK, ZERO])
fact("cervical by education", "literature-v1 oecd cervical education", f"**{cve['lower']}%** against **{cve['higher']}%**", [DECK, ZERO])
fact("self-sampling RR", "literature-v1 virtanen", f"{f(vi['value'], 2)} ({f(vi['ciLow'], 2)}-{f(vi['ciHigh'], 2)})", [DECK])

# --- product, real public data (web/data/app.json) ---------------------------------------------
app = J("web/data/app.json")
g3 = {i["id"]: i for i in app["analysis"]["goal3"]["indicators"]}
lung = next(x for x in g3["nordic-survival"]["rows"] if x["site"] == "lung" and x["sex"] == "male")
fact("lung survival Finland", "app.json goal3", f(lung["finland"], 1) + "%", [DECK])
fact("lung survival Sweden-Norway", "app.json goal3", f(lung["benchmark"], 1) + "%", [DECK])
fact("lung survival Finland spoken", "app.json goal3", f"men is {f(lung['finland'], 1)} percent", [VIDEO])
fact("lung survival benchmark spoken", "app.json goal3", f"average is {f(lung['benchmark'], 1)}.", [VIDEO])
same("treatment-within-target status", g3["treatment-within-target"]["status"], "NOT_PUBLICLY_MEASURABLE")
mort = {x["regionId"]: x for x in app["analysis"]["mortality"]["all_cancers"]["rows"]}
same("Satakunta shrunk 2dp", f(mort["HVA06"]["shrunk"], 2), "1.10")
same("Kymenlaakso shrunk 2dp", f(mort["HVA10"]["shrunk"], 2), "1.10")
fact("Satakunta and Kymenlaakso", "app.json mortality", "1.10 times", [DECK])
lrows = {x["regionId"]: x for x in app["analysis"]["mortality"]["lung"]["rows"]}
same("lung label", app["analysis"]["mortality"]["lung"]["label"], "Larynx, trachea and lung (C32-C34)")
fact("Lapland lung", "app.json mortality.lung HVA21 shrunk", f(lrows["HVA21"]["shrunk"], 2) + " times", [DECK])
sl = lrows["HVA06"]
fact("Satakunta lung", "app.json mortality.lung HVA06", f"**{f(sl['shrunk'], 3)}**, {f(sl['shrunkLow'], 3)}-{sl['shrunkHigh']}", [DECK])
fact("Lapland lung 3dp", "app.json mortality.lung HVA21", f"Lapland ({f(lrows['HVA21']['shrunk'], 3)})", [DECK])
fact("Kymenlaakso lung 3dp", "app.json mortality.lung HVA10", f"Kymenlaakso ({f(lrows['HVA10']['shrunk'], 3)})", [DECK])
arows = sorted([x for x in app["analysis"]["mortality"]["all_cancers"]["rows"] if not x.get("suppressed") and x.get("shrunk") is not None], key=lambda x: -x["shrunk"])
sa = next(x for x in arows if x["regionId"] == "HVA06")
fact("Satakunta all-cancer", "app.json mortality.all_cancers HVA06", f"(**{f(sa['shrunk'], 3)}**, **{f(sa['shrunkLow'], 3)}-{f(sa['shrunkHigh'], 3)}**)", [DECK])
fact("all-cancer top-two gap", "app.json mortality.all_cancers shrunk, two highest", f"differ by **{f(arows[0]['shrunk'] - arows[1]['shrunk'], 3)}**", [DECK])
same("Satakunta not highest lung", sorted(lrows, key=lambda k: -lrows[k]["shrunk"])[:3], ["HVA21", "HVA10", "HVA06"])
ind = app["analysis"]["indicators"]
c, cv = ind["screen_colorectal"], ind["screen_cervix"]
fact("colorectal below target", "app.json indicators", f"{c['countiesMissingTarget']} of {c['countiesWithData']}", [DECK])
fact("cervical below target", "app.json indicators", f"{cv['countiesMissingTarget']} of {cv['countiesWithData']}", [DECK])
same("screening target", (c["target"], cv["target"]), (80, 80))
br = {x["regionId"]: x["value"] for x in ind["screen_breast"]["rows"] if x["year"] == 2024}
for rid, label in (("HVA90", "Helsinki"), ("HVA03", "Uusimaa"), ("HVA04", "Kerava")):
    fact(f"breast {rid}", "app.json screen_breast 2024", f"{label} {f(br[rid], 1)}%", [DECK])
same("three lowest breast attendance", sorted(br, key=br.get)[:3], ["HVA90", "HVA03", "HVA04"])
edu = {x["regionId"]: x["value"] for x in ind["education_index"]["rows"] if x["year"] == ind["education_index"]["year"]}
both = [k for k in br if k in edu]
fact("breast counties", "app.json", f"Across {len(both)} counties", [DECK])
rr_all = statistics.correlation([br[k] for k in both], [edu[k] for k in both])
rr_noh = statistics.correlation([br[k] for k in both if k != "HVA90"], [edu[k] for k in both if k != "HVA90"])
fact("breast-education r", "app.json screen_breast x education_index", f"(r = {f(rr_all, 2)})", [DECK])
fact("breast-education r without Helsinki", "app.json", f"(r = {f(rr_noh, 2)})", [DECK])
fb = {x["regionId"]: x["value"] for x in ind["foreign_background"]["rows"] if x["year"] == ind["foreign_background"]["year"]}
same("top foreign background", sorted(fb, key=lambda k: -fb[k])[:3], ["HVA04", "HVA90", "HVA03"])
fact("foreign background", "app.json foreign_background", f"{fb['HVA04']}, {fb['HVA90']} and {fb['HVA03']}", [DECK])
fact("snapshot requests", "app.json provenance", f"**{app['provenance']['requests']}** requests", [DECK])
same("regions", len(app["analysis"]["regions"]), 23)
same("indicators", len(app["analysis"]["indicators"]), 20)
rec = app["recommendation"]
same("interventions", len(rec["interventions"]), 8)
p = rec["portfolio"]
fact("portfolio picks", "app.json portfolio", f"**{len(p['picks'])}** county actions", [DECK])
fact("portfolio spent millions", "app.json portfolio", f(p["spent"] / 1e6, 2) + " million", [DECK])
fact("budget millions", "app.json recommendation", f(rec["budget"] / 1e6, 1) + " million", [DECK])
fact("deaths postponed", "app.json portfolio", f"{f(p['deathsPostponed'], 1)} deaths postponed a year ({f(p['low'], 1)}-{f(p['high'], 1)})", [DECK])
fact("share in high mortality", "app.json portfolio", f(100 * p["shareInHighMortalityCounties"], 1) + "%", [DECK])
same("draws", rec["draws"], 300)
v = rec["validation"]
fact("model hazard ratio", "app.json validation", f"{v['modelHazardRatio']}", [DECK])
fact("Danish observed", "app.json validation", f"{v['observedHazardRatio']}** ({v['observedLow']}-{v['observedHigh']})", [DECK])
evl = app["eventLog"]
ds = J("data/eventlog/design-study-v1.json")["sample_sizes"]
row = next(x for x in ds["rows"] if x["slowdown"] == 1.2)
fact("episodes needed", "design-study-v1 sample_sizes", f"{row['primary_care']} / {row['diagnostic']} / {row['treatment']}", [DECK, PTS, CLOCK])
same("app.json sample sizes match design study", next(x for x in evl["sampleSizes"]["rows"] if x["slowdown"] == 1.2)["primary_care"], row["primary_care"])
same("comparisons", "0.05/69" in ds["formula"], True)
reach = next(x for x in evl["reach"] if x["slowdown"] == 1.2)
fact("counties within a quarter", "app.json eventLog.reach", f"{reach['quarter']} of 23", [DECK, PTS, CLOCK])
fact("counties within a year", "app.json eventLog.reach", f"{reach['year']} of 23", [DECK, PTS, CLOCK])
fact("cases assumed", "design-study-v1", thousands(ds["national_cases_assumed"]), [DECK, PTS, CLOCK])

cc = J("data/claim-check/eval-v1.json")["summary"]
fact("claim check true passed", "claim-check eval", f"{cc['true']['SUPPORTED']} of {cc['true']['n']}", [DECK])
same("claim check wrongly rejected", cc["true"]["NOT_SUPPORTED"], 0)
corrupted = [cc[k] for k in ("direction", "place", "causal", "number")]
fact("corrupted stopped", "claim-check eval", f"{sum(x['n'] - x['SUPPORTED'] for x in corrupted)} of {sum(x['n'] for x in corrupted)}", [DECK])
nar = J("data/narratives/fi-v1.json")["totals"]
fact("narratives kept", "narratives fi-v1", f"{nar['kept']} of {nar['generated']}", [DECK])

# --- roadmap -------------------------------------------------------------------------------------
mp = J("data/roadmap/mapping-v1.json")
pc = mp["pilotCard"]["snapshotEvidence"]
fact("pilot shrunk", "mapping-v1 pilotCard", f"{pc['shrunk']}", [DECK])
fact("pilot interval", "mapping-v1 pilotCard", f"{pc['shrunkLow']}-{pc['shrunkHigh']}", [DECK])
same("pilot rank", (pc["rankByShrunk"], pc["ofCounties"]), (1, 23))
same("pilot county", mp["pilotCard"]["county"]["id"], "HVA06")
acts = {a["actionId"]: a for a in mp["actions"]}
fits = collections.Counter(a["fit"] for a in mp["actions"])
same("fits", (len(acts), fits["named"], fits["serves"], fits.get("none", 0)), (9, 3, 6, 0))
for aid, a in acts.items():
    pages = mp["measures"][a["primary"]]["pages"]
    ptxt = f"{pages[0]}-{pages[-1]}" if len(pages) > 1 else f"{pages[0]}"
    label = aid if aid != "four-timestamps" else "four-timestamps (data proposal)"
    fact(f"roadmap {aid}", "mapping-v1", f"| {label} | {a['fit']} | {a['primary']} | {ptxt} |", [DECK])
same("lung pilot wording", "eight wellbeing services counties" in json.dumps(mp), True)
ms = mp["measures"]


def euros(mid):
    return "EUR " + thousands(int(re.search(r"([\d ]+) €", ms[mid]["resource"]["fi"]).group(1).replace(" ", "")))


fact("3.2.1 budget", "mapping-v1 measure 3.2.1 resource", euros("3.2.1") + ", pages 59-60", [DECK, CLOCK])
same("3.2.1 pages", ms["3.2.1"]["pages"], [59, 60])
fact("3.2.1 budget zero-euro", "mapping-v1 measure 3.2.1", f"budgeted at {euros('3.2.1')}", [ZERO])
same("1.2.3 page and 1.3.1 page", (ms["1.2.3"]["pages"], ms["1.3.1"]["pages"]), ([32], [33]))
fact("1.2.3 page", "mapping-v1", "1.2.3 (page 32)", [ZERO])
fact("1.3.1 page", "mapping-v1", "1.3.1 (page 33)", [ZERO])
same("3.2.1 metric 90%", "90 %" in ms["3.2.1"]["metrics"][0]["fi"], True)
same("1.3.1 metric mother tongue", "äidinkielenään muita kieliä kuin suomea ja ruotsia" in ms["1.3.1"]["metrics"][0]["fi"], True)
step2 = [x for x in jsonl("runs/laneC-step2.jsonl") if "quotes_checked_python" in (x.get("metrics") or {})]
fact("roadmap quotes", "runs/laneC-step2.jsonl", f"**{step2[-1]['metrics']['quotes_checked_python']}** Finnish quotes", [DECK])

# --- scribe: Gemma -------------------------------------------------------------------------------
dg = J("runs/diagnose/diagnose-v1.json")["runs"]
rel = dg["C-270m-all-v2data"]["test"]["by_has_relative"]
fact("relative-date notes", "diagnose-v1", f"{rel['True']['k']} of {rel['True']['n']}", [DECK, GEM])
fact("non-relative notes", "diagnose-v1", f"{rel['False']['k']} of {rel['False']['n']}", [GEM])
r1b = dg["S-1b-lora-r16"]["test"]["by_has_relative"]["True"]
fact("1B relative", "diagnose-v1", f"{r1b['k']} of {r1b['n']}", [DECK, GEM])
rp = J("data/scribe/v4/resolver/reproduce-v1.json")
pv, pt = rp["primary"]["validation"], rp["primary"]["test"]
same("reproduced exactly", rp["primary"]["reproduced_exactly"], True)
same("product default arm", rp["arm_Aprime"]["product_default_arm"], "A'")
fact("val after", "reproduce-v1", f"{pv['k']} of {pv['n']}", [DECK])
fact("val after slash", "reproduce-v1", f"{pv['k']}/{pv['n']}", [DECK, PTS])
fact("val pct", "reproduce-v1", pct(pv["k"], pv["n"]), [DECK, GEM])
fact("test after", "reproduce-v1", f"{pt['k']} of {pt['n']}", [DECK])
fact("test pct", "reproduce-v1", pct(pt["k"], pt["n"]), [DECK, GEM])
fact("test wilson", "reproduce-v1", f"Wilson {wilson(pt['k'], pt['n'])}", [DECK, GEM])
fact("val before", "reproduce-v1", f"| {pv['before']['k']}", [GEM])
fact("test before", "reproduce-v1", f"| {pt['before']['k']}", [GEM])
same("port identical", (rp["port_identical_to_diagnose_rule"]["notes_compared"], rp["port_identical_to_diagnose_rule"]["mismatches"]), (5050, 0))
fact("port notes", "reproduce-v1", "5,050", [DECK])
same("notes made worse", rp["notes_made_worse_arm_A_all_runs"], 0)
rr = J("runs/diagnose/resolve-relative-v1.json")["results"]
cr = rr["C-270m-all-v2data"]
fact("nemotron-written before/after", "resolve-relative-v1",
     f"{cr['test_nemotron']['before']['k']}/500 | {cr['test_nemotron']['after']['k']}/500", [DECK, GEM])
fact("haiku-written before/after", "resolve-relative-v1",
     f"{cr['test_haiku']['before']['k']}/200 | {cr['test_haiku']['after']['k']}/200", [DECK, GEM])
fact("nemotron-only adapter", "resolve-relative-v1", f"{rr['V3-270m-nemotron']['test_pooled']['after']['k']}/700", [GEM, EXP])
fz = J("data/scribe/v4/resolver/freeze.json")
fact("freeze time", "freeze.json", fz["frozen_at_utc"][11:19], [DECK, GEM])
# expression arm on MLX (validation = selection evidence)
mv = J("data/scribe/v4/mlx/validation-v1.json")
A, B = mv["arms"]["A-270m-abs"], mv["arms"]["B-270m-expr-aug"]
same("both MLX arms ok", (A["status"], B["status"]), ("ok", "ok"))
same("expression arm met preregistered rule", mv["rules"]["success_B"]["met"], True)
bk, ak = B["exact_match"]["code"], A["exact_match"]["A'"]
fact("expression arm val", "validation-v1 B", f"**{bk['k']} of {bk['n']}**", [DECK])
fact("expression arm val slash", "validation-v1 B", f"{bk['k']}/{bk['n']}", [DECK, GEM])
fact("expression arm pct", "validation-v1 B", pct(bk["k"], bk["n"]), [GEM])
fact("absolute arm val", "validation-v1 A A'", f"{ak['k']} of {ak['n']}", [DECK])
fact("absolute arm val slash", "validation-v1 A A'", f"{ak['k']}/{ak['n']}", [DECK, GEM])
cmpm = mv["comparisons"][0]
fact("arm McNemar", "validation-v1 comparisons", f"p = {f(cmpm['exact_p'], 2)}", [DECK, GEM])
bh, ah = B["by_writer"]["haiku"], A["by_writer"]["haiku"]
fact("arm haiku", "validation-v1 by_writer", f"{bh['k']} vs {ah['k']} of {bh['n']}", [DECK, GEM])
fact("arm B row", "validation-v1 B", f"{bh['k']}/{bh['n']} | {B['parse']['failed']} |", [DECK, GEM])
fact("arm A row", "validation-v1 A", f"{ah['k']}/{ah['n']} | {A['parse']['failed']} |", [DECK, GEM])
fact("arm B train", "validation-v1 B training", thousands(r(B["training"]["wall_seconds"], 0)) + " s", [DECK, GEM])
fact("arm A train", "validation-v1 A training", thousands(r(A["training"]["wall_seconds"], 0)) + " s", [GEM])
# CPU demo through the product endpoint
ht = J("data/scribe/demo/http-timing.json")
em = ht["exact_match_with_answer_key"]
fact("CPU demo exact", "demo http-timing", f"{em['k']} of {em['n']}", [DECK, GEM, PTS, VERDA])
fact("CPU demo median", "demo http-timing", f"{f(ht['http_wall_seconds']['median'], 1)} s", [DECK, GEM, PTS, VERDA])
same("CPU demo served live", ht["served_live"], em["n"])
tf = J("data/scribe/v2/training-figures-v1.json")
gpu = tf["gpu"]
fact("train seconds", "training-figures gpu", f"{f(gpu['runs']['post-ablation C-270m-all-v2data']['train_seconds'], 0)} s", [DECK, GEM, VERDA])
fact("sum train seconds", "training-figures gpu", thousands(r(gpu["sum_train_seconds"], 0)) + " s", [VERDA])
same("runs with result", len(gpu["runs"]), 7)
fact("ablation seconds", "training-figures gpu", thousands(r(gpu["ablation_budget"]["elapsed_seconds"], 0)) + " s", [VERDA])
fact("1B peak", "training-figures gpu", f(gpu["runs"]["post-ablation S-1b-lora-r16"]["peak_gpu_memory_gib"], 1) + " GiB", [VERDA])
fact("idle gap", "training-figures gpu", f(gpu["gap_between_recorded_gpu_jobs"]["minutes"], 1) + " minutes", [VERDA])
mc = tf["machine_cost"]
fact("A100 cost", "training-figures machine_cost", "USD " + f(mc["list_price_times_hours_usd"], 2), [DECK, VERDA])
fact("A100 hours", "training-figures machine_cost", f(mc["hours"], 2) + " h", [DECK, VERDA])
fact("A100 price", "training-figures machine_cost", f"USD {mc['price_per_hour_usd_listed']}", [VERDA])
fact("teacher round 1", "training-figures api_spend", thousands(tf["api_spend"]["teacher_requests"]["round_1"]), [VERDA])
cmp_ = J("data/scribe/v3/student/compare-v1.json")
ref_h = cmp_["reference"]["summary"]["test_haiku"]["note_exact_match"]["k"]
c_h = cmp_["comparisons"][2]["summary"]["test_haiku"]["note_exact_match"]["k"]
fact("writer mix", "compare-v1", f"{pct(ref_h, 200)} to {pct(c_h, 200)}", [DECK, GEM])
fact("more nemotron notes", "compare-v1", f"{cmp_['reference']['summary']['test_nemotron']['note_exact_match']['k']} to "
     f"{cmp_['comparisons'][0]['summary']['test_nemotron']['note_exact_match']['k']} of 500", [GEM])
sm = J("serve/smoke/smoke-guided.json")
same("smoke valid", (sm["valid_output_rate"]["value"], sm["n"]), (1.0, 100))
fact("smoke p95", "smoke-guided", f(sm["latency_seconds"]["p95"], 2) + " s", [DECK, GEM, VERDA, PTS])
fact("smoke p50", "smoke-guided", f(sm["latency_seconds"]["p50"], 2) + " s", [VERDA])
fact("smoke rate", "smoke-guided", f(sm["notes_per_second"], 2) + " notes", [GEM, VERDA, PTS])
for name, path, writers in (("v3", "data/scribe/v3/dataset/train.parquet", ("nemotron-3.5-super-vl", "claude-haiku-5-5")),
                            ("v2", "data/scribe/v2/dataset/train.parquet", ("nemotron-3.5-super-vl", "claude-haiku-5-5"))):
    cnt = collections.Counter(pq.read_table(os.path.join(ROOT, path), columns=["writer"]).column("writer").to_pylist())
    if name == "v3":
        fact("v3 nemotron notes", path, f"{thousands(cnt[writers[0]])} of {thousands(sum(cnt.values()))}", [NV])
        fact("v3 haiku notes", path, f"{cnt[writers[1]]} Haiku-written notes", [NV])
    else:
        fact("v2 train notes", path, f"{thousands(sum(cnt.values()))} SYNTHETIC notes", [DECK, GEM])
        fact("v2 writers", path, f"{thousands(cnt[writers[0]])} by", [DECK, GEM])

# --- simulation ------------------------------------------------------------------------------------
# The integrated repository study (data/eventlog/design-study-v1.json, measured_interval_extraction), the same
# file the page and README read. The earlier scratch run (runs/diagnose/interval-impact-v1.json) gave slightly
# different values for the same quantities and is no longer quoted.
DS = "design-study-v1 measured_interval_extraction"
dsx = J("data/eventlog/design-study-v1.json")["measured_interval_extraction"]["rows"]


def drow(kind, cond, arm, writer="all", n=500, extras=False):
    return next(x for x in dsx if x["kind"] == kind and x["condition"] == cond and x["arm"] == arm and x["writer"] == writer
                and x["extras_modelled"] is extras and (n is None or x.get("n") == n))


ivs = ("primary_care", "diagnostic", "treatment")
b0, b1 = drow("planted", "measured_everywhere", "off")["intervals"], drow("planted", "measured_everywhere", "A")["intervals"]
fact("bias as is", DS, " / ".join("+" + f(b0[i]["median_bias_days"], 1) for i in ivs), [DECK, GEM])
fact("bias fixed", DS, " / ".join("+" + f(b1[i]["median_bias_days"], 2) for i in ivs), [DECK, GEM])
for cond, arm, label in (("confirmed", None, "power confirmed"), ("measured_everywhere", "off", "power as is"), ("measured_everywhere", "A", "power fixed")):
    cc_ = drow("planted_table_n", cond, arm, n=None)["intervals"]
    fact(label, DS, " / ".join(f(cc_[i]["located"], 3) for i in ivs), [DECK, GEM])
ff = lambda cond, arm, writer="all": f(drow("null", cond, arm, writer)["county_false_positive_rate"], 3)
fact("false flag as is", DS, ff("county_extracted_country_structured", "off"), [DECK, GEM, PTS, CLOCK])
fact("false flag fixed", DS, ff("county_extracted_country_structured", "A"), [DECK, GEM, PTS, CLOCK])
hk = "county_haiku_like_country_nemotron_like"
fact("writer style as is", DS, ff(hk, "off", "haiku vs nemotron"), [DECK])
fact("writer style fixed", DS, ff(hk, "A", "haiku vs nemotron"), [DECK])
same("reps", {x["replications"] for x in dsx if x["kind"] != "null"} | {1000}, {1000})

# --- FLARE (SYNTHETIC, simulator) --------------------------------------------------------------------
fs = J("data/flare/summary.json")
e12, ea = fs["equivalence"]["none-p12"], fs["equivalence"]["age_band-p12"]
same("FLARE success", (e12["success"], ea["success"], ea["suppressed_sets_identical"]), (True, True, True))
fact("FLARE cells", "flare summary none-p12", f"{e12['cells_ok']} of {e12['cells']}", [DECK, NV, PTS, CLOCK, VERDA])
same("FLARE suppressed equal", ea["cells_suppressed_central"], ea["cells_suppressed_flare"])
fact("FLARE suppressed", "flare summary age_band-p12", f"same {ea['cells_suppressed_flare']} small cells", [DECK])
same("FLARE within 1e-6", max(e12["max_abs_diff_mean_log"], e12["max_abs_diff_sd_log"]) < 1e-6, True)

# --- comparability gate on the clock (data/flare/gate-v1.json, SYNTHETIC) --------------------------
gt = J("data/flare/gate-v1.json")
same("gate synthetic", (gt["synthetic"], gt["label"]), (True, "SYNTHETIC"))
same("gate clock", (gt["clock"]["start_event"], gt["clock"]["end_event"], gt["clock"]["threshold_days"],
                    gt["clock"]["threshold_label"]), ("REFERRAL_SENT", "TREATMENT_START", 42, "placeholder (OECD/EU-reported target)"))
gs = gt["summary"]
fact("gate raw", "gate-v1 summary.raw", f"**{gs['raw']['not_comparable']} of {gs['raw']['of']}**", [DECK, CLOCK])
fact("gate resolver", "gate-v1 summary.resolver", f"**{gs['resolver']['not_comparable']} of {gs['resolver']['of']}**", [DECK, CLOCK])
fact("gate raw plain", "gate-v1 summary.raw", f"{gs['raw']['not_comparable']} of {gs['raw']['of']}", [PTS, NV])
fact("gate resolver plain", "gate-v1 summary.resolver", f"{gs['resolver']['not_comparable']} of {gs['resolver']['of']}", [PTS, NV])
geq = gt["flare"]["equivalence"]
same("gate FLARE success", (gt["flare"]["ran"], geq["success"], geq["suppressed_sets_identical"]), (True, True, True))
fact("gate FLARE cells", "gate-v1 flare.equivalence", f"{geq['cells_ok']} of {geq['cells']}", [DECK, CLOCK, PTS, NV])
fact("gate limits", "gate-v1 rule", f"median bias above {f(gt['rule']['bias_limit_days'], 0)} days, or more than "
     f"{f(100 * gt['rule']['missed_limit'], 0)}% of events missed", [DECK, CLOCK])
fact("gate edge", "gate-v1 clock", f"{gt['clock']['histogram_edge_days']} days", [DECK, CLOCK])
nn = [c_["notes"] for c_ in gt["counties"]]
fact("gate notes per county", "gate-v1 counties", f"{min(nn)}-{max(nn)} notes each", [DECK])
same("gate real data: only Pirkanmaa can see its stage", [a_["area"].split()[0] for a_ in gt["realData"]["areas"] if a_["canSee"]], ["Pirkanmaa"])
same("gate real data aim", gt["realData"]["aim_pct"], V("syopajarjestot-2026-stage-completeness")["aim"])

# --- safety net (data/safetynet/safetynet-v1.json, SYNTHETIC) ---------------------------------------
sn = J("data/safetynet/safetynet-v1.json")
same("safety net synthetic", (sn["synthetic"], sn["dataClass"], sn["pilotRegionId"]), (True, "SYNTHETIC", "HVA06"))
thr = {t_["clock"]: t_ for t_ in sn["thresholds"]}
trig = next(t_ for t_ in sn["thresholds"] if "worklist trigger" in t_["clock"])
same("worklist trigger", (trig["days"], trig["label"]), (42, "PLACEHOLDER"))
same("worklist sensitivity", next(t_["days"] for t_ in sn["thresholds"] if "sensitivity" in t_["clock"]), 90)
sc = next(c_ for c_ in sn["counties"] if c_["regionId"] == "HVA06")["counts"]
same("pilot overdue adds up", sc["imaging"]["overdue"] + sc["referral"]["overdue"], sc["overdue"])
fact("pilot loops", "safetynet HVA06", f"**{sc['open_loops']}** open loops, **{sc['overdue']}**", [DECK])
fact("pilot imaging overdue", "safetynet HVA06", f"**{sc['imaging']['overdue']}** imaging follow-ups", [DECK])
fact("pilot referral overdue", "safetynet HVA06", f"**{sc['referral']['overdue']}** referrals", [DECK])
fact("pilot awaiting person", "safetynet HVA06", f"**{sc['imaging']['awaiting_person']}** written recommendations", [DECK])
fact("pilot overdue plain", "safetynet HVA06", f"{sc['overdue']} overdue items among {sc['open_loops']} open loops", [ZERO])
fact("pilot overdue short", "safetynet HVA06", f"{sc['overdue']} overdue of {sc['open_loops']} open loops", [PTS, VIDEO])
same("replay date", sn["asOf"], "2025-12-01")
fact("replay date", "safetynet asOf", "as of 1 December 2025", [DECK])
rm = sn["rule"]["metrics"]
same("rule all correct", (rm["all_correct"]["k"], rm["all_correct"]["n"]), (rm["lines"], rm["lines"]))
fact("rule lines", "safetynet rule.metrics", f"{rm['all_correct']['k']} of {rm['all_correct']['n']}", [DECK, PTS])
gc = rm["gold_counts"]
fact("rule line mix", "safetynet rule.metrics", f"{gc['DUE_DATE']} due dates, {gc['PERSON']} vague or conditional lines sent to a person, "
     f"{gc['NONE']} lines with no follow-up", [DECK])
nat = sn["national"]
fact("safety net national", "safetynet national", f"**{thousands(nat['open_loops'])}** open loops, **{nat['overdue']}** overdue", [DECK])
fact("safety net sensitivity", "safetynet national", f"{nat['referral']['overdue_at_sensitivity_days']} referrals", [DECK])

# --- Nemotron reader --------------------------------------------------------------------------------
rd = J("data/scribe/nemotron/reader-v1.json")
val = rd["validation"]
for ver in ("v0", "v1", "v2", "v2g", "v3"):
    em_ = val[ver]["exact_match"]
    fact(f"val {ver}", "reader-v1", f"{em_['k']}/{em_['n']}", [DECK, NV])
    fact(f"val {ver} wilson", "reader-v1", f"({wilson(em_['k'], em_['n'])})", [NV])
    fact(f"val {ver} pct", "reader-v1", pct(em_["k"], 310), [NV, DECK])
lad = rd["validation_ladder"]
for ver in ("v0", "v1", "v1rep", "v2", "v2g", "v3"):
    x = val[ver]
    fact(f"form row {ver}", "reader-v1", f"| {x['parse_failures_final']} | {x['tokens_per_note']['completion']} | "
         f"{f(x['latency_seconds']['mean'], 2)} |", [NV])
for step in ("v1->v2", "v2->v2g"):
    x = lad[step]
    fact(f"form change {step}", "reader-v1", f"+{f(x['change_points'], 1)} pts, {x['gained']} fixed, {x['lost']} worse, "
         f"p = {f(x['mcnemar_exact_p'], 2)}", [NV])
hl = rd["validation_ladder_haiku_written"]
fact("haiku ladder", "reader-v1", ", ".join(str(n) for n in (hl["v0->v1"]["before"], hl["v0->v1"]["after"], hl["v1->v2"]["after"],
                                                             hl["v2->v2g"]["after"], hl["v2g->v3"]["after"])), [NV])
rl = rd["validation_ladder_relative_dates"]
fact("relative ladder all", "reader-v1", ", ".join(str(n) for n in (rl["v0->v1"]["before"], rl["v0->v1"]["after"], rl["v1->v2"]["after"],
                                                                    rl["v2->v2g"]["after"], rl["v2g->v3"]["after"])), [NV])
tex = rd["test"]["error_events_by_class"]
fact("test errors", "reader-v1", f"{tex['wrong_type']} wrong event types and {tex['wrong_date']} wrong date", [NV])
fact("test latency", "reader-v1", f"{f(rd['test']['latency_seconds']['mean'], 2)} s per note", [NV])
fact("v0->v1", "reader-v1", f"+{f(lad['v0->v1']['change_points'], 1)} points", [DECK, NV])
fact("v0->v1 fixed", "reader-v1", f"{lad['v0->v1']['gained']} fixed, {lad['v0->v1']['lost']} worse", [DECK])
fact("v2g->v3", "reader-v1", f"+{f(lad['v2g->v3']['change_points'], 1)} points", [DECK, NV])
fact("v2g->v3 fixed", "reader-v1", f"{lad['v2g->v3']['gained']} fixed, {lad['v2g->v3']['lost']} worse", [DECK, NV])
fact("v2g->v3 p", "reader-v1", f"p = {f(lad['v2g->v3']['mcnemar_exact_p'], 5)}", [DECK, NV])
rep = lad["v1->v1rep"]
fact("noise floor", "reader-v1", f"{rep['gained'] + rep['lost']} notes", [DECK, NV])
same("noise floor split", (rep["gained"], rep["lost"]), (6, 6))
same("parse failures v1 v2", (val["v1"]["parse_failures_final"], val["v2"]["parse_failures_final"]), (11, 3))
fact("relative ladder", "reader-v1", f"{rl['v0->v1']['before']}/166", [DECK])
fact("relative v3", "reader-v1", f"{rl['v0->v3']['after']}/166", [DECK])
te = rd["test"]
fact("test v3", "reader-v1", f"{te['exact_match']['k']}/{te['exact_match']['n']}", [DECK, NV, VERDA])
fact("test v3 wilson", "reader-v1", wilson(te['exact_match']['k'], te['exact_match']['n']), [DECK, NV])
fact("test v3 haiku", "reader-v1", f"{te['by_writer']['haiku_written']['k']}/200", [DECK, NV])
fact("test v3 nemotron", "reader-v1", f"{te['by_writer']['nemotron_written']['k']}/500", [DECK, NV])
fact("test v3 relative", "reader-v1", f"{te['relative_date_slice']['has_relative_date']['k']}/367", [NV])
fact("v3 tokens", "reader-v1", thousands(r(val["v3"]["tokens_per_note"]["completion"], 0)), [DECK, NV])
fact("v2g tokens", "reader-v1", f"{f(val['v2g']['tokens_per_note']['completion'], 0)} output tokens", [DECK, NV])
fact("v3 seconds", "reader-v1", f"{f(val['v3']['latency_seconds']['mean'], 2)} s", [DECK, NV])
same("requests ledger", rd["requests_ledger"], J("data/scribe/nemotron/ledger.json")["requests"])
reqs = jsonl("data/scribe/nemotron/requests.jsonl")
same("request errors", collections.Counter(x["status"] for x in reqs), collections.Counter({"ok": 2602}))
fact("reader requests", "requests.jsonl", thousands(len(reqs)), [DECK, NV, VERDA])
ca = J("data/scribe/nemotron/cascade-agreement-v1.json")
ct, cvv = ca["test"]["all"], ca["val"]["all"]
fact("cascade prefilled", "cascade-agreement", f"{ct['prefilled_for_one_click_confirmation']['k']}/700", [DECK, NV, VERDA, PTS])
ew = ct["error_among_prefilled"]
fact("cascade wrong", "cascade-agreement", f"{ew['k']} ({pct(ew['k'], ew['n'])}, Wilson {wilson(ew['k'], ew['n'])})", [DECK])
fact("cascade needs editing", "cascade-agreement", f"**{ct['flagged_needs_editing']['k']}** need editing", [DECK])
fact("cascade nemotron exact flagged", "cascade-agreement", f"| {cvv['flagged_where_nemotron_answer_is_exact']['k']} | {ct['flagged_where_nemotron_answer_is_exact']['k']} |", [DECK, NV])
fact("cascade per 100", "cascade-agreement", f"| {cvv['per_100_notes_prefilled_correct']} | {ct['per_100_notes_prefilled_correct']} |", [DECK, NV])
fact("cascade val", "cascade-agreement", f"{cvv['prefilled_for_one_click_confirmation']['k']}/310", [DECK, NV])
hw = ca["test"]["by_writer"]["haiku_written"]
fact("cascade haiku", "cascade-agreement", f"{hw['prefilled_for_one_click_confirmation']['k']}/200 pre-filled, {hw['error_among_prefilled']['k']} wrong", [DECK, NV])
same("agreed wrong", ca["test"]["agreed_but_wrong_differences"], {"wrong_type:REFERRAL_RECEIVED->REFERRAL_SENT:nemotron_written": 4})
sv = J("data/scribe/v3/summary-v1.json")
fact("baseline cascade slash", "summary-v1 cascade.jev.5pct", f"{sv['cascade.jev.5pct.test_pooled.coverage.n']}/700 with {sv['cascade.jev.5pct.test_pooled.error_among_accepted.n']} errors", [DECK])
fact("baseline cascade nvidia", "summary-v1 cascade.jev.5pct", f"{sv['cascade.jev.5pct.test_pooled.coverage.n']}/700 in the", [NV])
fact("teacher readback", "summary-v1", f"{thousands(sv['teacher.overall.code_check_pass_final.n'])} notes passed the code check and {thousands(sv['teacher.overall.readback_consistent_final.n'])}", [NV])
fact("gate accepted", "summary-v1", f"accepted {thousands(sv['gate.overall.rule_accepted_of_judged.n'])}", [NV])
t2 = [x for x in jsonl("runs/teacher2.jsonl") if x["step"] == "teacher_run" and x["metrics"]["specifications"] == 1600][0]["metrics"]
fact("teacher main run", "runs/teacher2.jsonl", f"{thousands(t2['teacher_requests_this_run'])} requests in {t2['wall_seconds']} s", [NV, VERDA])
fact("teacher rate", "runs/teacher2.jsonl", f(t2["teacher_requests_this_run"] / t2["wall_seconds"], 1), [NV, VERDA])
pf = J("data/scribe/nemotron/preflight-v1.json")
same("preflight", (pf["tool_call"]["ok"], pf["tool_call"]["name"], pf["tool_call"]["arguments"]["n"], pf["tool_call"]["arguments"]["unit"],
                   pf["thinking"]["parsed"], pf["thinking"]["exact"], pf["thinking"]["separate_reasoning_field"]),
     (True, "resolve_relative_date", 3, "weeks", True, True, True))

# --- Nemotron county planner and vision test -------------------------------------------------------
pl = J("data/planner/plans-v1.json")
ps = pl["summary"]
same("planner outcomes", (ps["counties"], ps["outcomes"].get("PLAN")), (23, 23))
fact("planner plans", "plans-v1 summary", f"{ps['outcomes']['PLAN']} of {ps['counties']}", [DECK, NV, VERDA])
fact("planner kept", "plans-v1 summary", f"{ps['keptSentences']} of {ps['sentences']}", [DECK, NV, VERDA])
fact("planner kept slash", "plans-v1 summary", f"{ps['keptSentences']}/{ps['sentences']}", [NV])
pv1 = ps["promptComparison"]["v1"]
fact("planner v1 kept", "plans-v1 promptComparison", f"{pv1['keptSentences']}/{pv1['sentences']}", [DECK, NV])
same("planner unmatched numbers", (ps["keptSentencesWithUnmatchedNumber"], ps["sentencesFailingNumberCheck"]), (0, 0))
fact("planner unmatched", "plans-v1 summary", f"**{ps['keptSentencesWithUnmatchedNumber']}** with a number", [DECK])
ol = ps["offLimits"]
fact("planner off-limits", "plans-v1 offLimits", f"{ol['pass']} of {ol['prompts']}", [NV])
fact("planner refused", "plans-v1 offLimits", f"refused {ol['refusedByModel']}", [DECK, NV])
fact("planner without the post hoc guard", "plans-v1 offLimits", f"Without it, {ol['passWithoutCodeGuard']} of {ol['prompts']}", [DECK, NV])
same("planner blocked by code", ol["blockedByCode"], 1)
fact("planner roadmap ids", "plans-v1 summary", ps["roadmapMeasureCodeChecked"], [DECK, NV])
ind_v1, ind_v2 = pv1["keptByField"]["indicator"], ps["keptByField"]["indicator"]
fact("planner indicator v1", "plans-v1", f"{ind_v1['kept']} of {ind_v1['n']} indicator lines", [NV])
fact("planner indicator v1 deck", "plans-v1", f"indicator lines {ind_v1['kept']}/{ind_v1['n']}", [DECK])
fact("planner indicator v2", "plans-v1", f"indicator lines {ind_v2['kept']} of {ind_v2['n']}", [NV])
fact("planner gate v1", "plans-v1 gateV1Comparison", f"against {ps['gateV1Comparison']['keptV1']}", [NV])
nu = ps["nemotronUsage"]
fact("planner calls", "plans-v1 nemotronUsage", f"{nu['calls']} Nemotron calls", [DECK, NV])
fact("planner tokens", "plans-v1 nemotronUsage", f"{thousands(nu['prompt_tokens'])} prompt and {thousands(nu['completion_tokens'])} completion tokens", [NV])
fact("planner jev", "plans-v1 jev", "USD " + f(ps["jev"]["cost_usd"], 4), [DECK, NV])
fact("planner ledger", "data/planner/ledger.json", f"{J('data/planner/ledger.json')['requests']} planner requests", [VERDA])
vs = J("data/planner/vision/vision-6b-v1.json")["summary"]
fact("vision image exact", "vision-6b summary", f"{vs['image_exact']} of {vs['notes']}", [DECK, NV])
fact("vision text exact", "vision-6b summary", f"{vs['text_exact']} of {vs['notes']}", [DECK, NV])
fact("vision table", "vision-6b summary", f"| {vs['image_exact']}/{vs['notes']} | {vs['text_exact']}/{vs['notes']} |", [NV])
rd_ = vs["relative_date_notes"]
fact("vision relative", "vision-6b summary", f"| {rd_['image']}/{rd_['n']} | {rd_['text']}/{rd_['n']} |", [NV])
fact("vision latency", "vision-6b summary", f"| {vs['mean_latency_s']['image']} | {vs['mean_latency_s']['text']} |", [NV])
tr = vs["transcription"]
fact("vision umlaut", "vision-6b transcription", f"{tr['notes_with_umlaut_misread']} of {tr['notes']}", [NV])
fact("vision dates", "vision-6b transcription", f"date string changed on {tr['notes_with_date_misread']} of {tr['notes']}", [NV])
same("vision verdict", vs["verdict"], "tested, not good enough yet")

# --- genomics, event log, export scans -------------------------------------------------------------
gh = J("data/genomics/brca1-evo2-v1.json")["runtime"]
fact("evo2 scored", "brca1-evo2 runtime", f"{thousands(gh['n_scored'])}", [VERDA])
fact("evo2 seconds", "brca1-evo2 runtime", f"{f(gh['score_seconds_this_run'], 0)} s", [VERDA])
same("evo2 cap", gh["cap_gib"], 16.0)
elf = [x for x in jsonl("runs/eventlog-fix.jsonl") if x["step"] == "calibrate_interval_log_sd"][0]["metrics"]
fact("calibration episodes", "runs/eventlog-fix.jsonl", thousands(elf["episodes"]), [PTS])
fact("calibration seconds", "runs/eventlog-fix.jsonl", f(elf["elapsed_seconds"], 1) + " s", [PTS])
mine = jsonl("runs/laneC-step10.jsonl") if os.path.exists(os.path.join(ROOT, "runs/laneC-step10.jsonl")) else []
scan = {x["step"]: x["metrics"] for x in mine}
if "export_scan" in scan:
    s_ = scan["export_scan"]
    fact("gitleaks findings", "runs/laneC-step10.jsonl", f"**{s_['gitleaks_findings']} findings, all false positives**", [EXP])
    fact("value scan files", "runs/laneC-step10.jsonl", thousands(s_["value_scan_files_scanned"]) + " files", [EXP])
    fact("home paths", "runs/laneC-step10.jsonl", f"**{s_['files_with_home_path']} files**", [EXP])
    fact("first name", "runs/laneC-step10.jsonl", f"**{s_['files_with_owner_first_name']} files**", [EXP])
    same("value scan hits", s_["value_scan_files_with_a_value"], 0)
    same("emails", s_["files_with_email"], 0)
else:
    failures.append("runs/laneC-step10.jsonl has no export_scan step")

# --- frozen stress set and recalibrated cascade (Lane A step 8, filled by the integrator 15 Nov) -----
_E = "data/scribe/v4/eval/results-v1.json"
_ev = J(_E)
_pr, _st = _ev["primary_result"], _ev["sets"]["stress"]["systems"]
same("stress primary verdict", (_pr["met"], _pr["A_prime_wins"]), (False, False))
fact("stress held-out, B", _E, f"**{_pr['b_correct']} of {_pr['n']}**", [GEM, DECK])
fact("stress held-out, A'", _E, f"**{_pr['a_correct']} of {_pr['n']}**", [GEM, DECK])
fact("stress held-out, B vs A' (appendix)", _E, f"B {_pr['b_correct']} of {_pr['n']} against A' {_pr['a_correct']} of {_pr['n']}", [DECK])
fact("stress McNemar p", _E, f"p = {_pr['exact_mcnemar_p']:.5f}", [GEM, DECK])
fact("stress difference, points", _E, f"+{f(_pr['difference_b_minus_a_points'], 1)} points", [GEM, DECK])
_bs = _pr["B_standard_slice"]
fact("stress standard slice, B (appendix)", _E, f"B {_bs['k']} of {_bs['n']} ({pct(_bs['k'], _bs['n'])})", [DECK])
fact("stress standard slice, B", _E, f"{_bs['k']} of {_bs['n']}", [GEM])
fact("stress held-out, C", _E, f"{_st['C']['slices']['heldout']['k']} of {_pr['n']}", [GEM, DECK])
fact("stress held-out, Nemotron", _E, f"Nemotron {_st['nemotron']['slices']['heldout']['k']} of {_pr['n']}", [GEM])
_vf = _st["A'"]["vague_outcome"]
fact("vague, A' to a person", _E, f"A' sends {_vf['sent_to_person']['k']} of {_vf['facts']} to a person", [GEM])
fact("vague, B invents", _E, f"invents a precise date for {_st['B']['vague_outcome']['invented_precise_date']['k']} of {_vf['facts']}", [GEM])
fact("stress notes", _E, f"{_ev['sets']['stress']['notes']} notes", [GEM, DECK])
_t = _ev["sets"]["test"]["systems"]
_ta, _tb = _t["A'"]["exact_match"]["k"], _t["B"]["exact_match"]["k"]
fact("test post hoc, A' and B", _E, f"A' got\n  {_ta} and B {_tb}", [DECK])
_c = [x for x in _ev["cascade"]["configurations"] if x["gemma"] == _ev["cascade"]["chosen"]["gemma"] and x["signal"] == _ev["cascade"]["chosen"]["signal"]][0]
_a = [x for x in _ev["cascade"]["configurations"] if x["gemma"] == _c["gemma"] and x["signal"] == "gemma_confidence_alone"][0]
same("cascade chosen", (_c["gemma"], _c["signal"]), ("C", "agreement"))
_ct, _cs = _c["test"], _c["stress"]
fact("cascade test pre-filled", _E, f"{_ct['prefilled_for_one_click_confirmation']['k']} of {_ct['notes']}", [GEM, DECK])
fact("cascade test wrong", _E, f"{_ct['error_among_prefilled']['k']} wrong", [GEM, DECK])
fact("cascade stress pre-filled", _E, f"{_cs['prefilled_for_one_click_confirmation']['k']} of {_cs['notes']}", [GEM, DECK])
fact("cascade stress wrong", _E, f"{_cs['error_among_prefilled']['k']} wrong", [GEM, DECK])
fact("confidence alone on stress", _E, f"{_a['stress']['prefilled_for_one_click_confirmation']['k']} of {_a['stress']['notes']} with {_a['stress']['error_among_prefilled']['k']} wrong", [GEM])

# --- wording, labels, video length, placeholders ---------------------------------------------------
for d, txt in TEXT.items():
    low = txt.lower()
    for b_ in BANNED:
        if b_ in low:
            failures.append(f"{d}: banned wording '{b_}'")
    if d != EXP:
        for b_ in RETIRED:
            if b_ in txt:
                failures.append(f"{d}: retired wording '{b_}' (see BIG_PICTURE.md section 2.2)")
    if "SYNTHETIC" not in txt:
        failures.append(f"{d}: no SYNTHETIC label")
    if "42 days" in txt or "42-day" in txt:
        if "placeholder" not in low:
            failures.append(f"{d}: a 42-day threshold without the word placeholder")
for d in (DECK, VIDEO):
    if PROMISE not in TEXT[d]:
        failures.append(f"{d}: promise line missing")
if "Finnish notes only" not in TEXT[DECK] or "other languages go to manual entry" not in TEXT[DECK]:
    failures.append("DECK.md: language scope line missing")
if "placeholder (OECD/EU-reported target)" not in TEXT[DECK] or "Placeholder (OECD/EU-reported target)" not in TEXT[CLOCK]:
    failures.append("DECK.md / PATHWAY_CLOCK.md: 42-day threshold not labelled 'placeholder (OECD/EU-reported target)'")
slides = re.findall(r"^## Slide (\d+)\.", TEXT[DECK], re.M)
if len(slides) > 12:
    failures.append(f"DECK.md: {len(slides)} slides, limit 12")
vo = []
for line in TEXT[VIDEO].splitlines():
    if re.match(r"^\| \d:\d\d-\d:\d\d \|", line):
        vo.append(line.split("|")[3].replace("STRESS:", "").replace("(silence)", ""))
words = len(" ".join(vo).split())
max_words = int(WORDS_PER_SECOND * MAX_SECONDS)
if words > max_words:
    failures.append(f"VIDEO_SCRIPT.md: {words} spoken words, limit {max_words}")
post = "\n".join(line[2:] if line.startswith("> ") else line[1:] for line in TEXT[VERDA].splitlines() if line.startswith(">"))
if len(post) >= 2000:
    failures.append(f"VERDA_DISCORD.md: post is {len(post)} characters, limit 2000")
pending = collections.OrderedDict()
for d, txt in TEXT.items():
    for m in re.finditer(r"\[(?:[A-Z][A-Z0-9 ]+ )?PENDING: ([^\]]+)\]", txt):
        pending.setdefault(m.group(0), set()).add(d)
pend_out = []
for ph, ds_ in pending.items():
    paths = re.findall(r"((?:data|runs|scribe|src)/[\w./*-]+)", ph)
    exists = {p_: bool(glob.glob(os.path.join(ROOT, p_))) for p_ in paths}
    pend_out.append({"placeholder": ph, "docs": sorted(ds_), "files_exist_now": exists})

summary = {"facts_checked": len(facts), "docs": DOCS, "slides": len(slides), "video_spoken_words": words,
           "video_word_limit": max_words, "verda_post_chars": len(post), "evidence_rows": len(ev),
           "pending_placeholders": pend_out, "failures": failures}
if "--json" in sys.argv:
    print(json.dumps(summary, ensure_ascii=False))
else:
    print(f"facts checked: {len(facts)}; slides: {len(slides)}; video spoken words: {words} (limit {max_words}); "
          f"verda post: {len(post)} chars; evidence rows: {len(ev)}")
    for p_ in pend_out:
        print("PENDING", p_["placeholder"], "in", ",".join(p_["docs"]), "files now:", p_["files_exist_now"])
    for x in failures:
        print("FAIL", x)
    print("OK" if not failures else f"{len(failures)} failure(s)")
sys.exit(1 if failures else 0)
