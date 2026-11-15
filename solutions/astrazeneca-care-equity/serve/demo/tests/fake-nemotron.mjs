// Stand-in for serve/demo/nemotron_live.py in the route tests: same stdin/stdout protocol, no endpoint, no key used.
// FAKE_NEMO: "agree" (default) answers with the stored Gemma answer for the demo note; "disagree" drops its last event;
// "fail" reports a network failure; "hang" never answers; "garbage" writes no JSON.
import {readFileSync} from 'node:fs';

const mode = process.env.FAKE_NEMO || 'agree';
const outputs = JSON.parse(readFileSync(new URL('../../../data/scribe/demo/demo-outputs.json', import.meta.url), 'utf8'));
let input = '';
process.stdin.on('data', (d) => { input += d; });
process.stdin.on('end', () => {
  const req = JSON.parse(input);
  if (mode === 'hang') return setInterval(() => {}, 1000);
  if (mode === 'garbage') return process.stdout.write('Traceback (most recent call last): not json\n');
  if (mode === 'fail') return process.stdout.write(JSON.stringify({ok: false, kind: 'network', error: 'the endpoint could not be reached (ConnectionRefusedError)'}) + '\n');
  const gemma = outputs.results[req.id].resolved.prediction;
  const prediction = mode === 'disagree' ? {...gemma, events: gemma.events.slice(0, -1)} : gemma;
  process.stdout.write(JSON.stringify({ok: true, prediction, model: 'nemotron-3.5-super-vl', version: 'v3', latency_ms: 1234, calls: 1, flagged: false, raw: '{}',
    saw_key: typeof process.env.VERDA_INFERENCE_KEY === 'string', timeout_s: req.timeout_s}) + '\n');
});
