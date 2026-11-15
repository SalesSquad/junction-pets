#!/usr/bin/env python3
"""Read-only, isolated static analysis of an already sanitized source snapshot."""

import argparse
import collections
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
HARD_DEADLINE = dt.datetime(2026, 11, 15, 17, tzinfo=dt.timezone.utc).timestamp()
MAX_FILE_BYTES = 1_048_576
MAX_SOURCE_BYTES = 67_108_864
MAX_FILES = 10000
MAX_CAPTURE_BYTES = 16_777_216
MAX_FINDINGS = 2000
EXTENSIONS = {
    ".py": "python", ".pyi": "python", ".js": "javascript", ".jsx": "javascript",
    ".mjs": "javascript", ".cjs": "javascript", ".ts": "typescript", ".tsx": "typescript",
    ".go": "go", ".rs": "rust", ".swift": "swift", ".java": "java", ".kt": "kotlin",
    ".kts": "kotlin", ".cs": "csharp", ".c": "c", ".h": "c", ".cpp": "cpp",
    ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".rb": "ruby", ".php": "php",
    ".scala": "scala", ".sh": "bash", ".bash": "bash", ".yml": "yaml", ".yaml": "yaml",
    ".json": "json", ".tf": "hcl", ".hcl": "hcl", ".html": "html", ".xml": "xml",
}
LANGUAGE_ALIASES = {"js": "javascript", "ts": "typescript", "py": "python", "c#": "csharp",
                    "c++": "cpp", "sh": "bash", "terraform": "hcl", "docker": "dockerfile"}
EXCLUDE_DIRS = {".git", "node_modules", ".venv", "venv", ".next", "dist", "build", "vendor", "__pycache__"}
MAINTENANCE_RULES = {"complexity", "max-depth", "max-params", "F401", "F403", "F405", "F841"}
ESLINT_MESSAGES = {
    "array-callback-return": "Array callback may fail to return its result.",
    "constructor-super": "Constructor may use super incorrectly.",
    "getter-return": "Getter may fail to return a value.",
    "no-async-promise-executor": "Async Promise executor can lose a rejected error.",
    "no-compare-neg-zero": "Comparison against negative zero is unreliable.",
    "no-constant-binary-expression": "Binary expression contains a constant-result condition.",
    "no-constructor-return": "Constructor returns an unexpected value.",
    "no-dupe-args": "Function parameters contain a duplicate name.",
    "no-dupe-class-members": "Class members contain a duplicate declaration.",
    "no-dupe-else-if": "Conditional branch duplicates an earlier condition.",
    "no-duplicate-case": "Switch contains a duplicate case.",
    "no-func-assign": "A function declaration is reassigned.",
    "no-import-assign": "An imported binding is reassigned.",
    "no-loss-of-precision": "Numeric literal loses precision.",
    "no-promise-executor-return": "Promise executor returns an ignored value.",
    "no-self-assign": "An assignment assigns a value to itself.",
    "no-sparse-arrays": "Sparse array may produce unexpected iteration behavior.",
    "no-unreachable": "Code is unreachable after a control-flow exit.",
    "no-unreachable-loop": "Loop cannot execute more than once.",
    "no-unsafe-finally": "Finally block may override an earlier control-flow result.",
    "no-unsafe-optional-chaining": "Optional-chain result is used where undefined is unsafe.",
    "use-isnan": "NaN comparison should use an explicit NaN check.",
    "valid-typeof": "typeof comparison uses an invalid result string.",
    "complexity": "Function exceeds the fixed cyclomatic-complexity threshold of 25.",
    "max-depth": "Nested control flow exceeds the fixed depth threshold of 5.",
    "max-params": "Function exceeds the fixed parameter threshold of 6.",
}
RUFF_MESSAGES = {"F821": "Reference to an undefined name.", "F822": "Export names an undefined binding.",
                 "F823": "Local variable is referenced before assignment.", "F811": "Declaration redefines an unused binding.",
                 "F831": "Function parameters contain a duplicate name.", "F901": "Exception construction is invalid."}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def public_text(value, maximum=300):
    text = re.sub(r"[\x00-\x1f\x7f]", " ", str(value))
    text = re.sub(r"(?:gh[pousr]_[A-Za-z0-9_]{12,}|github_pat_[A-Za-z0-9_]{12,}|sk-[A-Za-z0-9_-]{12,})", "[redacted]", text)
    return text[:maximum]


