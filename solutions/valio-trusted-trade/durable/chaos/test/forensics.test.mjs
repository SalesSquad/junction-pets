import test from 'node:test';
import assert from 'node:assert/strict';
import {redactPgLine,summarizePgTail} from '../forensics.mjs';

test('bounded WAL failure tail retains useful state but redacts credentials',()=>{
  const raw=[
    '2026 LOG: database system was interrupted; recovery in progress',
    '2026 ERROR: connection postgresql://buyer:secret@example.invalid/db failed',
    '2026 FATAL: password=verysecret token=abc123 authorization:bearer',
    ...Array.from({length:100},(_,i)=>`2026 LOG: status ${i}`)
  ].join('\n');
  const a=summarizePgTail(raw);
  assert.ok(a.length<=32);
  assert.ok(a.every(s=>s.length<=300));
  assert.equal(a.join('\n').includes('verysecret'),false);
  assert.equal(a.join('\n').includes('secret@example.invalid'),false);
  assert.equal(redactPgLine('2026 FATAL: password=verysecret').includes('verysecret'),false);
  assert.equal(redactPgLine('postgresql://buyer:secret@example.invalid/db').includes('secret@example.invalid'),false);
  assert.equal(redactPgLine('token=abc123').includes('abc123'),false);
});
