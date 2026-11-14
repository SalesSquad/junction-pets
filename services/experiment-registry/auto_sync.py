#!/usr/bin/env python3
"""One-shot owner-only run ledger reconciler, suitable for macOS launchd.

No daemon, GPU dispatch, direct main push, credentials export, model promotion or
unbounded raw data traversal. The existing portfolio PR integrator owns merging.
"""
from __future__ import annotations
import argparse
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

REPOSITORY = "SalesSquad/junction-pets"
BRANCH_PREFIX = "agent/experiment-auto-"
SOURCE_URL = "https://github.com/SalesSquad/junction-pets.git"
ACTIVE_LIMIT = 500


def call(args: list[str], cwd: Path | None = None, timeout=45, rc0=True) -> subprocess.CompletedProcess:
    env = {**os.environ, "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin", "GH_PROMPT_DISABLED": "1"}
    p = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    if rc0 and p.returncode != 0:
        # Never print potentially sensitive private receipt content or a command line.
        raise RuntimeError("external command failed")
    return p


def owner_dir(path: Path) -> None:
    if not path.is_absolute() or path.is_symlink():
        raise ValueError("owner directory must be absolute and not symlinked")
    path.mkdir(parents=True, mode=0o700, exist_ok=True)
    st = path.stat()
    if st.st_uid != os.getuid() or st.st_mode & 0o077:
        raise ValueError("owner directory permissions are unsafe")


def atomic_json(path: Path, data: dict) -> None:
    encoded = (json.dumps(data, sort_keys=True, allow_nan=False) + "\n").encode()
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".pending-", delete=False) as fp:
        tmp = Path(fp.name)
        os.fchmod(fp.fileno(), 0o600)
        fp.write(encoded)
        fp.flush()
        os.fsync(fp.fileno())
    os.replace(tmp, path)


def status(owner: Path, name: str, **fields) -> None:
    stamped = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    body = {"schemaVersion": 1, "phase": name, "observedAt": stamped, **fields}
    atomic_json(owner / "status.json", body)
    print(json.dumps(body, sort_keys=True), flush=True)


def ensure_checkout(src: Path):
    if not (src / ".git").exists():
        raise RuntimeError("dedicated checked-out source is missing")
    url = call(["git", "remote", "get-url", "origin"], cwd=src, timeout=10).stdout.strip()
    if url != SOURCE_URL:
        raise RuntimeError("unrecognized repository remote")
    branch = call(["git", "branch", "--show-current"], cwd=src, timeout=10).stdout.strip()
    if branch != "main":
        raise RuntimeError("expected dedicated main checkout")
    if call(["git", "status", "--porcelain"], cwd=src, timeout=12).stdout.strip():
        raise RuntimeError("dedicated main checkout is dirty")
    call(["git", "fetch", "--no-tags", "origin", "main"], cwd=src, timeout=55)
    call(["git", "merge", "--ff-only", "origin/main"], cwd=src, timeout=30)


def open_experiment_prs() -> list:
    result = call(["gh", "pr", "list", "--repo", REPOSITORY, "--state", "open",
                   "--limit", "100", "--json", "headRefName,url"], timeout=30)
    data = json.loads(result.stdout)
    return [row for row in data if row.get("headRefName", "").startswith(BRANCH_PREFIX)]



def archive_merged_envelopes(owner: Path, source: Path) -> int:
    # Move only metadata envelopes that match an immutable record already on
    # authoritative main. Raw private receipt files never leave receipts/.
    archive = owner / "archive"
    owner_dir(archive)
    count = 0
    for event in sorted((owner / "inbox").glob("*.json")):
        if event.is_symlink() or not event.is_file() or event.stat().st_size > 256 * 1024:
            continue  # importer will explicitly fail this unsafe item
        try:
            envelope = json.loads(event.read_text())
            run = envelope["run"]
            rid = run["runId"]
            if not isinstance(rid, str) or not re.fullmatch("[a-z][a-z0-9._-]{2,95}", rid):
                continue
            if event.name != rid + ".json":
                continue
            existing = source / "ops/experiments/runs" / (rid + ".json")
            if not existing.is_file() or json.loads(existing.read_text()) != run:
                continue
            dest = archive / event.name
            if dest.exists() or dest.is_symlink():
                continue  # never overwrite preserved history
            os.rename(event, dest)
            count += 1
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            pass  # invalid receipts remain visible in inbox
    return count

