import { spawnSync } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { pathToFileURL } from 'node:url';
import { PRODUCT_SOURCE_DIGEST } from './source-meta.mjs';

// Canonical manifest v1: sorted relative POSIX paths, UTF-8 path + NUL +
// lowercase SHA256(raw file bytes) + LF per file. Hash the UTF-8 manifest.
export const PRODUCT_SOURCE_FILES = Object.freeze([
  'cala-contract.d.ts', 'cala-contract.mjs', 'core.mjs', 'fixture.mjs',
  'public/app.mjs', 'public/index.html', 'public/style.css', 'server.mjs'
]);
export async function computeSourceDigest(root = new URL('./', import.meta.url)) {
  const entries = await Promise.all([...PRODUCT_SOURCE_FILES].sort().map(async path =>
    `${path}\0${createHash('sha256').update(await readFile(new URL(path, root))).digest('hex')}\n`));
  return createHash('sha256').update(entries.join(''), 'utf8').digest('hex');
}
export async function verifySourceDigest(root = new URL('./', import.meta.url)) {
  const actual = await computeSourceDigest(root);
  if (actual !== PRODUCT_SOURCE_DIGEST) throw Error(`Stale productSourceDigest: metadata=${PRODUCT_SOURCE_DIGEST}; current=${actual}`);
  return actual;
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await verifySourceDigest();
  for (const file of [...PRODUCT_SOURCE_FILES.filter(path => path.endsWith('.mjs')), 'source-meta.mjs']) {
    const r = spawnSync(process.execPath,['--check',new URL(file,import.meta.url).pathname],{stdio:'inherit'});
    if (r.status !== 0) process.exit(r.status ?? 1);
  }
  for (const file of ['public/index.html','public/style.css']) if (!(await readFile(new URL(file,import.meta.url))).length) throw Error(`Empty asset: ${file}`);
  console.log('Build verified: current product source digest, native ES modules and static assets; no generated bundle or dependencies.');
}
