#!/usr/bin/env python3
"""CFR-Annual, stage 1: download annual CFR editions from GovInfo bulk data and keep the sections that state
an amount. Streams: one title-year zip at a time, parsed with iterparse, deleted after parsing.

Editions are "revised as of" a fixed date per title: titles 1-16 January 1, 17-27 April 1, 28-41 July 1,
42-50 October 1. Every row keeps the official bulk URL and the SHA-256 of the zip it came from.

--mode focused  every section with a money amount or a percentage (consumer, worker and transport titles)
--mode cmp      only civil monetary penalty and inflation-adjustment sections (any title)

Usage: python3 fetch_parse.py --titles 12,14,16,20,29,49 --years 1996-2026 --mode focused --out sections-focused.jsonl.gz
"""
import argparse, concurrent.futures as cf, gzip, hashlib, io, json, re, sys, time, urllib.request, zipfile
import xml.etree.ElementTree as ET

ap = argparse.ArgumentParser()
ap.add_argument("--titles", required=True); ap.add_argument("--years", default="1996-2026")
ap.add_argument("--mode", choices=["focused", "cmp"], default="focused"); ap.add_argument("--out", required=True)
ap.add_argument("--workers", type=int, default=6)
a = ap.parse_args()
titles = [int(t) for t in a.titles.split(",")] if a.titles != "all" else [t for t in range(1, 51) if t != 35]
y0, y1 = (int(x) for x in a.years.split("-"))
UA = {"User-Agent": "cfr-annual-research/0.1 (time-aware legal amounts benchmark)"}

def revised(title, year):
    m = "01-01" if title <= 16 else "04-01" if title <= 27 else "07-01" if title <= 41 else "10-01"
    return f"{year}-{m}"

MONEY = re.compile(r"\$\s?\d")
PERCENT = re.compile(r"\d\s?(?:percent|per cent|%)", re.I)
CMP = re.compile(r"civil (?:monetary |money )?penalt|inflation adjust", re.I)

def get(url, tries=5):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                return r.read()
        except Exception as e:
            if getattr(e, "code", None) == 404:
                return None
            time.sleep(2 * 2 ** i)
    return None

def text_of(el):
    return re.sub(r"\s+", " ", " ".join(t.strip() for t in el.itertext() if t and t.strip())).strip()

def sections(xml_bytes):
    part = None
    for ev, el in ET.iterparse(io.BytesIO(xml_bytes), events=("start", "end")):
        if ev == "start" and el.tag == "PART":
            part = None
        if ev == "end" and el.tag == "HD" and part is None:
            m = re.match(r"PART\s+([0-9A-Za-z]+)", text_of(el) or "")
            if m:
                part = m.group(1)
        if ev == "end" and el.tag == "SECTION":
            no = el.findtext("SECTNO") or ""
            subject = el.findtext("SUBJECT") or el.findtext("RESERVED") or ""
            body = " ".join(text_of(c) for c in el if c.tag not in ("SECTNO", "SUBJECT"))
            m = re.search(r"([0-9]+[A-Za-z]?\.[0-9A-Za-z\-]+)", no)
            yield {"part": part or (m.group(1).split(".")[0] if m else None), "section": m.group(1) if m else no.strip(), "subject": subject.strip(), "text": body}
            el.clear()

def one(title, year):
    url = f"https://www.govinfo.gov/bulkdata/CFR/{year}/title-{title}/CFR-{year}-title-{title}.zip"
    blob = get(url)
    if not blob:
        return title, year, []
    sha = hashlib.sha256(blob).hexdigest()
    rows = []
    try:
        z = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile:
        return title, year, []
    for name in sorted(n for n in z.namelist() if n.endswith(".xml")):
        try:
            for s in sections(z.read(name)):
                t = s["text"]
                keep = (MONEY.search(t) or PERCENT.search(t)) if a.mode == "focused" else (CMP.search(s["subject"]) and MONEY.search(t))
                if keep:
                    rows.append({"title": title, "year": year, "edition": revised(title, year), **s, "text": f"§ {s['section']} {s['subject']} {t}".strip(), "volume": name.split("/")[-1], "source_url": url, "source_sha256": sha})
        except ET.ParseError as e:
            print(f"parse error {title}/{year}/{name}: {e}", file=sys.stderr)
    return title, year, rows

jobs = [(t, y) for t in titles for y in range(y0, y1 + 1)]
n = 0
with gzip.open(a.out, "wt", encoding="utf-8") as out, cf.ThreadPoolExecutor(a.workers) as ex:
    for title, year, rows in ex.map(lambda ty: one(*ty), jobs):
        for r in rows:
            out.write(json.dumps(r, ensure_ascii=False) + "\n")
        n += len(rows)
        print(f"title {title} {year}: {len(rows)} sections (total {n})", flush=True)
print(json.dumps({"mode": a.mode, "titles": titles, "years": [y0, y1], "sections": n}))
