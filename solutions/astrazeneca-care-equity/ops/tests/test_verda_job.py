"""Tests for ops/verda_job.py.

Run:  python -m unittest discover -s ops/tests

No test talks to Verda Cloud or to a real machine. A fake `verda`, `ssh` and `rsync`
(ops/tests/fakes/) are put first on PATH; the fake ssh runs the "remote" command locally
in a temporary directory, so the detached start, the log/exit-code files, polling and
artifact fetching are exercised for real.
"""
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOL = HERE.parent / "verda_job.py"
FAKES = HERE / "fakes"

OK_COMMAND = "mkdir -p out && cat input.txt > out/result.txt && echo done-ok"
LONG_COMMAND = "for i in $(seq 1 400); do echo tick $i; sleep 0.2; done"
FOREIGN = {"hostname": "t-1114-000000-abcdef-c1", "status": "running"}  # same prefix as ours, not ours


def strip(argv):
    """verda arguments without the global flags."""
    a = argv[1:-2]
    return a[2:] if a[:1] == ["--timeout"] else a


class Sandbox:
    def __init__(self, scenario):
        self.tmp = Path(tempfile.mkdtemp(prefix="verda-job-test-")).resolve()
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        for name in ("verda", "ssh", "rsync"):
            exe = self.bin / name
            exe.write_text(f"#!{sys.executable}\n" + (FAKES / f"fake_{name}.py").read_text())
            exe.chmod(0o755)
        self.fake = self.tmp / "fake"
        self.fake.mkdir()
        scenario = dict(scenario)
        scenario.setdefault("prices", {"gpuA": {"spot": 0.5, "ondemand": 2.0}, "gpuB": {"spot": 0.25, "ondemand": 1.0}})
        scenario.setdefault("existing", [FOREIGN])
        (self.fake / "scenario.json").write_text(json.dumps(scenario))
        self.state_dir = self.tmp / "state"
        self.run_log = self.tmp / "runlog.jsonl"
        self.art = self.tmp / "artifacts"
        self.pkg = self.tmp / "pkg"
        (self.pkg / "__pycache__").mkdir(parents=True)
        (self.pkg / "input.txt").write_text("hello\n")
        (self.pkg / "__pycache__" / "junk.pyc").write_text("junk")
        self.key = self.tmp / "id_test"
        self.key.write_text("not a real key\n")
        self.env = dict(os.environ, PATH=f"{self.bin}{os.pathsep}{os.environ['PATH']}", FAKE_VERDA_DIR=str(self.fake))

    def common(self):
        return ["--state-dir", str(self.state_dir), "--api-timeout-seconds", "5", "--delete-wait-seconds", "5",
                "--delete-retry-seconds", "0.05"]

    def argv(self, *extra, candidates=("gpuA@FIN-01:spot",), command=OK_COMMAND, artifacts=("out/result.txt",),
             max_minutes=2.0, budget=100.0):
        a = [sys.executable, str(TOOL), "run"]
        for c in candidates:
            a += ["--candidate", c]
        a += ["--image", "img-1", "--ssh-key-id", "key-1", "--ssh-key-path", str(self.key), "--hostname-prefix", "t",
              "--copy", str(self.pkg), "--exclude", "__pycache__", "--remote-dir", "job", "--command", command,
              "--max-minutes", str(max_minutes), "--budget-usd", str(budget),
              "--run-log", str(self.run_log), "--artifacts-dir", str(self.art),
              "--poll-seconds", "0.2", "--provision-poll-seconds", "0.05", "--ssh-retry-seconds", "0.05",
              "--describe-every", "1", "--lookup-window-seconds", "1", "--lookup-interval-seconds", "0.1",
              "--refusal-lookup-seconds", "1",
              "--teardown-reserve-seconds", "0"] + self.common()
        for art in artifacts:
            a += ["--artifact", art]
        return a + list(extra)

    def run(self, *extra, timeout=90, **kw):
        return subprocess.run(self.argv(*extra, **kw), env=self.env, cwd=self.tmp, capture_output=True, text=True, timeout=timeout)

    def popen(self, *extra, **kw):
        return subprocess.Popen(self.argv(*extra, **kw), env=self.env, cwd=self.tmp, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True)

    def sweep(self, *extra):
        return subprocess.run([sys.executable, str(TOOL), "sweep", *self.common(), *extra], env=self.env, cwd=self.tmp,
                              capture_output=True, text=True, timeout=60)

    def lines(self, name):
        p = self.fake / name
        return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []

    def calls(self, *words):
        out = [strip(c["argv"]) for c in self.lines("calls.jsonl")]
        return [c for c in out if c[:len(words)] == list(words)]

    def vms(self):
        p = self.fake / "state.json"
        return json.loads(p.read_text())["vms"] if p.exists() else {}

    def created(self):
        return [v for v in self.vms().values() if not v["foreign"]]

    def runlog(self):
        return [json.loads(x) for x in self.run_log.read_text().splitlines()]

    def state_files(self):
        return sorted(self.state_dir.glob("*.json")) if self.state_dir.exists() else []

    def wait_for(self, predicate, timeout=30):
        end = time.time() + timeout
        while time.time() < end:
            if predicate():
                return True
            time.sleep(0.05)
        return False

    def close(self):
        for pidfile in self.fake.glob("remote/*/.verda_job/*/pid"):
            try:
                pid = int(pidfile.read_text().strip())
            except (OSError, ValueError):
                continue
            subprocess.run(["pkill", "-KILL", "-P", str(pid)], capture_output=True)
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        shutil.rmtree(self.tmp, ignore_errors=True)


