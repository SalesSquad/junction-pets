#!/usr/bin/env python3
"""Install the pinned Linux x64 probe toolchain in a new task-local directory."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import tarfile
import urllib.request

ARTIFACTS = [
    {
        "type": "sdk", "version": "9.0.100",
        "url": "https://builds.dotnet.microsoft.com/dotnet/Sdk/9.0.100/dotnet-sdk-9.0.100-linux-x64.tar.gz",
        "hash": "7f69bda047de1f952286be330a5e858171ded952d1aa24169e62212f90a27149e63b636c88ad313a6e3ec860da31f8c547ff4ab6808103a070f7fb26ba99c1c7",
        "metadataUrl": "https://builds.dotnet.microsoft.com/dotnet/release-metadata/9.0/releases.json",
    },
    {
        "type": "runtime", "version": "8.0.11",
        "url": "https://builds.dotnet.microsoft.com/dotnet/Runtime/8.0.11/dotnet-runtime-8.0.11-linux-x64.tar.gz",
        "hash": "71ea528900c6fc7b54e951622296421d2a96191870c47e937117b84b28f91bf407d02046ddfecfe4ac37dc6182c65d1940927c33e45fa3d6f0179f81692490d6",
        "metadataUrl": "https://builds.dotnet.microsoft.com/dotnet/release-metadata/8.0/releases.json",
    },
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    if platform.system() != "Linux" or platform.machine() not in {"x86_64", "amd64"}:
        raise SystemExit("This reproducible installer targets Linux x64. No system installation was attempted.")
    root = args.directory.resolve()
    root.mkdir(parents=True, exist_ok=False)
    destination = root / "dotnet"
    destination.mkdir()
    for artifact in ARTIFACTS:
        with urllib.request.urlopen(artifact["metadataUrl"], timeout=60) as response:
            metadata = json.load(response)
        candidates = []
        for release in metadata["releases"]:
            values = release.get("sdks", [release.get("sdk", {})]) if artifact["type"] == "sdk" else [release.get("runtime", {})]
            for value in values:
                if value.get("version") == artifact["version"]:
                    candidates.extend(value.get("files", []))
        if not any(item.get("hash", "").lower() == artifact["hash"] and item.get("url") == artifact["url"] for item in candidates):
            raise RuntimeError("Microsoft release metadata did not confirm the pinned archive URL/hash.")
        archive = root / (artifact["type"] + "-" + artifact["version"] + ".tar.gz")
        with urllib.request.urlopen(artifact["url"], timeout=60) as response, archive.open("wb") as handle:
            while chunk := response.read(1024 * 1024):
                handle.write(chunk)
        with archive.open("rb") as handle:
            actual = hashlib.file_digest(handle, "sha512").hexdigest()
        if actual != artifact["hash"]:
            raise RuntimeError("Downloaded toolchain archive failed SHA512 verification.")
        with tarfile.open(archive) as handle:
            handle.extractall(destination, filter="data")
        print("Verified and installed", artifact["type"], artifact["version"])
    (root / "toolchain.json").write_text(json.dumps({"artifacts": ARTIFACTS}, indent=2) + "\n")


if __name__ == "__main__":
    main()