def safe_path(value, scan_root):
    try:
        path = Path(value)
        absolute = path if path.is_absolute() else scan_root / path
        relative = absolute.resolve().relative_to(scan_root.resolve()).as_posix()
    except (ValueError, OSError):
        return None
    return public_text(relative, 500)


def isolated_environment(directory, tool_dirs):
    import certifi

    # Explicit allowlist: no inherited tokens, provider keys, preload, Python/Node hooks, or user config.
    home = directory / "home"
    home.mkdir(exist_ok=True)
    certificate_file = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE") or certifi.where()
    env = {"PATH": os.pathsep.join([str(path) for path in tool_dirs] + ["/usr/bin", "/bin", "/usr/sbin", "/sbin"]),
            "HOME": str(home), "XDG_CONFIG_HOME": str(home / "config"), "XDG_CACHE_HOME": str(home / "cache"),
            "TMPDIR": str(directory), "LANG": "C.UTF-8", "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1",
            "SEMGREP_SEND_METRICS": "off", "SEMGREP_ENABLE_VERSION_CHECK": "0",
            "SEMGREP_SETTINGS_FILE": str(home / "semgrep-settings.yml"), "DO_NOT_TRACK": "1",
            "SSL_CERT_FILE": certificate_file,
            "REQUESTS_CA_BUNDLE": os.environ.get("REQUESTS_CA_BUNDLE") or certificate_file,
            "NO_COLOR": "1", "CI": "true"}
    # setup-python's trusted CPython installation on Linux uses this shared-library path.
    if os.environ.get("LD_LIBRARY_PATH"):
        env["LD_LIBRARY_PATH"] = os.environ["LD_LIBRARY_PATH"]
    return env


def terminate(process):
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)


def capture(command, cwd, env, seconds):
    """Bound both time and raw output in memory; never persist tool output/snippets."""
    if seconds <= 0:
        return {"status": "timeout", "reason": "deadline", "stdout": b"", "exit_code": None}
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    process = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=True)
    selector = selectors.DefaultSelector()
    for name, pipe in (("stdout", process.stdout), ("stderr", process.stderr)):
        os.set_blocking(pipe.fileno(), False)
        selector.register(pipe, selectors.EVENT_READ, name)
    end = time.monotonic() + seconds
    status, reason = "completed", None
    try:
        while selector.get_map():
            if time.monotonic() >= end:
                status, reason = "timeout", "time-budget"
                break
            for key, _ in selector.select(timeout=min(0.2, max(0, end - time.monotonic()))):
                data = os.read(key.fileobj.fileno(), 65536)
                if not data:
                    selector.unregister(key.fileobj)
                    continue
                buffers[key.data].extend(data)
                if sum(map(len, buffers.values())) > MAX_CAPTURE_BYTES:
                    status, reason = "error", "output-limit"
                    break
            if status != "completed":
                break
        if process.poll() is None:
            if status != "completed":
                terminate(process)
            else:
                process.wait(timeout=max(0.1, min(5, end - time.monotonic())))
    except subprocess.TimeoutExpired:
        status, reason = "timeout", "termination-timeout"
        terminate(process)
    finally:
        selector.close()
        process.stdout.close()
        process.stderr.close()
        if process.poll() is None:
            terminate(process)
    return {"status": status, "reason": reason, "stdout": bytes(buffers["stdout"]),
            "stderr_sha256": sha256(bytes(buffers["stderr"])), "exit_code": process.returncode}


