"""Download the BRCA1 saturation genome editing table (Findlay et al. 2018, Nature,
doi 10.1038/s41586-018-0461-z, Supplementary Table 1) and the GRCh37.p13
chromosome 17 reference, then build a clean table of single-nucleotide variants.

Standard library only. Raw downloads and the clean table go to data/genomics/raw/
(git-ignored: reuse terms of the journal supplement were not confirmed, so the
measurements are fetched at run time and not committed). URL, size and sha256 of
every download are written to data/genomics/sources.json.
Research use only; not for clinical decisions.
"""
import argparse, csv, datetime, hashlib, json, os, re, sys, urllib.request, zipfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from genomics.windows import read_first_fasta_record  # noqa: E402

ROOT = os.path.dirname(HERE)
RAW = os.path.join(ROOT, "data", "genomics", "raw")
SOURCES_JSON = os.path.join(ROOT, "data", "genomics", "sources.json")
CLEAN_CSV = os.path.join(RAW, "brca1-findlay2018-snvs.csv")
KEYS_CSV = os.path.join(RAW, "variants-keys.csv")     # chrom,pos,ref,alt only: the input copied to the GPU box

SOURCES = {
    "findlay2018_table": {
        "description": "Findlay et al. 2018 Supplementary Table 1 (BRCA1 SGE function scores)",
        "url": "https://static-content.springer.com/esm/art%3A10.1038%2Fs41586-018-0461-z/MediaObjects/41586_2018_461_MOESM3_ESM.xlsx",
        "file": "41586_2018_461_MOESM3_ESM.xlsx",
        "sha256_expected": "e9aa4186b8a5de91d61059d03f8dac1e5573d1e2802f50a6581c3053d22b923a",
        "citation": "Findlay GM et al. Nature 2018;562:217-222. doi:10.1038/s41586-018-0461-z",
    },
    "reference_grch37_chr17": {
        "description": "GRCh37.p13 chromosome 17 (NC_000017.10), the file used by the ArcInstitute/evo2 BRCA1 notebook",
        "url": "https://raw.githubusercontent.com/ArcInstitute/evo2/main/notebooks/brca1/GRCh37.p13_chr17.fna.gz",
        "file": "GRCh37.p13_chr17.fna.gz",
        "sha256_expected": "d50b4616790d7352c5025bcf9070a4de4f76bab41c6d2dcd504382c67c5534fb",
    },
}

COLUMNS = {  # column name in the supplement -> name in the clean table
    "chromosome": "chrom", "position (hg19)": "pos", "reference": "ref", "alt": "alt",
    "function.score.mean": "function_score", "func.class": "func_class",
    "consequence": "consequence", "clinvar_simple": "clinvar_simple", "clinvar": "clinvar",
    "transcript_variant": "transcript_variant", "protein_variant": "protein_variant",
    "CADD.score": "cadd_score", "phyloP (mammalian)": "phylop_mammalian",   # predictors listed in the supplement
}
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": "research-benchmark-fetch/1.0"})
    tmp = dest + ".part"
    with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as out:
        status = resp.status
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
    os.replace(tmp, dest)
    return status


def col_index(cell_ref):
    letters = re.match(r"[A-Z]+", cell_ref).group(0)
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def read_xlsx_rows(path):
    """Minimal .xlsx reader: first worksheet, returns a list of rows (lists of str/float/None)."""
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", NS):
                shared.append("".join(t.text or "" for t in si.iter("{%s}t" % NS["m"])))
        sheets = sorted(n for n in z.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n))
        root = ET.fromstring(z.read(sheets[0]))
        rows = []
        for row in root.iter("{%s}row" % NS["m"]):
            values = []
            for c in row.findall("m:c", NS):
                i = col_index(c.get("r"))
                while len(values) <= i:
                    values.append(None)
                t = c.get("t")
                v = c.find("m:v", NS)
                if t == "s" and v is not None:
                    values[i] = shared[int(v.text)]
                elif t == "inlineStr":
                    values[i] = "".join(x.text or "" for x in c.iter("{%s}t" % NS["m"]))
                elif v is not None and v.text is not None:
                    values[i] = v.text if t in ("str", "b", "e") else float(v.text)
            rows.append(values)
        return rows, len(sheets)


