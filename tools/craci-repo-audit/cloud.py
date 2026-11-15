#!/usr/bin/env python3
"""Fixed-destination, bounded private transport for repository static audits."""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request

REPO = "SalesSquad/junction-pets"
DEADLINE = "2026-11-15T17:00:00Z"
MAX_BUNDLE = 40 * 1024 * 1024
MAX_SOURCE = 100 * 1024 * 1024
MAX_FILE = 1024 * 1024
MAX_REPORT = 12 * 1024 * 1024
MAX_REPOS = 128
TOOLS = Path(__file__).resolve().parent
_PRIVATE = False
_RELEASES = {}
_ASSETS = {}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def utcnow():
    return dt.datetime.now(dt.timezone.utc)


def remaining(reserve=0):
    return (dt.datetime.fromisoformat(DEADLINE.replace("Z", "+00:00")) - utcnow()).total_seconds() - reserve


def before(reserve=0):
    if remaining(reserve) <= 0:
        raise ValueError("The authorized CRACI window has closed")


def gh(*args, binary=False, timeout=90):
    result = subprocess.run(["gh", *args], capture_output=True, timeout=min(timeout, max(1, remaining())))
    if result.returncode:
        # Never echo tool stderr, environment values, source or upload bodies.
        raise RuntimeError(f"GitHub operation failed (exit {result.returncode})")
    return result.stdout if binary else json.loads(result.stdout or b"null")


def private_destination(owner_only=False, force=False):
    global _PRIVATE
    before()
    if _PRIVATE and not owner_only and not force:
        return
    repo = gh("api", f"repos/{REPO}")
    if repo.get("full_name") != REPO or repo.get("private") is not True:
        raise ValueError("The fixed audit destination must remain private")
    if owner_only:
        collaborators = gh("api", f"repos/{REPO}/collaborators?per_page=100")
        if not collaborators or any(c.get("login") != "SalesSquad" for c in collaborators):
            raise ValueError("Cross-repository source snapshots require an owner-only destination")
    _PRIVATE = True


def validate_tag(tag):
    if not re.fullmatch(r"craci-repo-audit-20261115-(0[1-9]|1[0-2])", tag):
        raise ValueError("Only fixed dated audit batches 01 through 12 are accepted")


def release(tag):
    validate_tag(tag)
    if tag in _RELEASES:
        return _RELEASES[tag]
    item = gh("api", f"repos/{REPO}/releases/tags/{tag}")
    if item.get("tag_name") != tag or not item.get("prerelease") or item.get("draft"):
        raise ValueError("A private research prerelease is required")
    _RELEASES[tag] = item
    return item


def assets(tag):
    if tag in _ASSETS:
        return _ASSETS[tag]
    item = release(tag)
    result = []
    for page in range(1, 5):
        part = gh("api", f"repos/{REPO}/releases/{item['id']}/assets?per_page=100&page={page}")
        result.extend(part)
        if len(part) < 100:
            break
    names = [a.get("name") for a in result]
    if len(names) != len(set(names)) or len(result) >= 300:
        raise ValueError("Ambiguous or excessive audit assets")
    _ASSETS[tag] = result
    return result


def asset_named(tag, name):
    found = [a for a in assets(tag) if a.get("name") == name]
    if len(found) != 1:
        raise ValueError("The exact audit asset is absent or ambiguous")
    return found[0]


def download(tag, name, expected_digest=None, expected_size=None, limit=MAX_BUNDLE):
    before(60)
    private_destination()
    a = asset_named(tag, name)
    size = a.get("size", -1)
    if not isinstance(size, int) or not 0 < size <= limit:
        raise ValueError("Audit asset size is outside its bound")
    if expected_size is not None and size != expected_size:
        raise ValueError("Audit asset size does not match the frozen manifest")
    declared = a.get("digest", "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", declared):
        raise ValueError("Audit assets require a server SHA256")
    if expected_digest and declared != "sha256:" + expected_digest:
        raise ValueError("Audit asset digest does not match the frozen manifest")
    data = gh("api", f"repos/{REPO}/releases/assets/{a['id']}", "-H", "Accept: application/octet-stream", binary=True)
    if len(data) != size or "sha256:" + digest(data) != declared:
        raise ValueError("Actual audit asset bytes do not match their digest")
    return data


