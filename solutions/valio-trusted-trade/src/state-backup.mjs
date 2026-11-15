/** Explicit private backup; never overwrites files or resets the active store. */
import { lstatSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { openLocalStateStore } from './local-state-store.mjs';

export async function backupLocalState(source, destination) {
  if (!lstatSync(source).isFile()) throw new Error('Backup source must be an existing local state file.');
  const store = openLocalStateStore(source);
  try {
    if (!store.read()) throw new Error('Backup source has no committed checkpoint.');
    return await store.backup(destination);
  } finally { store.close(); }
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  if (args.length !== 4 || args[0] !== '--state' || args[2] !== '--output') {
    throw new Error('Usage: npm run state:backup -- --state /private/path/state.sqlite --output /private/path/new-backup.sqlite');
  }
  try { process.stdout.write(JSON.stringify(await backupLocalState(args[1], args[3])) + '\n'); }
  catch (error) { process.stderr.write(JSON.stringify({ code: error.code ?? 'BACKUP_FAILED', message: 'Backup failed safely; inspect the private paths and preserve the source.' }) + '\n'); process.exitCode = 1; }
}
