#!/usr/bin/env python3
"""Create offline review packets from the four pinned public sponsor commits.

No generated metadata is behavioral proof. A differential receipt is optional;
it must be produced by the task's verifier and retains its actual limitations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from datetime import datetime, timezone

BASE = "32258fdbee4bcd653c79f51b4376b5103c6f4d27"
REPOSITORY = "https://github.com/te-industry-tech-office/junction26-messagepack-csharp"
CASES = {
    "2283": {
        "sha": "9df83c38409c8bfad0517aebffe48211eda4a5b4",
        "title": "Metadata generics without crashes",
        "summary": "A consuming assembly receives a generated resolver for a generic value type defined in an external assembly.",
        "details": "Require both no analyzer/generator crash and the expected generated consumer resolver. A normal build succeeding alone is insufficient.",
        "count": 4,
    },
    "2234": {
        "sha": "9007cee1163c4a274fd60c3cc20c21ae63622786",
        "title": "Diagnostics when generation is suppressed",
        "summary": "Suppressing source generation must preserve relevant contract diagnostics and avoid collection crashes on invalid keys.",
        "details": "Required diagnostics, opt-out behavior and invalid-input crash prevention are separate claims; passing a branch's own suite does not prove all of them.",
        "count": 4,
    },
    "2129": {
        "sha": "083afd994c1c9a994cb2cd5aa0b6ad805a621457",
        "title": "Formatters across assembly boundaries",
        "summary": "Generate a formatter for an external type without making the external assembly depend on MessagePack.",
        "details": "Review the public feature contract, accessible members, surrogate mapping, wire compatibility and documented unsupported shapes. This is a larger semantic change despite its smaller file count.",
        "count": 28,
    },
    "2297": {
        "sha": "a0aa5ab2de7f5a669d97e37184a89034c1de82b6",
        "title": "Generated code and coverage",
        "summary": "Generated MessagePack code should be excluded from code coverage without hiding user-authored behavior.",
        "details": "Generated output containing an attribute is not evidence that a coverage tool excludes precisely the intended code. Separate generator changes from regenerated expected-output snapshots.",
        "count": 237,
    },
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), *args])


def file_role(path: str) -> tuple[str, str]:
    if path.startswith("tests/MessagePack.SourceGenerator.Tests/Resources/") and path.endswith(".g.cs"):
        return "generatedSnapshot", "Generated expected output"
    if path.endswith(".md"):
        return "documentation", "Documentation"
    if path.startswith("tests/"):
        return "test", "Behavior and generator tests"
    if path.startswith("src/MessagePack.SourceGenerator/Transforms/"):
        return "source", "Generator templates and transforms"
    if path.startswith("src/"):
        return "source", "Implementation"
    return "other", "Other changes"


def inventory(repo: Path, head: str) -> list[dict]:
    parent = git(repo, "rev-parse", head + "^").decode().strip()
    if parent != BASE:
        raise ValueError(f"Unexpected parent for pinned revision {head}: {parent}")
    items = []
    # --no-renames avoids the multi-path NUL record format; no line splitting of paths.
    for record in git(repo, "diff", "--no-renames", "--numstat", "-z", BASE, head).split(b"\0"):
        if not record:
            continue
        additions, deletions, path_bytes = record.split(b"\t", 2)
        path = path_bytes.decode("utf-8")
        if additions == b"-" or deletions == b"-":
            raise ValueError(f"Binary change requires explicit classification: {path}")
        role, group = file_role(path)
        items.append({"path": path, "role": role, "additions": int(additions),
                      "deletions": int(deletions), "group": group})
    return items


def structural_check(issue: str, head: str) -> dict:
    return {
        "id": f"diff-{issue}", "title": "Pinned change inventory",
        "requirementId": f"MP-{issue}", "kind": "structural", "evidence": "observed",
        "baseOutcome": "notRun", "headOutcome": "notRun",
        "baseSourceSha": BASE, "headSourceSha": head,
        "baseHarnessSha256": None, "headHarnessSha256": None,
        "baseLog": None, "headLog": None, "baseLogSha256": None, "headLogSha256": None,
        "limitations": ["File classification is source inspection, not behavioral or coverage-tool execution."],
    }


def build_packet(repo: Path, issue: str, now: str) -> dict:
    case = CASES[issue]
    files = inventory(repo, case["sha"])
    if len(files) != case["count"]:
        raise ValueError(f"Pinned {issue} inventory changed: {len(files)}")
    generated = sum(f["role"] == "generatedSnapshot" for f in files)
    if issue == "2297" and generated != 222:
        raise ValueError(f"Expected 222 generated snapshots, got {generated}")
    return {
        "schemaVersion": 1, "packetId": f"tieto-{issue}", "title": case["title"],
        "generatedAt": now,
        "source": {"repository": REPOSITORY, "baseSha": BASE, "headSha": case["sha"],
                   "issueId": issue, "issueURL": f"https://github.com/MessagePack-CSharp/MessagePack-CSharp/issues/{issue}",
                   "branch": f"ju26-issue-{issue}"},
        "requirement": {"id": f"MP-{issue}", "summary": case["summary"], "details": case["details"]},
        "checks": [structural_check(issue, case["sha"])],
        "claims": [{"id": f"inventory-{issue}", "title": "Changed paths are bound to the official source revisions",
                    "requirementId": f"MP-{issue}", "kind": "structural", "checkIds": [f"diff-{issue}"],
                    "paths": [f["path"] for f in files if f["role"] != "generatedSnapshot"]}],
        "files": files,
        "provenance": {"toolchain": "git diff --no-renames --numstat -z",
                       "origin": "structural-inspection",
                       "note": "Official AI-authored changes are supplied by the organizer; this review desk and evidence collector are our contribution."},
        "limitations": ["No behavioral qualification is inferred from source inspection.",
                        "Local hashes establish byte integrity, not runner identity, truthful outcomes or human authentication.",
                        "No model inference, merge, release or external approval is performed by this application."],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True,
                        help="Your separate copy of the official MessagePack repository, containing all four pinned commits")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timestamp", help="Reproducible UTC timestamp (otherwise now)")
    args = parser.parse_args()
    now = args.timestamp or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    for issue in CASES:
        packet = build_packet(args.repository.resolve(), issue, now)
        folder = args.output / issue
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / "packet.json"
        target.write_text(json.dumps(packet, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps({"issue": issue, "files": len(packet["files"]),
                          "generatedSnapshots": sum(f["role"] == "generatedSnapshot" for f in packet["files"]),
                          "packetSha256": digest(target.read_bytes()), "behavior": "not-executed"}))


if __name__ == "__main__":
    main()
