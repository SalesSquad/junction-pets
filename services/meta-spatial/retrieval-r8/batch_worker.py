#!/usr/bin/env python3
"""One pinned public-image extraction for a finite Verda batch replica.

The deployment supplies CONFIG. The request contains no labels or account keys;
its only upload capability is a short-lived PUT URL for one task-owned object.
The provider, not this process, enforces the replica's 3600-second deadline.
"""
from __future__ import annotations

import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import threading
import time
import urllib.parse
import urllib.request

SOURCE = "8948b44454f1a5dd174395e6d69e1ae8b533688b"
INPUT_SHA = "47a015b6cf7f2ef10ff246fbf325e3f63459aa277d8ab3bd4bd6f61b4e0ce25f"
ARCHIVE_SHA = "5d68feb39f2b3b718af2c18dfaa9bd7947b44b7d7c6af15dfc6acf4964a4bd73"
EXTRACTOR_SHA = "a31e08d925b439b5d9e01d75dc9eb8a4397696425c2908853a96f6809421da11"
ROOT = Path("/work/meta-r6")
MAX_BODY = 16 * 1024 * 1024
MAX_ARTIFACT = 512 * 1024 * 1024
LOCK = threading.Lock()
STARTED = False


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    with path.open("x", encoding="utf-8") as f:
        json.dump(value, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("redirect_refused")


def admit(packet):
    require(type(packet) is dict and set(packet) == {
        "schema", "job_id", "source_tar_b64", "inputs_b64", "bootstrap_b64", "artifact_put_url", "result_put_url"
    }, "unexpected_request_fields")
    require(packet["schema"] == "meta_r8_batch_input_v1", "unexpected_schema")
    require(packet["job_id"] == CONFIG["job_id"], "job_id_mismatch")
    for field, path_key in (("artifact_put_url", "output_path"), ("result_put_url", "result_path")):
        url = urllib.parse.urlsplit(packet[field])
        require(url.scheme == "https" and url.hostname == CONFIG["output_host"]
                and url.port in (None, 443) and url.username is None and url.password is None
                and url.path == CONFIG[path_key] and not url.fragment, "output_capability_scope_mismatch")
        query = urllib.parse.parse_qs(url.query, strict_parsing=True)
        require(query.get("X-Amz-Algorithm") == ["AWS4-HMAC-SHA256"]
                and len(query.get("X-Amz-Signature", [])) == 1
                and len(query.get("X-Amz-Expires", [])) == 1
                and 0 < int(query.get("X-Amz-Expires", ["0"])[0]) <= 7200, "bounded_presigned_put_required")
    files = {}
    for field, name, expected in (
        ("source_tar_b64", "source.tar", ARCHIVE_SHA),
        ("inputs_b64", "inputs.json", INPUT_SHA),
        ("bootstrap_b64", "bootstrap.sh", CONFIG["bootstrap_sha256"]),
    ):
        require(type(packet[field]) is str, "base64_string_required")
        raw = base64.b64decode(packet[field], validate=True)
        require(hashlib.sha256(raw).hexdigest() == expected, "input_hash_mismatch:" + name)
        files[name] = raw
    require(not ROOT.exists(), "existing_worker_directory_no_replay")
    ROOT.mkdir(parents=True, mode=0o700)
    for name, raw in files.items():
        with (ROOT / name).open("xb") as f:
            f.write(raw)
    destination = ROOT / "source"
    destination.mkdir()
    with tarfile.open(ROOT / "source.tar") as archive:
        members = archive.getmembers()
        require(len(members) <= 100 and sum(m.size for m in members) <= 8 * 1024 * 1024,
                "source_archive_too_large")
        for member in members:
            p = PurePosixPath(member.name)
            allowed_parent = member.isdir() and p.parts in (("services",), ("services", "meta-spatial"))
            require(not p.is_absolute() and ".." not in p.parts and (member.isdir() or member.isfile())
                    and (allowed_parent or tuple(p.parts[:3]) == ("services", "meta-spatial", "retrieval-r6")),
                    "source_archive_member_refused")
        archive.extractall(destination, filter="data")
    extractor = destination / "services/meta-spatial/retrieval-r6/extract_nvidia.py"
    require(sha(extractor) == EXTRACTOR_SHA, "extractor_hash_mismatch")
    return packet["artifact_put_url"], packet["result_put_url"]


def upload(path, url, content_type):
    last_error = None
    for attempt in range(2):
        try:
            with path.open("rb") as data:
                request = urllib.request.Request(url, data=data, method="PUT", headers={
                    "Content-Type": content_type, "Content-Length": str(path.stat().st_size)
                })
                with urllib.request.build_opener(NoRedirect).open(request, timeout=120) as response:
                    require(response.status in (200, 201), "artifact_upload_status")
                    response.read(1024)
            return
        except Exception as error:
            last_error = type(error).__name__
            if attempt == 0:
                time.sleep(2)
    raise RuntimeError("artifact_upload_failed:" + str(last_error))


def execute(put_url, result_url):
    started = time.monotonic()
    with (ROOT / "gpu-run.log").open("x") as log:
        p = subprocess.Popen([
            "timeout", "--signal=TERM", "--kill-after=15", "3000s", "bash", str(ROOT / "bootstrap.sh")
        ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        for line in p.stdout:
            log.write(line)
            log.flush()
            if line.startswith(("R8_PHASE=", "PREFETCH ", "PREFETCH_COMPLETE", "SOURCE_AND_INPUT_SHA_VERIFIED")):
                print(line.strip(), flush=True)
            elif line.startswith("{"):
                try:
                    value = json.loads(line)
                    if set(value) <= {"stage", "observed_images", "expected_images", "torch", "cuda", "gpu", "capability"}:
                        print(json.dumps(value, sort_keys=True), flush=True)
                except (ValueError, TypeError):
                    pass
        p.wait()
    completion = {"exit_code": p.returncode, "elapsed_seconds": time.monotonic() - started,
                  "source_commit": SOURCE, "worker_sha256": sha(__file__), "job_id": CONFIG["job_id"]}
    write_json(ROOT / "gpu-exit.json", completion)
    artifact = ROOT / "extraction.tar.gz"
    with tarfile.open(artifact, "w:gz", compresslevel=3) as archive:
        for name in ("extraction-01", "runtime-freeze.txt", "prefetch-admissions.jsonl", "gpu-run.log", "gpu-exit.json"):
            path = ROOT / name
            if path.exists():
                archive.add(path, arcname=name)
    require(0 < artifact.stat().st_size <= MAX_ARTIFACT, "artifact_size_out_of_range")
    artifact_sha = sha(artifact)
    # The URL and its signature are never written to disk, logs or the result.
    # PUT retries, if transport fails, address the same object with identical bytes.
    upload(artifact, put_url, "application/gzip")
    result = {"schema": "meta_r8_batch_result_v1", **completion,
              "artifact_sha256": artifact_sha, "artifact_bytes": artifact.stat().st_size,
              "artifact_uploaded": True, "qualification": False}
    summary = ROOT / "extraction-01/summary.json"
    if summary.is_file():
        extraction = json.loads(summary.read_text())
        result.update(extraction_status=extraction["status"], counts=extraction["counts"],
                      extraction_summary_sha256=sha(summary))
    result_file = ROOT / "result.json"
    write_json(result_file, result)
    upload(result_file, result_url, "application/json")
    print(json.dumps(result, sort_keys=True), flush=True)
    return result


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self, status, value):
        raw = json.dumps(value, sort_keys=True, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
        self.wfile.flush()

    def do_GET(self):
        if self.path == "/health":
            self.respond(200, {"ready": True, "job_id": CONFIG["job_id"]})
        else:
            self.respond(404, {"error": "unknown_path"})

    def do_POST(self):
        global STARTED
        if self.path != "/run":
            self.respond(404, {"error": "unknown_path"})
            return
        with LOCK:
            if STARTED:
                self.respond(409, {"error": "job_already_admitted"})
                return
            STARTED = True
        exit_code = 1
        try:
            length = int(self.headers.get("Content-Length", "0"))
            require(0 < length <= MAX_BODY, "request_size_out_of_range")
            self.connection.settimeout(45)
            raw = self.rfile.read(length)
            require(len(raw) == length, "request_body_truncated")
            packet = json.loads(raw)
            put_url, result_url = admit(packet)
            packet.clear()
            result = execute(put_url, result_url)
            del put_url, result_url
            exit_code = 0 if result["exit_code"] == 0 else 1
            self.respond(200, result)
        except Exception as error:
            # No arbitrary exception strings: an upload error may contain a signed URL.
            safe = {"schema": "meta_r8_batch_failure_v1", "job_id": CONFIG["job_id"],
                    "error_type": type(error).__name__, "qualification": False}
            message = str(error)
            if len(message) <= 120 and all(c in "abcdefghijklmnopqrstuvwxyz0123456789_:.-" for c in message):
                safe["error_code"] = message
            print(json.dumps(safe), flush=True)
            try:
                self.respond(500, safe)
            except (BrokenPipeError, ConnectionResetError):
                pass
        finally:
            threading.Timer(2, lambda: os._exit(exit_code)).start()


if __name__ == "__main__":
    os.umask(0o077)
    require(set(CONFIG) == {"job_id", "bootstrap_sha256", "output_host", "output_path", "result_path"}, "invalid_deployment_config")
    print(json.dumps({"ready": True, "job_id": CONFIG["job_id"], "worker_sha256": sha(__file__)}), flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
