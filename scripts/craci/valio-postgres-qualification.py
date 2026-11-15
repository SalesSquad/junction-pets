#!/usr/bin/env python3
"""Run Valio's fictional multi-process ledger test on disposable local PostgreSQL.

The PostgreSQL cluster listens only on a private Unix socket. This harness
never touches an existing database or a sponsor/production account.
"""

import getpass
import glob
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    env = os.environ
    root = Path(env["CRACI_SOURCE_ROOT"]).resolve()
    expected = env["CRACI_SOURCE_SHA"]
    assert len(expected) == 40 and all(c in "0123456789abcdef" for c in expected)
    assert subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip() == expected, "Source checkout drifted from requested SHA"
    assert os.geteuid() != 0, "PostgreSQL initdb must run unprivileged"
    scripts = sorted(
        glob.glob("/usr/lib/postgresql/*/bin/initdb"),
        key=lambda p: int(Path(p).parts[4]),
    )
    assert scripts, "BLOCKED: PostgreSQL binary package missing"
    binary = Path(scripts[-1]).parent
    durable = root / "solutions/valio-trusted-trade/durable"
    assert (durable / "smoke.mjs").is_file()
    assert (durable / "package.json").is_file()

    tmp_root = Path(env["RUNNER_TEMP"]).resolve()
    scratch = Path(tempfile.mkdtemp(prefix="craci-valio-pg-", dir=tmp_root))
    data, socket = scratch / "data", scratch / "socket"
    socket.mkdir(mode=0o700)
    # Local peer-like trust is restricted to this private mode-0700 socket.
    # Product source is a separate pinned checkout, but it must not inherit
    # workflow/provider/session credentials from the runner environment.
    allowed = {"PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL",
               "LC_CTYPE", "TMPDIR", "TZ", "RUNNER_TEMP", "CI"}
    pg_env = {k: v for k, v in env.items() if k in allowed}
    # The node-postgres `socket:` URL defaults to PostgreSQL port 5432.
    # A private socket directory already isolates this ephemeral cluster.
    user, database, port = getpass.getuser(), "valio_j26_lab", "5432"
    started = False
    try:
        subprocess.run(
            [str(binary / "initdb"), "-D", str(data), "--encoding=UTF8",
             "--auth-local=trust", "--auth-host=reject", "--no-locale"],
            env=pg_env, check=True, stdout=subprocess.DEVNULL,
        )
        subprocess.run(
            [str(binary / "pg_ctl"), "-D", str(data), "-l",
             str(scratch / "postgres.log"), "-o",
             f"-c listen_addresses='' -k {socket} -p {port}", "-w", "start"],
            env=pg_env, check=True, stdout=subprocess.DEVNULL,
        )
        started = True
        subprocess.run(
            [str(binary / "createdb"), "-h", str(socket), "-p", port,
             "-U", user, database], env=pg_env, check=True,
        )
        pg_env["VALIO_TEST_DATABASE_URL"] = f"socket:{socket}?db={database}"
        for name, cmd, timeout in [
            ("multi-process-crash", ["node", "smoke.mjs", "--workers", "8", "--requests", "1000"], 600),
            ("postgres-invariants", ["node", "--test", "test/postgres.test.mjs"], 180),
        ]:
            completed = subprocess.run(
                cmd, cwd=durable, env=pg_env, text=True, capture_output=True,
                timeout=timeout,
            )
            if completed.returncode:
                # Even a synthetic test failure must not echo its connection
                # URI or private socket location into a public CI log.
                def tail(value):
                    return (value[-2500:]
                        .replace(pg_env["VALIO_TEST_DATABASE_URL"], "[LOCAL_PG_URL]")
                        .replace(str(socket), "[PRIVATE_SOCKET]"))
                print(json.dumps({"phase": name, "result": "failed",
                    "returnCode": completed.returncode,
                    "stdoutTail": tail(completed.stdout),
                    "stderrTail": tail(completed.stderr)}))
                raise SystemExit(completed.returncode)
            if name == "multi-process-crash":
                result = json.loads(completed.stdout)
                assert result["workersStarted"] == 8
                assert result["independentOsPids"] == 8
                assert result["postCommitCrashObserved"] and result["crashReplayed"]
                assert result["verified"]["balanced"] and result["verified"]["nonnegative"]
                assert result["verified"]["batches"] == 203
                assert result["verified"]["outboxEvents"] == 203
                print(json.dumps({"phase": name, "result": "passed", "summary": result}))
            else:
                print(json.dumps({"phase": name, "result": "passed",
                    "testOutputTail": completed.stdout[-1800:]}))
        receipt = {"scope": "synthetic local PostgreSQL; no bank transfer",
            "sourceSha": expected, "postgres": subprocess.check_output(
                [str(binary / "postgres"), "--version"], text=True).strip(),
            "workers": 8, "mixedRequests": 1000, "databaseMode": "private-unix-socket",
            "result": "passed"}
        artifacts = Path(env["CRACI_RECEIPT_DIR"]) / "artifacts"
        artifacts.mkdir(parents=True, exist_ok=True)
        with (artifacts / "valio-durable-pg.json").open("x") as stream:
            json.dump(receipt, stream, sort_keys=True)
        print(json.dumps(receipt, sort_keys=True))
    finally:
        if started:
            subprocess.run(
                [str(binary / "pg_ctl"), "-D", str(data), "-m", "fast",
                 "-w", "stop"], env=pg_env, check=True, stdout=subprocess.DEVNULL,
            )
        shutil.rmtree(scratch)


if __name__ == "__main__":
    main()
