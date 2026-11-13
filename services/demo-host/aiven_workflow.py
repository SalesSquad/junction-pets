#!/usr/bin/env python3
"""Finite public/synthetic developer demo. No server, Chibi grant or production default."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HELPER = Path(__file__).with_name('workflow.mjs')
MAX_RESULT_BYTES = 60000


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def plan(source_commit: str, request_id: str) -> dict:
    if not re.fullmatch(r'[a-f0-9]{40}', source_commit or ''):
        raise ValueError('INVALID_SOURCE_COMMIT')
    if not re.fullmatch(r'[a-z0-9][a-z0-9._:-]{1,99}', request_id or ''):
        raise ValueError('INVALID_REQUEST_ID')
    payload = {'version': 1, 'sourceCommit': source_commit, 'workflow': 'fixed-public-aiven-observability',
               'fixtureSha256': digest((ROOT / 'pets/mariadb/explain-example.mjs').read_bytes())}
    return {'sourceCommit': source_commit, 'requestId': request_id,
            'envelopeDigest': digest(canonical(payload).encode()),
            'handoffsDigest': digest(HELPER.read_bytes())}


def check_source(source_commit: str):
    def git(*args):
        return subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True, text=True,
                              timeout=10, check=True).stdout.strip()
    if git('rev-parse', 'HEAD') != source_commit or git('status', '--porcelain=v1', '--untracked-files=all'):
        raise RuntimeError('SOURCE_NOT_CLEAN_OR_PINNED')
    if git('remote', 'get-url', 'origin') not in ('https://github.com/SalesSquad/junction-pets.git',
                                               'git@github.com:SalesSquad/junction-pets.git'):
        raise RuntimeError('SOURCE_ORIGIN_MISMATCH')


def run_stage(stage: str, source_commit: str, value=None):
    output = subprocess.run(['node', str(HELPER), '--stage', stage, '--source-commit', source_commit],
                            input=None if value is None else canonical(value), capture_output=True,
                            text=True, timeout=110, check=True,
                            env={key: value for key, value in os.environ.items()
                                 if not key.startswith('PG') and key != 'JUNCTION_DEMO_DATABASE_URL'})
    if len(output.stdout.encode()) > MAX_RESULT_BYTES:
        raise RuntimeError('STAGE_RESULT_TOO_LARGE')
    return json.loads(output.stdout)


def execute_plan(item, caller, store, results, stage=run_stage, verify=check_source, run_id_factory=None):
    """Injected test seams are not CLI transports; one reservation authorizes no Chibi effect."""
    if run_id_factory is None:
        from council.replay import deterministic_run_id
        run_id_factory = deterministic_run_id
    verify(item['sourceCommit'])
    reservation = store.reserve(caller, item['requestId'], item['envelopeDigest'],
                                run_id_factory(caller, item['requestId']), item['handoffsDigest'])
    if not store.is_current(caller, reservation):
        raise RuntimeError('RESERVATION_NOT_CURRENT')
    if not reservation.created:
        prior = results.read(caller, reservation, item)
        if prior is None:
            raise RuntimeError('IN_PROGRESS_OR_OUTCOME_UNKNOWN_NO_AUTOMATIC_RETRY')
        return {'replayed': True, 'result': prior}
    try:
        verify(item['sourceCommit'])
        if not store.is_current(caller, reservation):
            raise RuntimeError('RESERVATION_NOT_CURRENT')
        evidence = stage('evidence', item['sourceCommit'])
        verify(item['sourceCommit'])
        if not store.is_current(caller, reservation):
            raise RuntimeError('RESERVATION_NOT_CURRENT')
        observed = stage('model', item['sourceCommit'], evidence)
        if not isinstance(observed, dict) or observed.get('kind') != 'public-synthetic-developer-demo':
            raise RuntimeError('INVALID_STAGE_RESULT')
        result = {'status': 'completed', 'sourceCommit': item['sourceCommit'],
                  'requestId': item['requestId'], 'envelopeDigest': item['envelopeDigest'],
                  'handoffsDigest': item['handoffsDigest'], 'observation': observed,
                  'chibiHostVerified': False, 'signedReceiptVerified': False}
    except Exception:
        # A response may have happened before a transport/parse error. Never infer safe retry.
        result = {'status': 'failed', 'sourceCommit': item['sourceCommit'], 'requestId': item['requestId'],
                  'error': 'STAGE_FAILED_OR_OUTCOME_UNKNOWN', 'automaticRetryAllowed': False,
                  'chibiHostVerified': False, 'signedReceiptVerified': False}
    verify(item['sourceCommit'])
    if not store.is_current(caller, reservation):
        raise RuntimeError('RESERVATION_NOT_CURRENT')
    results.save(caller, reservation, item, result)
    return {'replayed': False, 'result': result}


DEMO_DDL = """
CREATE TABLE IF NOT EXISTS junction_council.demo_public_results (
  tenant_id varchar(100) NOT NULL,
  user_id varchar(100) NOT NULL,
  run_id uuid PRIMARY KEY REFERENCES junction_council.replay_reservations(run_id),
  envelope_digest char(64) NOT NULL,
  handoffs_digest char(64) NOT NULL,
  fence_token bigint NOT NULL,
  source_commit char(40) NOT NULL CHECK (source_commit ~ '^[a-f0-9]{40}$'),
  result_text text NOT NULL CHECK (octet_length(result_text) <= 60000),
  result_sha256 char(64) NOT NULL CHECK (result_sha256 ~ '^[a-f0-9]{64}$')
);
CREATE OR REPLACE FUNCTION junction_council.guard_demo_public_result()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Demo public results are immutable' USING ERRCODE = '23514'; END;
$$;
DROP TRIGGER IF EXISTS demo_public_result_immutable ON junction_council.demo_public_results;
CREATE TRIGGER demo_public_result_immutable BEFORE UPDATE OR DELETE ON junction_council.demo_public_results
FOR EACH ROW EXECUTE FUNCTION junction_council.guard_demo_public_result();
"""


class PostgresResults:
    def __init__(self, factory):
        self.factory = factory

    @staticmethod
    def bindings(caller, r, item):
        return (caller.tenant_id, caller.user_id, caller.active_pet, r.run_id, r.envelope_digest,
                r.handoffs_digest, r.idempotency_key, r.fence_token)

    @staticmethod
    def current_sql():
        return """SELECT run_id FROM junction_council.replay_reservations
          WHERE tenant_id=%s AND user_id=%s AND active_pet=%s AND run_id=%s
          AND envelope_digest=%s AND handoffs_digest=%s AND idempotency_key=%s
          AND fence_token=%s AND active=true FOR SHARE"""

    def read(self, caller, reservation, item):
        with self.factory() as connection:
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL statement_timeout = '5s'")
                    cursor.execute("SET LOCAL lock_timeout = '2s'")
                    cursor.execute(self.current_sql(), self.bindings(caller, reservation, item))
                    if cursor.fetchone() is None:
                        raise RuntimeError('RESERVATION_NOT_CURRENT')
                    cursor.execute("""SELECT result_text,result_sha256 FROM junction_council.demo_public_results
                      WHERE tenant_id=%s AND user_id=%s AND run_id=%s AND envelope_digest=%s
                      AND handoffs_digest=%s AND fence_token=%s AND source_commit=%s""",
                      (caller.tenant_id, caller.user_id, reservation.run_id, reservation.envelope_digest,
                       reservation.handoffs_digest, reservation.fence_token, item['sourceCommit']))
                    row = cursor.fetchone()
                    if row is None:
                        return None
                    if digest(row[0].encode()) != row[1]:
                        raise RuntimeError('RESULT_DIGEST_MISMATCH')
                    return json.loads(row[0])

    def save(self, caller, reservation, item, value):
        text = canonical(value)
        if len(text.encode()) > MAX_RESULT_BYTES:
            raise RuntimeError('RESULT_TOO_LARGE')
        with self.factory() as connection:
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL synchronous_commit = on")
                    cursor.execute("SET LOCAL statement_timeout = '5s'")
                    cursor.execute("SET LOCAL lock_timeout = '2s'")
                    cursor.execute(self.current_sql(), self.bindings(caller, reservation, item))
                    if cursor.fetchone() is None:
                        raise RuntimeError('RESERVATION_NOT_CURRENT')
                    cursor.execute("""INSERT INTO junction_council.demo_public_results
                      (tenant_id,user_id,run_id,envelope_digest,handoffs_digest,fence_token,source_commit,result_text,result_sha256)
                      VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (run_id) DO NOTHING
                      RETURNING result_sha256""", (caller.tenant_id, caller.user_id, reservation.run_id,
                      reservation.envelope_digest, reservation.handoffs_digest, reservation.fence_token,
                      item['sourceCommit'], text, digest(text.encode())))
                    if cursor.fetchone() is None:
                        raise RuntimeError('RESULT_ALREADY_EXISTS_NO_OVERWRITE')


def database_factory():
    try:
        import psycopg
        from psycopg.conninfo import conninfo_to_dict
    except ImportError:
        raise RuntimeError('PYTHON_DEPENDENCIES_UNAVAILABLE') from None
    dsn = os.environ.get('JUNCTION_DEMO_DATABASE_URL')
    if not dsn:
        raise RuntimeError('DISPOSABLE_DATABASE_UNAVAILABLE')
    try:
        values = conninfo_to_dict(dsn)
    except Exception:
        raise RuntimeError('INVALID_DISPOSABLE_DATABASE_CONFIG') from None
    if set(values) - {'host', 'port', 'dbname', 'user', 'password', 'sslmode', 'connect_timeout'}:
        raise RuntimeError('UNSUPPORTED_DATABASE_OPTIONS')
    if any(value for key, value in os.environ.items() if key.startswith('PG') and key not in ('PGDATA', 'PGBIN')):

        raise RuntimeError('INHERITED_DATABASE_OVERRIDE_REFUSED')
    if not re.fullmatch(r'junction_council_test_[a-z0-9_]+', values.get('dbname', '')):
        raise RuntimeError('DISPOSABLE_DATABASE_NAME_REQUIRED')
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]{0,62}', values.get('user', '')):
        raise RuntimeError('EXPLICIT_DATABASE_USER_REQUIRED')
    host = values.get('host', '')
    if (not isinstance(host, str) or ',' in host or any(ord(char) < 32 or ord(char) == 127 for char in host)
            or host not in ('127.0.0.1', '::1') and
            (not host.startswith('/') or host != os.path.normpath(host))):
        raise RuntimeError('LOCAL_DISPOSABLE_DATABASE_REQUIRED')
    port = values.get('port')
    if port is not None and (not port.isascii() or not port.isdigit() or not 1 <= int(port) <= 65535):
        raise RuntimeError('INVALID_DATABASE_PORT')
    values['connect_timeout'] = '5'
    return lambda: psycopg.connect(**values)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--request-id', default='public-demo-1')
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--execute', action='store_true')
    actions.add_argument('--init-db', action='store_true')
    args = parser.parse_args()
    item = plan(args.source_commit, args.request_id)
    if not args.execute and not args.init_db:
        print(canonical({'mode': 'offline-preview', **item, 'databaseAccessed': False,
                         'networkAccessed': False, 'modelResponseObserved': False, 'chibiHostVerified': False}))
        return
    check_source(args.source_commit)
    factory = database_factory()
    if args.init_db:
        migration = ROOT / 'services/council/migrations/001_replay_reservations.sql'
        with factory() as connection:
            connection.execute(migration.read_text())
            connection.execute(DEMO_DDL)
        print(canonical({'mode': 'disposable-demo-database-initialized', 'sourceCommit': args.source_commit}))
        return
    sys.path.insert(0, str(ROOT / 'services/council'))
    try:
        from council.core import Caller
        from council.postgres_replay import PostgresReplayStore
    except ImportError:
        raise RuntimeError('PYTHON_DEPENDENCIES_UNAVAILABLE') from None
    caller = Caller(tenant_id='synthetic-public-demo', user_id='synthetic-developer', active_pet='junction-aiven')
    outcome = execute_plan(item, caller, PostgresReplayStore(factory), PostgresResults(factory))
    print(canonical({'mode': 'public-developer-demo', **outcome}))
    if outcome['result']['status'] != 'completed':
        raise SystemExit(1)


if __name__ == '__main__':
    try:
        main()
    except Exception as cause:
        # Only fixed, local error codes are printable; DB/provider details stay private.
        safe = {'INVALID_SOURCE_COMMIT', 'INVALID_REQUEST_ID', 'SOURCE_NOT_CLEAN_OR_PINNED',
                'SOURCE_ORIGIN_MISMATCH', 'PYTHON_DEPENDENCIES_UNAVAILABLE', 'DISPOSABLE_DATABASE_UNAVAILABLE',
                'INVALID_DISPOSABLE_DATABASE_CONFIG', 'UNSUPPORTED_DATABASE_OPTIONS',
                'INHERITED_DATABASE_OVERRIDE_REFUSED', 'DISPOSABLE_DATABASE_NAME_REQUIRED',
                'LOCAL_DISPOSABLE_DATABASE_REQUIRED', 'EXPLICIT_DATABASE_USER_REQUIRED', 'INVALID_DATABASE_PORT', 'IN_PROGRESS_OR_OUTCOME_UNKNOWN_NO_AUTOMATIC_RETRY',
                'RESERVATION_NOT_CURRENT', 'RESULT_DIGEST_MISMATCH', 'RESULT_ALREADY_EXISTS_NO_OVERWRITE'}
        code = str(cause) if str(cause) in safe else 'DEMO_WORKFLOW_FAILED'
        print(canonical({'error': code, 'automaticRetryAllowed': False}), file=sys.stderr)
        raise SystemExit(1)