def inventory(source, target, deadline):
    files, counters, languages = {}, collections.Counter(), collections.Counter()
    total = 0
    for root, directories, names in os.walk(source, followlinks=False):
        if time.time() >= deadline:
            counters["inventory_deadline_reached"] += 1
            break
        kept = []
        for name in sorted(directories):
            candidate = Path(root) / name
            if candidate.is_symlink() or name in EXCLUDE_DIRS:
                counters["excluded_directories"] += 1
            else:
                kept.append(name)
        directories[:] = kept
        for name in sorted(names):
            if time.time() >= deadline:
                counters["inventory_deadline_reached"] += 1
                return files, dict(counters), dict(languages), total
            path = Path(root) / name
            counters["files_seen"] += 1
            if path.is_symlink() or not path.is_file():
                counters["nonregular_or_symlink"] += 1
                continue
            language = "dockerfile" if name == "Dockerfile" else EXTENSIONS.get(path.suffix.lower())
            if not language:
                counters["unsupported_file_extension"] += 1
                continue
            languages[language] += 1
            size = path.stat().st_size
            if size > MAX_FILE_BYTES:
                counters["oversized_source_files"] += 1
                continue
            if len(files) >= MAX_FILES or total + size > MAX_SOURCE_BYTES:
                counters["inventory_budget_skips"] += 1
                continue
            relative = path.relative_to(source)
            content = path.read_bytes()
            if len(content) != size:
                raise ValueError("source changed during inventory")
            copy = target / relative
            copy.parent.mkdir(parents=True, exist_ok=True)
            copy.write_bytes(content)
            files[relative.as_posix()] = {"sha256": sha256(content), "language": language}
            total += size
    return files, dict(counters), dict(languages), total


def finding(tool, rule, severity, message, path, line, end_line, repository):
    rule = public_text(rule, 200)
    identity = json.dumps([repository, tool, rule, path, int(line or 1)], separators=(",", ":"))
    return {"tool": tool, "rule_id": rule, "severity": severity, "message": public_text(message, 400),
            "path": path, "line": max(1, int(line or 1)), "end_line": max(1, int(end_line or line or 1)),
            "classification": "maintainability" if rule in MAINTENANCE_RULES else "candidate_bug",
            "fingerprint": sha256(identity.encode())}


def rule_metadata(rules):
    import yaml

    content = rules.read_bytes()
    if len(content) > 4_194_304:
        raise ValueError("rulepack exceeds fixed size budget")
    parsed = yaml.safe_load(content)
    entries = parsed.get("rules") if isinstance(parsed, dict) else None
    if not isinstance(entries, list) or not entries:
        raise ValueError("missing explicit rules")
    metadata, languages = {}, set()
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            raise ValueError("invalid fixed rule metadata")
        # The static trusted rule message is used, never Semgrep's metavariable-expanded source text.
        message = re.sub(r"\$[A-Za-z_][A-Za-z0-9_]*", "[expression]", str(entry.get("message", "Static rule matched; review required.")))
        metadata[entry["id"]] = public_text(message, 400)
        languages.update(LANGUAGE_ALIASES.get(value, value) for value in entry.get("languages", []))
    return metadata, languages, sha256(content)


def tool_version(command, cwd, env, deadline):
    result = capture(command, cwd, env, min(15, max(0, deadline - time.time())))
    if result["status"] != "completed" or result["exit_code"] != 0:
        return None
    match = re.search(rb"\b[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?\b", result["stdout"])
    return match.group().decode() if match else None


