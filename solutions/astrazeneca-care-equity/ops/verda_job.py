#!/usr/bin/env python3
"""verda_job.py - run one batch job on a short-lived Verda Cloud VM and always clean up.

Python 3.10+, standard library only. Every Verda call goes through the CLI as
`verda --agent ... -o json`. See ops/README.md for the behaviour contract.

  run    create a VM from an ordered candidate list, copy a directory, run a command
         detached, stream its log, fetch artifacts, delete the VM with its volumes.
  sweep  list state files this tool left behind and what still exists; deletes nothing
         unless --delete-mine is given.

The tool deletes only instance ids that it recorded itself in a state file under
ops/.state/. It never passes --all, --hostname or --status to `verda vm delete`.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import shlex
import signal
import socket
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Callable

STATE_SCHEMA = "verda-job-state-v1"
OPS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = OPS_DIR.parent
DEFAULT_STATE_DIR = OPS_DIR / ".state"
DEFAULT_RUN_LOG = PROJECT_ROOT / "runs" / "v2-ops.jsonl"
DEFAULT_ARTIFACTS_ROOT = OPS_DIR / "artifacts"

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_NO_CANDIDATE = 70      # no candidate produced a usable machine
EXIT_SETUP_FAILED = 71      # copy or job start failed on a machine that was up
EXIT_TIME_CAP = 72          # --max-minutes reached
EXIT_BUDGET_CAP = 73        # --budget-usd reached
EXIT_SPOT_RECLAIMED = 74    # spot machine taken back by the provider mid-run
EXIT_ARTIFACT_MISSING = 75  # command exited 0 but a requested artifact could not be fetched
EXIT_DELETE_FAILED = 76     # a machine created by this run could not be confirmed deleted
EXIT_MACHINE_LOST = 77      # unreachable, host key changed, job vanished, on-demand machine lost
EXIT_INTERNAL = 78
EXIT_NEEDS_SWEEP = 79       # a create was never confirmed either way, or a delete was accepted but never confirmed

OUTCOME_EXIT = {
    "ok": EXIT_OK,
    "no_candidate": EXIT_NO_CANDIDATE,
    "setup_failed": EXIT_SETUP_FAILED,
    "time_cap": EXIT_TIME_CAP,
    "budget_cap": EXIT_BUDGET_CAP,
    "spot_reclaimed": EXIT_SPOT_RECLAIMED,
    "artifact_missing": EXIT_ARTIFACT_MISSING,
    "machine_lost": EXIT_MACHINE_LOST,
    "unreachable": EXIT_MACHINE_LOST,
    "host_key_changed": EXIT_MACHINE_LOST,
    "job_vanished": EXIT_MACHINE_LOST,
    "internal_error": EXIT_INTERNAL,
}

# A machine in one of these states is not coming (back) up. Only 'discontinued' is named in
# the task brief; the others are defensive and only ever make the tool give up on a machine.
FAILED_STATUSES = {"discontinued", "error", "no_capacity", "installation_failed", "notfound", "deleted", "deleting"}
GONE_STATUSES = {"deleted", "deleting"}

REFUSAL_CODES = {"AUTH_ERROR", "INSUFFICIENT_BALANCE", "VALIDATION_ERROR", "MISSING_REQUIRED_FLAGS", "CONFIRMATION_REQUIRED"}
STOP_CODES = {"AUTH_ERROR", "INSUFFICIENT_BALANCE"}  # no point trying further candidates
CAPACITY_RE = re.compile(r"\b503\b|not enough resources|no capacity|insufficient capacity|out of capacity", re.I)
TIMEOUT_RE = re.compile(r"context deadline exceeded|Client\.Timeout|i/o timeout|timed out|timeout exceeded", re.I)
HOSTKEY_RE = re.compile(r"REMOTE HOST IDENTIFICATION HAS CHANGED|Host key verification failed", re.I)
UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
SAFE_REMOTE_PATH_RE = re.compile(r"^[A-Za-z0-9_./@%+=:,~-]+$")
CANDIDATE_RE = re.compile(r"^(?P<type>[A-Za-z0-9._-]+)@(?P<loc>[A-Za-z0-9-]+):(?P<mode>spot|on-demand)$")
CANDIDATE_HELP = "TYPE@LOCATION:spot|on-demand[,image=SLUG][,usd=HOURLY_PRICE]"
PREFIX_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,29}$")


# ----------------------------------------------------------------------------- small helpers

def utc_iso(t: float | None = None) -> str:
    return dt.datetime.fromtimestamp(time.time() if t is None else t, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Terminal output must never stop the cleanup. When stdout or stderr stops accepting writes (a pipe
# reader such as `tee` or `head` exited, the terminal was closed, the ssh session dropped), every
# later message goes to the fallback log next to the state file instead, and file descriptors 1 and
# 2 are pointed at /dev/null so that neither a later write nor the flush at interpreter exit raises.
_OUT: dict = {"broken": False, "fallback": None}


def _fallback_write(text: str) -> None:
    path = _OUT.get("fallback")
    if not path:
        return
    try:
        os.makedirs(os.path.dirname(str(path)) or ".", exist_ok=True)
        fd = os.open(str(path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, text.encode(errors="replace"))
        finally:
            os.close(fd)
    except OSError:
        pass


def _mark_output_broken() -> None:
    _OUT["broken"] = True
    try:
        null = os.open(os.devnull, os.O_WRONLY)
        for fd in (1, 2):
            try:
                os.dup2(null, fd)
            except OSError:
                pass
        os.close(null)
    except OSError:
        pass
    _fallback_write(f"[{utc_iso()}] terminal output stopped accepting writes; the rest of this run is logged here\n")


def emit(text: str, stream: Any = None) -> None:
    """Write text to the terminal; never raises."""
    if not _OUT["broken"]:
        try:
            s = stream if stream is not None else sys.stdout
            s.write(text)
            s.flush()
            return
        except (OSError, ValueError):
            _mark_output_broken()
    _fallback_write(text)


def out(*parts: Any, end: str = "\n", file: Any = None, flush: bool = True) -> None:  # noqa: ARG001 - print-like
    emit(" ".join(str(p) for p in parts) + end, file)


def say(msg: str) -> None:
    emit(f"[{dt.datetime.now(dt.timezone.utc):%H:%M:%SZ}] {msg}\n")


def loud(lines: list[str]) -> None:
    bar = "!" * 78
    emit("\n" + bar + "\n" + "".join("!! " + line + "\n" for line in lines) + bar + "\n\n")


def report_exception() -> None:
    emit(traceback.format_exc(), sys.stderr)


SECRET_RE = re.compile(r"(?i)(?:\b(?:dc|hf|verda_s3)_[A-Za-z0-9_\-]{6,}|\bnvapi-[A-Za-z0-9_\-]{6,}|\bsk-[A-Za-z0-9_\-]{6,}"
                       r"|(?<=Bearer )[A-Za-z0-9._~+/=\-]{6,})")


def redact(text: str) -> str:
    """Command text as it may be logged or printed: token-like values masked."""
    return SECRET_RE.sub("[REDACTED]", text)


def nice(path: str | os.PathLike) -> str:
    """Path as used in commands: relative when it is inside the current directory."""
    p = os.path.abspath(os.path.expanduser(str(path)))
    cwd = os.getcwd()
    if p == cwd:
        return "."
    if p.startswith(cwd + os.sep):
        return os.path.relpath(p, cwd)
    return p


def fmt(argv: list[str]) -> str:
    return shlex.join(argv)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_json_atomic(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def append_run_log(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(obj, ensure_ascii=False) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, line.encode())
    finally:
        os.close(fd)


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except (OSError, ValueError, TypeError):
        return False
    return True


# ----------------------------------------------------------------------------- process runner

@dataclasses.dataclass
class Proc:
    argv: list[str]
    rc: int
    out: str
    err: str
    timed_out: bool = False


def _text(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, bytes):
        return x.decode(errors="replace")
    return str(x)


class Interrupted(Exception):
    def __init__(self, signum: int):
        super().__init__(f"signal {signum}")
        self.signum = signum


class _Interrupt:
    """Signals never raise from the handler. The handler records the signal and stops the
    child process that is running; the main flow raises Interrupted exactly once at the next
    checkpoint (before/after a command, inside a pause). Cleanup can therefore not be cut short
    by an exception arriving at an arbitrary point."""
    signum: int | None = None
    cleaning = False
    raised = False
    current: subprocess.Popen | None = None
    protected = False


INT = _Interrupt()


def on_signal(signum, _frame) -> None:
    if INT.cleaning:
        # No buffered print from inside a signal handler (not re-entrant, and it can raise on a
        # closed pipe); one unbuffered write that is allowed to fail.
        if not _OUT["broken"]:
            try:
                os.write(2, f"\n[signal {signum}] cleanup is already running and will not be interrupted\n".encode())
            except OSError:
                pass
        return
    second = INT.signum is not None
    if not second:
        INT.signum = signum
    p = INT.current
    if p is not None and not INT.protected:
        try:
            p.kill() if second else p.terminate()
        except OSError:
            pass


def install_signals() -> None:
    for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(s, on_signal)


def checkpoint() -> None:
    if INT.signum is not None and not INT.cleaning and not INT.raised:
        INT.raised = True
        raise Interrupted(INT.signum)


def pause(seconds: float) -> None:
    end = time.time() + seconds
    while True:
        checkpoint()
        left = end - time.time()
        if left <= 0:
            return
        time.sleep(min(0.25, left))


def run_cmd(argv: list[str], *, timeout: float, stdin_text: str | None = None, echo: bool = True,
            protected: bool = False) -> Proc:
    """Run one command. `protected` commands (deletes) are not stopped by a signal."""
    checkpoint()
    if echo:
        say("$ " + fmt(argv))
    try:
        # Deletes and everything run during cleanup get their own session: Ctrl-C on a terminal is
        # delivered to the whole foreground process group and must not reach a delete in flight.
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace",
                                start_new_session=protected or INT.cleaning)
    except FileNotFoundError:
        return Proc(argv, 127, "", f"{argv[0]}: command not found")
    INT.current, INT.protected = proc, protected
    try:
        try:
            out, err = proc.communicate(stdin_text, timeout=timeout)
            res = Proc(argv, proc.returncode, _text(out), _text(err))
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
            res = Proc(argv, -1, _text(out), _text(err), timed_out=True)
    finally:
        INT.current = None
    checkpoint()
    return res


# ----------------------------------------------------------------------------- verda CLI wrapper

@dataclasses.dataclass
class VerdaResult:
    ok: bool
    data: Any
    code: str | None
    message: str
    http_status: int | None
    timed_out: bool
    rc: int

    @property
    def not_found(self) -> bool:
        return self.code == "NOT_FOUND" or self.http_status == 404

    @property
    def capacity(self) -> bool:
        return self.http_status == 503 or bool(CAPACITY_RE.search(self.message))

    @property
    def definitive_failure(self) -> bool:
        """The CLI or the API answered and refused: no machine was created by this call."""
        if self.ok or self.timed_out:
            return False
        if self.capacity or self.code in REFUSAL_CODES:
            return True
        return self.http_status is not None and 400 <= self.http_status < 500

    def brief(self) -> str:
        if self.ok:
            return "ok"
        bits = [self.code or "error"]
        if self.http_status:
            bits.append(f"http {self.http_status}")
        if self.timed_out:
            bits.append("client timeout")
        msg = " ".join(self.message.split())
        return f"{' / '.join(bits)}: {msg[:300]}"


class Verda:
    MUTATING = (("vm", "create"), ("vm", "delete"))

    def __init__(self, binary: str, api_timeout: float, dry_run: bool = False):
        self.binary = binary
        self.api_timeout = api_timeout
        self.dry_run = dry_run

    def argv(self, args: list[str]) -> list[str]:
        return [self.binary, "--agent", "--timeout", f"{int(self.api_timeout)}s", *args, "-o", "json"]

    def call(self, args: list[str], *, extra_timeout: float = 0.0, echo: bool = True, protected: bool = False) -> VerdaResult:
        if self.dry_run and tuple(args[:2]) in self.MUTATING:
            raise RuntimeError("refusing to run a state-changing verda command in --dry-run: " + fmt(self.argv(args)))
        p = run_cmd(self.argv(args), timeout=self.api_timeout + 30 + extra_timeout, echo=echo, protected=protected)
        return self.parse(p)

    @staticmethod
    def parse(p: Proc) -> VerdaResult:
        if p.timed_out:
            return VerdaResult(False, None, "CLIENT_TIMEOUT", "verda process did not return in time", None, True, p.rc)
        if p.rc == 0:
            text = p.out.strip()
            if not text:
                return VerdaResult(True, None, None, "", None, False, 0)
            try:
                return VerdaResult(True, json.loads(text), None, "", None, False, 0)
            except json.JSONDecodeError:
                return VerdaResult(True, text, None, "", None, False, 0)
        code, message, status = None, "", None
        for blob in (p.err, p.out):
            blob = blob.strip()
            if not blob:
                continue
            try:
                obj = json.loads(blob)
            except json.JSONDecodeError:
                message = message or blob
                continue
            err = obj.get("error") if isinstance(obj, dict) else None
            if isinstance(err, dict):
                code = err.get("code")
                message = str(err.get("message") or "")
                details = err.get("details")
                if isinstance(details, dict) and isinstance(details.get("status"), int):
                    status = details["status"]
                break
            message = message or blob
        if status is None:
            m = re.search(r"API error (\d{3})", message)
            if m:
                status = int(m.group(1))
        timed_out = bool(TIMEOUT_RE.search(message))
        return VerdaResult(False, None, code, message or f"exit code {p.rc}", status, timed_out, p.rc)


def find_id(data: Any) -> str | None:
    """Instance id in the output of `vm create`, whatever its exact shape."""
    if isinstance(data, str):
        return data.strip() if UUID_RE.fullmatch(data.strip()) else None
    if isinstance(data, list):
        return find_id(data[0]) if len(data) == 1 else None
    if isinstance(data, dict):
        for k in ("id", "instance_id"):
            v = data.get(k)
            if isinstance(v, str) and v:
                return v
        ids = data.get("instance_ids")
        if isinstance(ids, list) and len(ids) == 1 and isinstance(ids[0], str):
            return ids[0]
        for k in ("instance", "data", "result"):
            r = find_id(data.get(k))
            if r:
                return r
    return None


def vm_rows(data: Any) -> list[dict]:
    if isinstance(data, dict):
        data = data.get("instances") or data.get("data") or []
    return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []


def delete_args(instance_id: str, wait_seconds: int) -> list[str]:
    return ["vm", "delete", instance_id, "--with-volumes", "--yes", "--wait", "--wait-timeout", f"{int(wait_seconds)}s"]


def describe_status(verda: Verda, instance_id: str, echo: bool = False) -> tuple[str | None, dict | None]:
    """('running' | ... | 'not_found' | None when the API could not be asked, describe data)."""
    res = verda.call(["vm", "describe", instance_id], echo=echo)
    if res.ok and isinstance(res.data, dict):
        return str(res.data.get("status") or "").lower(), res.data
    if res.not_found:
        return "not_found", None
    return None, None


def delete_instance(verda: Verda, m: dict, save: Callable[[], None], wait_seconds: int, attempts: int = 3,
                    retry_seconds: float = 5.0) -> bool:
    """Delete one machine recorded by this tool, with its volumes. True when it is confirmed gone.

    The id is described first. It is deleted only when describe reports this run's hostname for it,
    or when the id was verified earlier (found by exact hostname, or described with our hostname).
    An id that describe reports under another hostname is disowned and never deleted. An id that was
    only ever read from create output and cannot be described now is kept on record, not deleted."""
    if m.get("deleted"):
        return True
    if m.get("disowned"):
        return False
    status, data = describe_status(verda, m["id"])
    reported = (data or {}).get("hostname")
    if reported and m.get("hostname") and reported != m["hostname"]:
        m.update(disowned=True, final_status="foreign_id")
        save()
        say(f"instance {m['id']} reports hostname {reported}, not {m['hostname']}: not this run's machine, NOT deleted")
        return False
    if status == "not_found" or status in GONE_STATUSES:
        m.update(deleted=True, deleted_epoch=time.time(), deleted_ts=utc_iso(), final_status=status)
        save()
        say(f"instance {m['id']} is already gone ({status})")
        return True
    if reported == m.get("hostname"):
        m["verified"] = True
    if status is None and not m.get("verified", True):
        m["final_status"] = "unverified_id"
        save()
        say(f"instance {m['id']} could not be described and its id was never confirmed as this run's machine; "
            "NOT deleted. Run `sweep` once the API answers.")
        return False
    for attempt in range(1, attempts + 1):
        say(f"deleting instance {m['id']} ({m.get('hostname')}) with its volumes, attempt {attempt}/{attempts}")
        res = verda.call(delete_args(m["id"], wait_seconds), extra_timeout=wait_seconds, protected=True)
        m["delete_calls"] = m.get("delete_calls", 0) + 1
        save()
        status, _ = describe_status(verda, m["id"])
        if status == "not_found" or status in GONE_STATUSES or (res.not_found and status is None):
            m.update(deleted=True, deleted_epoch=time.time(), deleted_ts=utc_iso(), final_status=status or "not_found")
            save()
            say(f"instance {m['id']} is gone ({m['final_status']})")
            return True
        if res.ok and status is None:
            # Delete was accepted and waited for; the confirming describe could not be asked. Ask again
            # a few times; if it still cannot be confirmed, keep the machine on record for `sweep`.
            for _ in range(3):
                pause(retry_seconds)
                status, _ = describe_status(verda, m["id"])
                if status is not None:
                    break
            if status == "not_found" or status in GONE_STATUSES:
                m.update(deleted=True, deleted_epoch=time.time(), deleted_ts=utc_iso(), final_status=status)
                save()
                say(f"instance {m['id']} is gone ({status})")
                return True
            if status is None:
                m.update(final_status="unverified", delete_accepted=True, delete_accepted_ts=utc_iso())
                save()
                say(f"instance {m['id']}: delete returned success but no describe confirmed it (unverified); "
                    "kept on record, run `sweep` to re-check")
                return False
        m["final_status"] = status
        save()
        say(f"instance {m['id']} still reports status '{status}' after delete ({res.brief()})")
        if attempt < attempts:
            pause(retry_seconds * attempt)
    return False


def volume_ids_of(data: dict) -> list[str]:
    ids: list[str] = []
    if isinstance(data.get("os_volume_id"), str):
        ids.append(data["os_volume_id"])
    for v in data.get("volume_ids") or []:
        if isinstance(v, str):
            ids.append(v)
    for v in data.get("volumes") or []:
        if isinstance(v, dict) and isinstance(v.get("id"), str):
            ids.append(v["id"])
    return sorted(set(i for i in ids if i))


def check_volumes(verda: Verda, m: dict) -> list[dict]:
    """Informational: what `volume describe` says about this machine's volumes after deletion."""
    out = []
    for vid in m.get("volume_ids") or []:
        res = verda.call(["volume", "describe", vid], echo=False)
        if res.not_found:
            out.append({"id": vid, "state": "not_found"})
        elif res.ok and isinstance(res.data, dict):
            out.append({"id": vid, "state": str(res.data.get("status") or "exists").lower()})
        else:
            out.append({"id": vid, "state": "unknown"})
    return out


