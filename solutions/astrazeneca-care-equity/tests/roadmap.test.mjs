import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFileSync, spawnSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { INTERVENTIONS } from '../src/recommend.mjs';
import { analyse } from '../src/analysis.mjs';
import { MANIFEST, ROADMAP, getPilotCard, getRoadmapMeasure, getThresholdRelabels, listActionIds } from '../src/roadmap.mjs';

const at = (p) => new URL(p, import.meta.url);
const sha256 = (buf) => createHash('sha256').update(buf).digest('hex');
const norm = (s) => s.replace(/­/g, '').replace(/\s+/g, ' ').trim();
const TEXT = readFileSync(at('../data/roadmap/roadmap.txt'));
const PAGES = TEXT.toString('utf8').split('\f').map(norm);
const ROADMAP_CLI = fileURLToPath(at('../src/roadmap.mjs'));

// Every { fi, page } object anywhere in the mapping, with its JSON path.
function quotes(node, path = '$', out = []) {
  if (Array.isArray(node)) node.forEach((v, i) => quotes(v, `${path}[${i}]`, out));
  else if (node && typeof node === 'object') {
    if (typeof node.fi === 'string') out.push({ path, fi: node.fi, page: node.page });
    for (const [k, v] of Object.entries(node)) quotes(v, `${path}.${k}`, out);
  }
  return out;
}
function strings(node, key = '', out = []) {
  if (Array.isArray(node)) node.forEach((v) => strings(v, key, out));
  else if (node && typeof node === 'object') for (const [k, v] of Object.entries(node)) strings(v, k, out);
  else if (typeof node === 'string') out.push({ key, value: node });
  return out;
}

test('the pdftotext output is the pinned one, and the PDF (when present) matches its sha256', () => {
  assert.equal(sha256(TEXT), MANIFEST.text.sha256);
  assert.equal(PAGES.length, MANIFEST.pdf.pages + 1, 'one form feed per page');
  assert.equal(ROADMAP.sourceSha256, MANIFEST.pdf.sha256);
  const pdf = at(`../${MANIFEST.pdf.file}`);
  if (existsSync(pdf)) assert.equal(sha256(readFileSync(pdf)), MANIFEST.pdf.sha256);
});

test('the pdftotext output can be regenerated from the PDF when the same pdftotext version is installed', (t) => {
  const pdf = fileURLToPath(at(`../${MANIFEST.pdf.file}`));
  let version = '';
  try { version = spawnSync('pdftotext', ['-v'], { encoding: 'utf8' }).stderr || ''; } catch { version = ''; }
  const wanted = MANIFEST.text.tool.match(/pdftotext version [\d.]+/)[0];
  if (!existsSync(pdf) || !version.includes(wanted)) { t.skip(`needs the PDF and ${wanted}`); return; }
  const out = execFileSync('pdftotext', ['-enc', 'UTF-8', pdf, '-'], { maxBuffer: 16 * 1024 * 1024 });
  assert.equal(sha256(out), MANIFEST.text.sha256);
});

test('every quoted Finnish phrase occurs, word for word, on its stated page of the pdftotext output', () => {
  const all = quotes(ROADMAP);
  assert.ok(all.length >= 100, `expected the full quote set, got ${all.length}`);
  const missing = all.filter((q) => !Number.isInteger(q.page) || !PAGES[q.page - 1]?.includes(norm(q.fi)));
  assert.deepEqual(missing.map((q) => `${q.path} p.${q.page}: ${q.fi.slice(0, 70)}`), []);
});

test('Finnish text appears only inside verifiable quote fields', () => {
  const stray = strings(ROADMAP).filter(({ key, value }) => key !== 'fi' && key !== 'nameFi' && /[äöÄÖ]/.test(value));
  assert.deepEqual(stray, []);
});

test('every measure carries its heading on its first page, an owner, a schedule and a page number', () => {
  for (const [id, m] of Object.entries(ROADMAP.measures)) {
    assert.equal(m.id, id);
    assert.ok(m.heading.fi.startsWith(`Toimenpide ${id} `), id);
    assert.equal(m.heading.page, m.pages[0], id);
    assert.ok(m.owner?.fi && m.owner_en, `${id} owner`);
    assert.ok(m.schedule.length >= 1, `${id} schedule`);
    assert.ok(m.metrics.length >= 1 || m.metricsNote, `${id} metric or an explicit note`);
    for (const q of quotes(m)) assert.ok(m.pages.includes(q.page) || q.path.includes('resourceShared'), `${id} quote page ${q.page} outside ${m.pages}`);
  }
});