def analyze(name, command, source, env, deadline, repository, messages, considered):
    status = {"status": "unsupported", "files_considered": considered, "files_analyzed": 0, "parse_errors": 0}
    if not considered:
        return status, []
    try:
        raw = capture(command, source, env, min(480, max(0, deadline - time.time())))
    except (OSError, subprocess.SubprocessError):
        return dict(status, status="error", reason="tool-start-failed"), []
    status.update(exit_code=raw["exit_code"], diagnostic_sha256=raw.get("stderr_sha256"))
    if raw["status"] != "completed":
        return dict(status, status=raw["status"], reason=raw["reason"]), []
    allowed_exits = (0,) if name == "semgrep" else (0, 1)
    try:
        data = json.loads(raw["stdout"])
    except (ValueError, UnicodeDecodeError):
        return dict(status, status="error", reason="invalid-tool-json"), []
    status["status"] = "success" if raw["exit_code"] in allowed_exits else "error"
    found = []
    if name == "semgrep":
        scanned = data.get("paths", {}).get("scanned", [])
        status["files_analyzed"] = len(scanned)
        status["tool_errors"] = len(data.get("errors", []))
        status["files_skipped"] = max(0, considered - len(scanned))
        if status["tool_errors"]:
            status["status"] = "error"
        for item in data.get("results", []):
            path = safe_path(item.get("path", ""), source)
            if path is None:
                continue
            rule = item.get("check_id", "unknown-rule")
            message = messages.get(rule, "Static Semgrep rule matched; manual review required.")
            severity = {"ERROR": "high", "WARNING": "medium", "INFO": "low"}.get(item.get("extra", {}).get("severity"), "medium")
            found.append(finding(name, rule, severity, message, path, item.get("start", {}).get("line"),
                                 item.get("end", {}).get("line"), repository))
    elif name == "ruff":
        status["files_analyzed"] = considered if status["status"] == "success" else 0
        for item in data:
            path = safe_path(item.get("filename", ""), source)
            if path is None:
                continue
            rule = item.get("code") or "parse-error"
            if rule == "invalid-syntax" or rule.startswith("E9") or rule == "parse-error":
                status["parse_errors"] += 1
                status["status"] = "error"
            message = RUFF_MESSAGES.get(rule, "Fixed Python bug-oriented rule matched; manual review required.")
            found.append(finding(name, rule, "low" if rule in MAINTENANCE_RULES else "medium", message, path,
                                 item.get("location", {}).get("row"), item.get("end_location", {}).get("row"), repository))
    else:
        status["files_analyzed"] = len(data)
        for item in data:
            path = safe_path(item.get("filePath", ""), source)
            if path is None:
                continue
            for notice in item.get("messages", []):
                if notice.get("fatal") or not notice.get("ruleId"):
                    status["parse_errors"] += 1
                    status["status"] = "error"
                    continue
                rule = notice["ruleId"]
                found.append(finding(name, rule, "low" if notice.get("severity") == 1 else "medium",
                                     ESLINT_MESSAGES.get(rule, "Fixed JavaScript/TypeScript bug rule matched; review required."),
                                     path, notice.get("line"), notice.get("endLine"), repository))
        status["files_skipped"] = max(0, considered - len(data))
    return status, found


