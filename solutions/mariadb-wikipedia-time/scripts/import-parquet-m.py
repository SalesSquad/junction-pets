#!/usr/bin/env python3
"""Offline M release admission. No network, database or global dependency install."""
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

RELEASE = 'm-2026-10'
RELEASE_URL = 'https://github.com/MariaDB/mariadb-wikipedia-datasets/releases/tag/' + RELEASE
# GitHub release asset digest, observed 2026-11-15 at releases/expanded_assets/m-2026-10.
MANIFEST_SHA256 = '7d59a6a28b10f996be3c36fc4d82f5faa97624f8fca7a37cbf5d70e4bb809f68'
MAX_BODY = 128 * 1024
MAX_TOTAL = 2 * 1024 * 1024
COLUMNS = ['page_id', 'title', 'rev_id', 'timestamp', 'text']


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest_file(file):
    h = hashlib.sha256()
    file.seek(0)
    for chunk in iter(lambda: file.read(1024 * 1024), b''):
        h.update(chunk)
    file.seek(0)
    return h.hexdigest()


def manifest_entries(raw):
    require(len(raw) <= 16384, 'MANIFEST_TOO_LARGE')
    entries = {}
    for line in raw.decode('ascii').splitlines():
        match = re.fullmatch(r'([a-f0-9]{64}) [ *](versions-(?:0[1-9]|1[0-6])\.parquet|README\.md)', line)
        require(match is not None, 'INVALID_MANIFEST')
        checksum, name = match.groups()
        require(name not in entries, 'DUPLICATE_MANIFEST_ENTRY')
        entries[name] = checksum
    require(bool(entries), 'EMPTY_MANIFEST')
    return entries


def page_id(value):
    require(isinstance(value, str) and re.fullmatch(r'[1-9][0-9]{0,9}', value) is not None
            and int(value) <= 4294967295, 'INVALID_PAGE_ID')
    return int(value)


