import datetime as dt
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
import subprocess
import sys
from unittest.mock import patch
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location("intent_cloud", Path(__file__).with_name("cloud.py"))
cloud = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cloud)


class CloudBoundaries(unittest.TestCase):
    def test_deadline_refuses_equality_and_after(self):
        end = cloud.instant(cloud.DEADLINE)
        cloud.before(cloud.DEADLINE, end - dt.timedelta(microseconds=1))
        for now in (end, end + dt.timedelta(days=1)):
            with self.assertRaises(ValueError):
                cloud.before(cloud.DEADLINE, now)

    def test_identity_and_source_binding(self):
        for source, run, tag in (("bad", "123", cloud.TAG), ("a" * 40, "../123", cloud.TAG),
                                  ("a" * 40, "123", "another-campaign")):
            with self.assertRaises(ValueError):
                cloud.identities(source, run, tag)
        receipt = {"source_sha": "a" * 40, "run_id": "123", "dataset": "banking77", "lane": "word_svm"}
        cloud.binding(receipt, "a" * 40, "123", "banking77", "word_svm")
        with self.assertRaises(ValueError):
            cloud.binding(receipt, "b" * 40, "123", "banking77", "word_svm")
        with self.assertRaises(ValueError):
            cloud.binding(receipt, "a" * 40, "124", "banking77", "word_svm")

    def test_actions_context_is_required_and_exact(self):
        context = {"GITHUB_REPOSITORY": cloud.REPO, "GITHUB_SHA": "a" * 40,
                   "GITHUB_RUN_ID": "123", "GITHUB_REF": "refs/heads/main"}
        with patch.dict("os.environ", context, clear=True):
            cloud.identities("a" * 40, "123", cloud.TAG)
        for key in context:
            for replacement in (None, "different"):
                changed = dict(context)
                if replacement is None:
                    changed.pop(key)
                else:
                    changed[key] = replacement
                with self.subTest(key=key, replacement=replacement), patch.dict("os.environ", changed, clear=True):
                    with self.assertRaises(ValueError):
                        cloud.identities("a" * 40, "123", cloud.TAG)

    def package(self, root, extra=None):
        model = b"not executed: opaque skops test data"
        best = {"source_sha": "a" * 40, "run_id": "123", "dataset": "banking77", "lane": "word_svm",
                "model_sha256": hashlib.sha256(model).hexdigest()}
        metadata = dict(best, manifest_sha256="m" * 64,
                        history_sha256=hashlib.sha256(b"").hexdigest())
        members = {"best.skops": model, "best.json": json.dumps(best).encode(),
                   "metadata.json": json.dumps(metadata).encode(), "history.jsonl": b""}
        if extra:
            members.update(extra)
        path = root / "checkpoint.tar.gz"
        cloud.pack_checkpoint(members, path)
        return path

    def test_archive_success_does_not_execute_model(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = self.package(root)
            best = cloud.unpack_checkpoint(archive, root / "unpacked", "a" * 40, "123", "banking77", "word_svm", "m" * 64)
            self.assertEqual(best["dataset"], "banking77")
            self.assertTrue((root / "unpacked" / "best.skops").is_file())

    def test_atomic_pack_repairs_old_partial_and_is_deterministic(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            destination = root / "checkpoint.tar.gz"
            destination.write_bytes(b"old interrupted gzip")
            archive = self.package(root)
            digest = cloud.sha256(archive)
            cloud.unpack_checkpoint(archive, root / "out", "a" * 40, "123", "banking77", "word_svm", "m" * 64)
            self.package(root)
            self.assertEqual(cloud.sha256(archive), digest)
            # Dataset packing uses the same deterministic, atomic primitive.
            data_pack = root / "datasets.tar.gz"
            cloud.atomic_pack({"banking77/train.parquet": b"original dataset bytes"}, data_pack, 20_000_000)
            data_digest = cloud.sha256(data_pack)
            cloud.atomic_pack({"banking77/train.parquet": b"original dataset bytes"}, data_pack, 20_000_000)
            self.assertEqual(cloud.sha256(data_pack), data_digest)

    def test_interrupted_pack_never_replaces_valid_final_archive(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = self.package(root)
            original = archive.read_bytes()
            with patch.object(tarfile.TarFile, "addfile", side_effect=OSError("interrupted compression")):
                with self.assertRaises(OSError):
                    cloud.pack_checkpoint({"best.json": b"new metadata"}, archive)
            self.assertEqual(archive.read_bytes(), original)
            self.assertFalse(list(root.glob("*.part")))

    def test_archive_path_traversal_and_unknown_members_refused(self):
        for name in ("../escape", "/tmp/escape", "extra.py"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                archive = self.package(root, {name: b"not executed"})
                with self.assertRaises(ValueError):
                    cloud.unpack_checkpoint(archive, root / "unpacked", "a" * 40, "123", "banking77", "word_svm", "m" * 64)
                self.assertFalse((root / "escape").exists())

    def test_archive_symlink_and_oversize_refused(self):
        for symbolic in (True, False):
            with self.subTest(symbolic=symbolic), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                archive = root / "bad.tar.gz"
                with tarfile.open(archive, "w:gz") as package:
                    for name in ("best.skops", "best.json", "metadata.json", "history.jsonl"):
                        member = tarfile.TarInfo(name)
                        data = b""
                        if name == "best.skops" and symbolic:
                            member.type, member.linkname = tarfile.SYMTYPE, "/etc/passwd"
                        elif name == "best.json" and not symbolic:
                            data = b"x" * (cloud.MEMBER_LIMITS[name] + 1)
                            member.size = len(data)
                        package.addfile(member, io.BytesIO(data))
                with self.assertRaises(ValueError):
                    cloud.unpack_checkpoint(archive, root / "out", "a" * 40, "123", "banking77", "word_svm", "m" * 64)
                if not symbolic:
                    self.assertFalse((root / "out" / "best.json").exists())

    def test_checkpoint_source_mismatch_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = self.package(root)
            with self.assertRaises(ValueError):
                cloud.unpack_checkpoint(archive, root / "out", "b" * 40, "123", "banking77", "word_svm", "m" * 64)

    def test_history_and_model_tampering_refused(self):
        for member in ("best.skops", "history.jsonl"):
            with self.subTest(member=member), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                archive = self.package(root, {member: b"different bytes"})
                with self.assertRaises(ValueError):
                    cloud.unpack_checkpoint(archive, root / "out", "a" * 40, "123", "banking77", "word_svm", "m" * 64)

    def test_latest_sequence_not_lexicographic_or_cross_lane(self):
        items = [{"name": "banking77-word_svm-s0002.tar.gz"}, {"name": "banking77-word_svm-s0010.tar.gz"},
                 {"name": "banking77-char_svm-s0003.tar.gz"}, {"name": "banking77-word_svm-s0009.tar.gz.old"}]
        selected = cloud.latest_checkpoints(items)
        self.assertEqual(selected[("banking77", "word_svm")][0], 10)
        self.assertEqual(selected[("banking77", "char_svm")][0], 3)

    def test_child_does_not_receive_publication_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            result = root / "environment.json"
            program = "import os,json,sys;open(sys.argv[1],'w').write(json.dumps(dict(os.environ)))"
            with patch.dict("os.environ", {"GH_TOKEN": "test-secret", "GITHUB_TOKEN": "another-secret",
                                           "ACTIONS_RUNTIME_TOKEN": "runtime-secret", "RUNNER_TRACKING_ID": "task-tracking"}):
                status = cloud.run_child([sys.executable, "-c", program, str(result)], root / "child.log", 3)
            self.assertEqual(status, 0)
            child = json.loads(result.read_text())
            for secret in ("GH_TOKEN", "GITHUB_TOKEN", "ACTIONS_RUNTIME_TOKEN"):
                self.assertNotIn(secret, child)
            self.assertEqual(child["RUNNER_TRACKING_ID"], "task-tracking")

    def test_child_time_bound_delivers_termination(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            result = root / "terminated"
            program = ("import signal,time,sys;"
                       "signal.signal(signal.SIGTERM,lambda *_:(open(sys.argv[1],'w').write('terminated'),sys.exit(0)));"
                       "time.sleep(20)")
            with self.assertRaises(subprocess.TimeoutExpired):
                cloud.run_child([sys.executable, "-c", program, str(result)], root / "child.log", 1)
            self.assertEqual(result.read_text(), "terminated")

    def test_credential_bearing_upload_redirect_refused(self):
        request = cloud.urllib.request.Request("https://uploads.github.com/", headers={"Authorization": "Bearer test"})
        with self.assertRaises(ValueError):
            cloud.NoGitHubRedirects().redirect_request(request, None, 302, "Found", {}, "https://another.example/")

    def test_failed_transfer_does_not_poison_final_name_and_resume_verifies(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "restored.tar.gz"
            payload = b"complete task-owned download"
            digest = hashlib.sha256(payload).hexdigest()
            def interrupted(out):
                out.write(payload[:4])
                raise OSError("interrupted")
            with self.assertRaises(OSError):
                cloud.atomic_verified_write(path, len(payload), digest, interrupted)
            self.assertFalse(path.exists())
            self.assertFalse(list(root.glob("*.part")))
            # Also repair a final filename left partial by the old implementation.
            path.write_bytes(b"old partial")
            cloud.atomic_verified_write(path, len(payload), digest, lambda out: out.write(payload))
            self.assertEqual(path.read_bytes(), payload)
            cloud.atomic_verified_write(path, len(payload), digest,
                                        lambda _: self.fail("Valid cached bytes must not be downloaded again"))

    def test_streaming_archive_never_uses_eager_header_scan(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = self.package(root, {"state.json": b"{}"})
            with patch.object(tarfile.TarFile, "getmembers", side_effect=AssertionError("eager scan refused")):
                cloud.unpack_checkpoint(archive, root / "out", "a" * 40, "123", "banking77", "word_svm", "m" * 64)
            # Same valid restore is idempotent; it verifies and reuses existing bytes.
            cloud.unpack_checkpoint(archive, root / "out", "a" * 40, "123", "banking77", "word_svm", "m" * 64)

    def test_explicit_token_required_instead_of_fallback_credentials(self):
        with patch.dict("os.environ", {"GITHUB_TOKEN": "must-not-be-used"}, clear=True):
            with patch.object(cloud, "release", side_effect=AssertionError("No provider request without explicit token")):
                with self.assertRaises(RuntimeError):
                    cloud.upload(Path("unopened"))
            with self.assertRaises(RuntimeError):
                cloud.gh("api", "user")

    def test_spend_reservation_and_next_chunk_respect_cap(self):
        manifest = {"max_spend_eur": 150, "credit": {"authorized_existing_eur": 1000,
                    "observed_junction_balance_eur": 995.95, "published_eur_per_vcpu_minute": .0017}}
        start = cloud.instant("2026-11-15T03:00:00Z")
        self.assertLess(cloud.estimated_spend(manifest, now=start), 150)
        too_small = dict(manifest, max_spend_eur=100)
        with self.assertRaises(ValueError):
            cloud.estimated_spend(too_small, now=start)
        unauthorized = dict(manifest, max_spend_eur=1001)
        with self.assertRaises(ValueError):
            cloud.spend_limit(unauthorized)
        near_limit = dict(manifest, max_spend_eur=107)
        admission = {"created_at": start.isoformat(), "max_spend_eur": 107}
        now = cloud.instant("2026-11-15T16:00:00Z")
        self.assertLess(cloud.estimated_spend(near_limit, admission, now=now), 107)
        with self.assertRaises(ValueError):
            cloud.estimated_spend(near_limit, admission, additional_seconds=735, now=now)

    def receipt(self, dataset="banking77", model="b" * 64):
        return {"dataset": dataset, "lane": "word_svm", "source_sha": "a" * 40,
                "run_id": "123", "model_sha256": model, "test_sha256": "c" * 64,
                "rows": 3, "accuracy": .5, "macro_f1_observed": .4, "macro_f1_all_labels": .3}

    def test_test_receipt_reuse_is_bound_to_exact_model_and_test(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "banking77-test-evaluation.json"
            path.write_text(json.dumps(self.receipt()))
            spec = {"sha256": "c" * 64, "rows": 3}
            with patch.object(cloud, "run_child", side_effect=AssertionError("Do not rerun an evaluated test")):
                reused = cloud.reused_evaluation(path, [], "banking77", "b" * 64, spec, "a" * 40, "123", "word_svm")
            self.assertEqual(reused, self.receipt())
            with self.assertRaises(ValueError):
                cloud.reused_evaluation(path, [], "banking77", "d" * 64, spec, "a" * 40, "123", "word_svm")
            with self.assertRaises(ValueError):
                cloud.reused_evaluation(path, [], "banking77", "b" * 64,
                                        dict(spec, sha256="e" * 64), "a" * 40, "123", "word_svm")

    def test_completed_summary_resumes_markdown_without_test_predictions(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            manifest = {"datasets": {d: {"files": {"test": {"sha256": "c" * 64, "rows": 3}}} for d in cloud.DATASETS}}
            manifest_path = work / "manifest.json"
            manifest_path.write_text(json.dumps(manifest))
            summary = {"source_sha": "a" * 40, "run_id": "123", "manifest_sha256": cloud.sha256(manifest_path),
                       "status": "complete", "missing_lanes": [], "finished_at": "2026-11-15T16:44:00Z", "winners": {}}
            items = []
            for dataset in cloud.DATASETS:
                receipt = self.receipt(dataset)
                (work / f"{dataset}-test-evaluation.json").write_text(json.dumps(receipt))
                archive_hash = hashlib.sha256(dataset.encode()).hexdigest()
                summary["winners"][dataset] = {"lane": "word_svm", "model_sha256": "b" * 64,
                                              "validation_macro_f1": .5, "winner_archive_sha256": archive_hash,
                                              "test_evaluation": receipt}
                items.append({"name": f"{dataset}-winner.tar.gz", "label": "sha256:" + archive_hash})
            summary_path = work / "campaign-summary.json"
            summary_path.write_text(json.dumps(summary))
            original = summary_path.read_bytes()
            args = SimpleNamespace(source_sha="a" * 40, run_id="123", manifest=str(manifest_path))
            published = []
            with patch.object(cloud, "upload", side_effect=lambda p: published.append(Path(p).name)), \
                    patch.object(cloud, "run_child", side_effect=AssertionError("Never recompute the held-out test")), \
                    patch.object(cloud, "dataset_files", side_effect=AssertionError("No fresh test download needed")):
                result = cloud.recover_summary(args, manifest, work, items)
            self.assertEqual(result, 0)
            self.assertEqual(summary_path.read_bytes(), original)
            self.assertIn("campaign-summary.md", published)
            self.assertTrue((work / "campaign-summary.md").is_file())

    def cache_transport(self, payload, asset_changes=None, private=True, tag=None):
        digest = hashlib.sha256(payload).hexdigest()
        entry = {"url": "https://huggingface.co/datasets/publisher/data/resolve/" + "a" * 40 + "/data.parquet",
                 "sha256": digest, "bytes": len(payload)}
        asset = {"id": 1234, "name": "sha256-" + digest, "size": len(payload),
                 "label": "sha256:" + digest, "digest": "sha256:" + digest}
        asset.update(asset_changes or {})
        calls = []
        def provider(*args, output=None, timeout=180):
            calls.append(args)
            if args == ("api", f"repos/{cloud.REPO}"):
                return json.dumps({"private": private, "full_name": cloud.REPO}).encode()
            if args == ("api", f"repos/{cloud.REPO}/releases/tags/{cloud.DATA_CACHE_TAG}"):
                return json.dumps({"id": 900, "tag_name": tag or cloud.DATA_CACHE_TAG,
                                   "prerelease": True, "draft": False}).encode()
            if args == ("api", "--paginate", "--slurp", f"repos/{cloud.REPO}/releases/900/assets?per_page=100"):
                return json.dumps([[asset]]).encode()
            if args == ("api", f"repos/{cloud.REPO}/releases/assets/1234", "-H", "Accept: application/octet-stream"):
                output.write(payload)
                return None
            raise AssertionError("Unexpected provider request")
        return entry, provider, calls

    def test_private_cache_fetches_exact_opaque_publisher_bytes(self):
        payload = b"opaque public licensed dataset bytes"
        entry, provider, calls = self.cache_transport(payload)
        with tempfile.TemporaryDirectory() as folder, patch.object(cloud, "_DATA_CACHE_ASSETS", None), \
                patch.object(cloud, "gh", side_effect=provider):
            path = Path(folder) / "train.parquet"
            cloud.fetch(entry, path)
            self.assertEqual(path.read_bytes(), payload)
            count = len(calls)
            cloud.fetch(entry, path)
            self.assertEqual(len(calls), count)

    def test_private_cache_refuses_wrong_name_hash_and_size(self):
        for changed in ({"name": "sha256-" + "f" * 64}, {"label": "sha256:" + "f" * 64},
                        {"digest": "sha256:" + "f" * 64}, {"size": 999}):
            entry, provider, _ = self.cache_transport(b"public bytes", changed)
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as folder, \
                    patch.object(cloud, "_DATA_CACHE_ASSETS", None), patch.object(cloud, "gh", side_effect=provider):
                path = Path(folder) / "train.parquet"
                with self.assertRaises(ValueError):
                    cloud.fetch(entry, path)
                self.assertFalse(path.exists())

    def test_private_cache_refuses_public_repository_and_wrong_release(self):
        for settings in ({"private": False}, {"tag": "other-release"}):
            entry, provider, _ = self.cache_transport(b"public bytes", **settings)
            with self.subTest(settings=settings), tempfile.TemporaryDirectory() as folder, \
                    patch.object(cloud, "_DATA_CACHE_ASSETS", None), patch.object(cloud, "gh", side_effect=provider):
                with self.assertRaises(ValueError):
                    cloud.fetch(entry, Path(folder) / "train.parquet")


if __name__ == "__main__":
    unittest.main()