def scan(args):
    now = time.time()
    requested = dt.datetime.fromisoformat(args.deadline.replace("Z", "+00:00"))
    if requested.tzinfo is None or requested.utcoffset() != dt.timedelta(0):
        raise ValueError("explicit UTC deadline required")
    deadline = min(requested.timestamp(), HARD_DEADLINE, now + 25 * 60)
    if deadline <= now:
        raise ValueError("audit deadline reached")
    if not re.fullmatch(r"SalesSquad/[A-Za-z0-9_.-]+", args.repository) or not re.fullmatch(r"[0-9a-f]{40}", args.source_sha):
        raise ValueError("invalid repository/source identity")
    source, output, rules = Path(args.source).resolve(), Path(args.output).resolve(), Path(args.rules).resolve()
    if not source.is_dir() or output == source or output.is_relative_to(source) or rules.is_relative_to(source):
        raise ValueError("source, output and fixed rules must be isolated")
    messages, rule_languages, rule_hash = rule_metadata(rules)
    output.mkdir(parents=True, exist_ok=False)
    result = {"schema_version": 1, "repository": args.repository, "source_sha": args.source_sha,
              "rulepack_sha256": rule_hash, "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "tool_versions": {}, "analyzers": {}, "findings": [], "clean_claim": False}
    with tempfile.TemporaryDirectory(prefix="craci-static-") as temporary:
        # Node's cwd resolves macOS /var -> /private/var; use one canonical base for fixed ESLint globs.
        root = Path(temporary).resolve()
        copied = root / "source"
        copied.mkdir()
        files, counters, languages, source_bytes = inventory(source, copied, deadline)
        node = shutil.which("node")
        venv_bin = Path(sys.executable).absolute().parent
        tools = [venv_bin] + ([Path(node).parent] if node else [])
        env = isolated_environment(root, tools)
        applicable = {"semgrep": sum(item["language"] in rule_languages for item in files.values()),
                      "ruff": sum(item["language"] == "python" for item in files.values()),
                      "eslint": sum(item["language"] in {"javascript", "typescript"} for item in files.values())}
        semgrep = str(venv_bin / "semgrep")
        ruff = str(venv_bin / "ruff")
        eslint = [node or "/missing-node", str(HERE / "node_modules/eslint/bin/eslint.js")]
        commands = {
            "semgrep": [semgrep, "scan", "--config", str(rules), "--metrics", "off", "--disable-version-check",
                        "--disable-nosem", "--no-git-ignore", "--oss-only", "--no-rewrite-rule-ids", "--jobs", "2",
                        "--max-target-bytes", str(MAX_FILE_BYTES), "--json", "--quiet", str(copied)],
            "ruff": [ruff, "check", "--isolated", "--no-cache", "--no-respect-gitignore", "--ignore-noqa",
                     "--exclude", "", "--select", "F,E9,B,PLE", "--ignore", "F401,F403,F405,F841", "--output-format", "json", str(copied)],
            "eslint": eslint + ["--no-config-lookup", "--no-ignore", "--no-inline-config", "--config", str(HERE / "eslint.config.mjs"),
                                 "--format", "json", str(copied)],
        }
        versions = {"semgrep": [semgrep, "--version"], "ruff": [ruff, "--version"], "eslint": eslint + ["--version"]}
        for name in ("semgrep", "ruff", "eslint"):
            try:
                analyzer_deadline = min(deadline, time.time() + 473)
                version = tool_version(versions[name], copied, env, analyzer_deadline) if applicable[name] else None
                result["tool_versions"][name] = version
                status, findings = analyze(name, commands[name], copied, env, analyzer_deadline, args.repository, messages, applicable[name])
            except (OSError, subprocess.SubprocessError):
                result["tool_versions"][name] = None
                status, findings = {"status": "error", "reason": "tool-start-failed", "files_considered": applicable[name]}, []
            result["analyzers"][name] = status
            result["findings"].extend(findings)
        unchanged = all((source / path).is_file() and sha256((source / path).read_bytes()) == item["sha256"] for path, item in files.items())
        supported = rule_languages | {"python", "javascript", "typescript"}
        result["coverage"] = {"inventory": counters, "source_bytes_copied": source_bytes, "source_files_copied": len(files),
                              "languages_seen": languages, "unsupported_languages": {key: val for key, val in languages.items() if key not in supported},
                              "copied_source_files_unchanged": unchanged,
                              "integrity_scope": "copied source files only; original tree was never an analyzer working directory"}
        if not unchanged:
            raise ValueError("source integrity changed")
    order = {"high": 0, "medium": 1, "low": 2}
    findings = sorted({item["fingerprint"]: item for item in result["findings"]}.values(),
                      key=lambda item: (order[item["severity"]], item["path"], item["line"], item["rule_id"]))
    result["findings_truncated"] = max(0, len(findings) - MAX_FINDINGS)
    result["findings"] = findings[:MAX_FINDINGS]
    result["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    result["limitations"] = ["Static findings are candidates, not validated bugs or exploits.",
                             "Project code/config/plugins/hooks/install scripts were not executed.",
                             "Unsupported, excluded, oversized, parser-error and timed-out files are not clean evidence.",
                             "No dependency vulnerability audit, build, runtime, native SDK or scientific correctness test was performed."]
    (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    lines = [f"# Static audit: {args.repository}", "", f"Source: `{args.source_sha}`", "",
             "Static candidates only; no validated exploit or clean-security claim.", "", "| Analyzer | Version | Status | Files considered |", "| --- | --- | --- | ---: |"]
    lines.extend(f"| {name} | {result['tool_versions'].get(name) or 'unavailable'} | {status['status']} | {status.get('files_considered', 0)} |"
                 for name, status in result["analyzers"].items())
    lines += ["", f"Retained candidates: {len(result['findings'])}; omitted by report cap: {result['findings_truncated']}.",
              f"Unsupported languages: {json.dumps(result['coverage']['unsupported_languages'], sort_keys=True)}.", ""]
    for item in result["findings"][:100]:
        location = item["path"].replace("`", "_").replace("\n", " ")
        lines.append(f"- **{item['severity']} / {item['classification']}** `{item['tool']}:{item['rule_id']}` — `{location}:{item['line']}` — {item['message']}")
    lines += ["", *result["limitations"]]
    (output / "summary.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"status": "report-written", "repository": args.repository, "findings": len(result["findings"]),
                      "analyzers": {key: val["status"] for key, val in result["analyzers"].items()}}))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "repository", "source-sha", "output", "deadline", "rules"):
        parser.add_argument("--" + name, required=True)
    try:
        return scan(parser.parse_args())
    except Exception:
        # Tool/path/parser exceptions may contain private source. Only a fixed diagnostic is emitted.
        print(json.dumps({"status": "error", "reason": "scanner-input-or-infrastructure-error"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
