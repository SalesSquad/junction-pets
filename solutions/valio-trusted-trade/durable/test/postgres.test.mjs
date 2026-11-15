import test from 'node:test';
import assert from 'node:assert/strict';

test('real PostgreSQL multi-process durability and crash-before-ACK',
  {skip:!process.env.VALIO_TEST_DATABASE_URL?'BLOCKED: no disposable VALIO_TEST_DATABASE_URL in this executor':false,timeout:180_000},async()=>{
    const {runChaosLab}=await import('../smoke.mjs');
    const r=await runChaosLab({connectionString:process.env.VALIO_TEST_DATABASE_URL,requestCount:100,workerCount:8});
    assert.equal(r.postCommitCrashObserved,true);
    assert.equal(r.crashReplayed,true);
    assert.equal(r.sealedBatchRefusal,true);
    assert.equal(r.refundRaceSingleWinner,true);
    assert.equal(r.outboxDeleteRefusal,true);
    assert.equal(r.outboxRetargetRefusal,true);
    assert.equal(r.outboxTruncateRefusal,true);
    assert.equal(r.verified.balanced,true);
    assert.equal(r.verified.matching,true);
    assert.equal(r.verified.nonnegative,true);
    assert.equal(r.verified.batches,203);
    assert.equal(r.verified.outboxEvents,203);
  });