test('all 8 INTERVENTIONS and the four-timestamp proposal map to a roadmap measure with a page, or say "no roadmap measure"', () => {
  const ids = INTERVENTIONS.map((i) => i.id);
  assert.equal(ids.length, 8);
  for (const id of [...ids, 'four-timestamps']) {
    const r = getRoadmapMeasure(id);
    assert.equal(r.error, undefined, id);
    assert.ok(['named', 'serves', 'none'].includes(r.fit), id);
    if (r.fit === 'none') { assert.equal(r.statement, 'no roadmap measure'); continue; }
    assert.ok(Number.isInteger(r.primaryMeasure.pages[0]), id);
    assert.ok(r.primaryMeasure.owner.fi.length > 0 && r.primaryMeasure.schedule.length > 0, id);
    for (const rel of r.relatedMeasures) assert.ok(ROADMAP.measures[rel.id], `${id} -> ${rel.id}`);
    assert.ok(r.reading_en && r.gap_en, id);
  }
  assert.deepEqual(new Set(listActionIds()), new Set([...ids, 'four-timestamps']));
  assert.equal(getRoadmapMeasure('core-four').actionId, 'four-timestamps');
});

test('the four measures named by the earlier reading are re-checked against the text', () => {
  const checked = new Map(ROADMAP.earlierReadingCheck.map((c) => [c.measure, c]));
  for (const id of ['2.5.2', '3.1.4', '3.2.1', '3.2.2']) {
    assert.ok(ROADMAP.measures[id], id);
    assert.ok(checked.get(id)?.quotes.length >= 1, `${id} re-check has quotes`);
  }
  assert.equal(getRoadmapMeasure('timed-pathways').primaryMeasure.id, '3.1.2');
  assert.equal(getRoadmapMeasure('3.2.2').measure.resource.fi, 'Arvioitu tarvittava määräraha 300 000 €.');
});

test('target-time thresholds are relabelled as placeholders tied to 3.1.2 and 3.1.4', () => {
  const r = getThresholdRelabels();
  assert.ok(r.length >= 3);
  for (const x of r) {
    assert.match(x.relabel_en, /placeholder|not yet defined/i);
    assert.ok(x.measures.every((m) => ROADMAP.measures[m]));
    assert.ok(x.actions.every((a) => listActionIds().includes(a)));
  }
  assert.ok(r.some((x) => x.currentValues.primary_care === 90 && x.measures.includes('3.1.4')));
});

test('the Satakunta pilot card is the default, states the language scope and recomputes from the snapshot', () => {
  const card = getPilotCard();
  assert.equal(card.county.id, 'HVA06');
  assert.equal(card.choice, 'default, owner may change');
  assert.match(card.languageScope_en, /Finnish notes only/);
  assert.match(card.languageScope_en, /manual entry/);
  assert.match(card.humanReview_en, /confirms every extracted event/);
  assert.match(card.dataNote_en, /SYNTHETIC/);
  const snap = readFileSync(at('../data/snapshot/public-v1.json'));
  const e = card.snapshotEvidence;
  assert.equal(sha256(snap), e.sourceSha256);
  const all = analyse(JSON.parse(snap.toString('utf8'))).mortality.all_cancers;
  const row = all.rows.find((x) => x.regionId === 'HVA06');
  for (const k of ['observed', 'expected', 'smr', 'smrLow', 'smrHigh', 'shrunk', 'shrunkLow', 'shrunkHigh']) assert.equal(row[k], e[k], k);
  assert.deepEqual(all.window, e.window);
  const ranked = all.rows.filter((x) => !x.suppressed).sort((a, b) => b.shrunk - a.shrunk);
  assert.equal(ranked.findIndex((x) => x.regionId === 'HVA06') + 1, e.rankByShrunk);
  assert.equal(ranked.length, e.ofCounties);
  assert.equal(e.shrunk.toFixed(2), '1.10');
  for (const h of card.roadmapHooks) assert.ok(ROADMAP.measures[h.measure], h.measure);
});

test('no wording claims automation without a person or clinical accuracy', () => {
  const text = readFileSync(at('../data/roadmap/mapping-v1.json'), 'utf8') + readFileSync(at('../src/roadmap.mjs'), 'utf8');
  for (const banned of ['auto-confirmed', 'skips review', 'skip review', 'clinically accurate', 'works on real notes', 'hospital-grade']) {
    assert.equal(text.toLowerCase().includes(banned), false, banned);
  }
});

test('the CLI prints JSON for an action, a measure and the pilot, and fails cleanly on an unknown id', () => {
  const run = (...args) => spawnSync(process.execPath, [ROADMAP_CLI, ...args], { encoding: 'utf8' });
  const ok = run('ai-mammography');
  assert.equal(ok.status, 0);
  const a = JSON.parse(ok.stdout);
  assert.equal(a.primaryMeasure.id, '2.4.2');
  assert.match(a.primaryMeasure.url, /#page=48$/);
  assert.equal(JSON.parse(run('3.1.4').stdout).measure.pages[0], 58);
  assert.equal(JSON.parse(run('pilot').stdout).county.id, 'HVA06');
  const bad = run('no-such-action');
  assert.equal(bad.status, 2);
  assert.equal(JSON.parse(bad.stdout).error, 'unknown action');
  assert.equal(run().status, 2);
});
