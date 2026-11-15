#!/usr/bin/env node
import { open, constants } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { LIMITS, IntakeError, refuse } from './intake.mjs';
import { DEMO_ENROLLMENT, demoReplay, replayText } from './replay.mjs';

const USAGE = 'Usage: node device-proof/cli.mjs demo|fixture positive|negative | replay FILE.ndjson STREAM_ID CLOCK_ID';

// No writes; no symlinks, pipes or devices; bound the actual read as well as stat
// to cover a file growing after inspection. Never echo a path or OS error.
async function readLocalFile(path) {
  let handle;
  try {
    handle = await open(path, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
    const info = await handle.stat();
    if (!info.isFile() || info.size > LIMITS.replayBytes) refuse('LOCAL_FILE_TYPE_OR_SIZE');
    const bytes = Buffer.alloc(LIMITS.replayBytes + 1);
    let size = 0;
    while (size < bytes.length) {
      const result = await handle.read(bytes, size, bytes.length - size, null);
      if (!result.bytesRead) break;
      size += result.bytesRead;
    }
    if (size > LIMITS.replayBytes) refuse('LOCAL_FILE_TYPE_OR_SIZE');
    try { return new TextDecoder('utf-8', { fatal: true }).decode(bytes.subarray(0, size)); }
    catch { refuse('INVALID_UTF8'); }
  } catch (error) {
    if (error instanceof IntakeError) throw error;
    refuse('LOCAL_INPUT_UNREADABLE');
  } finally { await handle?.close(); }
}

export async function runCli(args) {
  if (args.length === 2 && args[0] === 'fixture' && ['positive', 'negative'].includes(args[1])) return demoReplay(args[1]);
  if (args.length === 2 && args[0] === 'demo' && ['positive', 'negative'].includes(args[1])) {
    return { source: 'DEMO_FIXTURE_NOT_HARDWARE', ...replayText(demoReplay(args[1]), DEMO_ENROLLMENT) };
  }
  if (args.length === 4 && args[0] === 'replay') {
    return { source: 'LOCAL_USER_FILE', ...replayText(await readLocalFile(args[1]), {
      streamId: args[2], clockId: args[3],
    }) };
  }
  refuse('CLI_ARGUMENTS');
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    const result = await runCli(process.argv.slice(2));
    process.stdout.write(typeof result === 'string' ? result : JSON.stringify(result, null, 2) + '\n');
  }
  catch (error) {
    console.error(error instanceof IntakeError ? error.message : 'Telemetry intake refused: INTERNAL_ERROR');
    if (error?.code === 'CLI_ARGUMENTS') console.error(USAGE);
    process.exitCode = error?.code === 'CLI_ARGUMENTS' ? 2 : 1;
  }
}
