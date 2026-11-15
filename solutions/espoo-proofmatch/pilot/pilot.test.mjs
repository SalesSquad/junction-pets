import test from 'node:test';
import assert from 'node:assert/strict';
import { createScenario, applyCommand, reviewSession, PEOPLE, MODES } from './outcomes.mjs';
import { EVENT_ID, SLOT_MINUTES } from '../event-meetings.mjs';
import { handleRequest } from './serve.mjs';

const [mira, rowan] = PEOPLE.map(p => p.id);
const command = (state, type, fields = {}) => ({ type, expectedVersion: state.version, simulation: 'SIMULATED', ...fields });
const act = (state, type, fields = {}) => applyCommand(state, command(state, type, fields));
const end = state => act(state, 'end-conversation', { confirmed: true });
const ack = (state, actorId) => act(state, 'acknowledge', { actorId, confirmed: true });
const choose = (state, actorId, decision = 'accepted') => act(state, 'consent', { actorId, decision, confirmed: true });
const answers = (nextStep = 'small-exercise') => ({ takeaway: 'open-question', nextStep, support: 'thinking-time' });
const reflect = (state, actorId, nextStep) => act(state, 'reflect', { actorId, reflection: answers(nextStep) });
const acknowledged = () => ack(ack(end(createScenario()), mira), rowan);
const ready = () => reflect(reflect(choose(choose(acknowledged(), mira), rowan), mira), rowan, 'pause');

test('positive journey reuses the accepted W2 meeting, preserves two voices and conflicting next-step choices', () => {
  for (const mode of MODES) {
    const state = createScenario(mode);
    assert.equal(state.meeting.eventId, EVENT_ID);
    assert.equal(state.meeting.status, 'accepted');
    assert.equal((Date.parse(state.meeting.slot.end) - Date.parse(state.meeting.slot.start)) / 60000, SLOT_MINUTES);
    assert.equal(state.meeting.simulation, 'SIMULATED');
    assert.equal(reviewSession(state).label, 'accepted');
    assert.ok(state.participants.every(p => !p.acknowledged && p.consent === 'pending' && p.reflection === null));
  }
  assert.equal(reviewSession(end(createScenario())).label, 'awaiting-acknowledgements');
  assert.equal(reviewSession(acknowledged()).label, 'awaiting-choices');
  assert.equal(reviewSession(choose(choose(acknowledged(), mira), rowan)).label, 'awaiting-reflections');
  const review = reviewSession(ready());
  assert.equal(review.label, 'ready-for-review');
  assert.equal(review.reciprocalEvidence, true);
  assert.equal(review.nextSteps, 'different-choices');
  assert.equal(review.realWorldOutcome, 'not-established');
  assert.deepEqual(review.shared.map(p => p.actorId), [mira, rowan]);
});

test('false consent and merely selecting an actor never accept sharing', () => {
  const state = acknowledged();
  for (const confirmed of [false, undefined, null, 0, 1, 'true', 'false', [], {}]) {
    assert.throws(() => applyCommand(state, command(state, 'consent', { actorId: mira, decision: 'accepted', confirmed })), TypeError);
  }
  assert.throws(() => act(state, 'consent', { actorId: mira }), TypeError);
  for (const decision of [true, false, null, 'accept', 'ACCEPTED', 1]) assert.throws(() => choose(state, mira, decision), TypeError);
  assert.ok(state.participants.every(p => p.consent === 'pending'));
  assert.deepEqual(reviewSession(state).shared, []);
});

test('both acknowledgements are explicit, post-meeting and distinct; unknown actor IDs fail', () => {
  assert.throws(() => ack(createScenario(), mira), /end/);
  const ended = end(createScenario());
  for (const actorId of ['unknown', 'pilot-admin', '', null, {}, 1]) assert.throws(() => ack(ended, actorId), /actor/);
  assert.throws(() => act(ended, 'acknowledge', { actorId: mira, confirmed: false }), /confirmation/);
  const one = ack(ended, mira);
  assert.throws(() => ack(one, mira), /already acknowledged/);
  assert.throws(() => choose(one, mira), /Both/);
  assert.throws(() => reflect(one, mira), /acknowledgements/);
  assert.equal(one.participants[1].acknowledged, false);
  assert.throws(() => end(one), /already ended/);
});

