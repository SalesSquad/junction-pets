#!/usr/bin/env python3
"""Offline, SHA-pinned V13 receipt compiler; zero external effects.

Example:
 python3 scripts/craci/feedback_loop_v4/cli.py \
  --repo-root . --hosted-artifact /private/original.zip \
  --artifact-sha256 EXTERNALLY_PINNED_64_HEX \
  --harness-sha EXTERNALLY_PINNED_40_HEX \
  --github-run 43660619725 --output-dir /private/v14-feedback
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile

import core


def write_fresh(output_dir, result):
    """Do not create final outputs until every input/source check passes."""
    target=Path(output_dir).absolute()
    core.need(not target.exists() and target.parent.is_dir() and
              not target.parent.is_symlink(),"V14_OUTPUT_TARGET_MUST_BE_NEW")
    stage=Path(tempfile.mkdtemp(prefix=".v14-evidence-staging-",dir=target.parent))
    try:
        contents={"next_training_decision.json":
                     core.canonical(result["decision"])+b"\n",
                  "training_dataset_manifest.json":
                     core.canonical(result["manifest"])+b"\n"}
        if result["manifest"]["trainingRowsFilename"] is not None:
            contents["training_rows.jsonl"]=result["rowsBytes"]
        for name,raw in contents.items():
            dest=stage/name
            with dest.open("xb") as f:
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
        # Source-only declared dataset digest must cover the exact output.
        if "training_rows.jsonl" in contents:
            core.need(core.digest(contents["training_rows.jsonl"])==
                      result["manifest"]["trainingRowsSha256"],
                      "V14_OUTPUT_ROWS_SHA_CHANGED_DURING_SAVE")
        os.rename(stage,target)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return target


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root",type=Path,required=True)
    parser.add_argument("--hosted-artifact",type=Path,required=True)
    parser.add_argument("--artifact-sha256",required=True)
    parser.add_argument("--harness-sha",required=True)
    parser.add_argument("--github-run",type=int,required=True)
    parser.add_argument("--v12-index",type=Path,
                        help="Optional external staged SHA24460... audited 48-world public index")
    parser.add_argument("--output-dir",type=Path,required=True)
    args=parser.parse_args(argv)
    verified=core.load_verified_hosted(args.hosted_artifact,args.artifact_sha256,
                      args.harness_sha,args.github_run,args.repo_root,args.v12_index)
    result=core.compile_from_verified(verified)
    out=write_fresh(args.output_dir,result)
    print(json.dumps({"output":str(out),"decision":result["decision"]["decision"],
                      "sourceRun":verified["hostedRun"],"sciencePromotion":False,
                      "automaticPaidDispatch":False},sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
