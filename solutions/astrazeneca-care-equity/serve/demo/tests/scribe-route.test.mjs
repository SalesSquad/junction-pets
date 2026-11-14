// POST /api/scribe (web/serve.mjs) and the demo render function (web/scribe-demo.mjs). No model is loaded: the live
// path runs against serve/demo/tests/fake-worker.mjs, the fallback against data/scribe/demo/demo-outputs.json.
// Run: node --test serve/demo/tests/
import test from 'node:test';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {scribeDemoHtml, highlightNote} from '../../../web/scribe-demo.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const fake = path.join(root, 'serve/demo/tests/fake-worker.mjs');
const outputs = JSON.parse(readFileSync(path.join(root, 'data/scribe/demo/demo-outputs.json'), 'utf8'));
const notes = JSON.parse(readFileSync(path.join(root, 'data/scribe/demo/demo-notes.json'), 'utf8'));
const BANNED = ['auto-confirmed', 'skips review', 'skip review', 'clinically accurate', 'works on real notes', 'hospital-grade'];

async function startServer(env) {
  const proc = spawn(process.execPath, [path.join(root, 'web/serve.mjs')], {env: {...process.env, PORT: '0', ...env}, stdio: ['ignore', 'pipe', 'inherit']});
  const port = await new Promise((resolve, reject) => {
    proc.stdout.on('data', (d) => { const m = /127\.0\.0\.1:(\d+)/.exec(String(d)); if (m) resolve(Number(m[1])); });
    proc.on('exit', (c) => reject(new Error(`server exited ${c}`)));
  });
  const post = async (body, raw = false) => {
    const r = await fetch(`http://127.0.0.1:${port}/api/scribe`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: raw ? body : JSON.stringify(body)});
    return {status: r.status, body: await r.json()};
  };
  return {proc, port, post, stop: () => new Promise((r) => { proc.on('exit', r); proc.kill(); })};
}

test('fallback only: demo ids return the stored CPU output; free text has no fallback', async () => {
  const s = await startServer({SAMA_SCRIBE_LIVE: '0'});
  try {
    const a = await s.post({demo_id: 'demo-01'});
    assert.equal(a.status, 200);
    assert.equal(a.body.served, 'precomputed');
    assert.match(a.body.fallback_reason, /SAMA_SCRIBE_LIVE=0/);
    assert.equal(a.body.person_confirms, 'a person confirms every event');
    assert.deepEqual(a.body.result.resolved, outputs.results['demo-01'].resolved);
    assert.ok(a.body.result.highlights.some((h) => h.phrase === 'kolme viikkoa sitten' && h.kind === 'relative'));
    const b = await s.post({note_text: 'Lähete lähetettiin eilen.', note_date: '2025-03-10'});
    assert.equal(b.status, 503);
    assert.equal(b.body.status, 'UNAVAILABLE');
    assert.equal((await s.post({demo_id: 'demo-03', mode: 'precomputed'})).body.served, 'precomputed');
  } finally { await s.stop(); }
});

test('input validation', async () => {
  const s = await startServer({SAMA_SCRIBE_LIVE: '0'});
  try {
    assert.equal((await s.post({demo_id: 'demo-99'})).status, 404);
    assert.equal((await s.post({demo_id: '../../etc'})).status, 404);
    assert.equal((await s.post({note_text: 'x', note_date: '2025-02-30'})).status, 400);
    assert.equal((await s.post({note_text: '', note_date: '2025-02-03'})).status, 400);
    assert.equal((await s.post({note_text: 'x'.repeat(6001), note_date: '2025-02-03'})).status, 400);
    assert.equal((await s.post({demo_id: 'demo-01', mode: 'fast'})).status, 400);
    assert.equal((await s.post([1, 2])).status, 400);
    assert.equal((await s.post('{not json', true)).status, 400);
    const health = await fetch(`http://127.0.0.1:${s.port}/api/health`);
    assert.equal(health.status, 200);
  } finally { await s.stop(); }
});

