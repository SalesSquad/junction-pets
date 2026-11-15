"""Source-bound official replay qualification. No server, simulator or robot launcher."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import os
from pathlib import Path
import selectors
import subprocess
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

UPSTREAM = "36daf5b44dad46b8f448a5124ded7faa9947be1e"
BASE = "f8fcde20a81b52a6d208de74284efcd209b35eda"
DATASET = "04046a85586feb5727f991adee3367176015cab0"
URDF = Path("third_party/xr_teleoperate/assets/g1/g1_body29_hand14.urdf")
MAX_OUTPUT = 65536
METRIC_KEYS = {"calls", "ticks", "command_hz", "min_hz", "errors", "n_errors",
               "pass", "connect_s", "latency_ms_p50", "latency_ms_max"}


class Rejected(ValueError):
    """A failed admission or invalid official result."""


def policy_url(value):
    try:
        u = urlsplit(value)
        if (u.scheme != "ws" or u.hostname not in {"127.0.0.1", "localhost"}
                or u.username is not None or u.password is not None
                or u.path or u.query or u.fragment or u.port is None
                or not 1 <= u.port <= 65535
                or value != f"ws://{u.hostname}:{u.port}"):
            raise ValueError
    except ValueError:
        raise argparse.ArgumentTypeError("policy must be ws://127.0.0.1:PORT or ws://localhost:PORT") from None
    return value


def count(value):
    try:
        n = int(value)
        if not 2 <= n <= 200:
            raise ValueError
    except ValueError:
        raise argparse.ArgumentTypeError("synthetic count must be 2..200") from None
    return n


def parse_metrics(stdout, expected):
    """One bounded literal dict; never eval code or select a convenient green line."""
    if type(expected) is not int or not 2 <= expected <= 200:
        raise Rejected("invalid expected count")
    if len(stdout.encode("utf-8")) > MAX_OUTPUT:
        raise Rejected("official output exceeds limit")
    lines = [s.strip() for s in stdout.splitlines() if s.strip()]
    if len(lines) != 1 or len(lines[0]) > 8192:
        raise Rejected("expected exactly one official metrics line")
    try:
        tree = ast.parse(lines[0], mode="eval")
        if not isinstance(tree.body, ast.Dict):
            raise ValueError
        keys = [ast.literal_eval(k) for k in tree.body.keys]
        if any(type(k) is not str for k in keys) or len(set(keys)) != len(keys):
            raise ValueError
        metrics = ast.literal_eval(tree)
    except (ValueError, SyntaxError, TypeError, RecursionError, MemoryError):
        raise Rejected("invalid metrics literal") from None
    if type(metrics) is not dict or set(metrics) != METRIC_KEYS:
        raise Rejected("unexpected metrics keys")
    for key in ("calls", "ticks", "n_errors"):
        if type(metrics[key]) is not int or metrics[key] < 0:
            raise Rejected("invalid integer metric")
    for key in ("command_hz", "min_hz", "connect_s", "latency_ms_p50", "latency_ms_max"):
        v = metrics[key]
        if type(v) not in (int, float) or v < 0 or v > 1e12 or not math.isfinite(v):
            raise Rejected("invalid finite numeric metric")
    if type(metrics["pass"]) is not bool or type(metrics["errors"]) is not list:
        raise Rejected("invalid pass/errors types")
    if (metrics["calls"] != expected or metrics["ticks"] != expected
            or metrics["min_hz"] != 27 or metrics["command_hz"] < 27
            or metrics["n_errors"] != 0 or metrics["errors"] != []
            or metrics["pass"] is not True
            or metrics["latency_ms_p50"] > metrics["latency_ms_max"]):
        raise Rejected("official metrics fail exact count/rate/error gate")
    return metrics


def git(root, *args):
    p = subprocess.run(["git", "--no-optional-locks", "-C", str(root), *args],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10,
                       env={**os.environ, "GIT_NO_REPLACE_OBJECTS": "1"})
    if p.returncode:
        raise Rejected("git source verification failed")
    return p.stdout


def blob_id(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def verify_tree(root, revision, prefix):
    """Compare bytes to immutable git blobs, including ignored import-shadow files."""
    entries = git(root, "ls-tree", "-rz", revision, "--", prefix).split(b"\0")
    tracked = set()
    digests = {}
    for entry in filter(None, entries):
        meta, raw_name = entry.split(b"\t", 1)
        mode, kind, oid = meta.decode().split()
        name = raw_name.decode()
        if kind != "blob" or mode not in {"100644", "100755"}:
            raise Rejected("unsupported source tree entry")
        path = root / name
        if path.resolve() != path.absolute() or not path.is_file():
            raise Rejected("missing or symlinked source")
        data = path.read_bytes()
        if blob_id(data) != oid:
            raise Rejected("source bytes differ from pinned commit")
        tracked.add(name)
        digests[name] = hashlib.sha256(data).hexdigest()
    if not tracked:
        raise Rejected("source tree absent at pin")
    for p in (root / prefix).rglob("*"):
        if p.is_symlink():
            raise Rejected("symlink in import tree")
        if p.is_file() and p.suffix in {".py", ".pyc", ".so", ".pyd"}:
            # CPython validates cached bytecode poorly for this provenance claim.
            # Child uses a fresh pycache prefix; existing caches cannot be imported.
            if "__pycache__" in p.parts and p.suffix == ".pyc":
                continue
            if p.relative_to(root).as_posix() not in tracked:
                raise Rejected("untracked import source in pinned tree")
    return digests


def mock_status(upstream):
    if not (upstream / URDF).is_file():
        return "blocked_missing_asset"
    # A filename or a short revision string cannot authenticate the licensed blob.
    # No mock execution is admitted in this milestone, even if an asset appears.
    return "blocked_unverified_asset"


def verify_sources(upstream):
    if git(upstream, "rev-parse", "--show-toplevel").decode().strip() != str(upstream):
        raise Rejected("upstream must be the actual repository root")
    sha = git(upstream, "rev-parse", "HEAD").decode().strip()
    if sha != UPSTREAM:
        raise Rejected("upstream HEAD differs from required SHA")
    hashes = verify_tree(upstream, UPSTREAM, "aaltonomous")
    parent = Path(__file__).resolve().parents[1]
    repo = Path(git(parent, "rev-parse", "--show-toplevel").decode().strip())
    policy_hashes = {}
    for name in ("policy.py", "adapter.py", "joint_limits.py"):
        p = parent / name
        rel = p.relative_to(repo).as_posix()
        original = git(repo, "show", f"{BASE}:{rel}")
        if p.is_symlink() or p.read_bytes() != original:
            raise Rejected("local policy/adapter bytes differ from assigned baseline")
        policy_hashes[name] = hashlib.sha256(original).hexdigest()
    spec = (upstream / "aaltonomous/interface/joint_spec.yaml").read_text()
    if "source_urdf: xr_teleoperate@76a63c4:assets/g1/g1_body29_hand14.urdf\n" not in spec:
        raise Rejected("unexpected URDF source declaration")
    return {"upstream_sha": sha, "upstream_sha256": hashes,
            "local_baseline": BASE, "local_sha256": policy_hashes,
            "asset_status": mock_status(upstream), "asset_declared_pin": "xr_teleoperate@76a63c4",
            "asset_exact_blob_verified": False}


# -I excludes cwd/user-site/environment import shadows. The sole PYTHONPATH root
# is inserted explicitly; a fresh pycache prefix prevents stale bytecode use.
BOOTSTRAP = """import os, pathlib, runpy, sys
root = pathlib.Path(os.environ['PYTHONPATH']).resolve()
sys.path.insert(0, str(root))
import aaltonomous.deploy.protocol, aaltonomous.deploy.policy_server
import aaltonomous.deploy.runner, aaltonomous.interface.backends
for name, module in list(sys.modules.items()):
    if name == 'aaltonomous' or name.startswith('aaltonomous.'):
        paths = list(getattr(module, '__path__', []))
        if getattr(module, '__file__', None): paths.append(module.__file__)
        if not paths or any(not pathlib.Path(p).resolve().is_relative_to(root / 'aaltonomous') for p in paths):
            raise RuntimeError('mixed official import provenance')
