// Stand-in for serve/demo/worker.py in the route tests: same JSON-lines protocol, no model.
// FAKE_MODE: "ok" (default) answers with a canned result; "crash" exits after "ready"; "nostart" reports a start error.
import {createInterface} from 'node:readline';

const mode = process.env.FAKE_MODE || 'ok';
const send = (o) => process.stdout.write(JSON.stringify(o) + '\n');
if (mode === 'nostart') {
  send({event: 'error', error: 'OSError: base model not in the local cache'});
  process.exit(1);
}
send({event: 'ready', provenance: {resolver: {arm: "A'", frozen: true}}, load_seconds: 0});
if (mode === 'crash') setTimeout(() => process.exit(3), 50);
createInterface({input: process.stdin}).on('line', (line) => {
  const req = JSON.parse(line);
  if (req.note_text === 'bad') return send({id: req.id, ok: false, error: 'note_date must be an ISO date YYYY-MM-DD', input_error: true});
  if (req.note_text === 'boom') return send({id: req.id, ok: false, error: 'RuntimeError: out of memory'});
  send({id: req.id, ok: true, result: {
    schema: 'sama-scribe-demo-v1', synthetic_note: req.synthetic ?? null,
    note: {id: req.note_id, note_date: req.note_date, note_text: req.note_text},
    highlights: [], model: {raw: '{"entry_route":"SCREENING","events":[]}', parsed: {entry_route: 'SCREENING', events: []}, errors: []},
    resolved: {entry_route: 'SCREENING', events: [], prediction: {entry_route: 'SCREENING', events: []}},
    date_resolution: {rule: 'r', arm: "A'", changes: [], needs_person: []}, flags: [], errors: [],
    review: 'pre-filled for one-click confirmation', person_confirms: 'a person confirms every event',
    timing: {total_seconds: 0.01}, provenance: {resolver: {arm: "A'", frozen: true}},
  }});
});
