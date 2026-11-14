#!/usr/bin/env python3
"""Reproducible public-data snapshot for the Care Equity Navigator.

Fetches only open, aggregate, licensed statistics. No patient-level data, no
credentials. Every series in the snapshot carries its source id, request URL,
licence, retrieval time and the SHA-256 of the raw response it was parsed from.

Sources
  THL Sotkanet REST API ............ https://sotkanet.fi/rest/1.1   (CC BY 4.0)
  Statistics Finland PxWeb (StatFin)  https://pxdata.stat.fi         (CC BY 4.0)
  NORDCAN 2.0 (IARC / ANCR) ........ https://nordcan.iarc.who.int    (citation required)

Usage:  python3 pipeline/fetch_public_data.py [--out data/snapshot/public-v1.json]
Stdlib only; Python >= 3.10.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

UA = "care-equity-navigator/1.0"
SOTKA = "https://sotkanet.fi/rest/1.1"
STATFIN = "https://pxdata.stat.fi/PXWeb/api/v1/fi/StatFin"
NORDCAN = "https://canapi.iarc.who.int/api/nordcan/v2/961"

YEARS = list(range(2015, 2026))
MORTALITY_WINDOW = ["2021", "2022", "2023", "2024", "2025"]
PROJECTION_YEARS = ["2024", "2030", "2035", "2040"]

# Sotkanet indicators. stage = where on the cancer pathway the indicator speaks.
# direction: +1 higher is better, -1 higher is worse, 0 context only.
SOTKA_INDICATORS = {
    3621: dict(key="screen_breast", stage="detection", direction=1, unit="%", target=80.0),
    3620: dict(key="screen_cervix", stage="detection", direction=1, unit="%", target=80.0),
    6103: dict(key="screen_colorectal", stage="detection", direction=1, unit="%", target=80.0),
    6411: dict(key="gp_wait_over_7d", stage="primary_care", direction=-1, unit="%", target=None),
    6410: dict(key="gp_wait_over_3m", stage="primary_care", direction=-1, unit="%", target=None),
    13: dict(key="referral_handled_3d", stage="referral", direction=1, unit="%", target=None),
    5033: dict(key="referral_handled_over_21d", stage="referral", direction=-1, unit="%", target=None),
    3336: dict(key="specialist_wait_over_6m", stage="referral", direction=-1, unit="per 10 000", target=None),
    3054: dict(key="private_referral_share", stage="route", direction=0, unit="%", target=None),
    3051: dict(key="health_centre_referral_share", stage="route", direction=0, unit="%", target=None),
    3626: dict(key="cervix_5y_survival", stage="outcome", direction=1, unit="%", target=None),
    5643: dict(key="cancer_index", stage="need", direction=0, unit="index (FI=100)", target=None),
    5641: dict(key="morbidity_index", stage="need", direction=0, unit="index (FI=100)", target=None),
    5659: dict(key="alcohol_morbidity_index", stage="need", direction=0, unit="index (FI=100)", target=None),
    180: dict(key="education_index", stage="ses", direction=0, unit="index", target=None),
    181: dict(key="unemployment", stage="ses", direction=0, unit="%", target=None),
    3099: dict(key="low_income", stage="ses", direction=0, unit="%", target=None),
    1068: dict(key="age_65_plus", stage="need", direction=0, unit="%", target=None),
    127: dict(key="population", stage="need", direction=0, unit="persons", target=None),
    5102: dict(key="foreign_background", stage="ses", direction=0, unit="per 1 000", target=None),
}

# Statistics Finland time-series cause-of-death classes (table 13u5 / 11az).
CANCER_SITES = {
    "04-21": dict(key="all_cancers", label="All cancers (C00-C97)"),
    "11": dict(key="lung", label="Larynx, trachea and lung (C32-C34)"),
    "07": dict(key="colon", label="Colon (C18-C19)"),
    "08": dict(key="rectum", label="Rectum and anus (C20-C21)"),
    "13": dict(key="breast", label="Breast (C50)"),
    "10": dict(key="pancreas", label="Pancreas (C25)"),
    "09": dict(key="liver", label="Primary liver (C22)"),
    "17": dict(key="prostate", label="Prostate (C61)"),
    "14": dict(key="cervix", label="Cervix uteri (C53)"),
    "20": dict(key="haematological", label="Lymphoid and haematopoietic (C81-C96)"),
}

NORDCAN_CANCERS = {160: "lung", 130: "pancreas", 110: "liver", 520: "colorectal", 180: "breast", 240: "prostate", 990: "all_sites_excl_nmsc"}
NORDCAN_COUNTRIES = {246: "Finland", 752: "Sweden", 578: "Norway", 208: "Denmark"}

AGE_GROUPS = ["0-4", "5-9", "10-14", "15-19", "20-24", "25-29", "30-34", "35-39", "40-44", "45-49",
              "50-54", "55-59", "60-64", "65-69", "70-74", "75-79", "80-84", "85-89", "90-94", "95-"]


class Fetcher:
    def __init__(self) -> None:
        self.manifest: list[dict] = []

    def get(self, url: str, source: str, body: dict | None = None, retries: int = 4):
        data = json.dumps(body).encode() if body is not None else None
        headers = {"User-Agent": UA, "Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        last: Exception | None = None
        for attempt in range(retries):
            try:
                req = urllib.request.Request(url, data=data, headers=headers)
                with urllib.request.urlopen(req, timeout=90) as resp:
                    raw = resp.read()
                self.manifest.append({
                    "source": source,
                    "url": url,
                    "method": "POST" if data is not None else "GET",
                    "query": body,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "bytes": len(raw),
                    "retrievedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                })
                return json.loads(raw)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:  # noqa: PERF203
                last = exc
                time.sleep(2 + 3 * attempt)
        raise RuntimeError(f"failed to fetch {url}: {last}")


def jsonstat_cells(js: dict):
    """Yield (dict of dimension code -> category code, value) for a json-stat2 dataset."""
    ids = js["id"]
    sizes = js["size"]
    cats = []
    for d in ids:
        index = js["dimension"][d]["category"]["index"]
        ordered = sorted(index, key=index.get) if isinstance(index, dict) else list(index)
        cats.append(ordered)
    values = js["value"]
    total = 1
    for s in sizes:
        total *= s
    strides = []
    acc = total
    for s in sizes:
        acc //= s
        strides.append(acc)
    for flat in range(total):
        v = values[flat] if isinstance(values, list) else values.get(str(flat))
        coord = {}
        rem = flat
        for d, stride, cat in zip(ids, strides, cats):
            coord[d] = cat[rem // stride]
            rem %= stride
        yield coord, v


def age_group_of(single: str) -> str:
    a = int(single.rstrip("-"))
    if a >= 95:
        return "95-"
    lo = (a // 5) * 5
    return f"{lo}-{lo + 4}"


def statfin_age_to_group(code: str) -> str | None:
    if code in ("000", "1-4"):
        return "0-4"
    if code in ("SSS", "0-14", "15-64", "65-"):
        return None
    return code.replace(" ", "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/snapshot/public-v1.json")
    args = ap.parse_args()
    root = Path(__file__).resolve().parent.parent
    out_path = (root / args.out).resolve()
    f = Fetcher()

    # ---------------------------------------------------------------- regions
    regions_raw = f.get(f"{SOTKA}/regions", "thl-sotkanet")
    by_id = {r["id"]: r for r in regions_raw}
    hva = sorted((r for r in regions_raw if r["category"] == "HYVINVOINTIALUE"), key=lambda r: r["code"])
    country = next(r for r in regions_raw if r["category"] == "MAA")
    region_key = {r["id"]: f"HVA{r['code']}" for r in hva}
    muni_to_hva: dict[str, str] = {}
    for r in regions_raw:
        if r["category"] != "KUNTA":
            continue
        parents = [p for p in r.get("memberOf", []) if p in region_key]
        if len(parents) == 1:
            muni_to_hva[f"KU{r['code']}"] = region_key[parents[0]]
    regions = [
        {
            "id": region_key[r["id"]],
            "sotkanetId": r["id"],
            "code": r["code"],
            "nameFi": r["title"].get("fi"),
            "nameEn": r["title"].get("en") or r["title"].get("fi"),
            "nameSv": r["title"].get("sv"),
            "municipalities": sorted(k for k, v in muni_to_hva.items() if v == region_key[r["id"]]),
        }
        for r in hva
    ]

    # ------------------------------------------------------------- indicators
    indicators = {}
    year_q = "&".join(f"years={y}" for y in YEARS)
    for ind_id, spec in SOTKA_INDICATORS.items():
        meta = f.get(f"{SOTKA}/indicators/{ind_id}", "thl-sotkanet")
        url = f"{SOTKA}/json?indicator={ind_id}&{year_q}&genders=total"
        rows = f.get(url, "thl-sotkanet")
        values: dict[str, dict[str, float]] = {}
        abs_values: dict[str, dict[str, float]] = {}
        national: dict[str, float] = {}
        for row in rows:
            if row.get("gender") != "total" or row.get("value") is None:
                continue
            y = str(row["year"])
            if row["region"] == country["id"]:
                national[y] = row["value"]
            elif row["region"] in region_key:
                values.setdefault(region_key[row["region"]], {})[y] = row["value"]
                if row.get("absValue") is not None:
                    abs_values.setdefault(region_key[row["region"]], {})[y] = row["absValue"]
        indicators[spec["key"]] = {
            **spec,
            "sotkanetId": ind_id,
            "titleFi": meta["title"].get("fi"),
            "titleEn": meta["title"].get("en") or meta["title"].get("fi"),
            "organization": (meta.get("organization") or {}).get("title", {}).get("fi"),
            "dataUpdated": meta.get("data-updated"),
            "sourceId": "thl-sotkanet",
            "requestUrl": url,
            "indicatorPage": f"https://sotkanet.fi/sotkanet/fi/metadata/indicators/{ind_id}",
            "values": values,
            "absValues": abs_values,
            "national": national,
        }

    # ------------------------------------------------- population by age (14wx)
    pop_url = f"{STATFIN}/vaenn/14wx.px"
    pop_meta = f.get(pop_url, "statfin")
    area_var = next(v for v in pop_meta["variables"] if v["code"].startswith("alue"))
    age_var = next(v for v in pop_meta["variables"] if v["code"].startswith("ika"))
    sex_var = next(v for v in pop_meta["variables"] if v["code"].startswith("sukupuoli"))
    single_ages = [a for a in age_var["values"] if a != "SSS"]
    population: dict[str, dict[str, dict[str, float]]] = {}
    national_pop: dict[str, dict[str, float]] = {}
    unmapped: set[str] = set()
    for year in PROJECTION_YEARS:
        body = {
            "query": [
                {"code": area_var["code"], "selection": {"filter": "item", "values": area_var["values"]}},
                {"code": "timeperiod_y", "selection": {"filter": "item", "values": [year]}},
                {"code": sex_var["code"], "selection": {"filter": "item", "values": ["SSS"]}},
                {"code": age_var["code"], "selection": {"filter": "item", "values": single_ages}},
            ],
            "response": {"format": "json-stat2"},
        }
        js = f.get(pop_url, "statfin", body)
        for coord, v in jsonstat_cells(js):
            if v is None:
                continue
            area = coord[area_var["code"]]
            g = age_group_of(coord[age_var["code"]])
            if area == "SSS":
                national_pop.setdefault(year, {}).setdefault(g, 0.0)
                national_pop[year][g] += v
                continue
            region = muni_to_hva.get(area)
            if region is None:
                unmapped.add(area)
                continue
            population.setdefault(region, {}).setdefault(year, {}).setdefault(g, 0.0)
            population[region][year][g] += v

    # ------------------------------- national deaths by cancer site and age (11az)
    nat_url = f"{STATFIN}/ksyyt/11az.px"
    nat_meta = f.get(nat_url, "statfin")
    nat_cause = next(v for v in nat_meta["variables"] if v["code"].startswith("kuolinsyyt"))
    nat_age = next(v for v in nat_meta["variables"] if v["code"].startswith("ika"))
    nat_sex = next(v for v in nat_meta["variables"] if v["code"].startswith("sukupuoli"))
    window = [y for y in MORTALITY_WINDOW if y in next(v for v in nat_meta["variables"] if v["code"] == "timeperiod_y")["values"]]
    body = {
        "query": [
            {"code": nat_cause["code"], "selection": {"filter": "item", "values": list(CANCER_SITES)}},
            {"code": nat_age["code"], "selection": {"filter": "item", "values": [a for a in nat_age["values"] if statfin_age_to_group(a)]}},
            {"code": nat_sex["code"], "selection": {"filter": "item", "values": ["SSS"]}},
            {"code": "timeperiod_y", "selection": {"filter": "item", "values": window}},
        ],
        "response": {"format": "json-stat2"},
    }
    js = f.get(nat_url, "statfin", body)
    national_deaths_by_age: dict[str, dict[str, float]] = {}
    national_deaths_by_year: dict[str, dict[str, float]] = {}
    for coord, v in jsonstat_cells(js):
        if v is None:
            continue
        site = CANCER_SITES[coord[nat_cause["code"]]]["key"]
        g = statfin_age_to_group(coord[nat_age["code"]])
        national_deaths_by_age.setdefault(site, {}).setdefault(g, 0.0)
        national_deaths_by_age[site][g] += v
        national_deaths_by_year.setdefault(site, {}).setdefault(coord["timeperiod_y"], 0.0)
        national_deaths_by_year[site][coord["timeperiod_y"]] += v

    # --------------------------- deaths by wellbeing county and cancer site (13u5)
    reg_url = f"{STATFIN}/ksyyt/13u5.px"
    reg_meta = f.get(reg_url, "statfin")
    reg_area = next(v for v in reg_meta["variables"] if v["code"].startswith("alue"))
    reg_cause = next(v for v in reg_meta["variables"] if v["code"].startswith("kuolinsyyt"))
    reg_years = next(v for v in reg_meta["variables"] if v["code"] == "timeperiod_y")["values"]
    series_years = [y for y in reg_years if int(y) >= 2010]
    body = {
        "query": [
            {"code": reg_area["code"], "selection": {"filter": "item", "values": [a for a in reg_area["values"] if a.startswith("HVA")]}},
            {"code": reg_cause["code"], "selection": {"filter": "item", "values": list(CANCER_SITES)}},
            {"code": "timeperiod_y", "selection": {"filter": "item", "values": series_years}},
            {"code": "contentscode", "selection": {"filter": "item", "values": ["ksyylkm"]}},
        ],
        "response": {"format": "json-stat2"},
    }
    js = f.get(reg_url, "statfin", body)
    deaths: dict[str, dict[str, dict[str, float]]] = {}
    for coord, v in jsonstat_cells(js):
        if v is None:
            continue
        site = CANCER_SITES[coord[reg_cause["code"]]]["key"]
        deaths.setdefault(site, {}).setdefault(coord[reg_area["code"]], {})[coord["timeperiod_y"]] = v

    # ------------------- indirect age standardisation: expected deaths per region
    base_year = "2024"
    nat_pop = national_pop[base_year]
    mortality = {}
    for site_code, site in CANCER_SITES.items():
        key = site["key"]
        per_region = {}
        for region in (r["id"] for r in regions):
            pop = population.get(region, {}).get(base_year)
            obs_years = deaths.get(key, {}).get(region, {})
            if not pop:
                continue
            expected = sum(
                national_deaths_by_age[key].get(g, 0.0) * pop.get(g, 0.0) / nat_pop[g]
                for g in AGE_GROUPS if nat_pop.get(g)
            )
            observed = sum(obs_years.get(y, 0.0) for y in window)
            per_region[region] = {
                "observed": observed,
                "expected": round(expected, 3),
                "series": {y: obs_years.get(y) for y in series_years},
            }
        mortality[key] = {
            "label": site["label"],
            "statfinClass": site_code,
            "window": window,
            "nationalDeathsByYear": national_deaths_by_year.get(key, {}),
            "nationalDeathsByAge": national_deaths_by_age.get(key, {}),
            "regions": per_region,
        }

    # ------------- demand projection: expected cancer deaths under constant rates
    projection = {}
    for region in (r["id"] for r in regions):
        projection[region] = {}
        for year in PROJECTION_YEARS:
            pop = population.get(region, {}).get(year)
            if not pop:
                continue
            projection[region][year] = {
                "population": round(sum(pop.values())),
                "age65plus": round(sum(v for g, v in pop.items() if g[:2].isdigit() and int(g.split("-")[0]) >= 65)),
                "expectedCancerDeathsPerYear": round(sum(
                    national_deaths_by_age["all_cancers"].get(g, 0.0) / len(window) * pop.get(g, 0.0) / nat_pop[g]
                    for g in AGE_GROUPS if nat_pop.get(g)
                ), 2),
            }

    # --------------------------------------------- NORDCAN 5-year relative survival
    nordcan = {}
    pops = "_".join(str(c) for c in NORDCAN_COUNTRIES)
    for cancer_id, cancer_key in NORDCAN_CANCERS.items():
        url = f"{NORDCAN}/survival/population/5/1_2/{pops}/{cancer_id}/?surv_period=5&age_surv=0&year_start=1967&year_end=2024"
        try:
            js = f.get(url, "nordcan")
        except RuntimeError as exc:
            print(f"warn: NORDCAN {cancer_key}: {exc}", file=sys.stderr)
            continue
        rows = []
        for row in js.get("dataset", []):
            s = row.get("survival") or {}
            if s.get("value") in (None, ""):
                continue
            rows.append({
                "country": NORDCAN_COUNTRIES.get(row["country"], str(row["country"])),
                "sex": {1: "male", 2: "female"}.get(row["sex"], str(row["sex"])),
                "period": row["period"],
                "value": float(s["value"]),
                "low": float(s["lowCI"]) if s.get("lowCI") not in (None, "") else None,
                "high": float(s["upCI"]) if s.get("upCI") not in (None, "") else None,
            })
        nordcan[cancer_key] = {"nordcanCancerId": cancer_id, "requestUrl": url, "rows": rows}

    snapshot = {
        "schemaVersion": "care-equity-public-v1",
        "dataClass": "CLEARED_AGGREGATE_INPUT",
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "notes": [
            "Aggregate public statistics only. No patient-level or identifiable data.",
            "Expected deaths use indirect age standardisation: national age-specific cancer death counts "
            f"({window[0]}-{window[-1]}, Statistics Finland 11az) applied to each wellbeing services county's "
            f"{base_year} age structure (Statistics Finland 14wx, aggregated from municipalities).",
            "Åland (HVA91) and Helsinki (HVA90) are reported as their own units, as in the source statistics.",
        ],
        "sources": {
            "thl-sotkanet": {
                "title": "Sotkanet.fi Statistics and Indicator Bank",
                "publisher": "Finnish Institute for Health and Welfare (THL)",
                "url": "https://sotkanet.fi",
                "license": "CC BY 4.0",
                "isObservedPublicDataset": True,
            },
            "statfin": {
                "title": "StatFin: Causes of death (ksyyt 13u5, 11az); Population projection 2024 (vaenn 14wx)",
                "publisher": "Statistics Finland",
                "url": "https://pxdata.stat.fi/PxWeb/pxweb/fi/StatFin/",
                "license": "CC BY 4.0",
                "isObservedPublicDataset": True,
            },
            "nordcan": {
                "title": "NORDCAN 2.0: Cancer incidence, mortality, prevalence and survival in the Nordic countries",
                "publisher": "Association of the Nordic Cancer Registries / IARC",
                "url": "https://nordcan.iarc.who.int",
                "license": "Free reuse with citation (NORDCAN terms)",
                "isObservedPublicDataset": True,
            },
        },
        "regions": regions,
        "ageGroups": AGE_GROUPS,
        "indicators": indicators,
        "mortality": mortality,
        "population": {r: {y: {g: round(v) for g, v in ages.items()} for y, ages in years.items()} for r, years in population.items()},
        "nationalPopulation": {y: {g: round(v) for g, v in ages.items()} for y, ages in national_pop.items()},
        "projection": projection,
        "nordcanSurvival": nordcan,
        "unmappedMunicipalities": sorted(unmapped),
        "manifest": f.manifest,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    digest = hashlib.sha256(out_path.read_bytes()).hexdigest()
    print(json.dumps({
        "out": str(out_path), "sha256": digest, "regions": len(regions), "indicators": len(indicators),
        "sites": len(mortality), "requests": len(f.manifest), "unmappedMunicipalities": len(unmapped),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