sys.argv = ['aaltonomous.deploy.replay'] + sys.argv[1:]
runpy.run_module('aaltonomous.deploy.replay', run_name='__main__')
"""


def run_bounded(command, env, cwd):
    """Bound combined output and wall time; never shell-execute server output."""
    with subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT) as p:
        out = bytearray()
        deadline = time.monotonic() + 60
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(p.stdout, selectors.EVENT_READ)
                while selector.get_map():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise Rejected("official replay exceeded 60 seconds")
                    for key, _ in selector.select(min(remaining, 0.2)):
                        chunk = os.read(key.fd, 8192)
                        if not chunk:
                            selector.unregister(key.fileobj)
                        out.extend(chunk)
                        if len(out) > MAX_OUTPUT:
                            raise Rejected("official output exceeds limit")
                rc = p.wait(timeout=max(0.001, deadline - time.monotonic()))
        finally:
            if p.poll() is None:
                p.kill()
            p.wait()
        return rc, bytes(out).decode("utf-8", errors="strict")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--upstream", required=True, type=Path)
    ap.add_argument("--policy", required=True, type=policy_url)
    ap.add_argument("--python", required=True, type=Path)
    ap.add_argument("--synthetic", type=count, default=100)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--mock", action="store_true", help="check dependency only; never launch mock")
    a = ap.parse_args(argv)
    report = {"work_id": "J26-PF-AALTO-M320-M2-20261114", "status": "rejected",
              "started_utc": datetime.now(timezone.utc).isoformat(),
              "dataset_revision_metadata_only": DATASET, "synthetic": a.synthetic,
              "scope": "local synthetic official protocol replay only",
              "server_identity_verified": False, "robot_or_simulator_qualified": False}
    # Reserve evidence before admission/execution: never overwrite or run on collision.
    try:
        handle = a.output.open("x", encoding="utf-8")
    except OSError:
        print("Cannot exclusively create output; no replay executed.", file=sys.stderr)
        return 2
    with handle:
        try:
            upstream = a.upstream.resolve(strict=True)
            # Keep the venv executable path: resolving its symlink loses venv identity.
            python = a.python.absolute()
            if not python.is_file() or not os.access(python, os.X_OK):
                raise Rejected("selected Python is not executable")
            report["sources"] = verify_sources(upstream)
            report["harness_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
            if a.mock:
                report["status"] = mock_status(upstream)
                report["reason"] = "Exact licensed pinned asset unresolved; mock not launched; staff safety unchanged."
            else:
                import tempfile
                with tempfile.TemporaryDirectory(prefix="j26-m320-qualify-") as tmp:
                    command = [str(python), "-I", "-B", "-X", f"pycache_prefix={tmp}/pycache",
                               "-c", BOOTSTRAP, "--synthetic", str(a.synthetic), "--policy", a.policy]
                    report["command"] = command
                    report["pythonpath"] = str(upstream)
                    rc, stdout = run_bounded(command, {**os.environ, "PYTHONPATH": str(upstream)}, upstream)
                    report["returncode"] = rc
                    report["output_sha256"] = hashlib.sha256(stdout.encode()).hexdigest()
                    # Recheck bytes after execution to reject a changing checkout.
                    if verify_sources(upstream) != report["sources"]:
                        raise Rejected("source provenance changed during replay")
                    if rc != 0:
                        raise Rejected("official replay returned nonzero; raw output intentionally omitted")
                    report["metrics"] = parse_metrics(stdout, a.synthetic)
                    report["status"] = "pass_protocol_only"
        except (Rejected, OSError, subprocess.SubprocessError, UnicodeError) as exc:
            report["reason"] = str(exc) if isinstance(exc, Rejected) else type(exc).__name__
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        json.dump(report, handle, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"status": report["status"], "output": str(a.output)}))
    return 0 if report["status"] == "pass_protocol_only" else 2


if __name__ == "__main__":
    raise SystemExit(main())
