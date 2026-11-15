#!/usr/bin/env python3
"""Bounded private-release transport for the owner-authorized intent campaign."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import gzip
import io
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.parse
import urllib.error
import urllib.request

REPO = "SalesSquad/junction-pets"
TAG = "hf-intents-20261115"
DEADLINE = "2026-11-15T17:00:00Z"
CUTOFF = "2026-11-15T16:40:00Z"
DATASETS = ("banking77", "massive-fi-FI")
LANES = ("word_svm", "char_svm", "hybrid_linear", "complement_nb", "svd_mlp")
MAX_ARCHIVE = 120 * 1024 * 1024
MEMBER_LIMITS = {"best.skops": 100 * 1024 * 1024, "best.json": 256 * 1024,
                 "history.jsonl": 15 * 1024 * 1024, "state.json": 5 * 1024 * 1024,
                 "metadata.json": 256 * 1024}


def utcnow():
    return dt.datetime.now(dt.timezone.utc)


def instant(value):
    result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("UTC deadline requires a timezone")
    return result.astimezone(dt.timezone.utc)


def before(deadline, now=None):
    if (now or utcnow()) >= instant(deadline):
        raise ValueError("Authorized time window has closed")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as src:
        for chunk in iter(lambda: src.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def matching_file(path, size, digest):
    path = Path(path)
    return not path.is_symlink() and path.is_file() and path.stat().st_size == size and sha256(path) == digest


def atomic_verified_write(destination, size, digest, writer):
    """A failed transfer never leaves a final filename that looks complete."""
    destination = Path(destination)
    if matching_file(destination, size, digest):
        return destination
    if destination.is_symlink() or destination.is_dir():
        raise ValueError("Task cache destination is not a regular file")
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".part", dir=destination.parent)
    temporary = Path(name)
    try:
        with os.fdopen(handle, "wb") as out:
            writer(out)
        if not matching_file(temporary, size, digest):
            raise ValueError("Transferred bytes failed integrity checks")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def copy_verified(source, destination):
    source = Path(source)
    def writer(out):
        with source.open("rb") as src:
            for chunk in iter(lambda: src.read(1024 * 1024), b""):
                out.write(chunk)
    return atomic_verified_write(destination, source.stat().st_size, sha256(source), writer)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    os.replace(temporary, path)


def identities(source, run_id, tag):
    if not re.fullmatch(r"[a-f0-9]{40}", source) or not re.fullmatch(r"[1-9][0-9]*", run_id):
        raise ValueError("Exact source SHA and numeric run ID are required")
    if tag != TAG:
        raise ValueError("Only the fixed authorized campaign tag is supported")
    for key, expected in (("GITHUB_REPOSITORY", REPO), ("GITHUB_SHA", source),
                          ("GITHUB_RUN_ID", run_id), ("GITHUB_REF", "refs/heads/main")):
        if os.environ.get(key) != expected:
            raise ValueError(f"Unexpected execution context: {key}")


def load_manifest(path):
    manifest = json.loads(Path(path).read_text())
    if (manifest.get("repo") != REPO or manifest.get("deadline") != DEADLINE
            or manifest.get("training_cutoff") != CUTOFF
            or manifest.get("max_jobs") != 10 or manifest.get("vcpu_per_job") != 8
            or set(manifest.get("datasets", {})) != set(DATASETS)
            or tuple(manifest.get("lanes", ())) != LANES):
        raise ValueError("Manifest changes the authorized campaign bounds")
    total = 0
    for dataset, spec in manifest["datasets"].items():
        expected = {"train", "test"} | ({"validation"} if dataset == "massive-fi-FI" else set())
        if set(spec["files"]) != expected or spec.get("license") != "CC-BY-4.0":
            raise ValueError("Unexpected dataset splits or license")
        for entry in list(spec["files"].values()) + spec.get("documentation", []):
            if (not isinstance(entry["bytes"], int) or not 0 < entry["bytes"] <= 5_000_000
                    or not re.fullmatch(r"[a-f0-9]{64}", entry["sha256"])):
                raise ValueError("Missing bounded file size or digest")
            parsed = urllib.parse.urlparse(entry["url"])
            if (parsed.scheme != "https" or parsed.username or parsed.password or parsed.query
                    or parsed.fragment or parsed.hostname not in {"huggingface.co", "raw.githubusercontent.com"}
                    or not re.search(r"/[a-f0-9]{40}/", parsed.path)):
                raise ValueError("Dataset sources must be immutable HTTPS publisher paths")
            if "path" in entry and (Path(entry["path"]).name != entry["path"] or entry["path"] in {".", ".."}):
                raise ValueError("Documentation path must be a basename")
            total += entry["bytes"]
    if total > 20_000_000:
        raise ValueError("Dataset pack exceeds its size bound")
    spend_limit(manifest)
    return manifest


def spend_limit(manifest):
    credit = manifest["credit"]
    values = (manifest.get("max_spend_eur"), credit.get("authorized_existing_eur"),
              credit.get("observed_junction_balance_eur"))
    if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in values):
        raise ValueError("A finite positive campaign cap and existing credit are required")
    cap, authorized, observed = values
    if cap > min(authorized, observed) or credit.get("published_eur_per_vcpu_minute") != .0017:
        raise ValueError("Campaign cap exceeds its recorded credit authority or changes the rate")
    return float(cap)


def estimated_spend(manifest, admission=None, additional_seconds=0, now=None):
    now = now or utcnow()
    cap = spend_limit(manifest)
    if admission is None:
        seconds = max(0, (instant(DEADLINE) - now).total_seconds())
    else:
        if admission.get("max_spend_eur") != cap:
            raise ValueError("The admission spend cap differs from this manifest")
        seconds = (now - instant(admission["created_at"])).total_seconds()
        if seconds < 0:
            raise ValueError("Admission timestamp is in the future")
        seconds += additional_seconds
    # Conservatively charge all 80 vCPUs from admission, including queued time;
    # reserve another 80 vCPU-minutes for initialization/finalization overhead.
    estimate = (80 * seconds / 60 + 80) * .0017
    if estimate > cap:
        raise ValueError("Estimated campaign spend would exceed its explicit cap")
    return estimate


def gh(*args, output=None, timeout=180):
    if not os.environ.get("GH_TOKEN"):
        raise RuntimeError("Explicit workflow GH_TOKEN is required; stored credentials are not used")
    before(DEADLINE)
    seconds = min(timeout, max(1, int((instant(DEADLINE) - utcnow()).total_seconds())))
    result = subprocess.run(["gh", *args], stdout=output or subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=seconds, check=False)
    if result.returncode:
        # gh errors may contain URLs; do not echo credential-bearing provider responses.
        raise RuntimeError(f"GitHub operation failed (exit {result.returncode})")
    return result.stdout


def api(path):
    return json.loads(gh("api", f"repos/{REPO}/{path}"))


def release():
    repo = json.loads(gh("api", f"repos/{REPO}"))
    if repo.get("private") is not True or repo.get("full_name") != REPO:
        raise ValueError("Cloud destination must remain the exact private repository")
    item = api(f"releases/tags/{TAG}")
    if item.get("draft") or item.get("prerelease") is not True:
        raise ValueError("Expected the private campaign prerelease")
    return item


def assets(item):
    # Explicit pagination matters after the first 100 immutable checkpoints.
    return json.loads(gh("api", "--paginate", "--slurp",
                         f"repos/{REPO}/releases/{item['id']}/assets?per_page=100"))


def release_assets(item):
    return [asset for page in assets(item) for asset in page]


class NoGitHubRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Credential-bearing GitHub uploads may not redirect")


def upload(path):
    path = Path(path)
    token = os.environ.get("GH_TOKEN")
    if not token:
        raise RuntimeError("Publication requires the workflow's ephemeral GitHub token")
    digest = sha256(path)
    item = release()  # Re-check private visibility before every publication.
    query = urllib.parse.urlencode({"name": path.name, "label": f"sha256:{digest}"})
    url = f"https://uploads.github.com/repos/{REPO}/releases/{item['id']}/assets?{query}"
    opener = urllib.request.build_opener(NoGitHubRedirects())
    try:
        with path.open("rb") as src:
            request = urllib.request.Request(url, data=src, method="POST", headers={
                "Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "junction-intent-training",
                "Content-Type": "application/octet-stream", "Content-Length": str(path.stat().st_size)})
            timeout = min(180, max(1, int((instant(DEADLINE) - utcnow()).total_seconds())))
            with opener.open(request, timeout=timeout) as response:
                data = response.read(1_000_001)
                if len(data) > 1_000_000:
                    raise ValueError("Unexpected upload metadata response size")
                asset = json.loads(data)
    except urllib.error.HTTPError as error:
        if error.code != 422:
            raise RuntimeError(f"GitHub upload failed (HTTP {error.code})") from None
        # Only an exact, already uploaded copy may satisfy a resumed publication.
        found = [a for a in release_assets(item) if a["name"] == path.name]
        if len(found) != 1:
            raise ValueError("Upload name conflict is not an exact existing checkpoint") from None
        asset = found[0]
    if asset.get("name") != path.name or asset.get("size") != path.stat().st_size:
        raise ValueError("Cloud upload was not observed at the expected name and size")
    if asset.get("label") != f"sha256:{digest}":
        raise ValueError("Cloud upload lost its digest label")
    if asset.get("digest") and asset["digest"] != f"sha256:{digest}":
        raise ValueError("Server upload digest does not match")
    return asset


def download_asset(asset, destination):
    destination = Path(destination)
    if not 0 < asset["size"] <= MAX_ARCHIVE:
        raise ValueError("Release asset exceeds its byte bound")
    expected = asset.get("label", "")
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", expected):
        raise ValueError("Release asset lacks its SHA-256 label")
    if asset.get("digest") and asset["digest"] != expected:
        raise ValueError("Server and publisher digests disagree")
    def writer(out):
        gh("api", f"repos/{REPO}/releases/assets/{asset['id']}",
           "-H", "Accept: application/octet-stream", output=out)
    return atomic_verified_write(destination, asset["size"], expected[7:], writer)


def verify_admission(source, run_id, work, manifest_hash):
    item = release()
    candidates = [a for a in release_assets(item) if a["name"] == "admission.json"]
    if len(candidates) != 1:
        raise ValueError("Release lacks its unique admission record")
    path = Path(work) / f"admission-{time.time_ns()}.json"
    download_asset(candidates[0], path)
    admission = json.loads(path.read_text())
    binding(admission, source, run_id)
    if admission.get("deadline") != DEADLINE or admission.get("training_cutoff") != CUTOFF:
        raise ValueError("Admission time bounds changed")
    if admission.get("manifest_sha256") != manifest_hash:
        raise ValueError("Admission belongs to a different dataset manifest")
    ref = api(f"git/ref/tags/{TAG}")
    if ref["object"].get("type") != "commit" or ref["object"].get("sha") != source:
        raise ValueError("The release tag no longer identifies the admitted source")
    return item, admission


def binding(value, source, run_id, dataset=None, lane=None):
    if value.get("source_sha") != source or str(value.get("run_id")) != run_id:
        raise ValueError("Checkpoint belongs to a different source or run")
    if dataset is not None and value.get("dataset") != dataset:
        raise ValueError("Checkpoint belongs to a different dataset")
    if lane is not None and value.get("lane") != lane:
        raise ValueError("Checkpoint belongs to a different lane")


class DownloadRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        p = urllib.parse.urlparse(newurl)
        if p.scheme != "https" or not (p.hostname in {"huggingface.co", "raw.githubusercontent.com"}
                or (p.hostname or "").endswith((".hf.co", ".huggingface.co"))):
            raise ValueError("Dataset redirect left the allowed HTTPS storage origins")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(entry, path):
    before(DEADLINE)
    path = Path(path)
    if matching_file(path, entry["bytes"], entry["sha256"]):
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    opener = urllib.request.build_opener(DownloadRedirects())
    with opener.open(entry["url"], timeout=45) as response:
        data = response.read(entry["bytes"] + 1)
    if len(data) != entry["bytes"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
        raise ValueError("Publisher dataset bytes do not match the fixed manifest")
    return atomic_verified_write(path, entry["bytes"], entry["sha256"], lambda out: out.write(data))


def dataset_files(manifest, dataset, destination, splits, documentation=False):
    spec = manifest["datasets"][dataset]
    result = []
    for split in splits:
        result.append(fetch(spec["files"][split], Path(destination) / f"{split}.parquet"))
    if documentation:
        for entry in spec.get("documentation", []):
            result.append(fetch(entry, Path(destination) / entry["path"]))
    return result


def init(args, manifest):
    before(CUTOFF)
    reserve = estimated_spend(manifest)
    repo = json.loads(gh("api", f"repos/{REPO}"))
    if repo.get("private") is not True or repo.get("full_name") != REPO:
        raise ValueError("Cloud destination must remain private")
    work = Path(args.work_dir)
    work.mkdir(parents=True, exist_ok=True)
    files = []
    for dataset in DATASETS:
        files += dataset_files(manifest, dataset, work / dataset,
                               list(manifest["datasets"][dataset]["files"]), True)
    pack = work / "datasets.tar.gz"
    atomic_pack({str(path.relative_to(work)): path.read_bytes() for path in files}, pack, 20_000_000)
    before(CUTOFF)
    minutes = max(0, (instant(DEADLINE) - utcnow()).total_seconds() / 60)
    admission = {"schema_version": 1, "source_sha": args.source_sha, "run_id": args.run_id,
                 "deadline": DEADLINE, "training_cutoff": CUTOFF, "jobs": 10,
                 "vcpu_per_job": 8, "reserved_vcpu_minutes": 80 * minutes,
                 "reserved_eur_at_published_rate": round(reserve, 4),
                 "max_spend_eur": spend_limit(manifest),
                 "price_source": "https://craci.com/pricing", "cash_topup_authorized": False,
                 "manifest_sha256": sha256(args.manifest), "created_at": utcnow().isoformat()}
    # The publisher downloads and verifies all data BEFORE acquiring the lease.
    # Creation is atomic; only the SAME run/source may resume an interrupted upload.
    try:
        gh("release", "create", TAG, "--repo", REPO, "--target", args.source_sha,
           "--prerelease", "--title", "HF intent training — 15 November 2026",
           "--notes", json.dumps(admission, allow_nan=False))
    except RuntimeError:
        admission = json.loads(release().get("body", ""))
        binding(admission, args.source_sha, args.run_id)
        if admission.get("manifest_sha256") != sha256(args.manifest):
            raise ValueError("An existing campaign lease cannot be changed")
    write_json(work / "admission.json", admission)
    upload(work / "admission.json")
    verify_admission(args.source_sha, args.run_id, work, sha256(args.manifest))
    manifest_copy = work / "manifest.json"
    if manifest_copy.exists():
        if manifest_copy.read_bytes() != Path(args.manifest).read_bytes():
            raise ValueError("Preserve a different existing manifest")
    else:
        with manifest_copy.open("xb") as out:
            out.write(Path(args.manifest).read_bytes())
    for path in (pack, manifest_copy):
        upload(path)
    print(json.dumps({"release_tag": TAG, "cloud_dataset_pack": True, "admission": admission}))


def checkpoint_members(out, source, run_id, dataset, lane, manifest_hash, sequence):
    out = Path(out)
    best = json.loads((out / "best.json").read_text())
    binding(best, source, run_id, dataset, lane)
    for metric in ("cv_macro_f1", "validation_macro_f1"):
        if not isinstance(best.get(metric), (int, float)) or not math.isfinite(best[metric]) or not 0 <= best[metric] <= 1:
            raise ValueError("Checkpoint lacks a finite model-selection metric")
    if sha256(out / "best.skops") != best.get("model_sha256"):
        raise ValueError("Model and metric checkpoint are inconsistent")
    result = {}
    for name, limit in MEMBER_LIMITS.items():
        if name == "metadata.json":
            continue
        path = out / name
        if not path.exists() and name == "state.json":
            continue
        if not path.is_file() or not path.resolve().is_relative_to(out.resolve()) or path.stat().st_size > limit:
            raise ValueError("Checkpoint member is absent, outside its workspace, or too large")
        result[name] = path.read_bytes()
    metadata = {"schema_version": 1, "dataset": dataset, "lane": lane,
                "source_sha": source, "run_id": run_id, "sequence": sequence,
                "manifest_sha256": manifest_hash, "model_sha256": best["model_sha256"],
                "history_sha256": hashlib.sha256(result["history.jsonl"]).hexdigest(),
                "created_at": utcnow().isoformat()}
    result["metadata.json"] = (json.dumps(metadata, allow_nan=False) + "\n").encode()
    if sum(map(len, result.values())) > MAX_ARCHIVE:
        raise ValueError("Uncompressed checkpoint exceeds its bound")
    return result


def atomic_pack(members, destination, limit):
    """Regenerate the task cache, publishing only a fully closed bounded archive."""
    destination = Path(destination)
    if sum(map(len, members.values())) > limit:
        raise ValueError("Uncompressed archive exceeds its bound")
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".part", dir=destination.parent)
    temporary = Path(name)
    try:
        with os.fdopen(handle, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as zipped:
            with tarfile.open(fileobj=zipped, mode="w") as archive:
                for name, data in sorted(members.items()):
                    item = tarfile.TarInfo(name)
                    item.mode, item.size = 0o600, len(data)
                    archive.addfile(item, io.BytesIO(data))
        if temporary.stat().st_size > limit:
            raise ValueError("Compressed archive exceeds its bound")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def pack_checkpoint(members, destination):
    atomic_pack(members, destination, MAX_ARCHIVE)


def unpack_checkpoint(archive, destination, source, run_id, dataset, lane, manifest_hash):
    destination = Path(destination)
    contents, size = {}, 0
    with tarfile.open(archive, "r|gz") as package:
        for index, member in enumerate(package):
            if index >= len(MEMBER_LIMITS) or member.name not in MEMBER_LIMITS or member.name in contents:
                raise ValueError("Unexpected or excessive checkpoint members")
            size += member.size
            if (not member.isfile() or member.size < 0 or member.size > MEMBER_LIMITS[member.name]
                    or size > MAX_ARCHIVE):
                raise ValueError("Checkpoint links or oversized members are refused")
            data = package.extractfile(member).read(member.size + 1)
            if len(data) != member.size:
                raise ValueError("Truncated checkpoint member")
            contents[member.name] = data
    if not {"best.skops", "best.json", "history.jsonl", "metadata.json"}.issubset(contents):
        raise ValueError("Incomplete checkpoint archive")
    metadata = json.loads(contents["metadata.json"])
    best = json.loads(contents["best.json"])
    binding(metadata, source, run_id, dataset, lane)
    binding(best, source, run_id, dataset, lane)
    if (metadata.get("manifest_sha256") != manifest_hash
            or metadata.get("model_sha256") != hashlib.sha256(contents["best.skops"]).hexdigest()
            or best.get("model_sha256") != metadata["model_sha256"]
            or metadata.get("history_sha256") != hashlib.sha256(contents["history.jsonl"]).hexdigest()):
        raise ValueError("Checkpoint data/model digest binding failed")
    for name, data in contents.items():
        atomic_verified_write(destination / name, len(data), hashlib.sha256(data).hexdigest(), lambda out, b=data: out.write(b))
    return best


def latest_checkpoints(items):
    result = {}
    for dataset in DATASETS:
        for lane in LANES:
            pattern = re.compile(re.escape(f"{dataset}-{lane}-s") + r"([0-9]{4})\.tar\.gz")
            matches = [(int(m.group(1)), asset) for asset in items
                       if (m := pattern.fullmatch(asset["name"]))]
            if matches:
                sequence, asset = max(matches, key=lambda value: value[0])
                if not 1 <= sequence <= 90:
                    raise ValueError("Checkpoint sequence exceeds campaign bound")
                result[(dataset, lane)] = (sequence, asset)
    return result


def child_environment():
    allow = {"PATH", "HOME", "VIRTUAL_ENV", "TMPDIR", "LANG", "LC_ALL", "SYSTEMROOT",
             "LD_LIBRARY_PATH", "RUNNER_TRACKING_ID", "PYTHONUNBUFFERED", "PYTHONUTF8",
             "OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"}
    return {k: v for k, v in os.environ.items() if k in allow}


def run_child(argv, log_path, timeout):
    with Path(log_path).open("ab") as log:
        process = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT,
                                   env=child_environment(), start_new_session=True)
        try:
            return process.wait(timeout=max(1, timeout))
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
            raise


def run(args, manifest):
    work = Path(args.work_dir) / args.dataset / args.lane
    work.mkdir(parents=True, exist_ok=True)
    manifest_hash = sha256(args.manifest)
    item, admission = verify_admission(args.source_sha, args.run_id, work, manifest_hash)
    out, data = work / "model", work / "data"
    out.mkdir(exist_ok=True)
    latest = latest_checkpoints(release_assets(item)).get((args.dataset, args.lane))
    sequence = latest[0] if latest else 0
    published = None
    published_history = None
    marker = work / "published.json"
    if marker.exists():
        value = json.loads(marker.read_text())
        binding(value, args.source_sha, args.run_id, args.dataset, args.lane)
        if value["sequence"] != sequence:
            raise ValueError("Local and cloud checkpoint sequences disagree")
        published = value["model_sha256"]
        published_history = value.get("history_sha256")
    elif latest:
        restore = work / f"restore-{sequence}.tar.gz"
        download_asset(latest[1], restore)
        restored = out if not (out / "best.json").exists() else work / f"cloud-current-{sequence}"
        restored_best = unpack_checkpoint(restore, restored, args.source_sha, args.run_id, args.dataset, args.lane, manifest_hash)
        published = restored_best["model_sha256"]
        published_history = sha256(restored / "history.jsonl")
    if utcnow() < instant(CUTOFF):
        splits = ["train"] + (["validation"] if args.dataset == "massive-fi-FI" else [])
        dataset_files(manifest, args.dataset, data, splits)
    end = min(instant(CUTOFF), utcnow() + dt.timedelta(minutes=args.minutes))
    idle_chunks = 0
    while utcnow() < end:
        if sequence >= 90:
            print("Checkpoint count safety bound reached; preserving all published results", flush=True)
            break
        seconds = min(540, int((end - utcnow()).total_seconds()) - 15)
        if seconds < 5:
            break
        estimated_spend(manifest, admission, additional_seconds=seconds + 195)
        started = time.monotonic()
        argv = [sys.executable, str(Path(__file__).with_name("train.py")), "run",
                "--dataset", args.dataset, "--lane", args.lane, "--data-dir", str(data),
                "--out", str(out), "--seconds", str(seconds), "--cutoff", CUTOFF,
                "--source-sha", args.source_sha, "--run-id", args.run_id]
        print(json.dumps({"event": "training-chunk-start", "dataset": args.dataset,
                          "lane": args.lane, "source_sha": args.source_sha,
                          "run_id": args.run_id, "seconds": seconds,
                          "latest_cloud_sequence": sequence}), flush=True)
        timed_out = False
        try:
            status = run_child(argv, work / "training-process.log", min(seconds + 15, max(1, (end - utcnow()).total_seconds())))
        except subprocess.TimeoutExpired:
            status, timed_out = None, True
        if not (out / "best.json").is_file():
            raise RuntimeError("Training produced no complete checkpoint")
        best = json.loads((out / "best.json").read_text())
        history_digest = sha256(out / "history.jsonl")
        changed = best.get("model_sha256") != published or history_digest != published_history
        if changed:
            if sequence >= 90:
                raise ValueError("Checkpoint count bound reached")
            sequence += 1
            members = checkpoint_members(out, args.source_sha, args.run_id, args.dataset,
                                         args.lane, manifest_hash, sequence)
            checkpoint = work / f"{args.dataset}-{args.lane}-s{sequence:04d}.tar.gz"
            pack_checkpoint(members, checkpoint)
            upload(checkpoint)
            published = best["model_sha256"]
            published_history = history_digest
            write_json(marker, {"source_sha": args.source_sha, "run_id": args.run_id,
                                "dataset": args.dataset, "lane": args.lane,
                                "sequence": sequence, "model_sha256": published,
                                "history_sha256": published_history})
            print(json.dumps({"dataset": args.dataset, "lane": args.lane,
                              "checkpoint": checkpoint.name, "validation_macro_f1": best["validation_macro_f1"]}), flush=True)
        if status:
            raise RuntimeError(f"Training child failed (exit {status}); checkpoint preserved")
        if timed_out:
            print("Phase time bound reached; the last complete checkpoint is preserved", flush=True)
            break
        state = out / "state.json"
        if state.exists() and json.loads(state.read_text()).get("next_trial", 0) >= 10000:
            print("The fixed search budget is exhausted", flush=True)
            break
        idle_chunks = idle_chunks + 1 if not changed and time.monotonic() - started < 3 else 0
        if idle_chunks >= 2:
            print("Training search is exhausted; stopping this phase without idle compute", flush=True)
            break
    if not (out / "best.json").exists():
        raise ValueError("No complete model checkpoint exists; no training pass is claimed")
    # Late phase calls perform no training, but still verify the preserved pair.
    checkpoint_members(out, args.source_sha, args.run_id, args.dataset,
                       args.lane, manifest_hash, max(1, sequence))


def named_asset(items, name):
    matches = [item for item in items if item["name"] == name]
    if len(matches) > 1:
        raise ValueError("Cloud receipt filename is not unique")
    return matches[0] if matches else None


def receipt_json(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1_000_000:
        raise ValueError("Local campaign receipt exceeds its regular-file bound")
    return json.loads(path.read_text())


def validate_evaluation(value, dataset, model_hash, test_spec, source, run_id, lane):
    binding(value, source, run_id, dataset, lane)
    if (value.get("model_sha256") != model_hash or value.get("test_sha256") != test_spec["sha256"]
            or value.get("rows") != test_spec["rows"]):
        raise ValueError("Existing test receipt belongs to different model or test bytes")
    for metric in ("accuracy", "macro_f1_observed", "macro_f1_all_labels"):
        if type(value.get(metric)) not in (int, float) or not math.isfinite(value[metric]) or not 0 <= value[metric] <= 1:
            raise ValueError("Existing test receipt has invalid metrics")
    return value


def reused_evaluation(path, items, dataset, model_hash, test_spec, source, run_id, lane):
    asset = named_asset(items, Path(path).name)
    if asset:
        if asset["size"] > 1_000_000:
            raise ValueError("Test receipt exceeds its bound")
        download_asset(asset, path)
    if Path(path).exists():
        return validate_evaluation(receipt_json(path), dataset,
                                   model_hash, test_spec, source, run_id, lane)
    return None


def summary_markdown(summary):
    report = "# HF intent campaign\n\n" + f"Status: {summary['status']}. Exact source `{summary['source_sha']}`, run `{summary['run_id']}`.\n\n"
    report += "Official tests were evaluated only after selecting each family winner on validation.\n"
    report += "\n".join(f"- {dataset}: {winner['lane']}, validation macro-F1 {winner['validation_macro_f1']:.6f}." for dataset, winner in summary["winners"].items())
    if summary["missing_lanes"]:
        report += "\n\nMissing lanes: " + ", ".join(summary["missing_lanes"])
    return (report + "\n").encode()


def publish_summary(summary, work):
    path = Path(work) / "campaign-summary.json"
    if path.exists():
        existing = receipt_json(path)
        # Preserve the original timestamp/bytes during an interrupted publication.
        left, right = dict(existing), dict(summary)
        left.pop("finished_at", None)
        right.pop("finished_at", None)
        if left != right:
            raise ValueError("Preserve a different existing campaign summary")
        summary = existing
    else:
        write_json(path, summary)
    markdown = Path(work) / "campaign-summary.md"
    data = summary_markdown(summary)
    atomic_verified_write(markdown, len(data), hashlib.sha256(data).hexdigest(), lambda out: out.write(data))
    upload(path)
    upload(markdown)
    print(json.dumps(summary, allow_nan=False))
    return 1 if summary["status"] != "complete" else 0


def recover_summary(args, manifest, work, items):
    path = work / "campaign-summary.json"
    asset = named_asset(items, path.name)
    if asset:
        if asset["size"] > 1_000_000:
            raise ValueError("Campaign receipt exceeds its bound")
        download_asset(asset, path)
    if not path.exists():
        return None
    summary = receipt_json(path)
    binding(summary, args.source_sha, args.run_id)
    if (summary.get("manifest_sha256") != sha256(args.manifest)
            or summary.get("status") not in {"complete", "partial"}
            or set(summary.get("winners", {})) - set(DATASETS)):
        raise ValueError("Existing campaign receipt belongs to different inputs")
    if summary["status"] == "complete" and (set(summary["winners"]) != set(DATASETS) or summary.get("missing_lanes")):
        raise ValueError("Completed summary is missing its model results")
    for dataset, winner in summary["winners"].items():
        lane = winner["lane"]
        if lane not in LANES:
            raise ValueError("Campaign receipt contains an unknown lane")
        result = reused_evaluation(work / f"{dataset}-test-evaluation.json", items, dataset,
                                   winner["model_sha256"], manifest["datasets"][dataset]["files"]["test"],
                                   args.source_sha, args.run_id, lane)
        if result is None or result != winner["test_evaluation"]:
            raise ValueError("Completed campaign lacks its exact held-out receipt")
        archive = work / f"{dataset}-winner.tar.gz"
        cloud_archive = named_asset(items, archive.name)
        if cloud_archive:
            if cloud_archive.get("label") != "sha256:" + winner["winner_archive_sha256"]:
                raise ValueError("Completed winner differs from its cloud archive")
        elif archive.is_file() and sha256(archive) == winner["winner_archive_sha256"]:
            upload(archive)
        else:
            raise ValueError("Completed campaign lacks its winning model archive")
        upload(work / f"{dataset}-test-evaluation.json")
    return publish_summary(summary, work)


def finalize(args, manifest):
    work = Path(args.work_dir)
    work.mkdir(parents=True, exist_ok=True)
    item, _ = verify_admission(args.source_sha, args.run_id, work, sha256(args.manifest))
    cloud_items = release_assets(item)
    recovered = recover_summary(args, manifest, work, cloud_items)
    if recovered is not None:
        return recovered
    checkpoints = latest_checkpoints(cloud_items)
    manifest_hash = sha256(args.manifest)
    missing = [f"{d}/{l}" for d in DATASETS for l in LANES if (d, l) not in checkpoints]
    summary = {"source_sha": args.source_sha, "run_id": args.run_id,
               "manifest_sha256": manifest_hash, "missing_lanes": missing,
               "status": "partial" if missing else "complete", "winners": {}}
    for dataset in DATASETS:
        choices = []
        for lane in LANES:
            if (dataset, lane) not in checkpoints:
                continue
            sequence, asset = checkpoints[(dataset, lane)]
            local = work / dataset / lane
            local.mkdir(parents=True, exist_ok=True)
            package = download_asset(asset, local / asset["name"])
            best = unpack_checkpoint(package, local / "checkpoint", args.source_sha,
                                     args.run_id, dataset, lane, manifest_hash)
            for metric in ("validation_macro_f1", "cv_macro_f1"):
                if not isinstance(best.get(metric), (int, float)) or not math.isfinite(best[metric]) or not 0 <= best[metric] <= 1:
                    raise ValueError("Final candidate metrics are malformed")
            choices.append((best["validation_macro_f1"], best["cv_macro_f1"], lane, local, package, best))
        if not choices:
            continue
        _, _, lane, local, package, best = sorted(choices, key=lambda x: (-x[0], -x[1], x[2]))[0]
        # Selection has finished before any official test file is downloaded.
        # An exact completed cloud/local receipt is reused WITHOUT prediction.
        test_dir = work / dataset / "sealed-test"
        result = work / f"{dataset}-test-evaluation.json"
        test_spec = manifest["datasets"][dataset]["files"]["test"]
        receipt = reused_evaluation(result, cloud_items, dataset, best["model_sha256"], test_spec,
                                    args.source_sha, args.run_id, lane)
        if receipt is None:
            dataset_files(manifest, dataset, test_dir, ["test"])
            status = run_child([sys.executable, str(Path(__file__).with_name("train.py")), "evaluate",
                                "--dataset", dataset, "--model", str(local / "checkpoint" / "best.skops"),
                                "--data-dir", str(test_dir), "--out", str(result),
                                "--source-sha", args.source_sha, "--run-id", args.run_id],
                               work / f"{dataset}-evaluation.log",
                               min(300, max(1, (instant(DEADLINE) - utcnow()).total_seconds() - 90)))
            if status or not result.is_file():
                raise RuntimeError("Final held-out evaluation did not complete")
            receipt = validate_evaluation(receipt_json(result), dataset, best["model_sha256"],
                                          test_spec, args.source_sha, args.run_id, lane)
        winner = work / f"{dataset}-winner.tar.gz"
        copy_verified(package, winner)
        upload(winner)
        upload(result)
        summary["winners"][dataset] = {"lane": lane, "selection": "validation_macro_f1 then train CV then lane name",
                                         "model_sha256": best["model_sha256"],
                                         "winner_archive_sha256": sha256(winner),
                                         "validation_macro_f1": best["validation_macro_f1"],
                                         "test_evaluation": receipt}
    summary["finished_at"] = utcnow().isoformat()
    if len(summary["winners"]) != 2:
        summary["status"] = "partial"
    return publish_summary(summary, work)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("init", "run", "finalize"):
        sub = commands.add_parser(command)
        for field in ("manifest", "release-tag", "source-sha", "run-id", "work-dir"):
            sub.add_argument("--" + field, required=True)
        if command == "run":
            sub.add_argument("--dataset", choices=DATASETS, required=True)
            sub.add_argument("--lane", choices=LANES, required=True)
            sub.add_argument("--minutes", type=int, default=280)
    args = parser.parse_args(argv)
    identities(args.source_sha, args.run_id, args.release_tag)
    before(DEADLINE)
    manifest = load_manifest(args.manifest)
    if args.command == "run" and not 1 <= args.minutes <= 280:
        raise ValueError("A training phase must be bounded to 1..280 minutes")
    return {"init": init, "run": run, "finalize": finalize}[args.command](args, manifest) or 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Intent campaign refused or failed: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1)
