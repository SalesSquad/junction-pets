/** Private, same-host SQLite store for the NONCOMMERCIAL demo runtime. */
import { DatabaseSync, backup } from 'node:sqlite';
import { constants, closeSync, lstatSync, mkdirSync, openSync, realpathSync, statSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { createHash } from 'node:crypto';

export class StateStoreError extends Error {
  constructor(code, message, retryable = false) { super(message); this.code = code; this.retryable = retryable; }
}
const fail = (code, message, retryable) => { throw new StateStoreError(code, message, retryable); };
const sha = value => createHash('sha256').update(value).digest('hex');
const MAX_BYTES = 16 * 1024 * 1024;
function privateFile(path, { mustBeNew = false } = {}) {
  path = resolve(path);
  const parent = dirname(path);
  mkdirSync(parent, { recursive: true, mode: 0o700 });
  const directory = statSync(parent);
  if (realpathSync(parent) !== parent || !directory.isDirectory() ||
      (directory.mode & 0o077) || (process.getuid && directory.uid !== process.getuid())) {
    fail('STATE_PATH_UNSAFE', 'State and backup files require a private, owner-held directory without symlinks.');
  }
  let created = false;
  try {
    const descriptor = openSync(path, constants.O_CREAT | constants.O_EXCL | constants.O_WRONLY | constants.O_NOFOLLOW, 0o600);
    closeSync(descriptor); created = true;
  } catch (error) {
    if (error.code !== 'EEXIST') throw error;
    if (mustBeNew) fail('BACKUP_EXISTS', 'Choose a new backup path; existing files are never overwritten.');
  }
  const file = lstatSync(path);
  if (!file.isFile() || file.isSymbolicLink() || file.nlink !== 1 ||
      (file.mode & 0o077) || (process.getuid && file.uid !== process.getuid())) {
    fail('STATE_PATH_UNSAFE', 'State file must be a private regular file owned by this executor.');
  }
  return { path, created };
}

export function openLocalStateStore(path, { maxBytes = MAX_BYTES, beforeCommit } = {}) {
  if (!Number.isSafeInteger(maxBytes) || maxBytes < 1024 || maxBytes > MAX_BYTES) throw new TypeError('Invalid state size bound');
  let db;
  let closed = false;
  let allowEmpty = false;
  try {
    const opened = privateFile(path);
    db = new DatabaseSync(opened.path, { timeout: 1000, allowExtension: false,
      enableForeignKeyConstraints: true, enableDoubleQuotedStringLiterals: false });
    const version = db.prepare('PRAGMA user_version').get().user_version;
    allowEmpty = opened.created;
    const tables = db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").all();
    if (version !== 0 && version !== 1) fail('STATE_VERSION_UNSUPPORTED', 'This state schema needs an explicit compatible migration.');
    if (version === 1 && (tables.length !== 1 || tables[0].name !== 'trade_runtime')) fail('STATE_FOREIGN_DATABASE', 'This database has incompatible application tables.');
    if (version === 0 && tables.length) fail('STATE_FOREIGN_DATABASE', 'Refusing to initialize a database owned by another application.');
    if (!opened.created && version === 0) fail('STATE_CORRUPT', 'Existing state file is uninitialized or truncated; no fixture reset was performed.');
    db.exec('PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; PRAGMA foreign_keys=ON; PRAGMA trusted_schema=OFF;');
    db.exec(`CREATE TABLE IF NOT EXISTS trade_runtime (
      singleton INTEGER PRIMARY KEY CHECK(singleton=1), format INTEGER NOT NULL CHECK(format=1),
      revision INTEGER NOT NULL CHECK(revision>=1), body TEXT NOT NULL CHECK(json_valid(body)),
      sha256 TEXT NOT NULL CHECK(length(sha256)=64)
    ) STRICT; PRAGMA user_version=1;`);
    if (!allowEmpty && !db.prepare('SELECT singleton FROM trade_runtime WHERE singleton=1').get()) fail('STATE_CORRUPT', 'Existing persistent database lost its checkpoint; no new fixture was seeded.');
    if (db.prepare('PRAGMA quick_check').get().quick_check !== 'ok') fail('STATE_CORRUPT', 'State integrity check failed; preserve the file and restore a verified backup.');
  } catch (error) {
    db?.close();
    if (error instanceof StateStoreError) throw error;
    fail('STATE_OPEN_FAILED', 'Persistent state cannot be opened safely. No in-memory fallback was started.');
  }
  const readRow = knownRevision => {
    const metadata = db.prepare('SELECT revision FROM trade_runtime WHERE singleton=1').get();
    if (metadata && metadata.revision === knownRevision) return { revision: metadata.revision, unchanged: true };
    const row = db.prepare('SELECT revision,body,sha256 FROM trade_runtime WHERE singleton=1').get();
    if (!row) { if (!allowEmpty) fail('STATE_CORRUPT', 'Persistent checkpoint disappeared; preserve the database for recovery.'); return null; }
    if (Buffer.byteLength(row.body) > maxBytes || sha(row.body) !== row.sha256) fail('STATE_CORRUPT', 'Stored checkpoint checksum or size is invalid.');
    try { return { revision: row.revision, value: JSON.parse(row.body) }; }
    catch { fail('STATE_CORRUPT', 'Stored checkpoint is not valid JSON.'); }
  };
  return Object.freeze({
    transaction(write, action, { knownRevision } = {}) {
      if (closed) fail('STATE_CLOSED', 'Persistent runtime is closed.');
      try {
        db.exec(write ? 'BEGIN IMMEDIATE' : 'BEGIN');
        const current = readRow(knownRevision);
        const outcome = action(current);
        if (outcome?.then) throw new TypeError('State transactions must not await I/O');
        if (write) {
          const body = JSON.stringify(outcome.state);
          if (Buffer.byteLength(body) > maxBytes) fail('STATE_CAPACITY', 'Local demo state reached its bounded capacity. Preserve or archive it before continuing.');
          db.prepare(`INSERT INTO trade_runtime(singleton,format,revision,body,sha256) VALUES(1,1,?,?,?)
            ON CONFLICT(singleton) DO UPDATE SET revision=excluded.revision,body=excluded.body,sha256=excluded.sha256`)
            .run((current?.revision ?? 0) + 1, body, sha(body));
          beforeCommit?.(); // local fault-injection seam; never accepted from HTTP.
        }
        db.exec('COMMIT');
        if (write) allowEmpty = false;
        return { value: outcome.value, revision: (current?.revision ?? 0) + (write ? 1 : 0) };
      } catch (error) {
        if (db.isTransaction) db.exec('ROLLBACK');
        if (/SQLITE_BUSY|database is locked/i.test(String(error.code) + ' ' + error.message)) {
          fail('STATE_BUSY', 'Another local writer is busy. Retry the same command key after the bounded delay.', true);
        }
        throw error;
      }
    },
    read() { return this.transaction(false, row => ({ value: row } )).value; },
    async backup(destination) {
      const target = privateFile(destination, { mustBeNew: true }).path;
      await backup(db, target);
      const copy = new DatabaseSync(target, { readOnly: true });
      try {
        if (copy.prepare('PRAGMA quick_check').get().quick_check !== 'ok') fail('BACKUP_INVALID', 'Backup integrity check failed.');
      } finally { copy.close(); }
      return { format: 1, integrity: 'ok', storage: 'LOCAL_SYNTHETIC_SQLITE', secrets: 'PRIVATE_DEMO_KEYS_INCLUDED_KEEP_LOCAL' };
    },
    close() { if (!closed) { db.close(); closed = true; } },
  });
}
