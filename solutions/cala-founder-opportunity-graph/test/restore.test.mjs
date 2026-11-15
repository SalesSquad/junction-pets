import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fixture } from '../fixture.mjs';
import { makeArtifact, DEFAULT_GOAL, safeJSON } from '../core.mjs';
import { PRODUCT_SOURCE_DIGEST } from '../source-meta.mjs';
import { recoverArchive, LEGACY_FIXTURE_DIGESTS, MAX_ARCHIVE_BYTES } from '../workspace/restore.mjs';
const archive = (notes = 'Review the source once more') =>
  makeArtifact(fixture, DEFAULT_GOAL, [{ id: 'inv-larch', note: notes, approved: true }]);
const recover = value => recoverArchive(safeJSON(value), fixture);

test('previously exported current fixture archive restores only notes, not approval', () => {
  const saved = archive();
  assert.equal(saved.productSourceDigest, PRODUCT_SOURCE_DIGEST);
  const result = recover(saved);
  assert.deepEqual(result.goal, DEFAULT_GOAL);
  assert.deepEqual(result.reviews, [{ id: 'inv-larch', note: 'Review the source once more', approved: false }]);
  assert.equal(result.approvalsRevoked, true);
  assert.equal(result.mode, 'FICTIONAL_FIXTURE');
});

test('original published fixture digest can recover the same exact evidence', () => {
  const old = archive();
  old.productSourceDigest = LEGACY_FIXTURE_DIGESTS[0];
  assert.equal(recover(old).reviews[0].approved, false);
});

test('changed source, date, score, issuer, or economic round fails closed', () => {
  for (const edit of [
    a => { a.shortlist[0].rounds[0].citations[0].url = 'https://somewhere.example.invalid/forged'; },
    a => { a.shortlist[0].rounds[0].event.issuerId = 'co-kite'; },
    a => { a.shortlist[0].economicRoundCount = 777; },
    a => { a.asOf = '2026-11-13'; },
    a => { a.shortlist[0].entity.name = 'Namesake Capital'; },
    a => { a.shortlist[0].score = 10000; },
    a => { a.mode = 'LIVE'; },
    a => { a.autoSend = true; }
  ]) {
    const altered = structuredClone(archive());
    edit(altered);
    assert.throws(() => recover(altered), /ARCHIVE_/);
  }
});

test('extra, missing, duplicate, unknown, or future-source fields refuse', () => {
  const cases = [
    a => { a.unexpectedKey = 'owning'; },
    a => { delete a.shortlist[0].rounds; },
    a => { a.shortlist.push(a.shortlist[0]); },
    a => { a.shortlist[0].entity.id = 'inv-unknown'; },
    a => { a.productSourceDigest = '0'.repeat(64); },
    a => { a.goal.from = '2027-01-01'; },
    a => { a.shortlist[0].humanReview.state = 'ACCEPTED_AUTOMATICALLY'; },
    a => { a.shortlist[0].humanReview.note = 'a'.repeat(2001); }
  ];
  for (const edit of cases) { const a=structuredClone(archive());edit(a);assert.throws(() => recover(a), /ARCHIVE_/); }
});

test('malformed, oversized, empty and alternate-format file cannot overwrite review', () => {
  for (const raw of ['{not json', '{}', 'null', '[]', ' '.repeat(MAX_ARCHIVE_BYTES + 1)])
    assert.throws(() => recoverArchive(raw, fixture), /ARCHIVE_/);
  assert.throws(() => recoverArchive(Buffer.from('{}'), fixture), /ARCHIVE_/);
});

test('local XSS-looking notes round-trip verbatim but previous approval is revoked', () => {
  const suspicious = '<img src=x onerror=alert(1)>&"😅';
  const restored = recover(archive(suspicious));
  assert.equal(restored.reviews[0].note, suspicious);
  assert.equal(restored.reviews[0].approved, false);
});

test('duplicate JSON property and unexpected prototype-bearing top-level data refuse', () => {
  const base = safeJSON(archive());
  const duplicate = base.replace('"schema": "roundlens.shortlist.v1",',
    '"schema": "roundlens.shortlist.v1", "schema": "roundlens.shortlist.v1",');
  assert.throws(() => recoverArchive(duplicate,fixture), /ARCHIVE_/);
  const poisoned = base.replace('"schema": "roundlens.shortlist.v1",',
    '"__proto__": {"admin": true}, "schema": "roundlens.shortlist.v1",');
  assert.throws(() => recoverArchive(poisoned,fixture), /ARCHIVE_/);
  assert.equal({}.admin,undefined);
});
