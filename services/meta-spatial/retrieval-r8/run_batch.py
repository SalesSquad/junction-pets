#!/usr/bin/env python3
"""Admit exactly one finite L40S batch and preserve its hash-bound output.

Run on the already authorized Verda controller host. Account credentials stay
in its existing store. Only two single-object, expiring PUT URLs reach the GPU.
Never replay this controller after an uncertain mutation: inspect its receipts.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import time
import urllib.parse
import urllib.error
import urllib.request
import zlib

import boto3
from botocore.config import Config
from botocore.exceptions import (ClientError, ConnectionClosedError, ConnectTimeoutError,
                                 EndpointConnectionError, IncompleteReadError, ReadTimeoutError,
                                 ResponseStreamingError, SSLError)

SOURCE = "8948b44454f1a5dd174395e6d69e1ae8b533688b"
INPUT_SHA = "47a015b6cf7f2ef10ff246fbf325e3f63459aa277d8ab3bd4bd6f61b4e0ce25f"
ARCHIVE_SHA = "5d68feb39f2b3b718af2c18dfaa9bd7947b44b7d7c6af15dfc6acf4964a4bd73"
COMMON_SHA = "19dfaa66ef8c7b80e0c173ea338ff6478caa176f5bbdb98dbab5e1560381c891"
IMAGE = "docker.io/nvidia/cuda@sha256:0eee3094c71518ad31d011a594ae6ed6de72959ee07e318cb31cffe71690e90c"
SCALING = {"max_replica_count": 1, "queue_message_ttl_seconds": 3000, "deadline_seconds": 3600}
MAX_HOURLY_USD = 2.22
MAX_ESTIMATE_USD = 3.0
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
TRANSIENT_S3 = (ConnectionClosedError, ConnectTimeoutError, EndpointConnectionError,
                IncompleteReadError, ReadTimeoutError, ResponseStreamingError, SSLError, OSError)


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write(path, value):
    with path.open("x", encoding="utf-8") as f:
        json.dump(value, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())


class Run:
    def __init__(self, args):
        self.args = args
        self.c = args.control
        self.started = time.time()
        # Even treating queue TTL and replica runtime as additive leaves five
        # minutes for local preservation, and ten before PUT capabilities expire.
        self.deadline = time.monotonic() + 115 * 60
        self.created = False
        self.create_attempted = False
        self.invoked = False
        self.pause_attempted = False
        self.artifact_verified = False
        self.stop = False
        self.api = None
        self.common = None
        self.result = None
        self.deployment_path = "/job-deployments/" + args.job_id
        self.object_prefix = "meta-lens/r8/" + args.job_id
        self.artifact_key = self.object_prefix + "/extraction.tar.gz"
        self.result_key = self.object_prefix + "/result.json"
        self.s3 = None
        self.result_route = None

    def phase(self, state, **extra):
        row = {"job_id": self.args.job_id, "state": state, "observed_unix": time.time(), **extra}
        with (self.c / "events.jsonl").open("a") as f:
            f.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
        tmp = self.c / "status.tmp"
        tmp.write_text(json.dumps(row, sort_keys=True, indent=2) + "\n")
        os.replace(tmp, self.c / "status.json")
        print(json.dumps(row, sort_keys=True), flush=True)

    def read_api(self, path, attempts=3):
        for attempt in range(attempts):
            status, value, headers = self.api(path)
            if status == 200:
                return value
            if status == 401 and attempt + 1 < attempts:
                self.api = self.common.cloud()
            elif status not in (0, 429, 500, 502, 503, 504):
                raise RuntimeError("provider_read_http_" + str(status))
            if attempt + 1 < attempts:
                time.sleep(2 * (attempt + 1))
        raise RuntimeError("provider_read_unavailable")

    def missing_object(self, key):
        try:
            self.s3.head_object(Bucket=self.args.bucket, Key=key)
        except ClientError as error:
            if error.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 404:
                return True
            raise RuntimeError("object_scope_not_verified") from None
        return False

    def create_with_diagnostics(self, body):
        """Keep bounded validation diagnostics for this non-secret definition.

        The shared helper intentionally discards HTTP error bodies. This local
        adapter uses the same authorized OAuth route without changing that helper.
        Credentials and successful OAuth responses are never persisted.
        """
        cfg = self.common.credentials()
        status, auth, _ = self.common.request(self.common.API + "/oauth2/token", "POST", {
            "grant_type": "client_credentials", "client_id": cfg["verda_client_id"],
            "client_secret": cfg["verda_client_secret"]})
        require(status == 200 and isinstance(auth.get("access_token"), str), "cloud_authentication_failed")
        request = urllib.request.Request(self.common.API + "/job-deployments", method="POST",
            data=json.dumps(body).encode(), headers={"Content-Type": "application/json",
            "Authorization": "Bearer " + auth["access_token"]})
        try:
            with self.common.opener.open(request, timeout=20) as response:
                raw = response.read(65537)
                require(len(raw) <= 65536, "create_response_too_large")
                return response.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as error:
            try:
                raw = error.read(16385)
                value = json.loads(raw) if len(raw) <= 16384 else {}
                diagnostics = {}
                if isinstance(value, dict):
                    for key in ("message", "error", "code", "statusCode"):
                        item = value.get(key)
                        if isinstance(item, (str, int, list)):
                            rendered = json.dumps(item)
                            # Payload contains only code and public-image metadata;
                            # still suppress any provider-echoed credential pattern.
                            if len(rendered) <= 6000 and not re.search(r"(?i)bearer |access_token|client_secret|x-amz-signature", rendered):
                                diagnostics[key] = item
                return error.code, {"error": "provider_http_error", "diagnostics": diagnostics}
            except (ValueError, OSError):
                return error.code, {"error": "provider_http_error_body_unavailable"}
            finally:
                error.close()
        except (urllib.error.URLError, TimeoutError, OSError):
            return 0, {"error": "transport_unavailable_delivery_unknown"}

    def preflight(self):
        a = self.args
        require(re.fullmatch(r"meta-r8-[a-z0-9-]{8,60}", a.job_id), "invalid_owned_job_id")
        require(a.control.is_dir() and not a.control.is_symlink(), "control_directory_required")
        require(not any((a.control / n).exists() for n in ("start.json", "create-intent.json", "completion.json")),
                "existing_attempt_no_replay")
        require(sha(a.cloud_helper) == COMMON_SHA, "approved_helper_changed")
        require(sha(a.r6_control / "source.tar") == ARCHIVE_SHA
                and sha(a.r6_control / "prepared-01/inputs.json") == INPUT_SHA, "pinned_input_changed")
        head = subprocess.check_output(["git", "-C", str(a.source_worktree), "rev-parse", "HEAD"], text=True).strip()
        require(head == a.orchestration_commit and re.fullmatch(r"[0-9a-f]{40}", head), "orchestration_commit_mismatch")
        require(not subprocess.check_output(["git", "-C", str(a.source_worktree), "status", "--porcelain", "--untracked-files=all"]),
                "dirty_orchestration_source")
        for file in (Path(__file__), a.worker, a.bootstrap):
            rel = file.resolve().relative_to(a.source_worktree.resolve())
            committed = subprocess.check_output(["git", "-C", str(a.source_worktree), "show", head + ":" + str(rel)])
            require(hashlib.sha256(committed).hexdigest() == sha(file), "source_bytes_mismatch")
        spec = importlib.util.spec_from_file_location("approved_verda_common", a.cloud_helper)
        self.common = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.common)
        self.api = self.common.cloud()
        cfg = self.common.credentials()
        require(cfg["verda_s3_endpoint"] == "https://objects.eu-north-3.verda.storage"
                and cfg["verda_s3_region"] == "eu-north-3", "existing_storage_route_mismatch")
        self.inference_key = cfg["verda_inference_api_key"]
        self.s3 = boto3.client("s3", endpoint_url=cfg["verda_s3_endpoint"], region_name=cfg["verda_s3_region"],
            aws_access_key_id=cfg["verda_s3_access_key"], aws_secret_access_key=cfg["verda_s3_secret_key"],
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
                          request_checksum_calculation="when_required", response_checksum_validation="when_required",
                          connect_timeout=10, read_timeout=30, retries={"max_attempts": 1}))
        require(self.missing_object(self.artifact_key) and self.missing_object(self.result_key), "existing_output_no_overwrite")
        available = self.read_api("/serverless-compute-resources")
        require(isinstance(available, list) and any(r.get("name") == "L40S" and r.get("size") == 1
                and r.get("is_available") is True for r in available), "l40s_capacity_unavailable")
        types = self.read_api("/container-types")
        rows = [r for r in types if r.get("instance_type") == "1L40S.20V.58G"]
        require(len(rows) == 1 and rows[0]["currency"] == "usd", "price_record_mismatch")
        hourly = float(rows[0]["serverless_price"])
        require(math.isfinite(hourly) and 0 < hourly <= MAX_HOURLY_USD, "hourly_price_exceeds_cap")
        estimate = hourly * SCALING["deadline_seconds"] / 3600
        require(estimate <= MAX_ESTIMATE_USD, "allocation_exceeds_cap")
        balance = self.read_api("/balance")
        require(balance.get("currency", "usd").lower() == "usd" and math.isfinite(float(balance["amount"]))
                and float(balance["amount"]) >= 5,
                "existing_credit_below_floor")
        deployments = self.read_api("/job-deployments")
        require(isinstance(deployments, list) and not any(r.get("name") == a.job_id for r in deployments),
                "existing_deployment_no_replay")
        write(self.c / "start.json", {"job_id": a.job_id, "started_unix": self.started,
            "source_commit": SOURCE, "orchestration_commit": head, "controller_sha256": sha(__file__),
            "worker_sha256": sha(a.worker), "bootstrap_sha256": sha(a.bootstrap), "input_sha256": INPUT_SHA,
            "source_archive_sha256": ARCHIVE_SHA, "image": IMAGE, "scaling": SCALING,
            "hourly_usd": hourly, "maximum_compute_estimate_usd": estimate,
            "allocation_cap_usd": MAX_ESTIMATE_USD, "balance_before_usd": float(balance["amount"]),
            "existing_bucket": a.bucket, "artifact_key": self.artifact_key, "result_key": self.result_key,
            "new_credentials": False, "raw_inputs_published": False})
        self.phase("admitted", maximum_compute_estimate_usd=estimate, provider_deadline_seconds=3600)

    def create_once(self):
        a = self.args
        config = {"job_id": a.job_id, "bootstrap_sha256": sha(a.bootstrap),
                  "output_host": "objects.eu-north-3.verda.storage",
                  "output_path": "/" + a.bucket + "/" + self.artifact_key,
                  "result_path": "/" + a.bucket + "/" + self.result_key}
        worker = base64.b64encode(a.worker.read_bytes()).decode()
        launcher = ("import base64,hashlib\nfrom pathlib import Path\n"
                    + "raw=base64.b64decode(" + repr(worker) + ")\n"
                    + "assert hashlib.sha256(raw).hexdigest()==" + repr(sha(a.worker)) + "\n"
                    + "p=Path('/work/meta-r8-worker.py');p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)\n"
                    + "exec(compile(raw,str(p),'exec'),{'__name__':'__main__','__file__':str(p),'CONFIG':"
                    + repr(config) + "})\n")
        code = base64.b64encode(zlib.compress(launcher.encode(), level=9)).decode()
        bootstrap = ('apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends '
                     'python3 ca-certificates && exec python3 -u -c '
                     "'import sys,base64,zlib;exec(zlib.decompress(base64.b64decode(\"\".join(sys.argv[1:]))))' \"$@\"")
        require(len(bootstrap) <= 253, "entrypoint_argument_too_long")
        body = {"name": a.job_id, "containers": [{"image": IMAGE, "should_use_cached_image": True,
                "exposed_port": 8000, "healthcheck": {"enabled": True, "port": 8000, "path": "/health"},
                "entrypoint_overrides": {"enabled": True, "entrypoint": ["/bin/bash", "-c"],
                                         "cmd": [bootstrap, "--"] + [code[i:i+200] for i in range(0, len(code), 200)]}}],
                "compute": {"name": "L40S", "size": 1}, "scaling": SCALING}
        write(self.c / "deployment-spec.json", body)
        write(self.c / "create-intent.json", {"method": "POST", "path": "/job-deployments", "job_id": a.job_id,
                                               "spec_sha256": sha(self.c / "deployment-spec.json")})
        self.create_attempted = True
        status, response = self.create_with_diagnostics(body)
        write(self.c / "create-response.json", {"http_status": status, "body": response})
        # Never repeat POST, including a timeout. Reconcile only the exact unique name.
        detail = self.read_api(self.deployment_path)
        require(detail.get("name") == a.job_id and detail.get("compute") == {"name": "L40S", "size": 1},
                "created_deployment_identity_mismatch")
        containers = detail.get("containers", [])
        require(len(containers) == 1 and containers[0].get("image", {}).get("image") == IMAGE,
                "created_image_mismatch")
        overrides = containers[0].get("entrypoint_overrides")
        require(overrides == body["containers"][0]["entrypoint_overrides"], "created_entrypoint_mismatch")
        require(self.read_api(self.deployment_path + "/scaling") == SCALING, "provider_deadline_not_verified")
        endpoint = urllib.parse.urlsplit(detail["endpoint_base_url"])
        require(endpoint.scheme == "https" and endpoint.hostname in ("tasks.datacrunch.io", "tasks.verda.com")
                and endpoint.path.rstrip("/") == "/" + a.job_id and not endpoint.query and not endpoint.fragment
                and endpoint.username is None and endpoint.password is None and endpoint.port in (None, 443),
                "unexpected_task_endpoint")
        self.endpoint = urllib.parse.urlunsplit(("https", endpoint.netloc, "/" + a.job_id, "", ""))
        self.created = True
        write(self.c / "deployment-verified.json", {"job_id": a.job_id, "http_status": status,
            "endpoint_base_url": self.endpoint, "image": IMAGE, "scaling": SCALING,
            "compute": detail["compute"], "entrypoint_verified": True})
        self.phase("batch_deployment_verified")

    def invoke_once(self):
        a = self.args
        urls = [self.s3.generate_presigned_url("put_object", Params={"Bucket": a.bucket, "Key": key,
                "ContentType": content_type}, ExpiresIn=7200, HttpMethod="PUT") for key, content_type in
                ((self.artifact_key, "application/gzip"), (self.result_key, "application/json"))]
        payload = {"schema": "meta_r8_batch_input_v1", "job_id": a.job_id,
            "source_tar_b64": base64.b64encode((a.r6_control / "source.tar").read_bytes()).decode(),
            "inputs_b64": base64.b64encode((a.r6_control / "prepared-01/inputs.json").read_bytes()).decode(),
            "bootstrap_b64": base64.b64encode(a.bootstrap.read_bytes()).decode(),
            "artifact_put_url": urls[0], "result_put_url": urls[1]}
        require(len(json.dumps(payload).encode()) <= 16 * 1024 * 1024, "request_exceeds_worker_bound")
        write(self.c / "invoke-intent.json", {"job_id": a.job_id, "source_commit": SOURCE,
            "input_sha256": INPUT_SHA, "inference_id": a.job_id, "calls": 1,
            "scoped_put_capabilities": 2, "capability_expiry_seconds": 7200})
        self.invoked = True
        status, response, _ = self.common.request(self.endpoint + "/run", "POST", payload,
            {"Authorization": "Bearer " + self.inference_key, "X-Inference-Id": a.job_id}, timeout=40)
        payload.clear()
        urls.clear()
        write(self.c / "invoke-response.json", {"http_status": status, "body": response})
        require(status in (0, 200, 202, 409), "batch_request_rejected_http_" + str(status))
        origin = urllib.parse.urlsplit(self.endpoint)
        result_path = "/result/" + a.job_id
        if isinstance(response, dict) and response.get("ResultPath"):
            require(response["ResultPath"] == result_path, "result_route_mismatch")
        self.result_route = urllib.parse.urlunsplit(("https", origin.netloc, result_path, "", ""))
        # A lost response is not a second submission. The independently scoped
        # result object and provider job identity are the recovery path.
        self.phase("batch_submitted_once", http_status=status)

    def provider_failure(self):
        # This documented result route reads the cached response; calling a
        # batch deployment's application GET routes would create another job.
        status, value, _ = self.common.request(self.result_route, headers={
            "Authorization": "Bearer " + self.inference_key, "X-Inference-Id": self.args.job_id}, timeout=15)
        if isinstance(value, dict) and value.get("schema") == "meta_r8_batch_failure_v1":
            write(self.c / "worker-failure.json", {k: value[k] for k in
                ("schema", "job_id", "error_type", "error_code", "qualification") if k in value})
            raise RuntimeError("worker_failed_before_export")

    def download_artifact(self, value):
        size, expected = value["artifact_bytes"], value["artifact_sha256"]
        for attempt in range(1, 4):
            body = None
            try:
                artifact = self.s3.get_object(Bucket=self.args.bucket, Key=self.artifact_key)
                body = artifact["Body"]
                require(artifact["ContentLength"] == size, "object_length_mismatch")
                self.phase("preserving_gpu_output", artifact_bytes=size, extraction_exit_code=value["exit_code"], attempt=attempt)
                part = self.c / ("extraction-attempt-" + str(attempt) + ".part")
                with part.open("xb") as f:
                    total = 0
                    while True:
                        chunk = body.read(1024 * 1024)
                        if not chunk:
                            break
                        total += len(chunk)
                        require(total <= size, "object_size_exceeded")
                        f.write(chunk)
                require(total == size and sha(part) == expected, "output_transfer_hash_mismatch")
                target = self.c / "extraction.tar.gz"
                require(not target.exists(), "existing_output_no_overwrite")
                part.rename(target)
                return
            except TRANSIENT_S3:
                if attempt == 3:
                    raise RuntimeError("artifact_download_transport_unavailable") from None
                time.sleep(2 * attempt)
            finally:
                if body is not None:
                    body.close()

    def preserve(self):
        a = self.args
        errors = 0
        last_result_read = 0
        while time.monotonic() < self.deadline and not self.stop:
            try:
                obj = self.s3.get_object(Bucket=a.bucket, Key=self.result_key)
                require(0 < obj["ContentLength"] <= 16384, "result_size_out_of_range")
                raw = obj["Body"].read(16385)
                obj["Body"].close()
                value = json.loads(raw)
                require(value.get("schema") == "meta_r8_batch_result_v1"
                        and value.get("job_id") == a.job_id and value.get("source_commit") == SOURCE
                        and value.get("worker_sha256") == sha(a.worker)
                        and value.get("artifact_uploaded") is True and value.get("qualification") is False,
                        "batch_result_provenance_mismatch")
                size, expected = value["artifact_bytes"], value["artifact_sha256"]
                require(type(size) is int and 0 < size <= MAX_ARCHIVE_BYTES
                        and isinstance(expected, str) and re.fullmatch(r"[0-9a-f]{64}", expected), "artifact_descriptor_invalid")
                self.result = value
                write(self.c / "batch-result.json", value)
                self.download_artifact(value)
                write(self.c / "transfer.json", {"schema": "meta_r8_transfer_v1", "source_commit": SOURCE,
                    "sha256": expected, "bytes": size, "verified": True, "job_id": a.job_id,
                    "worker_sha256": sha(a.worker)})
                self.artifact_verified = True
                self.phase("gpu_output_preserved", extraction_exit_code=value["exit_code"], artifact_sha256=expected)
                return
            except ClientError as error:
                code = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
                if code not in (404, 429, 500, 502, 503, 504):
                    raise RuntimeError("object_read_http_" + str(code)) from None
            except TRANSIENT_S3:
                errors += 1
                self.phase("transient_output_read", failures=errors)
            if time.monotonic() - last_result_read >= 60:
                self.provider_failure()
                last_result_read = time.monotonic()
            time.sleep(15)
        raise RuntimeError("output_not_observed_before_controller_deadline")

    def cleanup(self):
        outcome = {"job_id": self.args.job_id, "pause_attempted": False, "paused_verified": False,
                   "provider_deadline_seconds": 3600, "provider_deadline_verified": self.created,
                   "objects_deleted": False, "volumes_deleted": False}
        if not self.create_attempted:
            outcome["no_deployment_created"] = True
            return outcome
        try:
            self.api = self.common.cloud()
            current = self.read_api(self.deployment_path)
            require(current.get("name") == self.args.job_id, "cleanup_identity_mismatch")
            write(self.c / "pause-intent.json", {"job_id": self.args.job_id, "method": "POST",
                                                 "path": self.deployment_path + "/pause"})
            outcome["pause_attempted"] = True
            status, value, _ = self.api(self.deployment_path + "/pause", "POST")
            write(self.c / "pause-response.json", {"http_status": status, "body": value})
            # One mutation only; uncertain delivery is resolved by readback.
            for _ in range(12):
                value = self.read_api(self.deployment_path + "/status", attempts=2)
                if value.get("status") == "paused":
                    outcome["paused_verified"] = True
                    outcome["observed_unix"] = time.time()
                    break
                time.sleep(5)
        except Exception as error:
            outcome["error_type"] = type(error).__name__
        return outcome

    def run(self):
        error_type = None
        try:
            self.preflight()
            self.create_once()
            self.invoke_once()
            self.preserve()
        except Exception as error:
            error_type = type(error).__name__
            # All controller-auth/S3 exception text is omitted: it can contain
            # endpoints, signed capabilities or account SDK internals.
            message = str(error)
            error_code = message if re.fullmatch(r"[a-z0-9_:.-]{1,120}", message) else error_type
            self.phase("failed", error_type=error_type, error_code=error_code)
        finally:
            cleanup = self.cleanup()
            success = self.artifact_verified and self.result["exit_code"] == 0 and cleanup["paused_verified"]
            out = {"job_id": self.args.job_id, "source_commit": SOURCE,
                   "orchestration_commit": self.args.orchestration_commit, "success": success,
                   "artifact_verified": self.artifact_verified, "create_calls": int(self.create_attempted),
                   "inference_calls": int(self.invoked), "error_type": error_type,
                   "cleanup": cleanup, "elapsed_seconds": time.time() - self.started, "qualification": False}
            write(self.c / "completion.json", out)
            self.phase("finished", success=success, artifact_verified=self.artifact_verified,
                       paused_verified=cleanup["paused_verified"])
        return 0 if success else 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("control", "worker", "bootstrap", "r6-control", "source-worktree", "cloud-helper"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--orchestration-commit", required=True)
    p.add_argument("--job-id", required=True)
    p.add_argument("--bucket", required=True)
    args = p.parse_args()
    for value in vars(args).values():
        if isinstance(value, Path):
            require(value.is_absolute(), "absolute_paths_required")
    os.umask(0o077)
    run = Run(args)
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: setattr(run, "stop", True))
    return run.run()


if __name__ == "__main__":
    raise SystemExit(main())
