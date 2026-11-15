import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("repo_bundle", Path(__file__).with_name("bundle.py"))
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)


class SourceSnapshotBoundaries(unittest.TestCase):
    def entry(self, path, size=10, mode="100644"):
        return {"path": path, "type": "blob", "mode": mode, "size": size, "sha": "a" * 40}

    def test_source_allowlist_and_sensitive_paths(self):
        for path in ("src/app.py", "src/child_authorization.rs", "web/main.tsx", "Cargo.toml", "requirements-dev.txt"):
            self.assertIsNone(bundle.allowed_path(path), path)
        for path in ("../escape.py", "/absolute.py", "src/../escape.py", "src\\escape.py", "x\n.py", ".git/config.py",
                     "private/customer.py", "child-data/records.py", "fixtures/example.ts", "dist/app.js", ".env.local",
                     "credentials.py", "id_rsa", "assets/photo.png", "database.json"):
            self.assertIsNotNone(bundle.allowed_path(path), path)

    def test_tree_refuses_symlink_oversize_and_truncated_inputs(self):
        entries = [self.entry("src/app.py"), self.entry("src/link.py", mode="120000"),
                   self.entry("src/huge.py", size=bundle.MAX_FILE + 1)]
        selected, excluded = bundle.selected_tree({"tree": entries})
        self.assertEqual([x["path"] for x in selected], ["src/app.py"])
        self.assertEqual({x["reason"] for x in excluded}, {"nonregular-file", "file-size-bound"})
        with self.assertRaises(ValueError):
            bundle.selected_tree({"tree": [], "truncated": True})

    def test_secret_file_is_removed_without_value_or_snippet(self):
        token = "ghp_" + "A" * 32
        data = ('print("safe")\napi_key = "' + token + '"\n').encode()
        excluded = []
        files, contents, candidates = bundle.filtered_sources([("src/config.py", data), ("src/good.py", b"value = 1\n")], excluded)
        self.assertEqual([x["path"] for x in files], ["src/good.py"])
        self.assertNotIn("src/config.py", contents)
        self.assertTrue(candidates)
        self.assertEqual(candidates[0]["line"], 2)
        self.assertNotIn(token, json.dumps({"excluded": excluded, "secret_candidates": candidates}))
        self.assertTrue(all(set(x) == {"path", "line", "rule_id"} for x in candidates))

    def test_binary_and_non_utf8_source_refused(self):
        excluded = []
        files, contents, _ = bundle.filtered_sources([("a.py", b"null\0data"), ("b.py", b"\xff\xfe"),
                                                     ("c.py", b"print('hello')\n")], excluded)
        self.assertEqual([x["path"] for x in files], ["c.py"])
        self.assertEqual(set(contents), {"c.py"})

    def test_lfs_pointer_is_not_misrepresented_as_actual_source(self):
        excluded = []
        pointer = b"version https://git-lfs.github.com/spec/v1\noid sha256:" + b"a" * 64 + b"\nsize 90000000\n"
        files, contents, _ = bundle.filtered_sources([("large.py", pointer)], excluded)
        self.assertFalse(files)
        self.assertFalse(contents)
        self.assertEqual(excluded, [{"path": "[excluded-path-3b10abbfceff5c26]", "reason": "lfs-pointer-not-source"}])

    def test_payload_bound_includes_manifest_and_refuses_unsafe_member(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "source.tar.gz"
            with patch.object(bundle, "MAX_SOURCE", 10):
                with self.assertRaises(ValueError):
                    bundle.write_bundle(path, {"schema_version": 1}, {"app.py": b"x=1\n"})
            with self.assertRaises(ValueError):
                bundle.write_bundle(path, {}, {"../outside.py": b"x=1\n"})
            self.assertFalse(path.exists())

    def test_bundle_is_deterministic_and_contains_only_manifested_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            metadata = {"schema_version": 1, "repository": "SalesSquad/example", "source_sha": "a" * 40,
                        "files": [{"path": "src/main.py", "bytes": 4, "sha256": hashlib.sha256(b"x=1\n").hexdigest()}],
                        "excluded": [], "secret_candidates": []}
            for name in ("one.tar.gz", "two.tar.gz"):
                bundle.write_bundle(root / name, metadata, {"src/main.py": b"x=1\n"})
            self.assertEqual((root / "one.tar.gz").read_bytes(), (root / "two.tar.gz").read_bytes())
            with tarfile.open(root / "one.tar.gz", "r:gz") as package:
                self.assertEqual(set(package.getnames()), {"files.json", "source/src/main.py"})
                self.assertEqual(package.extractfile("source/src/main.py").read(), b"x=1\n")

    def test_sparse_checkout_fetches_literal_selected_paths_without_hooks_or_smudge(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "repository"
            source.mkdir()
            bundle.git("init", cwd=source)
            (source / "src").mkdir()
            chosen = source / "src" / "literal[1].py"
            chosen.write_text("value = 1\n")
            (source / "src" / "literal1.py").write_text("not_selected = 1\n")
            (source / ".gitattributes").write_text("*.py filter=untrusted\n")
            # A local hook/filter would create a marker if the tool executed it.
            marker = root / "executed"
            hook = source / ".git" / "hooks" / "post-checkout"
            hook.parent.mkdir(exist_ok=True)
            hook.write_text("#!/bin/sh\ntouch '" + str(marker) + "'\n")
            hook.chmod(0o700)
            bundle.git("add", ".", cwd=source)
            bundle.git("-c", "user.name=Snapshot Test", "-c", "user.email=snapshot@example.invalid",
                       "-c", "commit.gpgsign=false", "commit", "-m", "fixture", cwd=source)
            source_sha = bundle.git("rev-parse", "HEAD", cwd=source).decode().strip()
            oid = bundle.git("rev-parse", "HEAD:src/literal[1].py", cwd=source).decode().strip()
            data = chosen.read_bytes()
            blobs = list(bundle.source_blobs(source, source_sha, [{"path": "src/literal[1].py", "sha": oid, "size": len(data)}]))
            self.assertEqual(blobs, [("src/literal[1].py", data)])
            self.assertFalse(marker.exists())
            self.assertFalse((source / "src" / "literal1.py").exists())


if __name__ == "__main__":
    unittest.main()
