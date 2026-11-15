/**
 * Local OCR (Apple Vision via a small Swift helper). macOS only; zero model cost.
 * Results are cached per image digest in the private cache directory.
 */
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdir, readFile, stat, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
import { CACHE } from './dataset.mjs';

const SOURCE = fileURLToPath(new URL('./ocr/vision-ocr.swift', import.meta.url));
const BIN = join(CACHE, 'bin', 'vision-ocr');

export const ocrAvailable = () => process.platform === 'darwin';

async function binary() {
  const [src, bin] = await Promise.all([stat(SOURCE), stat(BIN).catch(() => null)]);
  if (!bin || bin.mtimeMs < src.mtimeMs) {
    await mkdir(join(CACHE, 'bin'), { recursive: true });
    execFileSync('swiftc', ['-O', SOURCE, '-o', BIN], { stdio: 'ignore', timeout: 300_000 });
  }
  return BIN;
}

export async function ocr(imagePath) {
  const digest = createHash('sha256').update(await readFile(imagePath)).update(await readFile(SOURCE)).digest('hex');
  const cachePath = join(CACHE, 'ocr', `${digest}.json`);
  try { return JSON.parse(await readFile(cachePath, 'utf8')); } catch { /* not cached */ }
  const raw = execFileSync(await binary(), [imagePath], { encoding: 'utf8', timeout: 180_000, maxBuffer: 32 * 1024 * 1024 });
  const tokens = dedupe(JSON.parse(raw));
  await mkdir(join(CACHE, 'ocr'), { recursive: true });
  await writeFile(cachePath, JSON.stringify(tokens));
  return tokens;
}

const area = b => Math.max(0, b[2] - b[0]) * Math.max(0, b[3] - b[1]);
export function iou(a, b) {
  const i = area([Math.max(a[0], b[0]), Math.max(a[1], b[1]), Math.min(a[2], b[2]), Math.min(a[3], b[3])]);
  return i / (area(a) + area(b) - i || 1);
}
const center = b => [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2];

/** Merge repeated reads of the same text from rotations/tiles; keep the most confident. */
export function dedupe(tokens) {
  const kept = [];
  for (const t of [...tokens].sort((a, b) => b.conf - a.conf)) {
    const c = center(t.box);
    const dup = kept.some(k => {
      const kc = center(k.box);
      return iou(k.box, t.box) > 0.3 || (Math.abs(kc[0] - c[0]) < 0.012 && Math.abs(kc[1] - c[1]) < 0.012);
    });
    if (!dup) kept.push({ text: t.text, conf: +t.conf.toFixed(3), box: t.box.map(v => +v.toFixed(4)) });
  }
  return kept.map((t, i) => ({ id: `t${i + 1}`, ...t }));
}
