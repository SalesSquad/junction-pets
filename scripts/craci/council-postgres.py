"""Run the existing real-PG verifier against a disposable local Unix socket."""
import getpass
import glob
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

root = Path(os.environ["SOURCE_DIR"]).resolve()
expected = os.environ["EXPECTED_SOURCE_SHA"]
assert len(expected) == 40 and all(c in "0123456789abcdef" for c in expected)
assert subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip() == expected
assert os.geteuid() != 0, "Run PostgreSQL as the existing unprivileged CI user"
binaries = sorted(glob.glob("/usr/lib/postgresql/*/bin/initdb"), key=lambda p: int(Path(p).parts[4]))
assert binaries, "PostgreSQL binaries unavailable"
bin_dir = Path(binaries[-1]).parent
scratch = Path(tempfile.mkdtemp(prefix="craci-council-", dir=os.environ["RUNNER_TEMP"]))
data, sock = scratch / "data", scratch / "socket"
sock.mkdir(mode=0o700)
env = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
user = getpass.getuser()
database = "junction_council_test_craci"
started = False
try:
    subprocess.run([str(bin_dir / "initdb"), "-D", str(data), "--auth-local=trust",
        "--auth-host=reject", "--no-locale"], env=env, check=True, stdout=subprocess.DEVNULL)
    subprocess.run([str(bin_dir / "pg_ctl"), "-D", str(data), "-l", str(scratch / "postgres.log"),
        "-o", f"-c listen_addresses='' -k {sock} -p 54329", "-w", "start"],
        env=env, check=True, stdout=subprocess.DEVNULL)
    started = True
    subprocess.run([str(bin_dir / "createdb"), "-h", str(sock), "-p", "54329", "-U", user, database],
        env=env, check=True)
    from psycopg.conninfo import make_conninfo
    env["JUNCTION_COUNCIL_TEST_DATABASE_URL"] = make_conninfo(
        dbname=database, host=str(sock), port=54329, user=user, connect_timeout=3)
    env["PYTHONPATH"] = str(root / "services/council")
    gate = root / "services/council/tests/test_postgres_replay_pg.py"
    completed = subprocess.run([sys.executable, str(gate)], cwd=root, env=env, timeout=180)
    if completed.returncode:
        raise SystemExit(completed.returncode)
    print(json.dumps({"status": "passed", "scope": "existing-council-real-local-postgres-gate",
        "source_sha": expected, "postgres_version": subprocess.check_output(
            [str(bin_dir / "postgres"), "--version"], text=True).strip(),
        "aiven_service_verified": False, "provider_execution_verified": False}))
finally:
    if started:
        subprocess.run([str(bin_dir / "pg_ctl"), "-D", str(data), "-m", "fast", "-w", "stop"],
            env=env, check=True, stdout=subprocess.DEVNULL)
    shutil.rmtree(scratch)