def build_replay(parquet, sha256sums, page, *, _synthetic_test_manifest=None):
    """Tests may supply their own manifest digest; CLI can only use the release pin.

    That test seam ALWAYS emits SYNTHETIC provenance and no Wikipedia source URLs.
    Scan the entire shard to refuse >50 matches rather than silently truncating.
    """
    wanted = page_id(page)
    path = Path(parquet)
    require(re.fullmatch(r'versions-(?:0[1-9]|1[0-6])\.parquet', path.name) is not None,
            'INVALID_SHARD_BASENAME')
    with open(sha256sums, 'rb') as manifest:
        raw = manifest.read(16385)
    entries = manifest_entries(raw)
    manifest_hash = hashlib.sha256(raw).hexdigest()
    synthetic = _synthetic_test_manifest is not None
    require(manifest_hash == (_synthetic_test_manifest if synthetic else MANIFEST_SHA256),
            'UNTRUSTED_MANIFEST')
    require(path.name in entries, 'SHARD_NOT_IN_MANIFEST')
    with open(path, 'rb') as source:
        checksum = digest_file(source)
        require(checksum == entries[path.name], 'SHARD_SHA256_MISMATCH')
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError as exc:
            raise ValueError('DEPENDENCY_UNAVAILABLE: pyarrow; use an explicit project-local venv') from exc
        parquet_file = pq.ParquetFile(source)
        schema = parquet_file.schema_arrow
        require(all(c in schema.names for c in COLUMNS), 'M_SCHEMA_COLUMNS_REQUIRED')
        require(pa.types.is_uint32(schema.field('page_id').type)
                and pa.types.is_uint32(schema.field('rev_id').type)
                and pa.types.is_timestamp(schema.field('timestamp').type)
                and schema.field('timestamp').type.tz == 'UTC'
                and all(pa.types.is_string(schema.field(c).type) for c in ['title', 'text']),
                'M_SCHEMA_TYPES_REQUIRED')
        revisions, seen, previous, total = [], set(), None, 0
        # Bounded batches; only page IDs are decoded for nonmatching rows. Never read_table.
        for batch in parquet_file.iter_batches(batch_size=8, columns=COLUMNS, use_threads=False):
            ids = batch.column(0).to_pylist()
            for index, identity in enumerate(ids):
                require(identity is not None, 'NULL_PAGE_ID')
                if identity != wanted:
                    continue
                require(len(revisions) < 50, 'PAGE_EXCEEDS_50_VERSIONS')
                row = {c: batch.column(i)[index].as_py() for i, c in enumerate(COLUMNS)}
                rid, stamp, title, body = row['rev_id'], row['timestamp'], row['title'], row['text']
                require(type(rid) is int and rid > 0, 'INVALID_REVISION_ID')
                require(rid not in seen, 'DUPLICATE_REVISION_ID')
                require(isinstance(stamp, datetime) and stamp.utcoffset() is not None
                        and stamp.utcoffset().total_seconds() == 0 and stamp.microsecond == 0
                        and 1000 <= stamp.year <= 9999, 'INVALID_UTC_TIMESTAMP')
                require(previous is None or stamp > previous, 'TIMESTAMP_TIE_OR_REVERSED_ORDER')
                require(isinstance(title, str) and title.strip() and len(title.encode('utf-16-le')) <= 510, 'INVALID_TITLE')
                require(isinstance(body, str) and body.strip() and len(body.encode('utf-8')) <= MAX_BODY,
                        'INVALID_OR_OVERSIZE_TEXT')
                total += len(body.encode('utf-8'))
                require(total <= MAX_TOTAL, 'TOTAL_TEXT_LIMIT')
                seen.add(rid)
                previous = stamp
                revisions.append({'page_id': page, 'title': title, 'revision_id': str(rid),
                    'revised_at': stamp.astimezone(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z'),
                    'body': body, 'source_url': None if synthetic else
                    'https://fi.wikipedia.org/w/index.php?oldid=' + str(rid)})
        # Detect mutation while the same open shard was being decoded.
        require(digest_file(source) == checksum, 'SHARD_CHANGED_DURING_SCAN')
    require(bool(revisions), 'PAGE_NOT_IN_SHARD')
    return {'dataset_id': ('synthetic-m-test' if synthetic else RELEASE) + ':' + path.stem + ':' + page,
        'dataset_license': 'SYNTHETIC TEST ONLY' if synthetic else 'CC BY-SA 4.0',
        'provenance': 'SYNTHETIC' if synthetic else 'LICENSED_REPLAY',
        'revisions': revisions,
        'intake': {'format': 'M_PARQUET_LOCAL_REPLAY', 'release_tag': RELEASE,
            'source_release_url': RELEASE_URL, 'shard_basename': path.name,
            'shard_sha256': checksum, 'manifest_sha256': manifest_hash,
            'manifest_integrity': 'SYNTHETIC_TEST_ONLY' if synthetic else 'PINNED_OFFICIAL_RELEASE_MANIFEST',
            'verified_live_source': False, 'provider': 'NO_MARIADB_CONNECTION',
            'scope': 'ALL_MATCHING_ROWS_IN_ONE_SHARD_ONLY; other shards and hidden revisions not established',
            'revision_count': len(revisions), 'attribution': 'Synthetic test' if synthetic else
            'Finnish Wikipedia contributors; https://fi.wikipedia.org/w/index.php?curid=' + page + '&action=history',
            'data_license_url': None if synthetic else 'https://creativecommons.org/licenses/by-sa/4.0/',
            'upstream_loader_license': 'MIT (distinct from Wikipedia text rights)'}}


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for flag in ['parquet', 'sha256sums', 'page', 'out']:
        parser.add_argument('--' + flag, required=True)
    for flag in ['--parquet', '--sha256sums', '--page', '--out']:
        require(sum(arg == flag or arg.startswith(flag + '=') for arg in sys.argv[1:]) <= 1,
                'DUPLICATE_ARGUMENT')
    args = parser.parse_args()
    require(not Path(args.out).exists() and not Path(args.out).is_symlink(), 'OUTPUT_EXISTS')
    result = build_replay(args.parquet, args.sha256sums, args.page)
    # Exclusive create refuses races and symlinks; validation finishes before any output exists.
    with open(args.out, 'x', encoding='utf-8') as output:
        output.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': 'IMPORTED_LOCAL_REPLAY', 'revision_count': len(result['revisions']),
                      'verified_live_source': False, 'provider': 'NO_MARIADB_CONNECTION'}))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, UnicodeError) as exc:
        print(json.dumps({'status': 'REFUSED', 'reason': str(exc)}), file=sys.stderr)
        sys.exit(2)
