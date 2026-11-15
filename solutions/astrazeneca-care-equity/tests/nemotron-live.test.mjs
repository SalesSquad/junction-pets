// POST /api/scribe/second (web/serve.mjs): the live Nemotron second reader of the scribe demo, its stored fallback and
// the page's use of the two-reader rule (web/scribe-demo.mjs withSecondCall, secondCallHtml, applySecondReader).
// No paid call: the helper is serve/demo/tests/fake-nemotron.mjs, or the real serve/demo/nemotron_live.py against a
// local fake OpenAI-compatible endpoint started here. The key used is a dummy string that must never come back.
import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {spawn, spawnSync} from 'node:child_process';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {applySecondReader, withSecondCall, secondCallHtml, scribeDemoHtml} from '../web/scribe-demo.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const fake = path.join(root, 'serve/demo/tests/fake-nemotron.mjs');
const outputs = JSON.parse(readFileSync(path.join(root, 'data/scribe/demo/demo-outputs.json'), 'utf8'));
const notes = JSON.parse(readFileSync(path.join(root, 'data/scribe/demo/demo-notes.json'), 'utf8'));
const DUMMY_KEY = 'dummy-key-for-tests-0000';
const BANNED = ['auto-confirmed', 'skips review', 'skip review', 'clinically accurate', 'works on real notes', 'hospital-grade'];
const PRE = 'pre-filled for one-click confirmation';
const clone = (x) => JSON.parse(JSON.stringify(x));

async function startServer(env) {
  const base = {...process.env};
  for (const k of ['VERDA_INFERENCE_BASE_URL', 'VERDA_INFERENCE_KEY', 'SAMA_NEMOTRON_LIVE', 'SAMA_NEMOTRON_HELPER', 'SAMA_NEMOTRON_PYTHON', 'SAMA_NEMOTRON_TIMEOUT_MS']) delete base[k];
  const proc = spawn(process.execPath, [path.join(root, 'web/serve.mjs')], {env: {...base, PORT: '0', SAMA_SCRIBE_LIVE: '0', ...env}, stdio: ['ignore', 'pipe', 'inherit']});
  const port = await new Promise((resolve, reject) => {
    proc.stdout.on('data', (d) => { const m = /127\.0\.0\.1:(\d+)/.exec(String(d)); if (m) resolve(Number(m[1])); });
    proc.on('exit', (c) => reject(new Error(`server exited ${c}`)));
  });
  const post = async (body, raw = false) => {
    const r = await fetch(`http://127.0.0.1:${port}/api/scribe/second`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: raw ? body : JSON.stringify(body)});
    const text = await r.text();
    return {status: r.status, body: JSON.parse(text), text};
  };
  return {port, post, stop: () => new Promise((r) => { proc.on('exit', r); proc.kill(); })};
}
const withKey = {VERDA_INFERENCE_BASE_URL: 'http://127.0.0.1:9/v1', VERDA_INFERENCE_KEY: DUMMY_KEY};
const fakeHelper = (mode, extra = {}) => ({...withKey, SAMA_NEMOTRON_PYTHON: process.execPath, SAMA_NEMOTRON_HELPER: fake, FAKE_NEMO: mode, ...extra});

test('live path: the helper answer comes back as served live with model and latency, never the key', async () => {
  const s = await startServer(fakeHelper('agree'));
  try {
    const a = await s.post({demo_id: 'demo-01'}); // rewritten by code: no stored second answer, but a live one
    assert.equal(a.status, 200);
    assert.equal(a.body.served, 'live');
    assert.equal(a.body.model, 'nemotron-3.5-super-vl');
    assert.equal(a.body.version, 'v3');
    assert.equal(a.body.latency_ms, 1234);
    assert.ok(Number.isFinite(a.body.server_ms));
    assert.deepEqual(a.body.prediction, outputs.results['demo-01'].resolved.prediction);
    assert.equal(a.body.person_confirms, 'a person confirms every event');
    assert.match(a.body.how, /^live: Nemotron 3\.5 Super VL \(reader v3\)/);
    assert.ok(!a.text.includes(DUMMY_KEY) && !a.text.includes('saw_key') && !a.text.includes('127.0.0.1:9'), 'no key, no helper internals, no endpoint URL');
  } finally { await s.stop(); }
});

