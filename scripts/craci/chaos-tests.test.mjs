import {test} from 'node:test';
import {strict as assert} from 'node:assert';
import {chaosCampaign, mutationAudit} from './chaos-lab.mjs';

for (const [index,profile] of ['provenance','network','control','evidence'].entries()) {
  test(`${profile}: fail-closed metamorphic oracle and source-bound digest`,async()=>{
    const run = await chaosCampaign({seed:10007+index*73,cases:2000,profile});
    assert.equal(run.metrics.missedInjected,0);
    assert.equal(run.metrics.rejectedControl,0);
    assert(run.metrics.detectedInjected > 1000);
    assert(run.metrics.acceptedControl > 100);
    assert(run.metrics.baselineMissedInjected > 100);
    assert(run.metrics.distinctPairs > 30);
    assert(run.deterministicCorpusDigestSha256.match(/^[a-f0-9]{64}$/));
    assert.equal(run.actualCostEur,null);
    assert(!JSON.stringify(run).includes('SYNTHETIC_CANARY_DO_NOT_LOG'));
  });
}

test('identical cohorts replay deterministically',async()=>{
  const a=await chaosCampaign({seed:31,cases:900,profile:'evidence'});
  const b=await chaosCampaign({seed:31,cases:900,profile:'evidence'});
  assert.deepEqual(a,b);
});

test('changed seed changes pairwise corpus without rewriting prior evidence',async()=>{
  const a=await chaosCampaign({seed:31,cases:900,profile:'provenance'});
  const b=await chaosCampaign({seed:59,cases:900,profile:'provenance'});
  assert.notEqual(a.deterministicCorpusDigestSha256,b.deterministicCorpusDigestSha256);
});

test('unknown fault profile refuses to run',async()=>{
  await assert.rejects(chaosCampaign({seed:1,cases:900,profile:'unknown'}),/Unknown chaos profile/);
});

test('every one of 19 deleted synthetic safety gates is caught',()=>{
  const audit=mutationAudit();
  assert.equal(audit.killed,19);
  assert.equal(audit.total,19);
  assert.deepEqual(audit.surviving,[]);
});
