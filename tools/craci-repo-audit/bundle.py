#!/usr/bin/env python3
"""Build bounded, secret-filtered source snapshots on the authorized MacBook Pro.

This tool never runs project code, installs dependencies, or publishes anything.
Secret matching is heuristic: a clean snapshot is not proof that secrets or bugs
are absent. Excluded files and size/count limits reduce the review's coverage.
"""
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
import socket
import subprocess
import sys
import tarfile
import tempfile
import urllib.parse

OWNER = "SalesSquad"
DEADLINE = "2026-11-15T17:00:00Z"
MAX_FILE = 1024 * 1024
MAX_SOURCE = 100 * 1024 * 1024
MAX_COMPRESSED = 40 * 1024 * 1024
MAX_FILES = 10000
EXTENSIONS = {".py", ".pyi", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".rs", ".swift",
              ".go", ".java", ".kt", ".cs", ".c", ".h", ".cpp", ".hpp", ".rb", ".php", ".sh", ".bash", ".zsh", ".sql"}
MANIFESTS = {"package.json", "package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock",
             "cargo.toml", "cargo.lock", "pyproject.toml", "requirements.txt", "pipfile", "pipfile.lock",
             "poetry.lock", "uv.lock", "go.mod", "go.sum", "gemfile", "gemfile.lock", "composer.json",
             "composer.lock", "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts",
             "pom.xml", "package.resolved", "packages.lock.json", "directory.packages.props"}
DENIED_DIRS = {".git", "node_modules", ".venv", "venv", "env", "__pycache__", ".tox", ".mypy_cache",
               ".next", ".nuxt", ".cache", ".swiftpm", "build", "dist", "target", "vendor", "generated",
               "data", "datasets", "fixtures", "__fixtures__", "snapshots", "__snapshots__", "private",
               "records", "user-data", "user_data", "child-data", "child_data", "family-data", "family_data",
               "customer-data", "customer_data", "conversations", "transcripts", "memories", "memory",
               "backups", "exports", "uploads", "attachments", "receipts", "evidence", "logs"}
DENIED_NAMES = {".env", ".npmrc", ".pypirc", ".netrc", ".dockercfg", ".git-credentials", "credentials",
                "credentials.json", "credentials.yaml", "credentials.yml", "credentials.toml", "credentials.py",
                "secrets.json", "secrets.yaml", "secrets.yml", "secrets.toml", "secrets.py",
                "id_rsa", "id_ed25519", "id_ecdsa", "id_dsa"}