test('accepted and declined sharing are independent; decline never becomes a negative personal verdict', () => {
  const state = choose(choose(acknowledged(), mira, 'declined'), rowan);
  assert.throws(() => reflect(state, mira), /accepted sharing/);
  assert.throws(() => choose(state, mira), /already recorded/);
  const partial = reflect(state, rowan);
  const review = reviewSession(partial);
  assert.equal(review.label, 'closed-without-reciprocal-evidence');
  assert.equal(review.reciprocalEvidence, false);
  assert.deepEqual(review.shared.map(p => p.actorId), [rowan]);
  assert.equal(review.nextSteps, 'unavailable');
  assert.equal(partial.participants[0].reflection, null);
  const bothDecline = choose(choose(acknowledged(), mira, 'declined'), rowan, 'declined');
  assert.deepEqual(reviewSession(bothDecline).shared, []);
});

test('revocation removes only the selected reflection and invalidates reciprocal evidence immediately', () => {
  const before = ready();
  const after = act(before, 'revoke', { actorId: mira, confirmed: true });
  assert.equal(after.participants[0].consent, 'revoked');
  assert.equal(after.participants[0].reflection, null);
  assert.deepEqual(after.participants[1], before.participants[1]);
  assert.equal(reviewSession(after).label, 'sharing-withdrawn');
  assert.equal(reviewSession(after).reciprocalEvidence, false);
  assert.deepEqual(reviewSession(after).shared.map(p => p.actorId), [rowan]);
  assert.throws(() => reflect(after, mira), /accepted sharing/);
  assert.throws(() => choose(after, mira), /already recorded/);
  assert.throws(() => act(after, 'revoke', { actorId: mira, confirmed: true }), /Only accepted/);
  assert.throws(() => reflect(before, mira), /already exists/);
});

test('deletion drops both active participant records and meeting; no resurrection through later commands', () => {
  const state = ready();
  assert.throws(() => act(state, 'delete', { confirmed: 'true' }), /confirmation/);
  const deleted = act(state, 'delete', { confirmed: true });
  assert.equal(deleted.meeting, null);
  assert.deepEqual(deleted.participants, []);
  assert.deepEqual(reviewSession(deleted).shared, []);
  assert.equal(reviewSession(deleted).label, 'deleted');
  assert.throws(() => ack(deleted, mira), /deleted/);
  assert.throws(() => act(deleted, 'delete', { confirmed: true }), /deleted/);
  assert.ok(!JSON.stringify(deleted).includes('pilot-mira'));
  // Ordinary versioned actions are bounded, but deletion stays available at the limit.
  const atLimit = { ...state, version: 127 };
  assert.throws(() => act(atLimit, 'revoke', { actorId: mira, confirmed: true }), /limit/);
  assert.equal(reviewSession(act(atLimit, 'delete', { confirmed: true })).label, 'deleted');
});

test('stale commands fail and pure immutable rules leave caller state and payloads untouched', () => {
  const state = acknowledged(), original = JSON.stringify(state);
  const accepted = choose(state, mira);
  assert.throws(() => applyCommand(accepted, command(state, 'consent', { actorId: rowan, decision: 'accepted', confirmed: true })), /State conflict/);
  assert.throws(() => { accepted.participants[0].consent = 'declined'; }, TypeError);
  const payload = command(accepted, 'reflect', { actorId: mira, reflection: answers() });
  const reflected = applyCommand(accepted, payload);
  payload.reflection.takeaway = 'different-direction';
  assert.equal(reflected.participants[0].reflection.takeaway, 'open-question');
  assert.equal(JSON.stringify(state), original);
});

