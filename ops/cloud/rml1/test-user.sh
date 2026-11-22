#!/usr/bin/env bash
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT

RML1_INSTALL_RUST_1_98_1=0 bash "$here/setup-user.sh" > "$work/setup"
grep -Fx 'rml1_local_oci_checker=available' "$work/setup"
grep -Eq '^rml1_pinned_rust_1_98_1=(unavailable|not_requested)$' "$work/setup"

python3 -I - "$here/check-oci-layout.py" "$work" <<'PY'
import hashlib
import json
from pathlib import Path
import subprocess
import sys

checker, tmp = sys.argv[1:]
layout = Path(tmp) / "layout"
blobs = layout / "blobs" / "sha256"
blobs.mkdir(parents=True)
manifest = b'{"schemaVersion":2}'
digest = hashlib.sha256(manifest).hexdigest()
blob = blobs / digest
blob.write_bytes(manifest)
(layout / "oci-layout").write_text('{"imageLayoutVersion":"1.0.0"}')
index = layout / "index.json"
index.write_text(json.dumps({
    "schemaVersion": 2,
    "manifests": [{"digest": f"sha256:{digest}", "size": len(manifest)}],
}))

def run():
    return subprocess.run(
        [sys.executable, "-I", checker, str(layout)],
        capture_output=True, text=True, timeout=5,
    )

good = run()
assert good.returncode == 0, good.stderr
assert json.loads(good.stdout) == {
    "index_sha256": hashlib.sha256(index.read_bytes()).hexdigest(),
    "checked_descriptors": 1,
}
blob.write_bytes(manifest.replace(b"2", b"3"))
assert run().returncode == 1
blob.unlink()
outside = Path(tmp) / "outside.json"
outside.write_bytes(manifest)
blob.symlink_to(outside)
assert run().returncode == 1
blob.unlink()
blob.write_bytes(manifest)
with index.open("wb") as stream:
    stream.truncate(4 * 1024 * 1024 + 1)
assert run().returncode == 1
print("OCI layout regression passed")
PY
bash "$here/test_verify.sh"
