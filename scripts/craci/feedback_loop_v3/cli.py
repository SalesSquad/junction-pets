#!/usr/bin/env python3
"""Compile a no-dispatch V13 decision from exactly one original hosted V12 ZIP."""
import argparse
from pathlib import Path
import sys

from core import EvidenceRejected, canonical, compile_decision, read_original_hosted, sha


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True, help="original immutable GitHub artifact ZIP")
    parser.add_argument("--output", type=Path, required=True, help="new task-owned decision JSON path")
    args = parser.parse_args()
    bundle = read_original_hosted(args.artifact)
    decision = compile_decision(bundle)
    contents = canonical(decision) + b"\n"
    # Explicit exclusive creation; never rewrite an earlier decision in place.
    with args.output.open("xb") as out:
        out.write(contents)
        out.flush()
    print({"decision": decision["decision"],
           "original_artifact_sha": decision["evidence"]["hosted_artifact_zip_sha256"],
           "decision_sha256": sha(contents),
           "advisory_only": not decision["dispatch_authorized"]})


if __name__ == "__main__":
    try:
        main()
    except (EvidenceRejected, FileExistsError, OSError) as error:
        print("FEEDBACK_V3_REFUSED", type(error).__name__, str(error)[:120], file=sys.stderr)
        raise SystemExit(1) from error
