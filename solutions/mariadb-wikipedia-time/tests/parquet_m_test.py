"""SYNTHETIC ONLY: locally generated Parquet, never official dataset evidence."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import builtins
from datetime import datetime, timezone
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('intake', ROOT / 'scripts/import-parquet-m.py')
intake = importlib.util.module_from_spec(spec)
spec.loader.exec_module(intake)
SCHEMA = pa.schema([('page_id', pa.uint32()), ('title', pa.string()), ('rev_id', pa.uint32()),
                    ('timestamp', pa.timestamp('s', tz='UTC')), ('text', pa.string())])


class Admission(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='chronicle-synthetic-')
        self.directory = Path(self.temp.name)
        self.shard = self.directory / 'versions-01.parquet'
        self.manifest = self.directory / 'SHA256SUMS'
        self.rows = [dict(page_id=155, title='Synthetic title', rev_id=101+i,
            timestamp=datetime(2026, 1, 1+i, tzinfo=timezone.utc), text=text)
            for i, text in enumerate(['Original words', 'Changed words', 'Original words'])]

    def tearDown(self):
        self.temp.cleanup()

    def write(self, rows=None, schema=SCHEMA):
        pq.write_table(pa.Table.from_pylist(self.rows if rows is None else rows, schema=schema), self.shard,
                       row_group_size=2)
        checksum = hashlib.sha256(self.shard.read_bytes()).hexdigest()
        raw = (checksum + '  versions-01.parquet\n').encode()
        self.manifest.write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    def build(self, pin):
        return intake.build_replay(self.shard, self.manifest, '155', _synthetic_test_manifest=pin)

    def test_wrong_digest_and_untrusted_manifest(self):
        pin = self.write()
        with self.shard.open('ab') as output:
            output.write(b'tamper')
        with self.assertRaisesRegex(ValueError, 'SHARD_SHA256_MISMATCH'):
            self.build(pin)
        self.write()
        with self.assertRaisesRegex(ValueError, 'UNTRUSTED_MANIFEST'):
            intake.build_replay(self.shard, self.manifest, '155')

    def test_accepted_digest_exact_asof_compare_revert_and_determinism(self):
        rows = [dict(self.rows[0], page_id=777)] + self.rows
        pin = self.write(rows)
        replay = self.build(pin)
        self.assertEqual(replay, self.build(pin))
        self.assertEqual(replay['provenance'], 'SYNTHETIC')
        self.assertEqual(replay['intake']['manifest_integrity'], 'SYNTHETIC_TEST_ONLY')
        output = self.directory / 'synthetic.json'
        output.write_text(json.dumps(replay))
        result = subprocess.run(['node', str(ROOT/'src/cli.mjs'), '--data', str(output), '--page', '155',
            '--at', '2026-01-02T00:00:00Z', '--compare', '2026-01-01T00:00:00Z'],
            text=True, capture_output=True, check=True)
        answer = json.loads(result.stdout)
        self.assertEqual(answer['snapshot']['revision_id'], '102')
        self.assertEqual(answer['snapshot']['text'], 'Changed words')
        self.assertEqual(answer['comparison']['status'], 'CHANGED')
        self.assertEqual(answer['suspected_reverts'][0]['revision_ids'], ['101', '102', '103'])
        self.assertFalse(answer['verified_live_source'])
        self.assertEqual(answer['provider'], 'NO_MARIADB_CONNECTION')
        pin = self.write([dict(self.rows[0], rev_id=100+i,
            timestamp=datetime.fromtimestamp(1700000000+i, timezone.utc)) for i in range(50)])
        self.assertEqual(len(self.build(pin)['revisions']), 50)
        original_import = builtins.__import__
        def missing_pyarrow(name, *args, **kwargs):
            if name == 'pyarrow':
                raise ImportError('synthetic missing dependency')
            return original_import(name, *args, **kwargs)
        with patch('builtins.__import__', side_effect=missing_pyarrow):
            with self.assertRaisesRegex(ValueError, 'DEPENDENCY_UNAVAILABLE: pyarrow'):
                self.build(pin)

    def test_fail_closed_identity_time_order_text_count_schema(self):
        cases = []
        for field, value in [('rev_id', 0), ('text', ''), ('title', ''), ('text', 'x'*(128*1024+1))]:
            rows = copy.deepcopy(self.rows); rows[0][field] = value; cases.append(rows)
        rows = copy.deepcopy(self.rows); rows[1]['rev_id'] = rows[0]['rev_id']; cases.append(rows)
        rows = copy.deepcopy(self.rows); rows[1]['timestamp'] = rows[0]['timestamp']; cases.append(rows)
        cases.append(list(reversed(self.rows)))
        cases.append([dict(self.rows[0], page_id=777)])
        cases.append([dict(self.rows[0], rev_id=100+i,
                          timestamp=datetime.fromtimestamp(1700000000+i, timezone.utc)) for i in range(51)])
        cases.append([dict(self.rows[0], rev_id=100+i, text='x'*(128*1024),
                          timestamp=datetime.fromtimestamp(1700000000+i, timezone.utc)) for i in range(17)])
        for rows in cases:
            with self.subTest(rows=len(rows)):
                pin = self.write(rows)
                with self.assertRaises(ValueError):
                    self.build(pin)
        pin = self.write(schema=pa.schema(list(SCHEMA)[:-1]))
        with self.assertRaisesRegex(ValueError, 'M_SCHEMA_COLUMNS_REQUIRED'):
            self.build(pin)
        for stamp_type in [pa.timestamp('ms'), pa.timestamp('ms', tz='Europe/Helsinki')]:
            schema = SCHEMA.set(3, pa.field('timestamp', stamp_type))
            pin = self.write(schema=schema)
            with self.assertRaisesRegex(ValueError, 'M_SCHEMA_TYPES_REQUIRED'):
                self.build(pin)
        rows = copy.deepcopy(self.rows)
        rows[0]['timestamp'] = rows[0]['timestamp'].replace(microsecond=1000)
        pin = self.write(rows, schema=SCHEMA.set(3, pa.field('timestamp', pa.timestamp('ms', tz='UTC'))))
        with self.assertRaisesRegex(ValueError, 'INVALID_UTC_TIMESTAMP'):
            self.build(pin)

    def test_cli_pin_cannot_be_overridden_and_existing_output_preserved(self):
        self.write()
        output = self.directory / 'output.json'
        args = ['python3', str(ROOT/'scripts/import-parquet-m.py'), '--parquet', str(self.shard),
                '--sha256sums', str(self.manifest), '--page', '155', '--out', str(output)]
        result = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('UNTRUSTED_MANIFEST', result.stderr)
        self.assertFalse(output.exists())
        output.write_text('preserve')
        result = subprocess.run(args, capture_output=True, text=True)
        self.assertIn('OUTPUT_EXISTS', result.stderr)
        self.assertEqual(output.read_text(), 'preserve')


if __name__ == '__main__':
    unittest.main(verbosity=2)