def run_once(owner: Path, verda_db: Path | None) -> int:
    for d in (owner, owner / "inbox", owner / "receipts", owner / "worktrees"):
        owner_dir(d)
    fd = os.open(owner / "sync.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            status(owner, "already-running")
            return 0
        source = owner / "source"
        ensure_checkout(source)
        archived = archive_merged_envelopes(owner, source)
        # Import new Verda coordinator jobs as INCOMPLETE GPU probe/lease
        # records only. Existing historical jobs already on main are skipped.
        if verda_db and verda_db.is_file():
            v = call([sys.executable, str(source / "services/experiment-registry/verda_collect.py"),
                      "--db", str(verda_db),
                      "--registry", str(source / "ops/experiments"),
                      "--inbox", str(owner / "inbox"),
                      "--receipts-root", str(owner / "receipts")], timeout=28)
            collector = json.loads(v.stdout)
        else:
            collector = {"unavailable": True, "envelopesCreated": 0}
        names = sorted(x.name for x in (owner / "inbox").iterdir() if x.name.endswith(".json"))
        if not names:
            status(owner, "idle", collected=collector.get("envelopesCreated", 0), archived=archived, totalInbox=0)
            return 0
        if len(names) > ACTIVE_LIMIT:
            status(owner, "batch-overflow", totalInbox=len(names), maxInbox=ACTIVE_LIMIT)
            return 2
        pending = open_experiment_prs()
        if pending:
            status(owner, "pending-pr", pendingPrs=len(pending), totalInbox=len(names))
            return 0
        # A crash before PR creation may have left a dirty/unpushed task worktree.
        # Never submit a second copy while its original state needs reconciliation.
        orphaned = [x for x in (owner / "worktrees").iterdir() if x.is_dir()]
        if orphaned:
            status(owner, "orphaned-worktree", ownedWorktrees=len(orphaned))
            return 2
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        branch = BRANCH_PREFIX + stamp
        work = owner / "worktrees" / stamp
        if work.exists():
            raise RuntimeError("task worktree name already exists")
        call(["git", "worktree", "add", "-b", branch, str(work), "origin/main"], cwd=source, timeout=40)
        cli = ["node", "services/experiment-registry/inbox.mjs",
               "--inbox", str(owner / "inbox"),
               "--receipts-root", str(owner / "receipts"),
               "--root", str(work / "ops/experiments"),
               "--limit", str(ACTIVE_LIMIT)]
        result = call(cli, cwd=work, timeout=65, rc0=False)
        # Partial successful entries must not be discarded merely because
        # another item was invalid; errors remain visible in status.json.
        try:info = json.loads(result.stdout)
        except (ValueError, TypeError):
            raise RuntimeError("inbox returned invalid summary")
        if result.returncode not in (0, 1, 2) or info.get("exitCode") != result.returncode:
            raise RuntimeError("inbox returned inconsistent exit status")
        count = info.get("created", 0)
        failed = info.get("failed", 0)
        if not isinstance(count, int) or not isinstance(failed, int):
            raise RuntimeError("inbox summary invalid")
        if count == 0:
            # The new worktree contains no new owned files, so local cleanup is safe.
            if call(["git", "status", "--porcelain"], cwd=work, timeout=10).stdout.strip():
                raise RuntimeError("unexpected dirty worktree after zero imported records")
            call(["git", "worktree", "remove", str(work)], cwd=source, timeout=12)
            call(["git", "branch", "-d", branch], cwd=source, timeout=12)
            status(owner, "no-new-records" if failed == 0 else "invalid-receipts",
                   existing=info.get("existing", 0), failed=failed, totalInbox=len(names))
            return 0 if failed == 0 else 2
        dirty = call(["git", "status", "--porcelain"], cwd=work, timeout=12).stdout.splitlines()
        expected_prefix = "?? ops/experiments/runs/"
        if not dirty or any(not x.startswith(expected_prefix) or not x.endswith(".json") for x in dirty):
            raise RuntimeError("import modified unexpected repository paths")
        call(["git", "add", "--", "ops/experiments/runs"], cwd=work, timeout=12)
        staged = call(["git", "diff", "--cached", "--name-only"], cwd=work, timeout=12).stdout.splitlines()
        if len(staged) != count or any(not x.startswith("ops/experiments/runs/") or not x.endswith(".json") for x in staged):
            raise RuntimeError("staged diff count and paths differ from admitted records")
        call(["git", "diff", "--cached", "--check"], cwd=work, timeout=12)
        call(["git", "commit", "-m", "docs(experiments): ingest " + str(count) + " verified run receipts"], cwd=work, timeout=40)
        head = call(["git", "rev-parse", "HEAD"], cwd=work, timeout=10).stdout.strip()
        if not re.fullmatch("[a-f0-9]{40}", head):
            raise RuntimeError("invalid committed head")
        # Never force-push or directly write main.
        call(["git", "push", "-u", "origin", "refs/heads/" + branch + ":refs/heads/" + branch], cwd=work, timeout=65)
        remote = call(["git", "ls-remote", "origin", "refs/heads/" + branch], cwd=work, timeout=15).stdout
        if not remote.startswith(head + "\t"):
            raise RuntimeError("remote head mismatch after push")
        title = "docs(experiments): ingest " + str(count) + " immutable run receipts"
        body = ("Automatic source-bound owner inbox import. Exact head " + head +
                ". Admitted " + str(count) + " new sanitized metadata records; " +
                str(failed) + " rejected receipts remain in private inbox. No model " +
                "promotion, provider spending, raw artifacts, credentials or direct main push. " +
                "Use the existing authorized PR integrator for exact-HEAD merge.")
        pr = call(["gh", "pr", "create", "--repo", REPOSITORY,
                   "--base", "main", "--head", branch, "--title", title, "--body", body],
                  cwd=work, timeout=45)
        url = pr.stdout.strip().splitlines()[-1]
        if not url.startswith("https://github.com/SalesSquad/junction-pets/pull/"):
            raise RuntimeError("unexpected PR creation result")
        # Commit is preserved by verified remote ref + GitHub PR; close only the
        # clean task-owned worktree, not its local/remote task branch.
        if not call(["git", "status", "--porcelain"], cwd=work, timeout=10).stdout.strip():
            call(["git", "worktree", "remove", str(work)], cwd=source, timeout=15)
        status(owner, "pr-created", count=count, failed=failed, branch=branch, head=head, prUrl=url)
        return 0 if failed == 0 else 2
    finally:
        os.close(fd)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner-root", type=Path, required=True)
    parser.add_argument("--verda-db", type=Path)
    args = parser.parse_args()
    try:
        return run_once(args.owner_root, args.verda_db)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        if args.owner_root.is_dir():
            try:status(args.owner_root, "blocked", reason=type(exc).__name__)
            except OSError:pass
        return 2


if __name__ == "__main__":
    sys.exit(main())