class Base(unittest.TestCase):
    def sandbox(self, scenario=None):
        sb = Sandbox(scenario or {})
        self.addCleanup(sb.close)
        self.addCleanup(self.check_invariants, sb)
        return sb

    def check_invariants(self, sb):
        """Hold in every test: CLI contract, and nothing but our own ids is ever deleted."""
        for c in sb.lines("calls.jsonl"):
            self.assertEqual(c["argv"][0], "--agent", c["argv"])
            self.assertEqual(c["argv"][-2:], ["-o", "json"], c["argv"])
        ours = {v["id"] for v in sb.created()}
        for d in sb.calls("vm", "delete"):
            self.assertIn(d[2], ours, f"deleted an id this run did not create: {d}")
            self.assertIn("--with-volumes", d)
            self.assertIn("--yes", d)
            for banned in ("--all", "--hostname", "--status"):
                self.assertNotIn(banned, d)
        for v in sb.vms().values():
            if v["foreign"]:
                self.assertFalse(v["deleted"], "a machine that does not belong to the tool was deleted")

    def assert_deleted_exactly_once(self, sb, expected_count=1):
        created = sb.created()
        self.assertEqual(len(created), expected_count, "number of machines created")
        deletes = sb.calls("vm", "delete")
        self.assertEqual(sorted(d[2] for d in deletes), sorted(v["id"] for v in created),
                         "exactly one delete call per created id")
        for d in deletes:
            self.assertIn("--with-volumes", d)
        for v in created:
            self.assertTrue(v["deleted"])
            self.assertTrue(v["volumes_deleted"])

    def assert_rc(self, proc, rc):
        out = proc.stdout if isinstance(proc.stdout, str) else ""
        err = proc.stderr if isinstance(getattr(proc, "stderr", None), str) else ""
        self.assertEqual(proc.returncode, rc, f"\n--- stdout ---\n{out}\n--- stderr ---\n{err}")


