"""Turn a score_evo2.py checkpoint (JSON lines) into the score CSV (keys and model output only).
Used for a run that was stopped before it wrote its own CSV. Research use only; not for clinical decisions."""
import csv, json, sys

FIELDS = ["chrom", "pos", "ref", "alt", "window", "win_start_1based", "win_end_1based", "snv_index",
          "evo2_ref_score", "evo2_var_score", "evo2_delta_score", "evo2_delta_score_f64", "evo2_site_llr"]


def convert(src, dst, window=None):
    recs = {}
    with open(src) as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if window is None or r.get("window") == window:
                recs[(r["pos"], r["ref"], r["alt"])] = r
    with open(dst, "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(FIELDS)
        for key in sorted(recs, key=lambda k: (int(k[0]), k[2])):
            r = recs[key]
            wr.writerow(["" if r[f] is None else (repr(r[f]) if isinstance(r[f], float) else r[f]) for f in FIELDS])
    return len(recs), len({k[0] for k in recs})


if __name__ == "__main__":
    n, npos = convert(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else None)
    print(f"{n} variants at {npos} positions written to {sys.argv[2]}")