def build_clean_table(xlsx_path, fasta_path, out_csv):
    rows, n_sheets = read_xlsx_rows(xlsx_path)
    header = rows[2]                      # third row holds the column names (pandas header=2)
    idx = {name: header.index(name) for name in COLUMNS}
    _, seq = read_first_fasta_record(fasta_path)
    out, stats = [], {"rows_in_table": 0, "kept_snvs": 0, "dropped_not_snv": 0, "dropped_no_score": 0,
                      "reference_matches": 0, "reference_mismatches": 0}
    for r in rows[3:]:
        if r is None or all(v is None for v in r):
            continue
        stats["rows_in_table"] += 1
        get = lambda name: r[idx[name]] if idx[name] < len(r) else None  # noqa: E731
        ref, alt = str(get("reference") or "").upper(), str(get("alt") or "").upper()
        if len(ref) != 1 or len(alt) != 1 or ref not in "ACGT" or alt not in "ACGT" or ref == alt:
            stats["dropped_not_snv"] += 1
            continue
        if get("function.score.mean") is None or get("func.class") is None:
            stats["dropped_no_score"] += 1
            continue
        pos = int(get("position (hg19)"))
        if seq[pos - 1].upper() == ref:
            stats["reference_matches"] += 1
        else:
            stats["reference_mismatches"] += 1
        rec = {"chrom": str(int(get("chromosome"))), "pos": pos, "ref": ref, "alt": alt,
               "function_score": repr(float(get("function.score.mean"))),
               "func_class": str(get("func.class"))}
        for name in ("consequence", "clinvar_simple", "clinvar", "transcript_variant", "protein_variant"):
            v = get(name)
            rec[COLUMNS[name]] = "" if v is None else str(v)
        for name in ("CADD.score", "phyloP (mammalian)"):
            v = get(name)
            rec[COLUMNS[name]] = repr(float(v)) if isinstance(v, float) else ""
        out.append(rec)
    stats["kept_snvs"] = len(out)
    fields = ["chrom", "pos", "ref", "alt", "function_score", "func_class", "consequence",
              "clinvar_simple", "clinvar", "transcript_variant", "protein_variant", "cadd_score", "phylop_mammalian"]
    with open(out_csv, "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=fields)
        wr.writeheader()
        wr.writerows(out)
    with open(KEYS_CSV, "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["chrom", "pos", "ref", "alt"])
        wr.writerows([rec["chrom"], rec["pos"], rec["ref"], rec["alt"]] for rec in out)

    def counts(key):
        d = {}
        for rec in out:
            d[rec[key]] = d.get(rec[key], 0) + 1
        return dict(sorted(d.items(), key=lambda kv: (-kv[1], kv[0])))

    stats.update({"n_sheets": n_sheets, "n_columns_in_header": len([h for h in header if h is not None]),
                  "unique_positions": len({rec["pos"] for rec in out}),
                  "pos_min": min(rec["pos"] for rec in out), "pos_max": max(rec["pos"] for rec in out),
                  "func_class_counts": counts("func_class"), "consequence_counts": counts("consequence"),
                  "clinvar_simple_counts": counts("clinvar_simple"),
                  "reference_length": len(seq),
                  "n_with_cadd_score": sum(1 for rec in out if rec["cadd_score"] != ""),
                  "n_with_phylop_mammalian": sum(1 for rec in out if rec["phylop_mammalian"] != "")})
    return stats


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="download again even if the file exists")
    ap.add_argument("--allow-hash-mismatch", action="store_true")
    args = ap.parse_args()
    os.makedirs(RAW, exist_ok=True)
    report = {"schemaVersion": 1, "generated_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "note": "Raw files and the clean table are kept in data/genomics/raw/ (git-ignored). Research use only; not for clinical decisions.",
              "sources": {}}
    for key, src in SOURCES.items():
        dest = os.path.join(RAW, src["file"])
        status = "cached"
        if args.force or not os.path.exists(dest):
            status = download(src["url"], dest)
        digest = sha256_file(dest)
        entry = {k: v for k, v in src.items() if k != "file"}
        entry.update({"file": os.path.relpath(dest, ROOT), "http_status": status, "bytes": os.path.getsize(dest),
                      "sha256": digest, "sha256_matches_expected": digest == src["sha256_expected"]})
        report["sources"][key] = entry
        if not entry["sha256_matches_expected"] and not args.allow_hash_mismatch:
            raise SystemExit(f"sha256 mismatch for {src['file']}: got {digest}")
    header, _ = read_first_fasta_record(os.path.join(RAW, SOURCES["reference_grch37_chr17"]["file"]))
    report["sources"]["reference_grch37_chr17"]["fasta_header"] = header
    stats = build_clean_table(os.path.join(RAW, SOURCES["findlay2018_table"]["file"]),
                              os.path.join(RAW, SOURCES["reference_grch37_chr17"]["file"]), CLEAN_CSV)
    report["variant_keys"] = {"file": os.path.relpath(KEYS_CSV, ROOT), "sha256": sha256_file(KEYS_CSV),
                              "columns": ["chrom", "pos", "ref", "alt"]}
    report["clean_table"] = {"file": os.path.relpath(CLEAN_CSV, ROOT), "sha256": sha256_file(CLEAN_CSV),
                             "coordinates": "GRCh37/hg19, 1-based, plus-strand alleles", **stats}
    with open(SOURCES_JSON, "w") as fh:
        json.dump(report, fh, indent=1)
        fh.write("\n")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