class RunTests(Base):
    def test_first_candidate_503_second_succeeds(self):
        sb = self.sandbox({"create": [{"result": "503"}, {"result": "ok"}], "ssh_fail_first": 2})
        p = sb.run(candidates=("gpuA@FIN-01:spot", "gpuB@FIN-02:on-demand"))
        self.assert_rc(p, 0)
        self.assertLess(p.stdout.index("COST ESTIMATE"), p.stdout.index("vm create"), "estimate is printed before any create")
        creates = sb.calls("vm", "create")
        self.assertEqual(len(creates), 2)
        self.assertIn("--is-spot", creates[0])
        self.assertEqual(creates[0][creates[0].index("--os-volume-on-spot-discontinue") + 1], "delete_permanently")
        self.assertEqual(creates[0][creates[0].index("--instance-type") + 1], "gpuA")
        self.assertNotIn("--is-spot", creates[1])
        self.assertEqual(creates[1][creates[1].index("--instance-type") + 1], "gpuB")
        self.assertEqual(creates[1][creates[1].index("--location") + 1], "FIN-02")
        self.assert_deleted_exactly_once(sb, 1)
        # artifact arrived, with the sha256 in the run log
        self.assertEqual((sb.art / "result.txt").read_text(), "hello\n")
        self.assertIn("done-ok", (sb.art / "job.log").read_text())
        log = sb.runlog()[-1]
        self.assertEqual(log["step"], "verda_job")
        self.assertEqual(log["status"], "ok")
        m = log["metrics"]
        self.assertEqual((m["outcome"], m["exit_code"], m["remote_exit_code"]), ("ok", 0, 0))
        self.assertEqual((m["instance_type"], m["location"], m["spot"], m["hourly_usd"]), ("gpuB", "FIN-02", False, 1.0))
        self.assertEqual([a["result"] for a in m["attempts"]], ["no_capacity_503", "up"])
        sha = {Path(a["path"]).name: a["sha256"] for a in log["outputs"]["artifacts"]}
        self.assertEqual(sha["result.txt"], hashlib.sha256(b"hello\n").hexdigest())
        machine = log["outputs"]["machines"][0]
        self.assertTrue(machine["deleted"])
        self.assertEqual(machine["delete_calls"], 1)
        self.assertAlmostEqual(log["cost_usd"], machine["seconds"] / 3600 * 1.0, places=6)  # hours x hourly price
        self.assertGreater(m["seconds"], 0)
        # --exclude was honoured, the state file is gone, ssh was retried until it answered
        remote = next(sb.fake.glob("remote/*/job"))
        self.assertTrue((remote / "input.txt").exists())
        self.assertFalse((remote / "__pycache__").exists())
        self.assertEqual(sb.state_files(), [])
        self.assertGreaterEqual(len([c for c in sb.lines("ssh_calls.jsonl") if c["cmd"] == "true"]), 3)

    def test_create_times_out_but_machine_exists(self):
        sb = self.sandbox({"create": [{"result": "timeout_created"}, {"result": "ok"}]})
        p = sb.run(candidates=("gpuA@FIN-01:spot", "gpuB@FIN-02:on-demand"))
        self.assert_rc(p, 0)
        self.assertEqual(len(sb.calls("vm", "create")), 1, "no second create: the first machine existed after all")
        self.assertGreaterEqual(len(sb.calls("vm", "list")), 2, "looked the hostname up after the timeout")
        self.assert_deleted_exactly_once(sb, 1)
        log = sb.runlog()[-1]
        self.assertEqual(log["metrics"]["instance_type"], "gpuA")
        self.assertIn("hostname lookup", log["outputs"]["machines"][0]["found_by"])
        self.assertEqual(sb.state_files(), [])

    def test_create_returns_no_id_machine_found_by_hostname(self):
        sb = self.sandbox({"create": [{"result": "ok_no_id"}]})
        p = sb.run()
        self.assert_rc(p, 0)
        self.assertEqual(len(sb.calls("vm", "create")), 1)
        self.assert_deleted_exactly_once(sb, 1)

    def test_create_times_out_and_no_machine_then_next_candidate(self):
        sb = self.sandbox({"create": [{"result": "timeout"}, {"result": "ok"}]})
        p = sb.run(candidates=("gpuA@FIN-01:spot", "gpuB@FIN-02:on-demand"))
        # the job succeeded, but a create was never confirmed either way: exit 79, not 0
        self.assert_rc(p, 79)
        self.assertEqual(len(sb.calls("vm", "create")), 2)
        self.assert_deleted_exactly_once(sb, 1)
        log = sb.runlog()[-1]
        self.assertEqual((log["status"], log["metrics"]["outcome"], log["metrics"]["exit_code"]), ("needs_sweep", "ok", 79))
        # the unconfirmed create stays on record for `sweep`
        files = sb.state_files()
        self.assertEqual(len(files), 1)
        self.assertEqual(json.loads(files[0].read_text())["status"], "needs_sweep")
        s = sb.sweep()
        self.assert_rc(s, 0)
        self.assertIn("no such machine exists", s.stdout)
        self.assertEqual(len(sb.state_files()), 1, "listing removes nothing")
        self.assert_rc(sb.sweep("--delete-mine"), 0)
        self.assertEqual(sb.state_files(), [])

    def test_machine_discontinued_while_waiting(self):
        sb = self.sandbox({"create": [{"result": "ok", "statuses": ["provisioning", "discontinued"]}, {"result": "ok"}]})
        p = sb.run(candidates=("gpuA@FIN-01:spot", "gpuB@FIN-02:on-demand"))
        self.assert_rc(p, 0)
        self.assert_deleted_exactly_once(sb, 2)
        log = sb.runlog()[-1]
        self.assertEqual([a["result"] for a in log["metrics"]["attempts"]], ["machine_discontinued", "up"])
        self.assertEqual(log["metrics"]["instance_type"], "gpuB")
        # the discontinued machine is deleted before the next candidate is created
        seq = [c[:2] for c in (strip(x["argv"]) for x in sb.lines("calls.jsonl")) if c[:2] in (["vm", "create"], ["vm", "delete"])]
        self.assertEqual(seq, [["vm", "create"], ["vm", "delete"], ["vm", "create"], ["vm", "delete"]])

    def test_machine_discontinued_and_no_other_candidate(self):
        sb = self.sandbox({"create": [{"result": "ok", "statuses": ["provisioning", "discontinued"]}]})
        p = sb.run()
        self.assert_rc(p, 70)
        self.assert_deleted_exactly_once(sb, 1)
        self.assertEqual(sb.runlog()[-1]["metrics"]["outcome"], "no_candidate")
        self.assertEqual(sb.lines("ssh_calls.jsonl"), [])

    def test_remote_command_fails_exit_code_propagates(self):
        sb = self.sandbox()
        p = sb.run(command="echo boom; exit 7")
        self.assert_rc(p, 7)
        self.assert_deleted_exactly_once(sb, 1)
        self.assertIn("boom", (sb.art / "job.log").read_text())
        self.assertIn("| boom", p.stdout, "log lines are streamed")
        log = sb.runlog()[-1]
        self.assertEqual((log["metrics"]["outcome"], log["metrics"]["exit_code"], log["metrics"]["remote_exit_code"]),
                         ("remote_failed", 7, 7))
        self.assertEqual(log["status"], "error")
        self.assertEqual(sb.state_files(), [])

    def test_command_with_syntax_error_is_a_normal_failure(self):
        sb = self.sandbox()
        p = sb.run(command="echo before; if then fi (")
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(sb.runlog()[-1]["metrics"]["outcome"], "remote_failed")
        self.assert_deleted_exactly_once(sb, 1)

    def test_artifact_missing_after_successful_command(self):
        sb = self.sandbox()
        p = sb.run(artifacts=("out/result.txt", "out/never-written.bin"))
        self.assert_rc(p, 75)
        self.assert_deleted_exactly_once(sb, 1)
        arts = sb.runlog()[-1]["outputs"]["artifacts"]
        self.assertTrue(any(a.get("missing") and a["artifact"] == "out/never-written.bin" for a in arts))
        self.assertTrue(any(a.get("sha256") and a["artifact"] == "out/result.txt" for a in arts))

    def test_budget_cap(self):
        # 3600 USD/h = 1 USD per second; 3 USD of budget is gone after about three seconds.
        sb = self.sandbox({"prices": {"gpuA": {"spot": 3600.0, "ondemand": 3600.0}}})
        p = sb.run(command=LONG_COMMAND, budget=3.0)
        self.assert_rc(p, 73)
        self.assert_deleted_exactly_once(sb, 1)
        log = sb.runlog()[-1]
        self.assertEqual(log["metrics"]["outcome"], "budget_cap")
        self.assertIsNone(log["metrics"]["remote_exit_code"])
        self.assertLess(log["metrics"]["wall_seconds"], 40)
        self.assertIn("budget cap reached", p.stdout)
        self.assertEqual(sb.state_files(), [])

    def test_time_cap(self):
        sb = self.sandbox()
        p = sb.run(command=LONG_COMMAND, max_minutes=0.05)
        self.assert_rc(p, 72)
        self.assert_deleted_exactly_once(sb, 1)
        log = sb.runlog()[-1]
        self.assertEqual(log["metrics"]["outcome"], "time_cap")
        self.assertIn("tick 1", (sb.art / "job.log").read_text(), "the partial log is still fetched")

    def test_spot_reclaimed_mid_run_is_reported_distinctly(self):
        sb = self.sandbox({"create": [{"result": "ok", "statuses": ["provisioning", "running", "running", "discontinued"]}]})
        p = sb.run(command=LONG_COMMAND)
        self.assert_rc(p, 74)
        self.assertIn("SPOT MACHINE RECLAIMED", p.stdout)
        self.assert_deleted_exactly_once(sb, 1)
        log = sb.runlog()[-1]
        self.assertEqual(log["metrics"]["outcome"], "spot_reclaimed")
        self.assertTrue(log["metrics"]["spot"])

    def test_on_demand_machine_lost_is_not_called_a_reclaim(self):
        sb = self.sandbox({"create": [{"result": "ok", "statuses": ["provisioning", "running", "running", "discontinued"]}]})
        p = sb.run(command=LONG_COMMAND, candidates=("gpuA@FIN-01:on-demand",))
        self.assert_rc(p, 77)
        self.assertNotIn("SPOT MACHINE RECLAIMED", p.stdout)
        self.assertEqual(sb.runlog()[-1]["metrics"]["outcome"], "machine_lost")
        self.assert_deleted_exactly_once(sb, 1)

    def _signal_during_run(self, signum, expected_rc):
        sb = self.sandbox()
        proc = sb.popen(command=LONG_COMMAND)
        try:
            started = sb.wait_for(lambda: any(sb.fake.glob("remote/*/.verda_job/*/pid")))
            self.assertTrue(started, "job never started")
            time.sleep(0.6)
            proc.send_signal(signum)
            out, _ = proc.communicate(timeout=60)
        finally:
            if proc.poll() is None:
                proc.kill()
        self.assertEqual(proc.returncode, expected_rc, out)
        self.assert_deleted_exactly_once(sb, 1)
        log = sb.runlog()[-1]
        self.assertEqual(log["metrics"]["outcome"], f"signal_{signal.Signals(signum).name}")
        self.assertEqual(log["metrics"]["exit_code"], expected_rc)
        self.assertEqual(sb.state_files(), [])

    def test_sigterm_during_run(self):
        self._signal_during_run(signal.SIGTERM, 143)

    def test_sigint_during_run(self):
        self._signal_during_run(signal.SIGINT, 130)

    def test_sigterm_while_create_is_in_flight(self):
        # The API has accepted the create, the CLI has not answered yet, and the tool is told to stop.
        sb = self.sandbox({"create": [{"result": "slow_created", "delay": 30}]})
        proc = sb.popen()
        try:
            self.assertTrue(sb.wait_for(lambda: len(sb.created()) == 1), "create was never called")
            t = time.time()
            proc.send_signal(signal.SIGTERM)
            out, _ = proc.communicate(timeout=60)
        finally:
            if proc.poll() is None:
                proc.kill()
        self.assertEqual(proc.returncode, 143, out)
        self.assertLess(time.time() - t, 20, "did not wait for the slow create to return")
        self.assert_deleted_exactly_once(sb, 1)
        self.assertIn("hostname lookup at cleanup", sb.runlog()[-1]["outputs"]["machines"][0]["found_by"])

    def test_second_signal_does_not_stop_cleanup(self):
        sb = self.sandbox()
        proc = sb.popen(command=LONG_COMMAND)
        try:
            self.assertTrue(sb.wait_for(lambda: any(sb.fake.glob("remote/*/.verda_job/*/pid"))))
            time.sleep(0.4)
            proc.send_signal(signal.SIGTERM)
            for _ in range(20):
                time.sleep(0.02)
                if proc.poll() is None:
                    proc.send_signal(signal.SIGINT)
            out, _ = proc.communicate(timeout=60)
        finally:
            if proc.poll() is None:
                proc.kill()
        self.assertEqual(proc.returncode, 143, out)
        self.assert_deleted_exactly_once(sb, 1)

    def test_delete_fails_once_then_succeeds(self):
        sb = self.sandbox({"delete": [{"result": "fail"}, {"result": "ok"}]})
        p = sb.run()
        self.assert_rc(p, 0)
        deletes = sb.calls("vm", "delete")
        self.assertEqual(len(deletes), 2)
        self.assertEqual(deletes[0][2], deletes[1][2])
        self.assertTrue(sb.created()[0]["deleted"])

    def test_delete_keeps_failing_is_loud_and_recoverable(self):
        sb = self.sandbox({"delete": [{"result": "fail"}]})
        p = sb.run()
        self.assert_rc(p, 76)
        self.assertIn("COULD NOT CONFIRM DELETION", p.stdout)
        vm = sb.created()[0]
        self.assertFalse(vm["deleted"])
        self.assertIn(vm["id"], p.stdout)
        files = sb.state_files()
        self.assertEqual(len(files), 1)
        self.assertEqual(json.loads(files[0].read_text())["status"], "delete_failed")
        s = sb.sweep()
        self.assert_rc(s, 1)
        self.assertIn("STILL EXISTS", s.stdout)

    def test_keep_then_sweep(self):
        sb = self.sandbox()
        p = sb.run("--keep")
        self.assert_rc(p, 0)
        self.assertEqual(sb.calls("vm", "delete"), [])
        vm = sb.created()[0]
        self.assertIn(vm["id"], p.stdout)
        self.assertIn("STILL RUNNING", p.stdout)
        self.assertEqual(json.loads(sb.state_files()[0].read_text())["status"], "kept")
        # listing deletes nothing and says what exists
        s = sb.sweep()
        self.assert_rc(s, 1)
        self.assertIn(vm["id"], s.stdout)
        self.assertIn("STILL EXISTS", s.stdout)
        self.assertEqual(sb.calls("vm", "delete"), [])
        self.assertEqual(len(sb.state_files()), 1)
        # --delete-mine --dry-run still deletes nothing
        s = sb.sweep("--delete-mine", "--dry-run")
        self.assert_rc(s, 1)
        self.assertEqual(sb.calls("vm", "delete"), [])
        # --delete-mine deletes exactly the recorded id, with volumes
        s = sb.sweep("--delete-mine")
        self.assert_rc(s, 0)
        self.assert_deleted_exactly_once(sb, 1)
        self.assertEqual(sb.state_files(), [])
        self.assert_rc(sb.sweep(), 0)

    def test_sweep_skips_a_run_that_is_still_active(self):
        sb = self.sandbox()
        proc = sb.popen(command=LONG_COMMAND)
        try:
            self.assertTrue(sb.wait_for(lambda: any(sb.fake.glob("remote/*/.verda_job/*/pid"))))
            s = sb.sweep("--delete-mine")
            self.assertIn("still active", s.stdout)
            self.assertEqual(sb.calls("vm", "delete"), [], "sweep must not delete under a live run")
            proc.send_signal(signal.SIGTERM)
            proc.communicate(timeout=60)
        finally:
            if proc.poll() is None:
                proc.kill()
        self.assert_deleted_exactly_once(sb, 1)

    def test_dry_run_creates_nothing(self):
        sb = self.sandbox()
        p = sb.run("--dry-run", candidates=("gpuA@FIN-01:spot", "gpuB@FIN-02:on-demand"))
        self.assert_rc(p, 0)
        self.assertEqual({tuple(c[:2]) for c in sb.calls()}, {("cost", "estimate")}, "only the read-only price lookup ran")
        self.assertEqual(sb.lines("ssh_calls.jsonl"), [])
        self.assertEqual(sb.lines("rsync_calls.jsonl"), [])
        self.assertEqual(sb.created(), [])
        for needle in ("COST ESTIMATE", "vm create", "--with-volumes", "nohup", "rsync", "DRY RUN complete"):
            self.assertIn(needle, p.stdout)
        self.assertEqual(sb.state_files(), [])
        self.assertEqual(sb.runlog()[-1]["status"], "dry_run")

    def test_dry_run_offline_calls_nothing_at_all(self):
        sb = self.sandbox()
        p = sb.run("--dry-run", "--offline")
        self.assert_rc(p, 0)
        self.assertEqual(sb.calls(), [])

    def test_refuses_to_start_without_a_price(self):
        sb = self.sandbox()
        p = sb.run(candidates=("unknownType@FIN-01:spot",))
        self.assert_rc(p, 2)
        self.assertIn("refusing to start", p.stderr)
        self.assertEqual(sb.calls("vm", "create"), [])

    def test_candidate_options_image_and_stated_price(self):
        sb = self.sandbox({"create": [{"result": "503"}, {"result": "ok"}]})
        p = sb.run(candidates=("gpuA@FIN-01:spot,image=img-for-a", "gpuB@FIN-02:on-demand,usd=1.5"))
        self.assert_rc(p, 0)
        creates = sb.calls("vm", "create")
        self.assertEqual(creates[0][creates[0].index("--os") + 1], "img-for-a")
        self.assertEqual(creates[1][creates[1].index("--os") + 1], "img-1")
        self.assertEqual(len(sb.calls("cost", "estimate")), 1, "a stated price is not looked up")
        self.assertEqual(sb.runlog()[-1]["metrics"]["hourly_usd"], 1.5)
        self.assert_deleted_exactly_once(sb, 1)

    def test_bad_candidate_is_a_usage_error(self):
        sb = self.sandbox()
        for bad in ("gpuA:spot", "gpuA@FIN-01:cheap", "gpuA@FIN-01:spot,usd=free", "gpuA@FIN-01:spot,colour=red"):
            p = sb.run(candidates=(bad,))
            self.assert_rc(p, 2)
        self.assertEqual(sb.calls("vm", "create"), [])

    def test_validation_error_tries_next_candidate(self):
        sb = self.sandbox({"create": [{"result": "validation"}, {"result": "ok"}]})
        p = sb.run(candidates=("gpuA@FIN-01:spot", "gpuB@FIN-02:on-demand"))
        self.assert_rc(p, 0)
        self.assertEqual(len(sb.calls("vm", "list")), 2, "a refused create needs no hostname lookup")
        self.assert_deleted_exactly_once(sb, 1)