test('stored fallback: switched off, no key, helper failure, garbage and timeout all return the stored answer with a plain reason', async () => {
  const stored = outputs.results['demo-04'].second_reader.prediction;
  const cases = [
    [{...withKey, SAMA_NEMOTRON_LIVE: '0'}, /switched off \(SAMA_NEMOTRON_LIVE=0\)/],
    [{}, /no endpoint key in the server environment/],
    [{VERDA_INFERENCE_BASE_URL: 'http://127.0.0.1:9/v1'}, /no endpoint key/],
    [fakeHelper('fail'), /could not be reached/],
    [fakeHelper('garbage'), /gave no answer/],
    [fakeHelper('hang', {SAMA_NEMOTRON_TIMEOUT_MS: '600'}), /did not finish within 1 s/],
    [{...withKey, SAMA_NEMOTRON_PYTHON: path.join(root, 'no-such-python')}, /could not start/],
  ];
  for (const [env, reason] of cases) {
    const s = await startServer(env);
    try {
      const a = await s.post({demo_id: 'demo-04'});
      assert.equal(a.status, 200, String(reason));
      assert.equal(a.body.served, 'stored', String(reason));
      assert.match(a.body.reason, reason);
      assert.deepEqual(a.body.prediction, stored);
      assert.equal(a.body.source, 'data/scribe/nemotron/val-v3.jsonl');
      assert.ok(!a.text.includes(DUMMY_KEY));
      const b = await s.post({demo_id: 'demo-02'}); // rewritten by code: nothing stored
      assert.equal(b.status, 503);
      assert.equal(b.body.served, 'none');
      assert.equal(b.body.prediction, null);
      assert.match(b.body.reason, reason);
      assert.match(b.body.reason, /no stored second answer for this note \(it was rewritten by code/);
    } finally { await s.stop(); }
  }
});

test('input validation on /api/scribe/second', async () => {
  const s = await startServer({SAMA_NEMOTRON_LIVE: '0'});
  try {
    assert.equal((await s.post({demo_id: 'demo-99'})).status, 404);
    assert.equal((await s.post({demo_id: '../../etc'})).status, 404);
    assert.equal((await s.post({})).status, 404);
    assert.equal((await s.post([1])).status, 400);
    assert.equal((await s.post('{nope', true)).status, 400);
    assert.equal((await s.post(JSON.stringify({demo_id: 'demo-01', pad: 'x'.repeat(5000)}), true).catch(() => ({status: 413}))).status, 413);
  } finally { await s.stop(); }
});

test('two-reader rule on the page: a live answer equal to Gemma pre-fills, a different one needs editing, none changes nothing', () => {
  const shown = {served: 'precomputed', result: clone(outputs.results['demo-01'])}; // rewritten note: needs editing until a second reader answers
  assert.equal(shown.result.review, 'needs editing');
  const gemma = shown.result.resolved.prediction;
  const live = {served: 'live', prediction: clone(gemma), model: 'nemotron-3.5-super-vl', version: 'v3', latency_ms: 4321, calls: 1, how: 'live: Nemotron 3.5 Super VL (reader v3) read this SYNTHETIC note just now on the Verda-hosted endpoint', source: 'Verda-hosted endpoint'};
  const agree = withSecondCall(shown, live);
  assert.equal(agree.result.review, PRE);
  assert.equal(agree.result.second_reader.agrees, true);
  assert.equal(agree.result.review_reason, 'both readers agree exactly');
  assert.match(agree.result.second_reader.how, /4\.3 s$/);
  assert.equal(shown.result.review, 'needs editing', 'the result on screen is not mutated');
  const html = scribeDemoHtml(agree);
  assert.match(html, /Second reader: Nemotron 3\.5 Super VL, asked live/);
  assert.match(html, /Answered in <strong>4\.3 s<\/strong>/);
  assert.match(html, /Same answer as the Gemma answer on screen/);
  assert.match(html, /Two-reader rule: pre-filled for one-click confirmation\. A person confirms every event\./);
  assert.match(html, /Pre-filled for one-click confirmation\. A person confirms every event\./);

  const other = {...live, prediction: {...clone(gemma), events: gemma.events.slice(0, -1)}};
  const disagree = withSecondCall(shown, other);
  assert.equal(disagree.result.review, 'needs editing');
  assert.equal(disagree.result.review_reason, 'readers disagree');
  const dh = scribeDemoHtml(disagree);
  assert.match(dh, /A different answer from the Gemma answer on screen<\/strong>: only Gemma lists Specialist visit 13\.6\.2026/);
  assert.match(dh, /Two-reader rule: needs editing\./);

  const route = withSecondCall(shown, {...live, prediction: {...clone(gemma), entry_route: 'EMERGENCY'}});
  assert.equal(route.result.review, 'needs editing');
  assert.match(scribeDemoHtml(route), /entry route: Gemma Screening, Nemotron Emergency/);

  const unreadable = withSecondCall(shown, {...live, prediction: null});
  assert.equal(unreadable.result.review, 'needs editing');
  assert.match(scribeDemoHtml(unreadable), /could not be read as the expected JSON/);

  const none = withSecondCall(shown, {served: 'none', prediction: null, reason: 'no endpoint key in the server environment; there is no stored second answer for this note'});
  assert.deepEqual(none.result, shown.result);
  assert.match(scribeDemoHtml(none), /No second answer: no endpoint key/);

  // a Gemma answer that already needs editing stays that way even when Nemotron agrees
  const flaggedFirst = {...clone(outputs.results['demo-04']), single_reader_review: 'needs editing'};
  assert.equal(applySecondReader(flaggedFirst, {available: true, prediction: clone(flaggedFirst.resolved.prediction), how: 'live'}).review, 'needs editing');

  // stored fallback on a note that had the stored answer: same verdict as before
  const stored = withSecondCall({served: 'precomputed', result: clone(outputs.results['demo-19'])}, {served: 'stored', reason: 'live Nemotron switched off (SAMA_NEMOTRON_LIVE=0)', prediction: outputs.results['demo-19'].second_reader.prediction, how: 'stored output', source: 'data/scribe/nemotron/val-v3.jsonl'});
  assert.equal(stored.result.review, outputs.results['demo-19'].review);
  assert.match(scribeDemoHtml(stored), /The live call was not used \(live Nemotron switched off/);

  for (const h of [html, dh, scribeDemoHtml(none), scribeDemoHtml(stored), secondCallHtml({served: 'live', prediction: {entry_route: '<b>', events: [{type: '<script>', date: 'x', precision: 'DAY'}]}}, null)]) {
    for (const w of BANNED) assert.ok(!h.toLowerCase().includes(w), w);
    assert.ok(!h.includes('<script>') && !h.includes('<b>'), 'escaped');
  }
});

test('page wiring: the button, its plain-language line and the route', () => {
  const html = readFileSync(path.join(root, 'web/index.html'), 'utf8'), appJs = readFileSync(path.join(root, 'web/app.mjs'), 'utf8');
  const block = html.slice(html.indexOf('<div class="scribe-try"'), html.indexOf('<div id="scribe-content">'));
  assert.match(block, /<button id="demo-second" type="button">Ask Nemotron live \(second reader\)<\/button>/);
  assert.match(block, /sends this SYNTHETIC note to the hosted Nemotron 3\.5 Super VL endpoint\. In a pilot, the second reader runs in a county-controlled environment, and a person confirms every event\./);
  assert.match(appJs, /\/api\/scribe\/second/);
  assert.match(appJs, /withSecondCall\(shown,call\)/);
  for (const w of BANNED) assert.ok(!(block + appJs).toLowerCase().includes(w), w);
});

// The real helper (serve/demo/nemotron_live.py, the frozen v3 protocol) against a local fake endpoint: checks the
// request it sends and that code, not the model, resolves the dates. Skipped when no python3 is on PATH.
const python = process.env.SAMA_NEMOTRON_PYTHON || 'python3';
const hasPython = spawnSync(python, ['-c', 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)']).status === 0;
test('real helper against a fake endpoint: frozen v3 request, one repair retry, dates resolved by code', {skip: !hasPython && 'python3 >= 3.10 not found'}, async () => {
  const seen = [];
  const answer = '{"entry_route":"PRIVATE","events":[{"type":"REFERRAL_RECEIVED","date":{"kind":"WEEKS_AGO","n":2}}]}';
  const endpoint = http.createServer(async (req, res) => {
    let body = ''; for await (const c of req) body += c;
    seen.push({url: req.url, auth: req.headers.authorization, body: JSON.parse(body)});
    res.writeHead(200, {'Content-Type': 'application/json'});
    res.end(JSON.stringify({choices: [{message: {content: answer, reasoning_content: 'thinking'}, finish_reason: 'stop'}], usage: {prompt_tokens: 10, completion_tokens: 5}}));
  });
  await new Promise((r) => endpoint.listen(0, '127.0.0.1', r));
  const s = await startServer({VERDA_INFERENCE_BASE_URL: `http://127.0.0.1:${endpoint.address().port}/v1`, VERDA_INFERENCE_KEY: DUMMY_KEY, SAMA_NEMOTRON_PYTHON: python});
  try {
    const note = notes.notes.find((n) => n.demo_id === 'demo-04');
    const a = await s.post({demo_id: 'demo-04'});
    assert.equal(a.status, 200, a.text);
    assert.equal(a.body.served, 'live', a.text);
    const expected = new Date(Date.parse(`${note.note_date}T00:00:00Z`) - 14 * 86400000).toISOString().slice(0, 10);
    assert.deepEqual(a.body.prediction, {entry_route: 'PRIVATE', events: [{type: 'REFERRAL_RECEIVED', date: expected, precision: 'DAY'}]});
    assert.equal(a.body.calls, 2, '"2 viikkoa sitten" is not printed in the note: the grounding check asks for one repair');
    assert.equal(a.body.flagged, true);
    assert.ok(!a.text.includes(DUMMY_KEY));
    assert.equal(seen.length, 2);
    const [first, repair] = seen;
    assert.equal(first.url, '/v1/chat/completions');
    assert.equal(first.auth, `Bearer ${DUMMY_KEY}`);
    assert.equal(first.body.model, 'nemotron-3.5-super-vl');
    assert.equal(first.body.temperature, 0);
    assert.equal(first.body.max_tokens, 8000);
    assert.deepEqual(first.body.chat_template_kwargs, {enable_thinking: true});
    assert.match(first.body.messages[0].content, /^You read one SYNTHETIC Finnish clinical-style note/);
    assert.equal(first.body.messages[1].content, `Note date: ${note.note_date}\n${note.note_text}`);
    assert.equal(repair.body.messages.length, 4);
    assert.match(repair.body.messages[3].content, /^A program checked your answer/);
    assert.match(a.body.how, /^live:/);
  } finally { await s.stop(); endpoint.close(); }
});
