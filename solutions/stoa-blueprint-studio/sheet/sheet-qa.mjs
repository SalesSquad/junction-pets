/**
 * Sheet context: answer questions about a whole construction sheet (schedules, notes, plans).
 * The sheet's text comes from the PDF text layer (exact) or, for raster sheets, from local OCR;
 * text is merged into lines with ids and positions. A vision model gets the sheet image plus the
 * lines, answers, and cites line ids, so every answer maps back to exact boxes on the sheet.
 */
import { execFileSync } from 'node:child_process';
import { mkdir, readFile, stat } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
import { CACHE } from '../raster/dataset.mjs';
import { chat, imageDataUrl } from '../raster/vlm.mjs';
import { ocr } from '../raster/ocr.mjs';

const SRC = fileURLToPath(new URL('./pdf-sheet.swift', import.meta.url));
const BIN = join(CACHE, 'bin', 'pdf-sheet');

async function helper() {
  const [s, b] = await Promise.all([stat(SRC), stat(BIN).catch(() => null)]);
  if (!b || b.mtimeMs < s.mtimeMs) { await mkdir(join(CACHE, 'bin'), { recursive: true }); execFileSync('swiftc', ['-O', SRC, '-o', BIN], { stdio: 'ignore', timeout: 300_000 }); }
  return BIN;
}

/** Merge word boxes into reading lines: same row (vertical overlap) and small horizontal gaps. */
export function toLines(words) {
  const ws = words.filter(w => w.text.trim()).map(w => ({ ...w, cy: (w.box[1] + w.box[3]) / 2, h: w.box[3] - w.box[1] }));
  const hs = ws.map(w => w.h).sort((a, b) => a - b);
  const mh = hs[Math.floor(hs.length / 2)] || 0.005;
  ws.sort((a, b) => a.cy - b.cy || a.box[0] - b.box[0]);
  const rows = [];
  for (const w of ws) {
    const row = rows.find(r => Math.abs(r.cy - w.cy) < mh * 0.5);
    if (row) row.items.push(w); else rows.push({ cy: w.cy, items: [w] });
  }
  // Words → cells (small gaps, joined by a space) → row segments (table cells joined by " | ";
  // a gap wider than 6 % of the sheet starts a new segment, e.g. the next table on the sheet).
  const lines = [];
  for (const r of rows) {
    r.items.sort((a, b) => a.box[0] - b.box[0]);
    let cur = null;
    for (const w of r.items) {
      const gap = cur ? w.box[0] - cur.box[2] : Infinity;
      if (gap < 0.06) {
        cur.text += gap < mh * 1.2 ? (gap > mh * 0.15 ? ' ' : '') + w.text : ` | ${w.text}`;
        cur.box[2] = Math.max(cur.box[2], w.box[2]); cur.box[3] = Math.max(cur.box[3], w.box[3]); cur.box[1] = Math.min(cur.box[1], w.box[1]);
      } else { cur = { text: w.text, box: [...w.box] }; lines.push(cur); }
    }
  }
  return lines.map((l, i) => ({ id: `L${i + 1}`, ...l }));
}

/** Load a sheet (PDF or image): rendered image for the model + text lines with boxes. */
/**
 * textSource 'auto' uses the PDF text layer when present, else OCR. 'ocr' ignores the text layer
 * (the screenshot situation): the sheet is rendered at ocrPx and read by ocrFn (default: local
 * tiled Vision OCR), so OCR engines can be compared on the same sheets.
 */
export async function loadSheet(path, { maxPx = 3584, textSource = 'auto', ocrFn = ocr, ocrPx = 7168, label = 'local-ocr' } = {}) {
  const key = createHash('sha256').update(await readFile(path)).digest('hex').slice(0, 24);
  const img = join(CACHE, 'sheets', `${key}.jpg`);
  await mkdir(join(CACHE, 'sheets'), { recursive: true });
  let words = [], source, ocrInput = path;
  if (/\.pdf$/i.test(path)) {
    const out = JSON.parse(execFileSync(await helper(), [path, img, String(maxPx)], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024, timeout: 120_000 }));
    if (textSource !== 'ocr') { words = out.words; source = 'pdf-text-layer'; }
    if (!words.length) {
      ocrInput = join(CACHE, 'sheets', `${key}.${ocrPx}.jpg`);
      execFileSync(await helper(), [path, ocrInput, String(ocrPx)], { stdio: 'ignore', maxBuffer: 64 * 1024 * 1024, timeout: 120_000 });
    }
  } else {
    execFileSync('sips', ['-s', 'format', 'jpeg', '-s', 'formatOptions', '75', '-Z', String(maxPx), path, '--out', img], { stdio: 'ignore' });
  }
  if (!words.length) { words = (await ocrFn(ocrInput)).map(t => ({ text: t.text, box: t.box })); source = label; }
  return { path, image: await imageDataUrl(img), lines: toLines(words), source };
}

const SYSTEM = `You answer questions about one construction drawing sheet (plans, schedules, notes, title block).
You get the sheet image and, when available, its text lines as "id|text|x|y" (x,y = line centre, 0..1000, origin top-left).
Schedules are tables: a row is the set of lines with about the same y; columns align by x. Treat the text lines as the
authoritative reading of characters and the image as layout. Count carefully row by row; for sums add the listed values.
Reply with only JSON: {"answer": string|number, "evidence": [line ids that support the answer], "note": short string}.`;

export async function askSheet(sheet, question, cfg, { withText = true, maxTokens = 24000 } = {}) {
  const lines = withText ? sheet.lines.map(l => `${l.id}|${l.text}|${Math.round((l.box[0] + l.box[2]) * 500)}|${Math.round((l.box[1] + l.box[3]) * 500)}`).join('\n') : '';
  const text = withText ? `Question: ${question}\n\nText lines (${sheet.lines.length}):\n${lines}` : `Question: ${question}`;
  const r = await chat({ system: SYSTEM, text, images: [sheet.image.url], maxTokens, thinking: true, temperature: 0.2 }, cfg);
  const ids = new Set(Array.isArray(r.json?.evidence) ? r.json.evidence.map(String) : []);
  return { answer: r.json?.answer ?? null, note: r.json?.note, evidence: sheet.lines.filter(l => ids.has(l.id)).map(l => ({ id: l.id, text: l.text, box: l.box })),
    call: { ok: r.ok, finish: r.finish, ms: r.ms, usage: r.usage, attempts: r.attempts } };
}
