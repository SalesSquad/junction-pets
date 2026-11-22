import {canonical, exact, fail, freeze, hashJson, jsonCopy, text} from './json.mjs';
import {validateClaim} from './claim.mjs';
export async function createReview(dataset, inputClaim) {
  const claim = await validateClaim(dataset, inputClaim);
  const root = await hashJson({schema: 'evidence-kit.review/v1', claimSha256: claim.claimSha256, generation: claim.generation});
  let head = root, current = null, past = [], future = [], queue = Promise.resolve();
  const events = [], operations = new Map();
  const snapshot = () => freeze(jsonCopy({schema: 'evidence-kit.review/v1', claimSha256: claim.claimSha256,
    generation: claim.generation, root, head, events, current, canUndo: past.length > 0, canRedo: future.length > 0, identity: 'locally-declared', independentVerification: false}));
  async function append(command) {
    exact(command, ['id', 'expectedHead', 'kind', 'reviewer', 'note', 'value', 'refs'], 'review command');
    text(command.id, 'operation ID', 100); text(command.reviewer, 'reviewer declaration', 100);
    if (typeof command.note !== 'string' || command.note.length > 1000 || !Array.isArray(command.refs)) fail('INVALID_REVIEW', 'Invalid review note or citations.');
    const fingerprint = canonical(command);
    if (operations.has(command.id)) {
      if (operations.get(command.id) !== fingerprint) fail('OPERATION_CONFLICT', 'Operation ID has different content.');
      return snapshot();
    }
    if (command.expectedHead !== head) fail('STALE_REVIEW', 'Review changed; reload before applying another operation.');
    if (events.length >= 100) fail('RESOURCE_EXHAUSTED', 'Review history exceeds 100 events.');
    let next = current, nextPast = [...past], nextFuture = [...future];
    if (command.kind === 'correct' || command.kind === 'confirm') {
      if (command.kind === 'confirm' && claim.status !== 'supported') fail('INVALID_REVIEW', 'Unsupported engine claims cannot be confirmed.');
      const refs = command.kind === 'correct' ? command.refs : claim.refs;
      if (command.kind === 'correct') {
        text(command.value, 'manual correction', 400);
        if (!refs.length || refs.length > 100 || new Set(refs.map(r => r.id)).size !== refs.length) fail('INVALID_REVIEW', 'Use 1–100 distinct canonical correction citations.');
        refs.forEach(ref => dataset.resolve(ref));
      } else if (command.value !== null || command.refs.length) fail('INVALID_REVIEW', 'Confirmation uses the original engine value and citations.');
      nextPast.push(current); nextFuture = [];
      next = {status: command.kind === 'correct' ? 'corrected' : 'confirmed', reviewer: command.reviewer, note: command.note,
        value: command.kind === 'correct' ? command.value : claim.value, refs, independentVerification: false};
    } else if (command.kind === 'undo' || command.kind === 'redo') {
      if (command.value !== null || command.refs.length) fail('INVALID_REVIEW', 'Undo/redo cannot inject new answers.');
      if (command.kind === 'undo') {
        if (!nextPast.length) fail('NOTHING_TO_UNDO', 'Nothing to undo.');
        nextFuture.push(current); next = nextPast.pop();
      } else {
        if (!nextFuture.length) fail('NOTHING_TO_REDO', 'Nothing to redo.');
        nextPast.push(current); next = nextFuture.pop();
      }
    } else fail('INVALID_REVIEW', 'Unknown review operation.');
    const payload = {sequence: events.length + 1, previous: head, command, after: next};
    const sha256 = await hashJson(payload);
    events.push({...payload, sha256});
    operations.set(command.id, fingerprint);
    current = next; past = nextPast; future = nextFuture; head = sha256;
    return snapshot();
  }
  return Object.freeze({snapshot, apply(input) {
    // Snapshot before queuing; serialize async hashing to preserve compare-and-swap semantics.
    const command = jsonCopy(input);
    const result = queue.then(() => append(command));
    queue = result.catch(() => undefined);
    return result;
  }});
}
export async function restoreReview(dataset, claim, input) {
  const stored = jsonCopy(input), review = await createReview(dataset, claim);
  if (stored.claimSha256 !== claim.claimSha256 || stored.generation !== dataset.manifest().generation) fail('REVALIDATION_REQUIRED', 'Historical review belongs to a different source or result; retain it as history and review the new result explicitly.');
  if (!Array.isArray(stored.events) || stored.events.length > 100) fail('INVALID_REVIEW', 'Invalid history.');
  for (const event of stored.events) await review.apply(event.command);
  if (canonical(review.snapshot()) !== canonical(stored)) fail('INVALID_REVIEW', 'Review chain, state or provenance was altered.');
  return review;
}
