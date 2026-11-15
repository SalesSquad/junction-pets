#!/usr/bin/env python3
"""Owner-host publication of sanitized source bundles; no token is exported."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request

import cloud


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--batch", required=True)
    args = parser.parse_args()
    tag = "craci-repo-audit-20261115-" + args.batch
    cloud.validate_tag(tag)
    cloud.before(60 * 60)
    account = cloud.gh("api", "user")
    if account.get("login") != "SalesSquad":
        raise ValueError("Use the owner's existing authorized GitHub identity")
    cloud.private_destination(owner_only=True)
    directory = args.directory.resolve()
    manifest_path = directory / "campaign.json"
    manifest = json.loads(manifest_path.read_text())
    rule_path = directory / "semgrep-rules.yml"
    if not rule_path.exists():
        # Public anonymous rules only; GitHub credentials never enter this request.
        with urllib.request.urlopen("https://semgrep.dev/c/p/default", timeout=40) as response:
            rules = response.read(5_000_001)
        if not 0 < len(rules) <= 5_000_000 or not rules.startswith(b"rules:"):
            raise ValueError("Unexpected public rulepack")
        with rule_path.open("xb") as out:
            out.write(rules)
    rule_data = rule_path.read_bytes()
    manifest.update({"schema_version": 1, "deadline": cloud.DEADLINE, "max_parallel": 10,
                     "vcpu_per_job": 8, "max_job_minutes": 45, "max_estimated_eur": 100,
                     "rules": {"asset": rule_path.name, "sha256": cloud.digest(rule_data), "bytes": len(rule_data),
                               "source_url": "https://semgrep.dev/c/p/default"}})
    cloud.validate_manifest(manifest)
    # Every source bundle is checked locally, including all contained file hashes,
    # before any source is published. Validation writes only a task cache.
    for entry in manifest["repos"]:
        path = directory / entry["asset"]
        if path.is_symlink() or not path.is_file() or path.stat().st_size != entry["bytes"]:
            raise ValueError("Prepared source asset is missing or not regular")
        data = path.read_bytes()
        if cloud.digest(data) != entry["sha256"]:
            raise ValueError("Prepared source asset digest differs")
        with __import__("tempfile").TemporaryDirectory(prefix="audit-publish-") as tmp:
            cloud.unpack(data, Path(tmp) / "checked", entry)
    frozen = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    manifest_path.write_bytes(frozen)
    harness = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=cloud.TOOLS, text=True).strip()
    existing = subprocess.run(["gh", "api", f"repos/{cloud.REPO}/releases/tags/{tag}"], capture_output=True)
    if existing.returncode:
        # A provider failure is not treated as absence except for explicit404.
        error = existing.stdout + existing.stderr
        if b"404" not in error:
            raise RuntimeError("Could not verify absence of the private audit batch")
        notes = json.dumps({"purpose": "owner-requested read-only source audit", "deadline": cloud.DEADLINE,
                            "manifest_sha256": cloud.digest(frozen), "repositories": len(manifest["repos"]),
                            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                            "project_code_executed": False, "cash_topup_authorized": False})
        cloud.gh("release", "create", tag, "--repo", cloud.REPO, "--target", harness, "--prerelease",
                 "--title", f"Private repository bug audit — batch {args.batch}", "--notes", notes, binary=True)
    else:
        body = json.loads(existing.stdout)
        metadata = json.loads(body.get("body", "{}"))
        if metadata.get("manifest_sha256") != cloud.digest(frozen):
            raise ValueError("Preserve an existing different immutable audit batch")
    # Recheck current owner-only access immediately before cross-repo publication.
    cloud.private_destination(owner_only=True)
    for entry in manifest["repos"]:
        cloud.upload(tag, directory / entry["asset"])
        print(json.dumps({"source_published": entry["repository"], "source_sha": entry["source_sha"],
                          "files": entry.get("file_count"), "bytes": entry["bytes"]}), flush=True)
    cloud.upload(tag, rule_path)
    cloud.upload(tag, manifest_path)
    print(json.dumps({"private_tag": tag, "manifest_sha256": cloud.digest(frozen),
                      "repositories": len(manifest["repos"]), "dispatch_started": False}), flush=True)


if __name__ == "__main__":
    main()
