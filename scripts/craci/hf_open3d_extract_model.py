#!/usr/bin/env python3
"""Reassemble one trusted, source-bound CRACI model without deserializing it."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile

RUN = 43672442214
SOURCE = "76138f0c27fca50694aef7b6016af65478df65e4"
MAX_MODEL = 50 * 1024 * 1024


def sha(data):
    return hashlib.sha256(data).hexdigest()


def extract(artifacts, index, output, line, fold, method):
    expected_name = f"hf-open3d-cell-{RUN}-1-{line}-{fold}-{method}"
    matches = [x for x in json.loads(index.read_text(encoding="utf-8"))
               if x["name"] == expected_name]
    if len(matches) != 1:
        raise ValueError("cell missing or duplicated in index")
    record = matches[0]
    raw = (artifacts / (str(record["id"]) + ".zip")).read_bytes()
    if len(raw) != record["size_in_bytes"] or "sha256:" + sha(raw) != record["digest"]:
        raise ValueError("outer artifact digest mismatch")
    with zipfile.ZipFile(io.BytesIO(raw)) as outer:
        if len(outer.namelist()) != len(set(outer.namelist())):
            raise ValueError("duplicate ZIP entries")
        receipt = json.loads(outer.read("receipt.json"))
        manifest_raw = outer.read("manifest.json")
        manifest = json.loads(manifest_raw)
        binding = receipt["binding"]
        if not (receipt["status"] == "succeeded" and receipt["sourceVerified"]
                and receipt["harnessVerified"] and binding["sourceSha"] == SOURCE
                and binding["harnessSha"] == SOURCE
                and receipt["manifest"]["sha256"] == sha(manifest_raw)
                and manifest["complete"]):
            raise ValueError("source receipt mismatch")
        files = {x["path"]: x for x in manifest["files"]}
        prefix = "artifacts/hf-open3d/"

        def verified_read(path):
            if path not in files:
                raise ValueError("artifact is missing from the receipt manifest")
            data = outer.read(path)
            if len(data) != files[path]["bytes"] or sha(data) != files[path]["sha256"]:
                raise ValueError("artifact manifest mismatch")
            return data

        result = json.loads(verified_read(prefix + "result.json"))
        if (result["line"], result["fold"], result["method"]) != (line, fold, method):
            raise ValueError("cell result mismatch")
        chunks = []
        for part in result["trained_model"]["parts"]:
            if Path(part["file"]).name != part["file"]:
                raise ValueError("unsafe part path")
            packed = verified_read(prefix + part["file"])
            if sha(packed) != part["archive_sha256"]:
                raise ValueError("model archive mismatch")
            with zipfile.ZipFile(io.BytesIO(packed)) as inner:
                if inner.namelist() != [part["entry"]]:
                    raise ValueError("unexpected model archive entry")
                chunk = inner.read(part["entry"])
            if len(chunk) != part["bytes"] or sha(chunk) != part["sha256"]:
                raise ValueError("model part mismatch")
            chunks.append(chunk)
    model = b"".join(chunks)
    if len(model) > MAX_MODEL or sha(model) != result["trained_model"]["sha256"]:
        raise ValueError("reassembled model digest mismatch")
    with output.open("xb") as file:
        file.write(model)
    return {"line": line, "fold": fold, "method": method, "sha256": sha(model),
            "bytes": len(model), "run": RUN, "source": SOURCE,
            "warning": "joblib/pickle: deserialize only from a trusted artifact",
            "promotion_authorized": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--line", choices=("v2d", "g1", "robo"), required=True)
    parser.add_argument("--fold", type=int, choices=range(5), required=True)
    parser.add_argument("--method", choices=("ridge", "trees", "mlp"), required=True)
    args = parser.parse_args()
    print(json.dumps(extract(args.artifacts, args.index, args.output, args.line, args.fold,
                             args.method), sort_keys=True))