test('no personal ranking, inferred proficiency or arbitrary personal text is accepted or produced', () => {
  const state = ready();
  for (const person of state.participants) {
    assert.deepEqual(Object.keys(person), ['id', 'acknowledged', 'consent', 'reflection']);
    assert.ok(Object.values(person.reflection).every(v => typeof v === 'string'));
  }
  const serialized = JSON.stringify({ state, review: reviewSession(state) });
  assert.doesNotMatch(serialized, /score|rank|proficiency|eligibility|hiring|email/i);
  const accepted = choose(acknowledged(), mira);
  for (const reflection of [null, [], {}, { ...answers(), score: 5 }, { ...answers(), takeaway: 10 }, { ...answers(), support: 'Real personal details' }, { ...answers(), nextStep: 'x'.repeat(10000) }]) {
    assert.throws(() => act(accepted, 'reflect', { actorId: mira, reflection }), TypeError);
  }
});

test('malformed payloads, forged consent states, sparse records and state conflicts fail closed', () => {
  const state = acknowledged();
  for (const payload of [null, [], {}, 'accept', { ...command(state, 'delete', { confirmed: true }), personalData: 'no' }, { ...command(state, 'delete', { confirmed: true }), simulation: true }, command(state, 'constructor')]) {
    assert.throws(() => applyCommand(state, payload), TypeError);
  }
  for (const mode of ['remote-ish', null, 1, {}]) assert.throws(() => createScenario(mode), TypeError);
  const corruptions = [
    null, {}, { ...state, participants: new Array(2) }, { ...state, phase: 'ready' }, { ...state, version: NaN },
    { ...state, meeting: { ...state.meeting, status: 'pending' } },
    { ...state, participants: [{ ...state.participants[0], consent: true }, state.participants[1]] },
    { ...state, participants: [state.participants[0], state.participants[0]] },
    { ...state, participants: [{ ...state.participants[0], consent: 'declined', reflection: answers() }, state.participants[1]] },
    { ...state, participants: [{ ...state.participants[0], consent: 'accepted' }, { ...state.participants[1], acknowledged: false }] },
  ];
  for (const corrupt of corruptions) assert.throws(() => reviewSession(corrupt), TypeError);
});

test('isolated static route serves the pilot and reused modules; rejects writes, traversal and cross-site access', async () => {
  const request = async (url, method = 'GET', headers = {}) => {
    const result = { headers: {}, status: null, body: undefined };
    await handleRequest({ url, method, headers: { host: '127.0.0.1:4187', ...headers } }, {
      setHeader(key, value) { result.headers[key] = value; },
      writeHead(status) { result.status = status; },
      end(body) { result.body = body; },
    });
    return result;
  };
  for (const url of ['/', '/index.html', '/app.mjs', '/outcomes.mjs', '/styles.css', '/event-meetings.mjs', '/demo-validation.mjs']) {
    const response = await request(url);
    assert.equal(response.status, 200, url);
    assert.ok(response.body.length > 0);
    assert.equal(response.headers['Cache-Control'], 'no-store');
    assert.match(response.headers['Content-Security-Policy'], /connect-src 'none'/);
  }
  const page = await request('/');
  assert.match(page.body.toString(), /SIMULATED/);
  assert.match(page.body.toString(), /not authentication or real-person consent/);
  assert.equal((await request('/', 'HEAD')).body, undefined);
  for (const url of ['/../README.md', '/%2e%2e/README.md', '/README.md', '/api/outcomes', '/?actor=real']) assert.equal((await request(url)).status, 404);
  assert.equal((await request('/', 'POST')).status, 405);
  assert.equal((await request('/', 'GET', { host: 'outside.example:4187' })).status, 403);
  assert.equal((await request('/', 'GET', { 'sec-fetch-site': 'cross-site' })).status, 403);
});