def upload(tag, path):
    before(30)
    private_destination(force=True)
    path = Path(path)
    data = path.read_bytes()
    if not 0 < len(data) <= MAX_BUNDLE or not re.fullmatch(r"[A-Za-z0-9_.-]+", path.name):
        raise ValueError("Unexpected audit publication")
    existing = [a for a in assets(tag) if a["name"] == path.name]
    if existing:
        if download(tag, path.name, digest(data), len(data)) != data:
            raise ValueError("An existing immutable audit asset differs")
        return
    # No --clobber, deletion, arbitrary URL, broad credential or force update.
    if os.environ.get("GH_TOKEN") and os.environ.get("GITHUB_REPOSITORY") == REPO:
        # Use only the explicitly supplied short-lived current-repository job token.
        # Never read/export the owner's gh/Keychain credential into Python or a runner.
        context()
        url = f"https://uploads.github.com/repos/{REPO}/releases/{release(tag)['id']}/assets?" + urllib.parse.urlencode({"name": path.name, "label": "sha256:" + digest(data)})
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, request, file_pointer, code, message, headers, new_url):
                return None
        request = urllib.request.Request(url, data=data, method="POST", headers={
            "Authorization": "Bearer " + os.environ["GH_TOKEN"], "Content-Type": "application/octet-stream",
            "Accept": "application/vnd.github+json", "User-Agent": "private-craci-source-audit"})
        with urllib.request.build_opener(NoRedirect).open(request, timeout=min(60, max(1, remaining()))) as response:
            a = json.loads(response.read(1_000_000))
        _ASSETS[tag].append(a)
    else:
        # On the owner host gh retains its own approved credential handling.
        gh("release", "upload", tag, f"{path}#sha256:{digest(data)}", "--repo", REPO, binary=True)
        _ASSETS.pop(tag, None)
        a = asset_named(tag, path.name)
    if a.get("size") != len(data) or a.get("digest") != "sha256:" + digest(data):
        raise ValueError("Uploaded audit asset metadata did not verify")


def validate_manifest(m):
    if m.get("schema_version") != 1 or m.get("deadline") != DEADLINE:
        raise ValueError("Unexpected audit manifest or deadline")
    repos = m.get("repos", [])
    if not 1 <= len(repos) <= MAX_REPOS or m.get("max_parallel") != 10 or m.get("vcpu_per_job") != 8 or m.get("max_job_minutes") != 45:
        raise ValueError("Unexpected audit resource allocation")
    # One bounded pass per selected repository, no continuous idle loops.
    estimate = len(repos) * 8 * 45 * 0.0017 + 0.1
    if estimate > 100 or m.get("max_estimated_eur") != 100:
        raise ValueError("Audit batch exceeds its existing-credit reserve")
    seen = set()
    for e in repos:
        repo = e.get("repository", "")
        sha = e.get("source_sha", "")
        if not re.fullmatch(r"SalesSquad/[A-Za-z0-9_.-]+", repo) or repo in seen or not re.fullmatch(r"[a-f0-9]{40}", sha):
            raise ValueError("Unexpected or duplicate immutable source")
        seen.add(repo)
        if e.get("asset") != f"source-{repo.split('/')[1]}-{sha[:12]}.tar.gz":
            raise ValueError("Source archive name differs from its identity")
        if not re.fullmatch(r"[a-f0-9]{64}", e.get("sha256", "")) or not 0 < e.get("bytes", 0) <= MAX_BUNDLE:
            raise ValueError("Source archive has no bounded digest")
    rule = m.get("rules", {})
    if rule.get("asset") != "semgrep-rules.yml" or not re.fullmatch(r"[a-f0-9]{64}", rule.get("sha256", "")) or not 0 < rule.get("bytes", 0) <= 5_000_000:
        raise ValueError("The public rulepack must be frozen and bounded")
    return m