# ----------------------------------------------------------------------------- run

@dataclasses.dataclass
class Candidate:
    itype: str
    location: str
    spot: bool
    hourly: float | None = None
    price_source: str = ""
    image: str | None = None

    @property
    def label(self) -> str:
        return f"{self.itype}@{self.location}:{'spot' if self.spot else 'on-demand'}"


class Abort(Exception):
    def __init__(self, outcome: str, message: str):
        super().__init__(message)
        self.outcome = outcome


class CandidateFailed(Exception):
    def __init__(self, reason: str, message: str, fatal: bool = False):
        super().__init__(message)
        self.reason = reason
        self.fatal = fatal


class UsageError(Exception):
    pass


class Run:
    def __init__(self, a: argparse.Namespace):
        self.a = a
        self.dry = a.dry_run
        self.t0 = time.time()
        self.run_id = dt.datetime.fromtimestamp(self.t0, dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(3)
        self.verda = Verda(a.verda_bin, a.api_timeout_seconds, dry_run=self.dry)
        self.state_dir = Path(a.state_dir)
        self.state_file = self.state_dir / f"{self.run_id}.json"
        self.known_hosts = self.state_dir / f"{self.run_id}.known_hosts"
        _OUT["fallback"] = self.state_dir / f"{self.run_id}.log"  # used only if the terminal stops accepting output
        self.artifacts_dir = Path(a.artifacts_dir) if a.artifacts_dir else DEFAULT_ARTIFACTS_ROOT / self.run_id
        self.max_seconds = a.max_minutes * 60.0
        self.deadline = self.t0 + self.max_seconds
        self.candidates: list[Candidate] = []
        self.copies: list[tuple[str, str]] = []
        self.command = ""
        self.attempts: list[dict] = []
        self.artifacts: list[dict] = []
        self.remote_exit: int | None = None
        self.job_machine: dict | None = None
        self.notes: list[str] = []
        self.state: dict = {
            "schema": STATE_SCHEMA,
            "run_id": self.run_id,
            "tool_pid": os.getpid(),
            "tool_host": socket.gethostname(),
            "started": utc_iso(self.t0),
            "status": "active",
            "hostname_prefix": a.hostname_prefix,
            "pending": [],
            "machines": [],
        }

    # ------------------------------------------------------------------ validation and pricing

    def validate(self) -> None:
        a = self.a
        for spec in a.candidate:
            base, *options = spec.split(",")
            m = CANDIDATE_RE.match(base)
            if not m:
                raise UsageError(f"bad --candidate {spec!r}; expected {CANDIDATE_HELP}")
            c = Candidate(m["type"], m["loc"], m["mode"] == "spot", image=a.image)
            for opt in options:
                key, _, value = opt.partition("=")
                try:
                    if key == "image" and value:
                        c.image = value
                    elif key == "usd" and float(value) > 0:
                        c.hourly, c.price_source = float(value), "given on the command line"
                    else:
                        raise ValueError(opt)
                except ValueError:
                    raise UsageError(f"bad option {opt!r} in --candidate {spec!r}; expected {CANDIDATE_HELP}") from None
            if not c.image:
                raise UsageError(f"no OS image for candidate {base}: give --image or ,image=SLUG")
            self.candidates.append(c)
        if not PREFIX_RE.match(a.hostname_prefix):
            raise UsageError("--hostname-prefix must match [a-z0-9][a-z0-9-]{0,29}")
        if a.max_minutes <= 0 or a.budget_usd <= 0:
            raise UsageError("--max-minutes and --budget-usd must be positive")
        if not SAFE_REMOTE_PATH_RE.match(a.remote_dir):
            raise UsageError("--remote-dir may only contain [A-Za-z0-9_./@%+=:,~-]")
        for spec in a.copy:
            local, _, sub = spec.partition(":")
            sub = sub.strip("/")
            if sub and (not SAFE_REMOTE_PATH_RE.match(sub) or ".." in sub.split("/")):
                raise UsageError(f"bad remote sub-directory in --copy {spec!r}")
            if not os.path.isdir(os.path.expanduser(local)):
                self.problem(f"--copy: local directory not found: {local}")
            self.copies.append((local, sub))
        for art in a.artifact:
            if not SAFE_REMOTE_PATH_RE.match(art):
                raise UsageError(f"--artifact {art!r} may only contain [A-Za-z0-9_./@%+=:,~-]")
        if a.command_file:
            try:
                self.command = Path(a.command_file).read_text()
            except OSError as e:
                raise UsageError(f"--command-file: {e}") from e
        else:
            self.command = a.command or ""
        if not self.command.strip():
            raise UsageError("give the remote command with --command or --command-file")
        if not os.path.isfile(os.path.expanduser(a.ssh_key_path)):
            self.problem(f"--ssh-key-path: private key not found: {a.ssh_key_path}")
        # The ssh command is handed to rsync -e, which splits it on whitespace without a shell.
        for what, value in (("--ssh-key-path", a.ssh_key_path), ("--ssh-bin", a.ssh_bin), ("--ssh-user", a.ssh_user),
                            ("--state-dir (as seen from here)", nice(self.known_hosts))):
            if re.search(r"[\s'\"\\]", value):
                raise UsageError(f"{what} must not contain whitespace, quotes or backslashes: {value!r}")

    def problem(self, msg: str) -> None:
        if self.dry:
            say(f"WARNING (dry-run continues; a real run stops here): {msg}")
        else:
            raise UsageError(msg)

    def estimate_args(self, c: Candidate) -> list[str]:
        return ["cost", "estimate", "--type", c.itype, "--os-volume", str(self.a.os_volume_gb)] + (["--spot"] if c.spot else [])

    def price_candidates(self) -> None:
        cache: dict[tuple[str, bool], tuple[float | None, str]] = {}
        for c in self.candidates:
            if c.hourly is not None:
                continue
            key = (c.itype, c.spot)
            if key not in cache:
                if self.a.offline:
                    say("offline, not executed: $ " + fmt(self.verda.argv(self.estimate_args(c))))
                    cache[key] = (None, "not looked up (--offline)")
                else:
                    res = self.verda.call(self.estimate_args(c))
                    hourly = None
                    if res.ok and isinstance(res.data, dict):
                        total = res.data.get("total")
                        if isinstance(total, dict) and isinstance(total.get("hourly"), (int, float)):
                            hourly = float(total["hourly"])
                    if hourly is not None and hourly > 0:
                        cache[key] = (hourly, "verda cost estimate, total.hourly incl. OS volume")
                    else:
                        cache[key] = (None, "lookup failed: " + (res.brief() if not res.ok else "no total.hourly in output"))
            c.hourly, c.price_source = cache[key]

    def print_estimate(self) -> None:
        a = self.a
        out("\nCOST ESTIMATE (nothing has been created yet)", flush=True)
        out(f"  caps: max wall-clock {a.max_minutes:g} min, budget {a.budget_usd:.2f} USD, "
              f"OS volume {a.os_volume_gb} GiB, teardown reserve {a.teardown_reserve_seconds:g} s", flush=True)
        out(f"  {'#':>2}  {'candidate':<34} {'USD/hour':>9}  {'cost of max wall-clock':>22}  {'budget lasts':>12}  binding cap", flush=True)
        for i, c in enumerate(self.candidates, 1):
            if c.hourly is None:
                out(f"  {i:>2}  {c.label:<34} {'unknown':>9}  {'unknown':>22}  {'unknown':>12}  ({c.price_source})", flush=True)
                continue
            worst = c.hourly * self.max_seconds / 3600.0
            lasts_min = a.budget_usd / c.hourly * 60.0
            binding = "time" if worst <= a.budget_usd else "budget"
            out(f"  {i:>2}  {c.label:<34} {c.hourly:>9.4f}  {worst:>18.4f} USD  {lasts_min:>8.1f} min  {binding}", flush=True)
        known = [c.hourly for c in self.candidates if c.hourly is not None]
        if known:
            worst_all = min(a.budget_usd, max(known) * self.max_seconds / 3600.0)
            out(f"  planned ceiling for this run: {worst_all:.4f} USD = min(budget, hours x hourly price incl. volume "
                  f"of the dearest candidate); candidates are tried in the order given\n", flush=True)
        else:
            out("  planned ceiling for this run: unknown (no price)\n", flush=True)

    # ------------------------------------------------------------------ command builders

    def hostname(self, idx: int) -> str:
        stamp = dt.datetime.fromtimestamp(self.t0, dt.timezone.utc).strftime("%m%d-%H%M%S")
        return f"{self.a.hostname_prefix}-{stamp}-{self.run_id[-6:]}-c{idx + 1}"

    def create_args(self, c: Candidate, hostname: str) -> list[str]:
        a = self.a
        args = ["vm", "create", "--kind", a.kind, "--instance-type", c.itype, "--location", c.location,
                "--os", c.image, "--hostname", hostname, "--description", f"verda_job {self.run_id}",
                "--ssh-key", a.ssh_key_id, "--os-volume-size", str(a.os_volume_gb)]
        if c.spot:
            args += ["--is-spot", "--os-volume-on-spot-discontinue", a.spot_discontinue_policy]
        return args + ["--wait=false"]

    def ssh_base(self) -> list[str]:
        a = self.a
        return [a.ssh_bin, "-i", a.ssh_key_path, "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
                "-o", "StrictHostKeyChecking=accept-new", "-o", f"UserKnownHostsFile={nice(self.known_hosts)}",
                "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=3",
                "-o", "LogLevel=ERROR"]

    def target(self, ip: str) -> str:
        return f"{self.a.ssh_user}@{ip}"

    def ssh_argv(self, ip: str, remote_cmd: str) -> list[str]:
        return self.ssh_base() + [self.target(ip), remote_cmd]

    def job_dir(self) -> str:
        return f'"$HOME/.verda_job/{self.run_id}"'

    def remote_path(self, sub: str) -> str:
        base = self.a.remote_dir.rstrip("/") or "/"
        return f"{base}/{sub}" if sub else base

    def mkdir_cmd(self) -> str:
        dirs = " ".join(shlex.quote(self.remote_path(sub)) for _, sub in self.copies)
        return f'cd "$HOME" && mkdir -p -- {dirs} && J={self.job_dir()} && mkdir -p "$J"'

    def rsync_up_argv(self, ip: str, local: str, sub: str) -> list[str]:
        argv = [self.a.rsync_bin, "-az", "-e", " ".join(self.ssh_base())]
        for pat in self.a.exclude:
            argv += ["--exclude", pat]
        return argv + [local.rstrip("/") + "/", f"{self.target(ip)}:{self.remote_path(sub)}/"]

    def launcher(self) -> str:
        eof = "VERDA_JOB_EOF_" + self.run_id[-6:]
        return "\n".join([
            "#!/usr/bin/env bash",
            f"# Generated by ops/verda_job.py for run {self.run_id}.",
            'J="$(cd "$(dirname "$0")" && pwd)"',
            f"cat > \"$J/cmd.sh\" <<'{eof}'",
            self.command.rstrip("\n"),
            eof,
            f'if ! {{ cd "$HOME" && cd -- {shlex.quote(self.a.remote_dir)}; }}; then',
            f'  echo "verda_job: cannot cd to {self.a.remote_dir}" > "$J/job.log"; echo 97 > "$J/exit_code"; exit 97',
            "fi",
            'bash "$J/cmd.sh" > "$J/job.log" 2>&1 < /dev/null',
            "rc=$?",
            'echo "$rc" > "$J/exit_code.tmp" && mv "$J/exit_code.tmp" "$J/exit_code"',
            'exit "$rc"',
            "",
        ])

    def install_cmd(self) -> str:
        return f'J={self.job_dir()} && mkdir -p "$J" && cat > "$J/run.sh" && chmod 700 "$J/run.sh"'

    def start_cmd(self) -> str:
        return (f'J={self.job_dir()} && cd "$J" && '
                '{ nohup bash "$J/run.sh" > /dev/null 2>&1 < /dev/null & echo $! > "$J/pid"; } && echo STARTED')

    def poll_cmd(self, offset: int) -> str:
        return (f'J={self.job_dir()}; '
                'if [ -f "$J/exit_code" ]; then echo "EXIT=$(cat "$J/exit_code")"; else echo "EXIT="; fi; '
                'if kill -0 "$(cat "$J/pid" 2>/dev/null)" 2>/dev/null; then echo "ALIVE=1"; else echo "ALIVE=0"; fi; '
                'S=$(( $(wc -c < "$J/job.log" 2>/dev/null || echo 0) )); echo "SIZE=$S"; echo "----"; '
                f'if [ "$S" -gt {offset} ]; then tail -c +{offset + 1} "$J/job.log" | head -c $((S-{offset})) | tail -n {int(self.a.log_lines)}; fi')

    def rsync_down_argv(self, ip: str, remote: str) -> list[str]:
        argv = [self.a.rsync_bin, "-az", "-e", " ".join(self.ssh_base())]
        for pat in self.a.artifact_exclude:
            argv += ["--exclude", pat]
        return argv + [f"{self.target(ip)}:{remote}", nice(self.artifacts_dir) + "/"]

    def artifact_remote(self, art: str) -> str:
        return art if art.startswith("/") or art.startswith("~") else self.remote_path(art)

    # ------------------------------------------------------------------ dry run

    def dry_run_plan(self) -> int:
        a = self.a
        ip, iid = "<ip>", "<instance-id>"
        ssh_words = " ".join(self.ssh_base())

        def show(argv: list[str], note: str = "") -> None:
            # Same argv a real run executes; only the long ssh option block is abbreviated to $SSH.
            text = fmt(argv).replace(shlex.quote(ssh_words), '"$SSH"').replace(fmt(self.ssh_base()), "$SSH")
            out("  $ " + text + (f"\n      # {note}" if note else ""), flush=True)

        out("DRY RUN: nothing is created, copied or deleted. Commands a real run executes, in order.\n", flush=True)
        out(f'ssh options of every ssh and rsync command below, shown there as $SSH:\n  SSH="{ssh_words}"\n', flush=True)
        out(f"State file (written before the first create): {nice(self.state_file)}", flush=True)
        out(f"Run log line appended to: {nice(a.run_log)}\n", flush=True)
        out("1. Provision: candidates in order, stop at the first machine that answers on SSH.", flush=True)
        for i, c in enumerate(self.candidates):
            out(f"\n   candidate {i + 1}: {c.label}", flush=True)
            show(self.verda.argv(["vm", "list"]), "ids that exist before the create; the new hostname must not be among them")
            show(self.verda.argv(self.create_args(c, self.hostname(i))),
                 "HTTP 503 / not enough resources -> next candidate; client timeout -> look the hostname up in `vm list` before anything else")
            show(self.verda.argv(["vm", "describe", iid]),
                 f"every {a.provision_poll_seconds:g} s until status=running with an ip (max {a.provision_timeout_seconds:g} s); "
                 "'discontinued' -> delete this machine, next candidate")
            show(self.ssh_argv(ip, "true"), f"until it answers (max {a.ssh_timeout_seconds:g} s)")
            show(self.verda.argv(delete_args(iid, a.delete_wait_seconds)), "only if this candidate failed after its machine was created")
        out("\n2. Copy and start (detached: nohup, log file, exit-code file).", flush=True)
        show(self.ssh_argv(ip, self.mkdir_cmd()))
        for local, sub in self.copies:
            show(self.rsync_up_argv(ip, local, sub))
        show(self.ssh_argv(ip, self.install_cmd()), "stdin: the launcher script printed below")
        show(self.ssh_argv(ip, self.start_cmd()))
        out("\n   launcher script (run.sh):", flush=True)
        for line in redact(self.launcher()).rstrip("\n").split("\n"):
            out("   | " + line, flush=True)
        out(f"\n3. Poll every {a.poll_seconds:g} s, print new log lines; `vm describe` every {a.describe_every} polls "
              "and after every failed poll.", flush=True)
        show(self.ssh_argv(ip, self.poll_cmd(0)), "the byte offset (0 here) advances with the log")
        show(self.verda.argv(["vm", "describe", iid]), "discontinued or not found -> spot_reclaimed (exit 74) for spot, machine_lost (exit 77) otherwise")
        out("\n4. Fetch artifacts (also after a failed command or a time/budget cap, when the machine still answers).", flush=True)
        show(self.rsync_down_argv(ip, f".verda_job/{self.run_id}/job.log"))
        for art in a.artifact:
            show(self.rsync_down_argv(ip, self.artifact_remote(art)))
        out("\n5. Always: finally block, SIGINT/SIGTERM/SIGHUP, time cap, budget cap, spot reclaim."
              + (" SKIPPED because --keep is set." if a.keep else ""), flush=True)
        show(self.verda.argv(delete_args(iid, a.delete_wait_seconds)), "only ids recorded in this run's state file")
        show(self.verda.argv(["vm", "describe", iid]), "confirmation: expect NOT_FOUND")
        out("\nDRY RUN complete: 0 machines created, 0 deleted.", flush=True)
        append_run_log(Path(a.run_log), {
            "ts": utc_iso(), "step": "verda_job_dry_run", "host": socket.gethostname(), **self.command_record(),
            "inputs": self.inputs(), "outputs": {"artifacts": [], "machines": []},
            "metrics": {"outcome": "dry_run", "exit_code": 0, "seconds": round(time.time() - self.t0, 1),
                        "candidates_priced": [{"candidate": c.label, "hourly_usd": c.hourly, "price_source": c.price_source}
                                              for c in self.candidates]},
            "cost_usd": 0, "status": "dry_run"})
        return EXIT_OK

    # ------------------------------------------------------------------ state and accounting

    def save_state(self) -> None:
        write_json_atomic(self.state_file, self.state)

    def machines(self) -> list[dict]:
        return self.state["machines"]

    def accrued(self) -> float:
        now = time.time()
        return sum(((m.get("deleted_epoch") or now) - m["created_epoch"]) / 3600.0 * m["hourly_usd"] for m in self.machines())

    def cap_hit(self) -> str | None:
        if time.time() >= self.deadline:
            return "time_cap"
        live = [m["hourly_usd"] for m in self.machines() if not m.get("deleted")]
        reserve = (max(live) if live else 0.0) * self.a.teardown_reserve_seconds / 3600.0
        if self.accrued() + reserve >= self.a.budget_usd:
            return "budget_cap"
        return None

    def remaining(self) -> float:
        """Seconds until the first cap would be hit at the current burn rate."""
        left = self.deadline - time.time()
        live = [m["hourly_usd"] for m in self.machines() if not m.get("deleted")]
        if live:
            reserve = max(live) * self.a.teardown_reserve_seconds / 3600.0
            left = min(left, (self.a.budget_usd - self.accrued() - reserve) / (sum(live) / 3600.0))
        return left

    def step_timeout(self, limit: float) -> float:
        """A setup step may not run past a cap; the cap check after it then stops the run."""
        return min(limit, max(5.0, self.remaining()))

    def raise_if_cap(self) -> None:
        cap = self.cap_hit()
        if cap:
            raise Abort(cap, self.cap_message(cap))

    def cap_message(self, cap: str) -> str:
        if cap == "time_cap":
            return f"maximum wall-clock time of {self.a.max_minutes:g} min reached"
        return (f"budget cap reached: {self.accrued():.4f} USD accrued of {self.a.budget_usd:.2f} USD "
                f"(teardown reserve {self.a.teardown_reserve_seconds:g} s)")

    def inputs(self) -> dict:
        a = self.a
        return {"run_id": self.run_id, "candidates": [c.label for c in self.candidates], "kind": a.kind,
                "images": sorted({c.image for c in self.candidates if c.image}),
                "os_volume_gb": a.os_volume_gb, "copy": [f"{l}:{s}" if s else l for l, s in self.copies],
                "exclude": a.exclude, "remote_dir": a.remote_dir, "artifacts_requested": a.artifact,
                "max_minutes": a.max_minutes, "budget_usd": a.budget_usd, "keep": a.keep, "dry_run": a.dry_run}

    # ------------------------------------------------------------------ provisioning

    def list_vms(self, echo: bool = True) -> list[dict] | None:
        res = self.verda.call(["vm", "list"], echo=echo)
        if not res.ok:
            say("vm list failed: " + res.brief())
            return None
        return vm_rows(res.data)

    def lookup_by_hostname(self, pending: dict, window: float) -> dict | None:
        """Exact hostname, and an id that did not exist before our create call."""
        end = time.time() + window
        while True:
            rows = self.list_vms()
            if rows is not None:
                hits = [r for r in rows if r.get("hostname") == pending["hostname"] and r.get("id") not in pending["pre_ids"]]
                if hits:
                    return hits[0]
            if time.time() >= end:
                return None
            pause(min(self.a.lookup_interval_seconds, max(0.0, end - time.time())))

    def adopt(self, pending: dict, row: dict, how: str) -> dict:
        m = {"id": row["id"], "hostname": pending["hostname"], "instance_type": pending["instance_type"],
             "location": pending["location"], "spot": pending["spot"], "hourly_usd": pending["hourly_usd"],
             "created_epoch": pending["call_epoch"], "created_ts": utc_iso(pending["call_epoch"]), "found_by": how,
             "deleted": False, "delete_calls": 0, "ip": None, "volume_ids": [],
             # An id found by exact hostname (and absent before the create) is ours; an id read from the
             # create output is ours only once describe reports our hostname for it.
             "verified": how != "create output"}
        self.machines().append(m)
        pending.update(id=row["id"], state="created")
        self.save_state()
        return m

    def provision(self, idx: int, c: Candidate) -> dict:
        self.raise_if_cap()
        hostname = self.hostname(idx)
        say(f"candidate {idx + 1}/{len(self.candidates)}: {c.label} at {c.hourly:.4f} USD/h, hostname {hostname}")
        rows = self.list_vms()
        if rows is None:
            raise CandidateFailed("api_unavailable", "could not list machines before create")
        if any(r.get("hostname") == hostname for r in rows):
            raise CandidateFailed("hostname_collision", f"a machine named {hostname} already exists", fatal=True)
        pending = {"hostname": hostname, "instance_type": c.itype, "location": c.location, "spot": c.spot,
                   "hourly_usd": c.hourly, "pre_ids": [r.get("id") for r in rows], "call_epoch": time.time(),
                   "state": "calling", "id": None}
        self.state["pending"].append(pending)
        self.save_state()
        res = self.verda.call(self.create_args(c, hostname))
        iid = find_id(res.data) if res.ok else None
        if iid:
            m = self.adopt(pending, {"id": iid}, "create output")
        elif res.capacity:
            # A capacity answer (HTTP 503 or a capacity message) may come from a gateway in front of an
            # API that did create the machine. Look for the exact hostname before the next candidate,
            # and keep the entry so that cleanup and `sweep` look again.
            pending.update(state="refused_unverified", error=res.brief())
            self.save_state()
            say(f"create answered {res.brief()}; checking that no machine named {hostname} was created anyway")
            row = self.lookup_by_hostname(pending, self.a.refusal_lookup_seconds)
            if row is None:
                raise CandidateFailed("no_capacity_503", "create refused: " + res.brief())
            say(f"machine {row['id']} named {hostname} exists despite the refusal; using it")
            m = self.adopt(pending, row, "hostname lookup after a capacity refusal")
        elif res.definitive_failure:
            pending.update(state="refused", error=res.brief())
            self.save_state()
            reason = "no_capacity_503" if res.capacity else (res.code or "create_refused").lower()
            raise CandidateFailed(reason, "create refused: " + res.brief(), fatal=res.code in STOP_CODES)
        else:
            # Client timeout, a 5xx other than capacity, or success without an id: the machine may exist anyway.
            pending.update(state="ambiguous", error=res.brief())
            self.save_state()
            say(f"create outcome is unknown ({res.brief()}); looking for hostname {hostname} before trying anything else")
            row = self.lookup_by_hostname(pending, self.a.lookup_window_seconds)
            if row is None:
                raise CandidateFailed("create_timeout" if res.timed_out else "create_unknown",
                                      f"create did not return an id and no machine named {hostname} appeared within "
                                      f"{self.a.lookup_window_seconds:g} s")
            say(f"machine exists after all: {row['id']}")
            m = self.adopt(pending, row, "hostname lookup after ambiguous create")
        try:
            self.wait_running(m)
            self.wait_ssh(m)
        except CandidateFailed:
            if m in self.machines():  # a disowned id is never deleted
                self.delete(m)
            raise
        return m

    def wait_running(self, m: dict) -> None:
        end = time.time() + self.a.provision_timeout_seconds
        missing, first = 0, True
        while True:
            self.raise_if_cap()
            status, data = describe_status(self.verda, m["id"], echo=first)
            first = False
            if data is not None:
                if data.get("hostname") and data["hostname"] != m["hostname"]:
                    # Not the machine this run asked for: forget the id, never delete it. The
                    # hostname is looked up again at cleanup in case our machine exists elsewhere.
                    self.machines().remove(m)
                    for p in self.state["pending"]:
                        if p.get("id") == m["id"]:
                            p.update(id=None, state="ambiguous")
                    self.save_state()
                    raise CandidateFailed("foreign_id", f"id {m['id']} belongs to {data['hostname']}, not {m['hostname']}", fatal=True)
                if data.get("hostname") == m["hostname"] and not m.get("verified"):
                    m["verified"] = True
                ip = data.get("ip") or data.get("public_ip")
                m["ip"] = ip if isinstance(ip, str) and ip else None
                m["volume_ids"] = volume_ids_of(data) or m.get("volume_ids") or []
                self.save_state()
            if status == "running" and m["ip"]:
                say(f"instance {m['id']} is running at {m['ip']}")
                return
            missing = missing + 1 if status == "not_found" else 0
            if status in FAILED_STATUSES or missing >= 3:
                raise CandidateFailed(f"machine_{status}", f"instance {m['id']} became '{status}' while waiting for it to start")
            if time.time() >= end:
                raise CandidateFailed("provision_timeout", f"instance {m['id']} not running after {self.a.provision_timeout_seconds:g} s (status '{status}')")
            pause(self.a.provision_poll_seconds)

    def wait_ssh(self, m: dict) -> None:
        end = time.time() + self.a.ssh_timeout_seconds
        n = 0
        while True:
            self.raise_if_cap()
            n += 1
            p = run_cmd(self.ssh_argv(m["ip"], "true"), timeout=40, echo=(n == 1))
            if p.rc == 0:
                say(f"ssh is up on {m['ip']} after {n} attempt(s)")
                return
            if HOSTKEY_RE.search(p.err):
                raise CandidateFailed("host_key_changed", "ssh host key changed during start-up; not accepted")
            if n % 3 == 0:
                status, _ = describe_status(self.verda, m["id"])
                if status in FAILED_STATUSES or status == "not_found":
                    raise CandidateFailed(f"machine_{status}", f"instance {m['id']} became '{status}' while waiting for ssh")
            if time.time() >= end:
                raise CandidateFailed("ssh_timeout", f"ssh did not answer within {self.a.ssh_timeout_seconds:g} s: {' '.join(p.err.split())[:200]}")
            pause(self.a.ssh_retry_seconds)

    def delete(self, m: dict) -> bool:
        ok = delete_instance(self.verda, m, self.save_state, self.a.delete_wait_seconds, retry_seconds=self.a.delete_retry_seconds)
        if ok and m.get("volume_ids") and "volumes_after_delete" not in m:
            m["volumes_after_delete"] = check_volumes(self.verda, m)
            self.save_state()
            left = [v for v in m["volumes_after_delete"] if v["state"] not in ("not_found", "deleted", "deleting")]
            if left:
                loud([f"volume {v['id']} of deleted instance {m['id']} still reports '{v['state']}'." for v in left]
                     + ["It may still be billed. Inspect: verda --agent volume describe <id> -o json"])
        return ok

    # ------------------------------------------------------------------ job

    def ssh(self, m: dict, remote_cmd: str, timeout: float, stdin_text: str | None = None, echo: bool = True) -> Proc:
        return run_cmd(self.ssh_argv(m["ip"], remote_cmd), timeout=timeout, stdin_text=stdin_text, echo=echo)

    def setup(self, m: dict) -> None:
        steps: list[tuple[str, Callable[[], Proc]]] = [("mkdir", lambda: self.ssh(m, self.mkdir_cmd(), self.step_timeout(60)))]
        for local, sub in self.copies:
            steps.append((f"rsync {local}", lambda l=local, s=sub: run_cmd(
                self.rsync_up_argv(m["ip"], l, s), timeout=self.step_timeout(self.a.copy_timeout_seconds))))
        steps.append(("install launcher", lambda: self.ssh(m, self.install_cmd(), self.step_timeout(60), stdin_text=self.launcher())))
        steps.append(("start", lambda: self.ssh(m, self.start_cmd(), 60)))
        for name, step in steps:
            for attempt in (1, 2, 3):
                self.raise_if_cap()
                p = step()
                if p.rc == 0 and (name != "start" or "STARTED" in p.out):
                    break
                if HOSTKEY_RE.search(p.err):
                    raise Abort("host_key_changed", "ssh host key changed; not accepted")
                say(f"{name} failed (attempt {attempt}/3, rc={p.rc}{', timed out' if p.timed_out else ''}): {' '.join(p.err.split())[:300]}")
                if name == "start" or attempt == 3:
                    # Never start the command twice.
                    raise Abort("setup_failed", f"{name} failed on {m['ip']}")
                pause(3)
        m["job_started_epoch"] = time.time()
        self.save_state()
        say("remote command started (detached); polling")

    def poll(self, m: dict) -> tuple[str, int | None]:
        a = self.a
        offset, failures, vanished, n = 0, 0, 0, 0
        while True:
            cap = self.cap_hit()
            if cap:
                say(self.cap_message(cap))
                return cap, None
            n += 1
            p = self.ssh(m, self.poll_cmd(offset), timeout=60, echo=(n == 1))
            head, sep, chunk = p.out.partition("----\n")
            if p.rc == 0 and sep:
                failures = 0
                fields = dict(line.split("=", 1) for line in head.splitlines() if "=" in line)
                try:
                    size = int(fields.get("SIZE") or 0)
                except ValueError:
                    size = offset
                for line in chunk.splitlines():
                    out("    | " + line, flush=True)
                offset = max(offset, size)
                code = (fields.get("EXIT") or "").strip()
                if code:
                    try:
                        return "exited", int(code)
                    except ValueError:
                        return "exited", 1
                vanished = vanished + 1 if fields.get("ALIVE") == "0" else 0
                if vanished >= 2:
                    say("remote job process is gone and left no exit code")
                    return "job_vanished", None
            else:
                failures += 1
                if HOSTKEY_RE.search(p.err):
                    say("ssh host key changed mid-run; not accepted")
                    return "host_key_changed", None
                say(f"poll failed ({failures}/{a.max_ssh_failures}) rc={p.rc}{' timed out' if p.timed_out else ''}: {' '.join(p.err.split())[:200]}")
            if failures or n % a.describe_every == 0:
                status, _ = describe_status(self.verda, m["id"])
                if status in FAILED_STATUSES or status == "not_found":
                    m["final_status"] = status
                    self.save_state()
                    return ("spot_reclaimed" if m["spot"] else "machine_lost"), None
            if failures >= a.max_ssh_failures:
                return "unreachable", None
            pause(a.poll_seconds)

    def fetch(self, m: dict, timeout: float) -> bool:
        """Fetch job.log and the requested artifacts. True when every requested artifact arrived."""
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        end = time.time() + timeout
        all_ok = True
        wanted = [("job.log", f".verda_job/{self.run_id}/job.log", False)] + [(art, self.artifact_remote(art), True) for art in self.a.artifact]
        for name, remote, required in wanted:
            left = end - time.time()
            if left <= 0:
                self.artifacts.append({"artifact": name, "missing": True, "error": "fetch time budget used up"})
                all_ok = all_ok and not required
                continue
            p = run_cmd(self.rsync_down_argv(m["ip"], remote), timeout=left)
            local = self.artifacts_dir / os.path.basename(remote.rstrip("/"))
            if p.rc != 0 or not local.exists():
                err = "timed out" if p.timed_out else " ".join(p.err.split())[:300] or f"rc={p.rc}"
                self.artifacts.append({"artifact": name, "missing": True, "error": err})
                say(f"artifact {name}: NOT fetched ({err})")
                all_ok = all_ok and not required
                continue
            files = [local] if local.is_file() else sorted(f for f in local.rglob("*") if f.is_file())
            for f in files:
                self.artifacts.append({"artifact": name, "path": nice(f), "bytes": f.stat().st_size, "sha256": sha256_file(f)})
            say(f"artifact {name}: {len(files)} file(s) in {nice(local)}")
        return all_ok

    def execute(self) -> str:
        for idx, c in enumerate(self.candidates):
            t = time.time()
            try:
                m = self.provision(idx, c)
            except CandidateFailed as e:
                say(f"candidate {idx + 1} failed ({e.reason}): {e}")
                self.attempts.append({"candidate": c.label, "result": e.reason, "seconds": round(time.time() - t, 1)})
                if e.fatal:
                    raise Abort("no_candidate", f"stopping: {e}") from e
                continue
            self.attempts.append({"candidate": c.label, "result": "up", "seconds": round(time.time() - t, 1)})
            self.job_machine = m
            self.setup(m)
            outcome, rc = self.poll(m)
            self.remote_exit = rc
            if outcome in ("exited", "time_cap", "budget_cap", "job_vanished"):
                limit = self.a.fetch_timeout_seconds if outcome == "exited" else min(self.a.fetch_timeout_seconds, max(self.a.teardown_reserve_seconds, 30))
                complete = self.fetch(m, limit)
                if outcome == "exited":
                    if rc != 0:
                        return "remote_failed"
                    return "ok" if complete else "artifact_missing"
            return outcome
        raise Abort("no_candidate", "no candidate produced a usable machine: "
                    + ", ".join(f"{x['candidate']}={x['result']}" for x in self.attempts))

    # ------------------------------------------------------------------ cleanup and reporting

    def _settle_pending(self) -> None:
        """Look up, by exact hostname, every create whose machine is not known for certain."""
        by_id = {m["id"]: m for m in self.machines()}
        for p in self.state["pending"]:
            try:
                state = p.get("state")
                m = by_id.get(p.get("id")) if p.get("id") else None
                unverified_id = m is not None and not m.get("verified") and not m.get("deleted") and not m.get("disowned")
                if p.get("id") and not unverified_id:
                    continue
                if not p.get("id") and state not in ("calling", "ambiguous", "refused_unverified"):
                    continue
                why = {"refused_unverified": "create was answered with a capacity or 5xx error",
                       "calling": "create never settled", "ambiguous": "create never settled"}.get(
                    state, "the id from the create output was never confirmed by describe")
                say(f"{why} for {p['hostname']}; checking whether that machine exists")
                row = self.lookup_by_hostname(p, self.a.lookup_window_seconds if state == "calling" else 0)
                if row and m is not None and row["id"] == m["id"]:
                    m["verified"] = True
                elif row:
                    if m is not None:
                        m.update(disowned=True, final_status="foreign_id")  # our hostname lives under another id
                    say(f"found {row['id']} for {p['hostname']}; it was created by this run")
                    self.adopt(p, row, "hostname lookup at cleanup")
                elif state == "refused_unverified":
                    p["state"] = "refused_rechecked"
                elif m is None:
                    p["state"] = "unconfirmed"
                    self.notes.append(f"create of {p['hostname']} was never confirmed either way; run `sweep` later to re-check")
            except Exception as e:  # noqa: BLE001 - one lookup must not skip the others
                p["state"] = "unconfirmed" if not p.get("id") else p.get("state")
                self.notes.append(f"lookup of {p.get('hostname')} failed: {type(e).__name__}: {e}")
        self.save_state()

    def cleanup(self) -> None:
        # 1. Creates whose outcome was never settled (timeout, a signal while the call was in flight, a
        #    capacity answer that may have come from a proxy, or an id that describe never confirmed).
        self._settle_pending()
        # 2. Delete (or keep) every machine this run recorded. Each delete in its own try.
        for round_ in (1, 2):
            disowned_before = sum(1 for m in self.machines() if m.get("disowned"))
            for m in list(self.machines()):
                if m.get("deleted") or m.get("disowned"):
                    continue
                if self.a.keep:
                    m["kept"] = True
                    continue
                try:
                    self.delete(m)
                except Exception as e:  # noqa: BLE001
                    self.notes.append(f"delete of {m.get('id')} raised {type(e).__name__}: {e}")
            self.save_state()
            if round_ == 1 and sum(1 for m in self.machines() if m.get("disowned")) > disowned_before:
                # An id turned out to belong to another machine: look our hostname up again, then delete.
                for p in self.state["pending"]:
                    if any(m["id"] == p.get("id") and m.get("disowned") for m in self.machines()):
                        p.update(id=None, state="ambiguous")
                self._settle_pending()
            else:
                break
        self.save_state()

    def finish(self, outcome: str, error: str | None) -> int:
        a = self.a
        now = time.time()
        undeleted = [m for m in self.machines() if not m.get("deleted") and not m.get("disowned")]
        unverified = [m for m in undeleted if not a.keep and m.get("final_status") == "unverified"]
        leaked = [m for m in undeleted if not a.keep and m.get("final_status") not in ("discontinued", "unverified")]
        released = [m for m in undeleted if not a.keep and m.get("final_status") == "discontinued"]
        unconfirmed = [p for p in self.state["pending"] if p.get("state") == "unconfirmed"]

        if outcome == "remote_failed":
            code = self.remote_exit if self.remote_exit and 0 < self.remote_exit < 256 else 1
        elif outcome.startswith("signal_"):
            code = 128 + (INT.signum or signal.SIGTERM)
        else:
            code = OUTCOME_EXIT.get(outcome, EXIT_INTERNAL)
        # Machine state outranks the job outcome (which stays in metrics.outcome): 76, then 79.
        if leaked:
            code = EXIT_DELETE_FAILED
        elif released or unconfirmed or unverified:
            code = EXIT_NEEDS_SWEEP

        banners: list[list[str]] = []
        if a.keep and undeleted:
            self.state["status"] = "kept"
            banners.append([f"--keep: instance {m['id']} ({m['hostname']}, {m.get('ip')}) is STILL RUNNING and billing "
                            f"{m['hourly_usd']:.4f} USD/h." for m in undeleted]
                           + [f"delete it with: {fmt(self.verda.argv(delete_args(m['id'], a.delete_wait_seconds)))}" for m in undeleted]
                           + [f"or: python3 {nice(__file__)} sweep --delete-mine   (state file {nice(self.state_file)})"])
        elif leaked:
            self.state["status"] = "delete_failed"
            banners.append([f"COULD NOT CONFIRM DELETION of instance {m['id']} ({m['hostname']}); last status '{m.get('final_status')}'." for m in leaked]
                           + ["It may still be billing. Retry: python3 " + nice(__file__) + " sweep --delete-mine"])
        elif released or unconfirmed or unverified:
            self.state["status"] = "needs_sweep"
            for m in released:
                self.notes.append(f"instance {m['id']} is 'discontinued' and the delete call did not remove its record; `sweep` re-checks it")
            for m in unverified:
                self.notes.append(f"instance {m['id']}: delete was accepted but never confirmed; `sweep` re-checks it")
            banners.append(["A MACHINE OF THIS RUN MAY STILL EXIST: "
                            + ", ".join([f"create of {p['hostname']} unconfirmed" for p in unconfirmed]
                                        + [f"delete of {m['id']} unconfirmed" for m in unverified]
                                        + [f"{m['id']} discontinued" for m in released]) + ".",
                            f"Re-check: python3 {nice(__file__)} sweep   (state file {nice(self.state_file)})"])
        else:
            self.state["status"] = "closed"

        # State file and run-log line first: a banner that cannot be printed must not lose them.
        try:
            if self.state["status"] == "closed":
                for f in (self.state_file, self.known_hosts):
                    try:
                        f.unlink()
                    except FileNotFoundError:
                        pass
            else:
                self.save_state()
        except OSError as e:
            self.notes.append(f"state file could not be written: {e}")

        machines_out = []
        for m in self.machines():
            seconds = round((m.get("deleted_epoch") or now) - m["created_epoch"], 1)
            machines_out.append({"id": m["id"], "hostname": m["hostname"], "instance_type": m["instance_type"],
                                 "location": m["location"], "spot": m["spot"], "hourly_usd": m["hourly_usd"],
                                 "seconds": seconds, "cost_estimate_usd": round(seconds / 3600.0 * m["hourly_usd"], 6),
                                 "found_by": m.get("found_by"), "deleted": bool(m.get("deleted")), "delete_calls": m.get("delete_calls", 0),
                                 "final_status": m.get("final_status"), "volumes_after_delete": m.get("volumes_after_delete"),
                                 "disowned": bool(m.get("disowned"))})
        cost = round(sum(x["cost_estimate_usd"] for x in machines_out if not x["disowned"]), 6)
        jm = self.job_machine
        jm_out = next((x for x in machines_out if jm and x["id"] == jm["id"]), None)
        metrics = {"outcome": outcome, "exit_code": code, "remote_exit_code": self.remote_exit,
                   "instance_type": jm["instance_type"] if jm else None, "location": jm["location"] if jm else None,
                   "spot": jm["spot"] if jm else None, "hourly_usd": jm["hourly_usd"] if jm else None,
                   "seconds": jm_out["seconds"] if jm_out else None, "wall_seconds": round(now - self.t0, 1),
                   "cost_estimate_usd": cost, "cost_basis": "sum over machines of hours x hourly price incl. OS volume, create call to confirmed delete",
                   "attempts": self.attempts, "signal": INT.signum, "error": error, "notes": self.notes,
                   "output_redirected_to": nice(_OUT["fallback"]) if _OUT["broken"] and _OUT["fallback"] else None}
        status = "ok" if code == 0 else "needs_sweep" if code == EXIT_NEEDS_SWEEP else "error"
        append_run_log(Path(a.run_log), {
            "ts": utc_iso(), "step": "verda_job", "host": socket.gethostname(), **self.command_record(),
            "inputs": self.inputs(),
            "outputs": {"artifacts": self.artifacts, "artifacts_dir": nice(self.artifacts_dir) if self.artifacts else None,
                        "machines": machines_out, "state_file": None if self.state["status"] == "closed" else nice(self.state_file)},
            "metrics": metrics, "cost_usd": cost, "status": status})

        for lines in banners:
            loud(lines)
        for note in self.notes:
            say("NOTE: " + note)
        if outcome == "spot_reclaimed":
            loud(["SPOT MACHINE RECLAIMED by the provider while the command was running.",
                  "The command did not finish and no artifacts could be fetched. This is not a failure of the command."])
        where = f"{jm['instance_type']}@{jm['location']} {'spot' if jm['spot'] else 'on-demand'}" if jm else "none"
        say(f"RESULT outcome={outcome} exit_code={code} remote_exit_code={self.remote_exit} machine={where} "
            f"machines_created={len(machines_out)} deleted={sum(1 for x in machines_out if x['deleted'])} "
            f"cost_estimate_usd={cost:.4f} wall_seconds={now - self.t0:.0f}" + (f" error={error}" if error else ""))
        return code

    def command_record(self) -> dict:
        """The command as it is logged: a redacted preview and the sha256 of the exact text."""
        return {"command": redact(self.command), "command_sha256": hashlib.sha256(self.command.encode()).hexdigest()}

    def main(self) -> int:
        self.validate()
        self.price_candidates()
        self.print_estimate()
        if self.dry:
            return self.dry_run_plan()
        unpriced = [c for c in self.candidates if c.hourly is None]
        if unpriced:
            raise UsageError("no hourly price for " + ", ".join(f"{c.label} ({c.price_source})" for c in unpriced)
                             + "; refusing to start because the budget cap could not be enforced")
        outcome, error = "internal_error", None
        install_signals()
        try:
            self.save_state()
            outcome = self.execute()
        except Interrupted as e:
            outcome, error = f"signal_{signal.Signals(e.signum).name}", "interrupted by signal"
        except Abort as e:
            outcome, error = e.outcome, str(e)
        except BaseException as e:  # noqa: BLE001 - anything else must still reach the cleanup below
            outcome, error = "internal_error", f"{type(e).__name__}: {e}"
            report_exception()
        finally:
            # From here on signals are only reported (see _Interrupt); nothing raises asynchronously.
            # Cleanup comes first and in its own try: no message, banner or traceback may skip it.
            INT.cleaning = True
            say(f"stopping ({outcome}){': ' + error if error else ''}; cleaning up")  # never raises
            try:
                self.cleanup()
            except BaseException as e:  # noqa: BLE001
                self.notes.append(f"cleanup error: {type(e).__name__}: {e}")
                try:
                    self.save_state()
                except Exception:  # noqa: BLE001
                    pass
                report_exception()
            # Python restores default handlers while it shuts down; ignoring the signals from here
            # on keeps a late Ctrl-C from replacing the exit code after the work is done.
            for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
                signal.signal(s, signal.SIG_IGN)
        return self.finish(outcome, error)


# ----------------------------------------------------------------------------- sweep

def cmd_sweep(a: argparse.Namespace) -> int:
    state_dir = Path(a.state_dir)
    verda = Verda(a.verda_bin, a.api_timeout_seconds, dry_run=a.dry_run)
    files = sorted(state_dir.glob("*.json")) if state_dir.is_dir() else []
    if not files:
        out(f"sweep: no state files in {nice(state_dir)}; this tool has nothing left behind.", flush=True)
        return EXIT_OK
    out(f"sweep: {len(files)} state file(s) in {nice(state_dir)}"
          + ("" if a.delete_mine else "  (listing only; nothing is deleted without --delete-mine)"), flush=True)
    listing: list[dict] | None = None
    still, unknown = 0, 0
    for f in files:
        try:
            st = json.loads(f.read_text())
        except (OSError, json.JSONDecodeError) as e:
            out(f"\n{nice(f)}: unreadable ({e})", flush=True)
            unknown += 1
            continue
        if st.get("schema") != STATE_SCHEMA:
            out(f"\n{nice(f)}: not a {STATE_SCHEMA} file; ignored", flush=True)
            continue
        same_host = st.get("tool_host") == socket.gethostname()
        # A run recorded on another host cannot be checked from here, so it counts as active: deleting
        # its machines needs --include-active.
        active = (not same_host) or pid_alive(st.get("tool_pid", -1))
        out(f"\n{nice(f)}\n  run {st.get('run_id')} started {st.get('started')} status={st.get('status')} "
              f"owner pid {st.get('tool_pid')} on {st.get('tool_host')}: "
              f"{('STILL RUNNING' if active else 'not running') if same_host else 'other host, treated as active'}", flush=True)
        may_delete = a.delete_mine and (not active or a.include_active)
        if a.delete_mine and active and not a.include_active:
            why = "its run is still active" if same_host else "its run was recorded on another host and may still be active there"
            out(f"  skipped for deletion: {why} (use --include-active to override)", flush=True)

        def save(st=st, f=f):
            write_json_atomic(f, st)

        # Creates that never settled: exact hostname, id absent before the call.
        for p in st.get("pending", []):
            if p.get("id") or p.get("state") in ("refused", "created"):
                continue
            if listing is None:
                res = verda.call(["vm", "list"])
                listing = vm_rows(res.data) if res.ok else None
            if listing is None:
                out(f"  pending {p['hostname']}: could not list machines; unknown", flush=True)
                unknown += 1
                continue
            hits = [r for r in listing if r.get("hostname") == p["hostname"] and r.get("id") not in p.get("pre_ids", [])]
            if not hits:
                out(f"  pending {p['hostname']}: no such machine exists", flush=True)
                continue
            row = hits[0]
            out(f"  pending {p['hostname']}: EXISTS as {row['id']} (status {row.get('status')}); created by that run, id was never recorded", flush=True)
            st.setdefault("machines", []).append({
                "id": row["id"], "hostname": p["hostname"], "instance_type": p.get("instance_type"), "location": p.get("location"),
                "spot": p.get("spot"), "hourly_usd": p.get("hourly_usd"), "created_epoch": p.get("call_epoch"),
                "found_by": "hostname lookup in sweep", "deleted": False, "delete_calls": 0, "volume_ids": [], "verified": True})
            p.update(id=row["id"], state="created")
            if may_delete:
                save()

        remaining = 0
        for m in st.get("machines", []):
            if m.get("deleted"):
                out(f"  instance {m['id']} ({m.get('hostname')}): recorded as deleted", flush=True)
                continue
            if m.get("disowned"):
                out(f"  instance {m['id']}: recorded as belonging to another machine; never deleted", flush=True)
                continue
            status, data = describe_status(verda, m["id"], echo=True)
            reported = (data or {}).get("hostname")
            if reported and m.get("hostname") and reported != m["hostname"]:
                out(f"  instance {m['id']} reports hostname {reported}, not {m['hostname']}: not this tool's machine, never deleted", flush=True)
                m.update(disowned=True, final_status="foreign_id")
                for p in st.get("pending", []):
                    if p.get("id") == m["id"]:
                        p.update(id=None, state="ambiguous")  # look the hostname up again next time
                unknown += 1
                remaining += 1
                if may_delete:
                    save()
                continue
            if status == "not_found" or status in GONE_STATUSES:
                out(f"  instance {m['id']} ({m.get('hostname')}): gone ({status})", flush=True)
                m.update(deleted=True, final_status=status)
                continue
            if status is None:
                out(f"  instance {m['id']} ({m.get('hostname')}): could not be described; unknown", flush=True)
                unknown += 1
                remaining += 1
                continue
            price = f"{m['hourly_usd']:.4f} USD/h" if isinstance(m.get("hourly_usd"), (int, float)) else "price unknown"
            out(f"  instance {m['id']} ({m.get('hostname')}, {m.get('instance_type')}@{m.get('location')}, {price}): "
                  f"STILL EXISTS, status '{status}'", flush=True)
            if not may_delete:
                out(f"    to delete: {fmt(verda.argv(delete_args(m['id'], a.delete_wait_seconds)))}", flush=True)
                still += 1
                remaining += 1
            elif a.dry_run:
                out(f"    dry-run, would run: {fmt(verda.argv(delete_args(m['id'], a.delete_wait_seconds)))}", flush=True)
                still += 1
                remaining += 1
            elif delete_instance(verda, m, save, a.delete_wait_seconds, retry_seconds=a.delete_retry_seconds):
                out(f"    deleted {m['id']} with its volumes", flush=True)
            else:
                out(f"    DELETE FAILED for {m['id']}", flush=True)
                still += 1
                remaining += 1
        if may_delete and not a.dry_run:
            if remaining == 0:
                for g in (f, f.with_suffix(".known_hosts")):
                    try:
                        g.unlink()
                    except FileNotFoundError:
                        pass
                out("  nothing left; state file removed", flush=True)
            else:
                save()
    out(f"\nsweep: {still} machine(s) of this tool still exist, {unknown} could not be checked.", flush=True)
    if still:
        return 1
    return 3 if unknown else EXIT_OK


# ----------------------------------------------------------------------------- command line

def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR), help="state files of this tool (default: ops/.state)")
    common.add_argument("--verda-bin", default="verda")
    common.add_argument("--api-timeout-seconds", type=float, default=60, help="verda --timeout per request (default 60)")
    common.add_argument("--delete-wait-seconds", type=int, default=300, help="verda vm delete --wait-timeout (default 300)")
    common.add_argument("--delete-retry-seconds", type=float, default=5, help="pause before a delete is retried (x attempt number)")
    common.add_argument("--dry-run", action="store_true", help="print every command; create, copy and delete nothing")

    ap = argparse.ArgumentParser(prog="verda_job.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", parents=[common], help="run one command on a short-lived VM")
    r.add_argument("--candidate", action="append", required=True, metavar=CANDIDATE_HELP,
                   help="tried in the order given; repeat the flag. image= overrides --image for this candidate "
                        "(image slugs differ between instance types); usd= states the hourly price instead of looking it up")
    r.add_argument("--kind", choices=["gpu", "cpu"], default="gpu")
    r.add_argument("--image", help="OS image slug (verda vm create --os), unless every candidate carries image=")
    r.add_argument("--os-volume-gb", type=int, default=50)
    r.add_argument("--spot-discontinue-policy", default="delete_permanently", choices=["delete_permanently", "move_to_trash", "keep_detached"])
    r.add_argument("--ssh-key-id", required=True, help="id from `verda --agent ssh-key list -o json`")
    r.add_argument("--ssh-key-path", required=True, help="matching private key file")
    r.add_argument("--ssh-user", default="root")
    r.add_argument("--hostname-prefix", required=True)
    r.add_argument("--copy", action="append", required=True, metavar="LOCAL_DIR[:REMOTE_SUBDIR]",
                   help="directory whose contents are copied to --remote-dir[/REMOTE_SUBDIR]; repeat the flag")
    r.add_argument("--exclude", action="append", default=[], help="rsync --exclude pattern for --copy; repeat the flag")
    r.add_argument("--remote-dir", default="/root/job")
    r.add_argument("--command", help="shell command run in --remote-dir")
    r.add_argument("--command-file", help="file holding the shell command")
    r.add_argument("--artifact", action="append", default=[], help="remote file or directory to fetch (relative to --remote-dir); repeat the flag")
    r.add_argument("--artifact-exclude", action="append", default=[], help="rsync --exclude pattern for artifacts; repeat the flag")
    r.add_argument("--artifacts-dir", help="local directory for artifacts (default ops/artifacts/<run-id>)")
    r.add_argument("--max-minutes", type=float, required=True, help="maximum wall-clock time of the whole run")
    r.add_argument("--budget-usd", type=float, required=True, help="budget for the whole run")
    r.add_argument("--keep", action="store_true", help="do not delete the machine at the end; its id is printed loudly")
    r.add_argument("--offline", action="store_true", help="with --dry-run: do not run the read-only price lookup either")
    r.add_argument("--run-log", default=str(DEFAULT_RUN_LOG))
    r.add_argument("--ssh-bin", default="ssh")
    r.add_argument("--rsync-bin", default="rsync")
    r.add_argument("--poll-seconds", type=float, default=20)
    r.add_argument("--log-lines", type=int, default=20, help="new log lines shown per poll")
    r.add_argument("--describe-every", type=int, default=3, help="vm describe every N polls")
    r.add_argument("--max-ssh-failures", type=int, default=6, help="consecutive failed polls before the machine counts as unreachable")
    r.add_argument("--provision-poll-seconds", type=float, default=5)
    r.add_argument("--provision-timeout-seconds", type=float, default=900)
    r.add_argument("--ssh-timeout-seconds", type=float, default=420)
    r.add_argument("--ssh-retry-seconds", type=float, default=5)
    r.add_argument("--copy-timeout-seconds", type=float, default=1800)
    r.add_argument("--fetch-timeout-seconds", type=float, default=900)
    r.add_argument("--lookup-window-seconds", type=float, default=45, help="how long to look for a machine after an ambiguous create")
    r.add_argument("--lookup-interval-seconds", type=float, default=5)
    r.add_argument("--refusal-lookup-seconds", type=float, default=15,
                   help="how long to look for a machine after a capacity (HTTP 503) answer to create")
    r.add_argument("--teardown-reserve-seconds", type=float, default=120, help="budget kept back for fetching artifacts and deleting")

    s = sub.add_parser("sweep", parents=[common], help="list what this tool left behind")
    s.add_argument("--delete-mine", action="store_true", help="delete machines recorded in this tool's state files")
    s.add_argument("--include-active", action="store_true", help="with --delete-mine: also machines of a run that is still running")
    return ap


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    try:
        if a.cmd == "sweep":
            return cmd_sweep(a)
        if a.offline and not a.dry_run:
            raise UsageError("--offline only makes sense with --dry-run")
        return Run(a).main()
    except UsageError as e:
        out(f"verda_job.py: {e}", file=sys.stderr, flush=True)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