KEY_EXTENSIONS = {".pem", ".key", ".p12", ".pfx", ".keystore", ".jks", ".mobileprovision"}
DEFAULT_EXCLUDED_REPOS = {"work-archive", "taskupankki-notes", "macassetdam"}
SECRET_RULES = (
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("github-token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,255}|github_pat_[A-Za-z0-9_]{20,255})\b")),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("openai-style-key", re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("stripe-secret-key", re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")),
    ("credential-uri", re.compile(r"\b(?:https?|postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqps?)://[^\s:/@]+:[^\s/@]{3,}@", re.I)),
    ("jwt-literal", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("secret-assignment", re.compile(r'''(?i)\b(?:api[_-]?key|secret[_-]?key|client[_-]?secret|access[_-]?token|auth[_-]?token|token|secret|password|passwd|private[_-]?key)\s*[:=]\s*['"]([^'"\r\n]{8,})['"]''')),
)


def utc_guard():
    if dt.datetime.now(dt.timezone.utc) >= dt.datetime.fromisoformat(DEADLINE.replace("Z", "+00:00")):
        raise ValueError("Audit campaign deadline reached")


def repository_name(value):
    if not re.fullmatch(r"SalesSquad/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", value):
        raise ValueError("Only explicitly owned SalesSquad repositories are supported")
    return value


def command(argv, cwd=None, data=None, timeout=180, env=None):
    result = subprocess.run(argv, cwd=cwd, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=timeout, env=env, check=False)
    if result.returncode:
        # Never include provider responses, source snippets, or credentials in errors.
        raise RuntimeError(f"{Path(argv[0]).name} operation failed (exit {result.returncode})")
    return result.stdout


def api(path):
    raw = command(["gh", "api", path], timeout=90)
    if len(raw) > 15 * 1024 * 1024:
        raise ValueError("GitHub metadata response exceeds its bound")
    return json.loads(raw)


def git_environment():
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0",
               GIT_LFS_SKIP_SMUDGE="1", GIT_ATTR_NOSYSTEM="1", GIT_TEMPLATE_DIR=os.devnull)
    return env


def git(*args, cwd=None, data=None):
    options = ["-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
               "-c", "core.attributesFile=/dev/null", "-c", "filter.lfs.process=",
               "-c", "filter.lfs.smudge=", "-c", "filter.lfs.required=false",
               "-c", "protocol.file.allow=never", "-c", "protocol.ext.allow=never",
               "-c", "credential.helper=", "-c", "credential.helper=!gh auth git-credential"]
    return command(["git", *options, *args], cwd, data, timeout=240, env=git_environment())


def allowed_path(value):
    path = PurePosixPath(value)
    if (not value or value.startswith("/") or "\\" in value or any(ord(c) < 32 or ord(c) == 127 for c in value)
            or any(p in {"", ".", ".."} or p != p.strip() for p in value.split("/"))
            or len(value.encode("utf-8")) > 1024):
        return "unsafe-path"
    parts = [part.lower() for part in path.parts]
    name = parts[-1]
    if any(part in DENIED_DIRS for part in parts[:-1]):
        return "excluded-directory"
    if name in DENIED_NAMES or name.startswith(".env.") or path.suffix.lower() in KEY_EXTENSIONS:
        return "credential-file"
    if name.endswith((".min.js", ".min.css", ".generated.swift", ".generated.ts")) or name.endswith(".g.dart"):
        return "generated-file"
    if (path.suffix.lower() in EXTENSIONS or name in MANIFESTS or name.endswith(".csproj")
            or re.fullmatch(r"requirements[-_.a-z0-9]*\.txt", name)):
        return None
    return "unsupported-type"


def report_path(value):
    if any(pattern.search(value) for _, pattern in SECRET_RULES):
        return "[redacted-path-" + hashlib.sha256(value.encode()).hexdigest()[:16] + "]"
    return value


def excluded_path(value):
    # Excluded records/assets may have personal names or IDs in their filenames.
    # Preserve coverage counts/reasons without copying those filenames to cloud.
    return "[excluded-path-" + hashlib.sha256(value.encode()).hexdigest()[:16] + "]"


def secret_candidates(text, path):
    result = []
    for rule_id, pattern in SECRET_RULES:
        for match in pattern.finditer(text):
            if rule_id == "secret-assignment":
                literal = match.group(1).strip().lower()
                if (literal.startswith(("${", "{{", "<", "process.env", "os.environ"))
                        or literal in {"changeme", "your-api-key", "your_api_key", "placeholder", "example", "password"}):
                    continue
            result.append({"path": report_path(path), "line": text.count("\n", 0, match.start()) + 1, "rule_id": rule_id})
            if len(result) >= 20:
                return result
    return result


def sparse_pattern(path):
    if allowed_path(path):
        raise ValueError("Only selected safe source paths may enter sparse patterns")
    return "/" + re.sub(r"([\\*?\[\]])", r"\\\1", path)


def selected_tree(tree):
    if tree.get("truncated"):
        raise ValueError("Tree response is truncated; refuse an incomplete snapshot")
    selected, excluded, size = [], [], 0
    for entry in sorted(tree["tree"], key=lambda item: item["path"]):
        if entry.get("type") == "tree":
            continue
        path = entry["path"]
        reason = allowed_path(path)
        if not reason and (entry.get("type") != "blob" or entry.get("mode") not in {"100644", "100755"}):
            reason = "nonregular-file"
        count = entry.get("size")
        if not reason and (type(count) is not int or not 0 <= count <= MAX_FILE):
            reason = "file-size-bound"
        if not reason and (len(selected) >= MAX_FILES or size + count > MAX_SOURCE):
            reason = "repository-source-bound"
        if reason:
            excluded.append({"path": excluded_path(path), "reason": reason})
        else:
            if not re.fullmatch(r"[a-f0-9]{40}", entry.get("sha", "")):
                raise ValueError("Tree contains an invalid immutable blob identifier")
            selected.append(entry)
            size += count
    return selected, excluded


def source_blobs(clone, source_sha, selected):
    """Bulk-prefetch by safe sparse checkout, then read the original Git bytes."""
    git("sparse-checkout", "init", "--no-cone", cwd=clone)
    patterns = "\n".join(sparse_pattern(entry["path"]) for entry in selected) + "\n"
    git("sparse-checkout", "set", "--no-cone", "--stdin", cwd=clone, data=patterns.encode())
    git("checkout", "--detach", "--force", source_sha, cwd=clone)
    for entry in selected:
        data = git("cat-file", "blob", entry["sha"], cwd=clone)
        if len(data) != entry["size"] or len(data) > MAX_FILE:
            raise ValueError("Git blob size differs from the immutable tree")
        oid = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if oid != entry["sha"]:
            raise ValueError("Git blob identity mismatch")
        yield entry["path"], data


def filtered_sources(blobs, excluded):
    files, contents, candidates = [], {}, []
    for path, data in blobs:
        if data.startswith(b"version https://git-lfs.github.com/spec/v1\n"):
            excluded.append({"path": excluded_path(path), "reason": "lfs-pointer-not-source"})
            continue
        if b"\0" in data:
            excluded.append({"path": excluded_path(path), "reason": "binary-content"})
            continue
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            excluded.append({"path": excluded_path(path), "reason": "non-utf8-content"})
            continue
        if any(ord(c) < 32 and c not in "\n\r\t" for c in text):
            excluded.append({"path": excluded_path(path), "reason": "non-text-content"})
            continue
        matches = secret_candidates(text, path)
        if matches:
            remaining = max(0, 5000 - len(candidates))
            candidates.extend(matches[:remaining])
            reason = "likely-secret" if remaining >= len(matches) else "likely-secret;candidate-report-bound"
            excluded.append({"path": excluded_path(path), "reason": reason})
            continue
        contents[path] = data
        files.append({"path": path, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
    return files, contents, candidates


def write_bundle(destination, metadata, contents):
    destination = Path(destination)
    if any(allowed_path(path) for path in contents):
        raise ValueError("Unsafe or non-source archive member refused")
    manifest_data = (json.dumps(metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()
    if sum(map(len, contents.values())) + len(manifest_data) > MAX_SOURCE:
        raise ValueError("Total source and manifest payload exceeds 100 MiB")
    descriptor, name = tempfile.mkstemp(prefix=".source-bundle-", suffix=".part", dir=destination.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as zipped:
            with tarfile.open(fileobj=zipped, mode="w") as archive:
                members = {"source/" + path: data for path, data in contents.items()}
                members["files.json"] = manifest_data
                for path, data in sorted(members.items()):
                    item = tarfile.TarInfo(path)
                    item.mode, item.size = 0o600, len(data)
                    archive.addfile(item, io.BytesIO(data))
        if temporary.stat().st_size > MAX_COMPRESSED:
            raise ValueError("Compressed source bundle exceeds 40 MiB")
        if destination.exists():
            if hashlib.sha256(destination.read_bytes()).digest() != hashlib.sha256(temporary.read_bytes()).digest():
                raise ValueError("Preserve a differing existing source bundle")
        else:
            os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def snapshot(repository, output):
    utc_guard()
    repository_name(repository)
    info = api("repos/" + repository)
    if info.get("full_name") != repository or info.get("archived") or info.get("fork") or not info.get("default_branch"):
        raise ValueError("Repository is archived, a fork, empty, or outside the requested owner")
    branch = info["default_branch"]
    commit = api(f"repos/{repository}/commits/{urllib.parse.quote(branch, safe='')}")
    source_sha = commit.get("sha", "")
    if not re.fullmatch(r"[a-f0-9]{40}", source_sha):
        raise ValueError("Could not resolve an immutable default-branch SHA")
    tree = api(f"repos/{repository}/git/trees/{source_sha}?recursive=1")
    selected, excluded = selected_tree(tree)
    if not selected:
        raise ValueError("No allowlisted source files within snapshot bounds")
    with tempfile.TemporaryDirectory(prefix="craci-source-snapshot-") as temporary:
        clone = Path(temporary) / "source"
        git("clone", "--filter=blob:none", "--no-checkout", "--depth=1", "--single-branch",
            "--branch=" + branch, f"https://github.com/{repository}.git", str(clone))
        if git("rev-parse", "HEAD", cwd=clone).decode().strip() != source_sha:
            git("fetch", "--depth=1", "--filter=blob:none", "--no-tags", "origin", source_sha, cwd=clone)
        files, contents, candidates = filtered_sources(source_blobs(clone, source_sha, selected), excluded)
    if not files:
        raise ValueError("All selected files were excluded by content or secret guards")
    metadata = {"schema_version": 1, "repository": repository, "source_sha": source_sha,
                "files": files, "excluded": excluded, "secret_candidates": candidates}
    name = "source-" + repository.split("/")[1] + "-" + source_sha[:12] + ".tar.gz"
    destination = Path(output) / name
    write_bundle(destination, metadata, contents)
    return {"repository": repository, "source_sha": source_sha, "asset": name,
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(), "bytes": destination.stat().st_size,
            "file_count": len(files), "source_bytes": sum(item["bytes"] for item in files)}


def discover(limit):
    raw = command(["gh", "api", "--paginate", "--slurp", "user/repos?affiliation=owner&sort=pushed&per_page=100"], timeout=90)
    pages = json.loads(raw)
    choices = [repo for page in pages for repo in page
               if repo.get("owner", {}).get("login") == OWNER and not repo.get("archived") and not repo.get("fork")
               and repo.get("default_branch") and repo["name"].lower() not in DEFAULT_EXCLUDED_REPOS]
    choices.sort(key=lambda repo: (repo.get("pushed_at") or "", repo["full_name"]), reverse=True)
    return [repository_name(repo["full_name"]) for repo in choices[:limit]]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repos", nargs="+", help="Explicit SalesSquad/name repositories; omit for the first recent wave")
    parser.add_argument("--limit", type=int, default=10, help="Discovery wave size (1..1000)")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if socket.gethostname() != "Mikael-MacBook-Pro.local" or sys.platform != "darwin":
        raise ValueError("Snapshots may only be built on the already authorized MacBook Pro")
    utc_guard()
    if not 1 <= args.limit <= 1000:
        raise ValueError("Discovery limit must be in 1..1000")
    if api("user").get("login") != OWNER:
        raise ValueError("Existing GitHub identity is not the authorized repository owner")
    repositories = list(dict.fromkeys(repository_name(repo) for repo in args.repos)) if args.repos else discover(args.limit)
    args.output.mkdir(parents=True, exist_ok=True)
    if any(args.output.iterdir()):
        raise ValueError("Use a fresh empty output directory; previous snapshots are preserved")
    campaign = {"schema_version": 1, "deadline": DEADLINE, "repos": [], "skipped": []}
    for repository in repositories:
        try:
            item = snapshot(repository, args.output)
            campaign["repos"].append(item)
            print(json.dumps({"repository": repository, "file_count": item["file_count"], "source_sha": item["source_sha"]}), flush=True)
        except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as error:
            # Error messages are deliberately generic and never contain project text.
            reason = str(error) if isinstance(error, (ValueError, RuntimeError)) else type(error).__name__
            campaign["skipped"].append({"repository": repository, "reason": reason})
        (args.output / "campaign.json").write_text(json.dumps(campaign, indent=2, ensure_ascii=False) + "\n")
    return 0 if campaign["repos"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        message = str(error) if isinstance(error, (ValueError, RuntimeError)) else type(error).__name__
        print(f"Snapshot builder refused or failed: {message}", file=sys.stderr)
        raise SystemExit(1)