def manifest(tag, expected_hash):
    if not re.fullmatch(r"[a-f0-9]{64}", expected_hash):
        raise ValueError("A frozen campaign digest is required")
    return validate_manifest(json.loads(download(tag, "campaign.json", expected_hash, limit=5_000_000)))


def context():
    env = os.environ
    if env.get("GITHUB_REPOSITORY") != REPO or env.get("GITHUB_REF") != "refs/heads/main":
        raise ValueError("Audit execution is restricted to the trusted default branch")
    source, run = env.get("GITHUB_SHA", ""), env.get("GITHUB_RUN_ID", "")
    if not re.fullmatch(r"[a-f0-9]{40}", source) or not re.fullmatch(r"[0-9]+", run) or not env.get("GH_TOKEN"):
        raise ValueError("Missing exact source/run/scoped publishing context")
    return source, run


def admission(tag, expected_hash):
    source, run = context()
    value = json.loads(download(tag, "admission.json", limit=10_000))
    if value.get("harness_sha") != source or value.get("run_id") != run or value.get("manifest_sha256") != expected_hash or value.get("deadline") != DEADLINE:
        raise ValueError("Another run/source already owns this immutable audit batch")
    return value


def plan(args):
    source, run = context()
    m = manifest(args.tag, args.manifest_sha256)
    before((((len(m["repos"]) + 9) // 10) * 45 + 10) * 60)
    listed = {a["name"]: a for a in assets(args.tag)}
    for e in [*m["repos"], m["rules"]]:
        a = listed.get(e["asset"], {})
        if a.get("size") != e["bytes"] or a.get("digest") != "sha256:" + e["sha256"]:
            raise ValueError("The complete frozen source/rule batch must exist before allocation")
    work = Path(args.work_dir)
    work.mkdir(parents=True, exist_ok=True)
    if "admission.json" in listed:
        admission(args.tag, args.manifest_sha256)
    else:
        record = {"schema_version": 1, "harness_sha": source, "run_id": run,
                  "manifest_sha256": args.manifest_sha256, "deadline": DEADLINE,
                  "repo_count": len(m["repos"]), "max_parallel": 10, "vcpu_per_job": 8,
                  "reserved_max_estimate_eur": round(len(m["repos"]) * 8 * 45 * 0.0017 + 0.1, 4),
                  "max_estimated_eur": 100, "cash_topup_authorized": False}
        path = work / "admission.json"
        path.write_text(json.dumps(record, sort_keys=True) + "\n")
        upload(args.tag, path)
        admission(args.tag, args.manifest_sha256)
    with open(os.environ["GITHUB_OUTPUT"], "a") as out:
        out.write("matrix=" + json.dumps({"include": [{"repository": e["repository"]} for e in m["repos"]]}, separators=(",", ":")) + "\n")
    print(json.dumps({"admitted_repositories": len(m["repos"]), "max_parallel": 10, "deadline": DEADLINE}))


def safe_path(name):
    p = PurePosixPath(name)
    if p.is_absolute() or any(x in ("", ".", "..") for x in p.parts) or "\\" in name or any(ord(c) < 32 for c in name):
        raise ValueError("Unsafe source path")
    return p


def unpack(data, destination, entry):
    destination = Path(destination)
    if destination.exists():
        raise ValueError("The source workspace must be new")
    members = {}
    total = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r|gz") as archive:
        for member in archive:
            p = safe_path(member.name)
            if not member.isfile() or member.name in members or len(members) >= 50_001:
                raise ValueError("Unexpected source archive member")
            if member.name != "files.json" and (not member.name.startswith("source/") or len(p.parts) < 2):
                raise ValueError("Source archives contain only regular source files and inventory")
            cap = 5_000_000 if member.name == "files.json" else MAX_FILE
            total += member.size
            if not 0 <= member.size <= cap or total > MAX_SOURCE + 5_000_000:
                raise ValueError("Source expansion exceeds its bound")
            b = archive.extractfile(member).read(member.size + 1)
            if len(b) != member.size:
                raise ValueError("Truncated source archive")
            members[member.name] = b
    inventory = json.loads(members.pop("files.json"))
    if inventory.get("repository") != entry["repository"] or inventory.get("source_sha") != entry["source_sha"]:
        raise ValueError("Source inventory identity differs")
    expected = {"source/" + e["path"]: e for e in inventory["files"]}
    if set(members) != set(expected) or len(expected) != len(inventory["files"]):
        raise ValueError("Source inventory members differ")
    for name, b in members.items():
        e = expected[name]
        if e["bytes"] != len(b) or e["sha256"] != digest(b):
            raise ValueError("Source file digest differs from the pinned snapshot")
    # Validation completes before any archive path is written. No extractall/symlinks.
    destination.mkdir(parents=True)
    for name, b in members.items():
        p = destination / name
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("xb") as out:
            out.write(b)
        p.chmod(0o400)
    return inventory


def child_environment():
    allow = {"PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "LD_LIBRARY_PATH", "VIRTUAL_ENV",
             "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "PYTHONUNBUFFERED"}
    return {k: v for k, v in os.environ.items() if k in allow} | {"SEMGREP_SEND_METRICS": "off", "SEMGREP_ENABLE_VERSION_CHECK": "0"}


def run_scanner(argv, log, seconds):
    with Path(log).open("wb") as output:
        child = subprocess.Popen(argv, stdout=output, stderr=subprocess.STDOUT, env=child_environment(), start_new_session=True, cwd=TOOLS)
        try:
            return child.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=5)
            return 124


def pack_files(files, target):
    total = sum(len(x) for x in files.values())
    if total > MAX_REPORT:
        raise ValueError("Audit report exceeds its publication bound")
    with target.open("xb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as zipped:
        with tarfile.open(fileobj=zipped, mode="w") as archive:
            for name, data in sorted(files.items()):
                member = tarfile.TarInfo(name)
                member.size, member.mode = len(data), 0o600
                archive.addfile(member, io.BytesIO(data))


def scan(args):
    before(30 * 60)
    source, run = context()
    m = manifest(args.tag, args.manifest_sha256)
    admission(args.tag, args.manifest_sha256)
    matches = [e for e in m["repos"] if e["repository"] == args.repository]
    if len(matches) != 1:
        raise ValueError("Repository is outside the frozen campaign")
    entry = matches[0]
    work = Path(args.work_dir)
    work.mkdir(parents=True, exist_ok=True)
    inventory = unpack(download(args.tag, entry["asset"], entry["sha256"], entry["bytes"]), work / "snapshot", entry)
    rules = m["rules"]
    rule_path = work / "semgrep-rules.yml"
    rule_path.write_bytes(download(args.tag, rules["asset"], rules["sha256"], rules["bytes"], 5_000_000))
    out = work / "report"
    status = run_scanner([sys.executable, str(TOOLS / "scan.py"), "--source", str(work / "snapshot/source"),
                          "--repository", args.repository, "--source-sha", entry["source_sha"],
                          "--output", str(out), "--rules", str(rule_path), "--deadline", DEADLINE],
                         work / "scanner-process.log", min(25 * 60, max(1, remaining(180))))
    result_path = out / "result.json"
    if not result_path.is_file():
        result = {"schema_version": 1, "repository": args.repository, "source_sha": entry["source_sha"],
                  "coverage": {"controller": {"status": "error", "exit_code": status}}, "findings": [],
                  "incomplete": True, "reason": "Scanner did not produce a complete structured result"}
    else:
        if result_path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("Structured result exceeds its bound")
        result = json.loads(result_path.read_text())
    if result.get("repository") != args.repository or result.get("source_sha") != entry["source_sha"]:
        raise ValueError("Scanner result identity differs from the frozen source")
    result.update({"harness_sha": source, "run_id": run, "source_asset_sha256": entry["sha256"],
                   "source_files_in_snapshot": len(inventory["files"]), "source_files_excluded": len(inventory.get("excluded", [])),
                   "source_secret_candidates": inventory.get("secret_candidates", []),
                   "rulepack_sha256": rules["sha256"], "controller_exit_code": status,
                   "review_state": "static_candidates_require_triage"})
    result["analysis_incomplete"] = bool(status) or any(a.get("status") in ("error", "timeout") for a in result.get("analyzers", {}).values())
    files = {"result.json": (json.dumps(result, sort_keys=True) + "\n").encode()}
    summary = out / "summary.md"
    if summary.is_file() and summary.stat().st_size < 2 * 1024 * 1024:
        files["summary.md"] = summary.read_bytes()
    package = work / f"report-{entry['repository'].split('/')[1]}-{entry['source_sha'][:12]}.tar.gz"
    pack_files(files, package)
    upload(args.tag, package)
    print(json.dumps({"repository": args.repository, "source_sha": entry["source_sha"],
                      "findings": len(result.get("findings", [])), "source_files": len(inventory["files"]),
                      "report": package.name, "scanner_exit_code": status}))
    if result["analysis_incomplete"]:
        raise RuntimeError("Scanner reported incomplete analysis; its structured report is preserved")


def collect(args):
    before(60)
    source, run = context()
    m = manifest(args.tag, args.manifest_sha256)
    admission(args.tag, args.manifest_sha256)
    reports, missing = [], []
    listed = {a["name"]: a for a in assets(args.tag)}
    for e in m["repos"]:
        name = f"report-{e['repository'].split('/')[1]}-{e['source_sha'][:12]}.tar.gz"
        if name not in listed:
            missing.append(e["repository"])
            continue
        data = download(args.tag, name, limit=MAX_REPORT)
        with tarfile.open(fileobj=io.BytesIO(data), mode="r|gz") as archive:
            found = None
            for i, member in enumerate(archive):
                if i >= 2 or member.name not in ("result.json", "summary.md") or not member.isfile() or member.size > MAX_REPORT:
                    raise ValueError("Unexpected report archive member")
                if member.name == "result.json":
                    found = json.loads(archive.extractfile(member).read(member.size))
            if found is None or found.get("repository") != e["repository"] or found.get("source_sha") != e["source_sha"] or found.get("run_id") != run or found.get("harness_sha") != source:
                raise ValueError("Report source/run binding failed")
            reports.append(found)
    work = Path(args.work_dir)
    work.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": 1, "harness_sha": source, "run_id": run, "manifest_sha256": args.manifest_sha256,
              "review_state": "static_candidates_require_triage", "deadline": DEADLINE,
              "repositories_requested": len(m["repos"]), "repositories_reported": len(reports), "missing": missing,
              "source_preparation_skipped": m.get("skipped", []), "reports": reports}
    path = work / "campaign-report.json"
    path.write_text(json.dumps(report, sort_keys=True) + "\n")
    rows = ["# CRACI repository bug and quality audit", "", f"Run {run}; harness `{source}`.",
            "", "Static findings are candidates requiring source review; analyzer failures, unsupported languages and excluded files do not establish clean code.",
            "", "| Repository | Source | Candidate findings | Scanner exit |", "| --- | --- | ---: | ---: |"]
    for r in reports:
        rows.append(f"| {r['repository']} | `{r['source_sha']}` | {len(r.get('findings', []))} | {r.get('controller_exit_code')} |")
    rows += ["", "Missing reports: " + (", ".join(missing) or "none"), "", "No project code, project install scripts or auto-fixes were executed."]
    summary = work / "campaign-summary.md"
    summary.write_text("\n".join(rows) + "\n")
    upload(args.tag, path)
    upload(args.tag, summary)
    print(json.dumps({"reports_preserved": len(reports), "missing": missing,
                      "candidate_findings": sum(len(r.get("findings", [])) for r in reports)}))
    if missing or any(r.get("analysis_incomplete") or r.get("controller_exit_code") for r in reports):
        raise RuntimeError("Partial audit; complete findings and missing/error states are preserved")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("plan", "scan", "collect"))
    parser.add_argument("--tag", required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--repository")
    args = parser.parse_args()
    validate_tag(args.tag)
    {"plan": plan, "scan": scan, "collect": collect}[args.command](args)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Audit stopped: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1)