test('live path talks to one persistent process and adds the answer key for demo notes', async () => {
  const s = await startServer({SAMA_SCRIBE_PYTHON: process.execPath, SAMA_SCRIBE_WORKER: fake});
  try {
    const a = await s.post({note_text: 'Lähete lähetettiin eilen.', note_date: '2025-03-10'});
    assert.equal(a.status, 200);
    assert.equal(a.body.served, 'live');
    assert.equal(a.body.result.note.note_text, 'Lähete lähetettiin eilen.');
    assert.equal(a.body.result.synthetic_note, null);
    const b = await s.post({demo_id: 'demo-19'});
    assert.equal(b.body.served, 'live');
    assert.equal(b.body.result.synthetic_note, true);
    assert.equal(b.body.result.note.note_text, notes.notes.find((n) => n.demo_id === 'demo-19').note_text);
    assert.deepEqual(b.body.result.answer_key, notes.notes.find((n) => n.demo_id === 'demo-19').answer_key);
    assert.equal(typeof b.body.result.exact_match_with_answer_key, 'boolean');
    assert.equal((await s.post({note_text: 'bad', note_date: '2025-03-10'})).status, 400); // worker input error
    const boom = await s.post({note_text: 'boom', note_date: '2025-03-10'});
    assert.equal(boom.status, 503); // worker failure on free text: no fallback
  } finally { await s.stop(); }
});

test('a process that dies or never starts falls back to the stored output', async () => {
  for (const mode of ['crash', 'nostart']) {
    const s = await startServer({SAMA_SCRIBE_PYTHON: process.execPath, SAMA_SCRIBE_WORKER: fake, FAKE_MODE: mode});
    try {
      const a = await s.post({demo_id: 'demo-02'}); // starts the process on first use
      assert.equal(a.status, 200);
      if (mode === 'nostart') { assert.equal(a.body.served, 'precomputed'); assert.match(a.body.fallback_reason, /base model/); }
      await new Promise((r) => setTimeout(r, 300)); // the crashing process has exited by now
      const b = await s.post({demo_id: 'demo-02'});
      assert.equal(b.status, 200);
      assert.equal(b.body.served, 'precomputed');
      assert.deepEqual(b.body.result.resolved, outputs.results['demo-02'].resolved);
    } finally { await s.stop(); }
  }
});

test('render: note, highlighted phrases, model output, computed dates and the person-confirms line', () => {
  for (const [id, result] of Object.entries(outputs.results)) {
    const html = scribeDemoHtml({served: 'precomputed', result});
    assert.match(html, /A person confirms every event\./, id);
    assert.match(html, /SYNTHETIC/, id);
    assert.match(html, /What Gemma wrote/, id);
    for (const h of result.highlights) assert.ok(html.includes(`>${h.phrase.replace(/&/g, '&amp;')}</mark>`), `${id}: ${h.phrase}`);
    for (const e of result.resolved.events) if (e.date_computed_by_code) assert.match(html, /counted back from the note date/, id);
    for (const word of BANNED) assert.ok(!html.toLowerCase().includes(word), `${id}: ${word}`);
  }
  const one = scribeDemoHtml({served: 'precomputed', result: outputs.results['demo-01']});
  assert.match(one, /kolme viikkoa sitten<\/mark> <small>\(= 13\.6\.2026, computed by code\)<\/small>/);
  assert.match(one, /<s>11\.2\.2026<\/s>/);
});

test('render escapes text and survives an empty or failed response', () => {
  const html = highlightNote('<script>x</script> 3 viikkoa sitten', [{start: 19, end: 35, kind: 'relative', date: '2025-01-01', days_before_note: 21}, {start: 0, end: 400, kind: 'absolute'}]);
  assert.ok(!html.includes('<script>'));
  assert.match(html, /&lt;script&gt;/);
  assert.match(html, /<mark data-kind="relative"[^>]*> ?3 viikkoa sitten<\/mark>/);
  assert.match(scribeDemoHtml({status: 'UNAVAILABLE', error: 'live scribe timed out'}), /no result to show: live scribe timed out\. A person confirms every event\./);
  assert.match(scribeDemoHtml(null), /A person confirms every event/);
});

test('stored outputs and the payload never use banned wording', () => {
  const text = JSON.stringify(outputs).toLowerCase() + JSON.stringify(notes).toLowerCase();
  for (const word of BANNED) assert.ok(!text.includes(word), word);
});
