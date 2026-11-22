#!/usr/bin/env python3
"""Check a local OCI image index and its direct descriptor bytes."""
import argparse
import hashlib
import json
import os
import re
import stat
from contextlib import contextmanager

MAX_JSON = 4 * 1024 * 1024
MAX_DESCRIPTORS = 64


@contextmanager
def directory(name, parent=None):
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    try:
        yield fd
    finally:
        os.close(fd)


def read_file(parent, name, limit):
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    with os.fdopen(os.open(name, flags, dir_fd=parent), "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError("expected a bounded regular file")
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("file exceeds size limit")
    return data


def object_from_json(data):
    obj = json.loads(data)
    if not isinstance(obj, dict):
        raise ValueError("expected a JSON object")
    return obj


def check(path):
    with directory(path) as root:
        layout = object_from_json(read_file(root, "oci-layout", MAX_JSON))
        if layout.get("imageLayoutVersion") != "1.0.0":
            raise ValueError("unsupported image layout version")
        raw = read_file(root, "index.json", MAX_JSON)
        index = object_from_json(raw)
        descriptors = index.get("manifests")
        if (
            index.get("schemaVersion") != 2
            or not isinstance(descriptors, list)
            or not 1 <= len(descriptors) <= MAX_DESCRIPTORS
        ):
            raise ValueError("invalid or oversized image index")

        with directory("blobs", root) as blobs, directory("sha256", blobs) as hashes:
            total_size = 0
            for descriptor in descriptors:
                if not isinstance(descriptor, dict):
                    raise ValueError("expected a descriptor object")
                digest = descriptor.get("digest")
                size = descriptor.get("size")
                if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
                    raise ValueError("invalid SHA-256 descriptor digest")
                if type(size) is not int or not 0 < size <= MAX_JSON:
                    raise ValueError("invalid descriptor size")
                total_size += size
                if total_size > 4 * MAX_JSON:
                    raise ValueError("descriptor bytes exceed aggregate size limit")
                blob = read_file(hashes, digest.removeprefix("sha256:"), size)
                if len(blob) != size or "sha256:" + hashlib.sha256(blob).hexdigest() != digest:
                    raise ValueError("descriptor size or hash mismatch")
                if object_from_json(blob).get("schemaVersion") != 2:
                    raise ValueError("expected a schema version 2 manifest or index")
    return {"index_sha256": hashlib.sha256(raw).hexdigest(), "checked_descriptors": len(descriptors)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("layout")
    args = parser.parse_args()
    try:
        result = check(args.layout)
    except (OSError, ValueError, RecursionError) as error:
        parser.exit(1, f"OCI layout check failed: {error}\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
