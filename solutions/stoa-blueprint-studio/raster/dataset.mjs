/**
 * Local cache + deterministic held-out split for raster evaluation.
 * Drawings and questions stay in a private cache directory, never in git.
 */
import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile, access } from 'node:fs/promises';
import { homedir } from 'node:os';
import { join, dirname } from 'node:path';
import { openPreview } from './preview-zip.mjs';

export const CACHE = process.env.STOA_CACHE || join(homedir(), '.cache', 'stoa-junction-preview');
const SPLIT_SALT = 'stoa-raster-split-v1';

const exists = p => access(p).then(() => true, () => false);
let zip;
async function archive() { return (zip ??= await openPreview()); }

export async function cached(path) {
  const dst = join(CACHE, path);
  if (!(await exists(dst))) {
    const data = await (await archive()).read(path);
    await mkdir(dirname(dst), { recursive: true });
    await writeFile(dst, data, { mode: 0o600 });
  }
  return dst;
}

export async function loadQuestions() {
  const text = await readFile(await cached('questions.jsonl'), 'utf8');
  return text.split('\n').filter(Boolean).map(l => JSON.parse(l));
}

/** Language filter: the preview pairs each English question with a translation. */
export const isEnglish = q => !/[äöåÄÖÅ]|Kuinka|Montako|Wie |Combien|Quanti|Quante|Kui /.test(q.question);

/**
 * Self-made held-out split (the sponsor's final test protocol is unpublished):
 * drawings sorted by salted SHA-256 of their path; first `dev` are tuning,
 * the next `test` are untouched held-out. Prompt changes are tuned on dev only.
 */
export function split(paths, { dev = 8, test = 16 } = {}) {
  const order = [...new Set(paths)].sort((a, b) => key(a).localeCompare(key(b)));
  return { dev: order.slice(0, dev), test: order.slice(dev, dev + test) };
  function key(p) { return createHash('sha256').update(`${SPLIT_SALT}|${p}`).digest('hex'); }
}