class ReviewFixTests(Base):
    """Cases from the version-2 review (runs/review-findings-v2.json, findings 12, 13 and 16 to 19)."""

    def _run_until_started(self, sb, command, **popen_kw):
        proc = subprocess.Popen(sb.argv(command=command), env=sb.env, cwd=sb.tmp, **popen_kw)
        started = sb.wait_for(lambda: any(sb.fake.glob("remote/*/.verda_job/*/pid")))
        self.assertTrue(started, "job never started")
        return proc

    def _assert_cleaned_and_logged(self, sb):
        self.assert_deleted_exactly_once(sb, 1)
        self.assertEqual(len(sb.runlog()), 1, "exactly one run-log line")
        self.assertEqual(sb.state_files(), [])

    def test_closed_stdout_and_stderr_pipe_then_sigint(self):
        sb = self.sandbox()
        proc = self._run_until_started(sb, LONG_COMMAND, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            proc.stdout.close()
            proc.stderr.close()
            time.sleep(0.6)
            proc.send_signal(signal.SIGINT)
            proc.wait(timeout=60)
        finally:
            if proc.poll() is None:
                proc.kill()
        self.assertEqual(proc.returncode, 130)
        self._assert_cleaned_and_logged(sb)
        self.assertEqual(sb.runlog()[-1]["metrics"]["outcome"], "signal_SIGINT")

    def test_closed_stdout_pipe_without_a_signal(self):
        sb = self.sandbox()
        proc = self._run_until_started(sb, "sleep 2; " + OK_COMMAND, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            proc.stdout.close()
            proc.wait(timeout=60)
        finally:
            if proc.poll() is None:
                proc.kill()
        self.assertEqual(proc.returncode, 0)
        self._assert_cleaned_and_logged(sb)
        self.assertIsNotNone(sb.runlog()[-1]["metrics"]["output_redirected_to"])

    def test_terminal_hang_up(self):
        import pty
        import threading
        sb = self.sandbox()
        master, slave = pty.openpty()
        stop = threading.Event()

        def drain():  # a terminal that reads until it is told to stop
            import select
            while not stop.is_set():
                ready, _, _ = select.select([master], [], [], 0.1)
                if ready:
                    try:
                        if not os.read(master, 4096):
                            return
                    except OSError:
                        return

        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        proc = subprocess.Popen(sb.argv(command="sleep 2; " + OK_COMMAND), env=sb.env, cwd=sb.tmp, stdout=slave, stderr=slave)
        os.close(slave)
        try:
            self.assertTrue(sb.wait_for(lambda: any(sb.fake.glob("remote/*/.verda_job/*/pid"))), "job never started")
            stop.set()
            reader.join(timeout=5)
            os.close(master)  # the terminal goes away: writes to the slave now fail with EIO
            proc.wait(timeout=60)
        finally:
            if proc.poll() is None:
                proc.kill()
        self.assertEqual(proc.returncode, 0)
        self._assert_cleaned_and_logged(sb)

    def test_503_although_the_machine_was_created(self):
        sb = self.sandbox({"create": [{"result": "503_created"}, {"result": "ok"}]})
        p = sb.run(candidates=("gpuA@FIN-01:spot", "gpuB@FIN-02:on-demand"))
        self.assert_rc(p, 0)
        self.assertEqual(len(sb.calls("vm", "create")), 1, "the machine behind the 503 was found and used")
        self.assert_deleted_exactly_once(sb, 1)
        self.assertIn("capacity refusal", sb.runlog()[-1]["outputs"]["machines"][0]["found_by"])
        self.assertEqual(sb.state_files(), [])

    def test_503_with_no_machine_is_rechecked_at_cleanup(self):
        sb = self.sandbox({"create": [{"result": "503"}, {"result": "ok"}]})
        p = sb.run(candidates=("gpuA@FIN-01:spot", "gpuB@FIN-02:on-demand"))
        self.assert_rc(p, 0)
        self.assert_deleted_exactly_once(sb, 1)
        self.assertEqual([a["result"] for a in sb.runlog()[-1]["metrics"]["attempts"]], ["no_capacity_503", "up"])

    def test_create_output_names_a_foreign_id_that_cannot_be_described(self):
        sb = self.sandbox({"create": [{"result": "ok_foreign_id"}], "describe_fails_for_foreign": True})
        p = sb.run("--provision-timeout-seconds", "2")
        self.assert_rc(p, 70)
        # check_invariants: the foreign machine was not deleted; ours was found by hostname and deleted
        self.assert_deleted_exactly_once(sb, 1)
        machines = sb.runlog()[-1]["outputs"]["machines"]
        self.assertTrue(any(m["disowned"] and not m["deleted"] for m in machines))
        self.assertTrue(any(m["deleted"] and "hostname lookup" in m["found_by"] for m in machines))

    def test_delete_accepted_but_never_confirmed_exits_79(self):
        sb = self.sandbox({"describe_fails_after_delete": True})
        p = sb.run()
        self.assert_rc(p, 79)
        log = sb.runlog()[-1]
        self.assertEqual(log["status"], "needs_sweep")
        self.assertEqual(log["outputs"]["machines"][0]["final_status"], "unverified")
        files = sb.state_files()
        self.assertEqual(len(files), 1, "the state file is kept so that sweep re-checks the machine")
        self.assertEqual(json.loads(files[0].read_text())["status"], "needs_sweep")

    def test_sweep_treats_another_hosts_run_as_active(self):
        sb = self.sandbox()
        p = sb.run("--keep")
        self.assert_rc(p, 0)
        f = sb.state_files()[0]
        st = json.loads(f.read_text())
        st["tool_host"] = "some-other-host.invalid"
        f.write_text(json.dumps(st))
        s = sb.sweep("--delete-mine")
        self.assertIn("another host", s.stdout)
        self.assertEqual(sb.calls("vm", "delete"), [], "no delete without --include-active")
        self.assert_rc(sb.sweep("--delete-mine", "--include-active"), 0)
        self.assert_deleted_exactly_once(sb, 1)

    def test_secret_in_command_is_not_logged(self):
        sb = self.sandbox()
        secret = "hf_" + "A1b2C3d4E5f6G7h8"
        p = sb.run(command=f"HF_TOKEN={secret} true && " + OK_COMMAND)
        self.assert_rc(p, 0)
        log = sb.run_log.read_text()
        self.assertNotIn(secret, log)
        self.assertIn("[REDACTED]", log)
        self.assertEqual(len(sb.runlog()[-1]["command_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
