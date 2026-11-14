import test from 'node:test';
import assert from 'node:assert/strict';
import {runWalChaos} from '../wal-lab.mjs';

test('WAL SIGKILL path refuses to touch any cluster without explicit destructive-test flag',async()=>{
  await assert.rejects(runWalChaos({requests:200,allowKill9:false}),/explicit --allow-kill9/);
});
test('WAL lab keeps worker count and wall-time hard bounded before cluster creation',async()=>{
  await assert.rejects(runWalChaos({requests:200,allowKill9:true,workerCount:9}),/3\.\.8/);
  await assert.rejects(runWalChaos({requests:200,allowKill9:true,maxMinutes:26}),/5\.\.25/);
});
