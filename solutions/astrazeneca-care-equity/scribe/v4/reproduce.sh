#!/usr/bin/env bash
# Offline reproduction of the SAMA pathway scribe's final numbers (all notes SYNTHETIC).
#
#   bash scribe/v4/reproduce.sh
#
# Needs no keys, no network, no model and no GPU: eval8.py and local_pairs.py read only stored outputs.
# What it does:
#   1. backs up every file the two scripts rewrite (results-v1.json, scribe/v4/RESULTS.md,
#      local-pairs-posthoc-v1.json, and the append-only run log runs/laneA-step8.jsonl);
#   2. runs `eval8.py verify`, `eval8.py score`, `local_pairs.py`;
#   3. compares each regenerated file with the committed one, ignoring only timestamps;
#   4. restores the committed files, so data/ and runs/ are left exactly as they were;
#   5. prints REPRODUCED, or DIFFERS with the differing keys. Exit status 0 only for REPRODUCED.
# Override the interpreter with PYTHON=/path/to/python (default python3; needs pyarrow).
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 2
PY="${PYTHON:-python3}"
BK="$(mktemp -d "${TMPDIR:-/tmp}/scribe-reproduce.XXXXXX")"

FILES=(
  data/scribe/v4/eval/results-v1.json
  scribe/v4/RESULTS.md
  data/scribe/v4/eval/local-pairs-posthoc-v1.json
  runs/laneA-step8.jsonl
)
# regenerated copies are kept here for the comparison; the committed files are restored from $BK
for f in "${FILES[@]}"; do
  mkdir -p "$BK/orig/$(dirname "$f")" "$BK/new/$(dirname "$f")"
  [ -f "$f" ] && cp -p "$f" "$BK/orig/$f"
done

restore() {
  for f in "${FILES[@]}"; do
    if [ -f "$BK/orig/$f" ]; then cp -p "$BK/orig/$f" "$f"; else rm -f "$f"; fi
  done
}
trap restore EXIT

status=0
echo "== eval8.py verify"
"$PY" scribe/v4/eval8.py verify > "$BK/verify.json" || { echo "verify failed (see $BK/verify.json)"; status=1; }
echo "== eval8.py score"
"$PY" scribe/v4/eval8.py score > "$BK/score.out" || { echo "score failed (see $BK/score.out)"; status=1; }
echo "== local_pairs.py"
"$PY" scribe/v4/local_pairs.py > "$BK/pairs.out" || { echo "local_pairs failed (see $BK/pairs.out)"; status=1; }

for f in data/scribe/v4/eval/results-v1.json scribe/v4/RESULTS.md data/scribe/v4/eval/local-pairs-posthoc-v1.json; do
  [ -f "$f" ] && cp -p "$f" "$BK/new/$f"
done

"$PY" - "$BK" <<'PY'
import json, re, sys, pathlib
bk = pathlib.Path(sys.argv[1])
TS_KEY = re.compile(r"^(created|generated|written|computed|ts)(_.*)?$|_utc$|_at$")
TS_VAL = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")
KEEP = set()  # file_mtime_utc is the checkout time of preregistration.json, so it differs per clone: ignored too

def walk(a, b, path, out):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            p = f"{path}.{k}" if path else k
            if k not in a or k not in b:
                out.append(p + " (missing on one side)")
            elif TS_KEY.search(k) and k not in KEEP:
                continue
            else:
                walk(a[k], b[k], p, out)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path} (length {len(a)} vs {len(b)})")
        for i, (x, y) in enumerate(zip(a, b)):
            walk(x, y, f"{path}[{i}]", out)
    elif a != b:
        out.append(path)

diffs = {}
for rel in ("data/scribe/v4/eval/results-v1.json", "data/scribe/v4/eval/local-pairs-posthoc-v1.json"):
    o, n = bk / "orig" / rel, bk / "new" / rel
    if not n.exists() or not o.exists():
        diffs[rel] = ["file missing"]; continue
    out = []; walk(json.loads(o.read_text()), json.loads(n.read_text()), "", out)
    if out: diffs[rel] = out
rel = "scribe/v4/RESULTS.md"
o, n = bk / "orig" / rel, bk / "new" / rel
if not n.exists() or not o.exists():
    diffs[rel] = ["file missing"]
else:
    f = lambda p: TS_VAL.sub("<ts>", p.read_text())
    if f(o) != f(n):
        la, lb = f(o).splitlines(), f(n).splitlines()
        diffs[rel] = [f"line {i+1}" for i, (x, y) in enumerate(zip(la, lb)) if x != y][:20] or ["length"]
if diffs:
    print("DIFFERS")
    for k, v in diffs.items():
        print(f"  {k}: {', '.join(v[:40])}")
    sys.exit(1)
print("REPRODUCED")
print("  results-v1.json, scribe/v4/RESULTS.md and local-pairs-posthoc-v1.json match the committed files (timestamps ignored)")
PY
cmp=$?
[ "$status" -ne 0 ] && { echo "DIFFERS (a step failed above)"; cmp=1; }
restore
trap - EXIT
echo "Committed files restored; backups in $BK. Check: git status data/ runs/"
exit $cmp
