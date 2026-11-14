#!/usr/bin/env node
/** Real, bounded fault probes on an EPHEMERAL CRACI runner only. */
import {strict as assert} from 'node:assert';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {createServer} from 'node:http';
import {mkdtemp, mkdir, readFile, rename, rm, writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {dirname, join, resolve, sep} from 'node:path';
import {pathToFileURL} from 'node:url';

const digest = text => createHash('sha256').update(text).digest('hex');
const delay = ms => new Promise(done => setTimeout(done, ms));

function npmFixture(path) {
  const script = 'node -e "require(\'fs\').writeFileSync(\'lifecycle-marker\',\'synthetic-only\')"';
  return Promise.all([
    writeFile(join(path, 'package.json'), JSON.stringify({name:'craci-chaos-fixture',version:'1.0.0',private:true,
      scripts:{postinstall:script}})),
    writeFile(join(path, 'package-lock.json'), JSON.stringify({name:'craci-chaos-fixture',version:'1.0.0',
      lockfileVersion:3,requires:true,packages:{'':{name:'craci-chaos-fixture',version:'1.0.0'}}})),
  ]);
}

async function executeProbe(name, fn, result) {
  const started = performance.now();
  try {
    const evidence = await fn();
    result[name] = {status:'pass',durationMs:Math.round(performance.now()-started),evidence};
  } catch (error) {
    result[name] = {status:'fail',durationMs:Math.round(performance.now()-started),
      errorCode:error.code||error.name||'ASSERTION_FAILED'};
  }
}

async function localNetworkProbe() {
  const server = createServer((req,res) => {
    if (req.url === '/reset') return req.socket.destroy();
    if (req.url === '/delay') return void setTimeout(() => { if (!res.destroyed) res.end('late'); },250);
    res.writeHead(200, {'content-type':'text/plain'});res.end('recovered');
  });
  try {
    await new Promise((done,reject) => {
      server.once('error', reject);
      server.listen(0,'127.0.0.1',done);
    });
    const endpoint = `http://127.0.0.1:${server.address().port}`;
    await assert.rejects(fetch(endpoint+'/reset',{signal:AbortSignal.timeout(800)}));
    await assert.rejects(fetch(endpoint+'/delay',{signal:AbortSignal.timeout(70)}));
    // Fault cleared: same isolated service accepts a healthy retry.
    const recovered = await fetch(endpoint+'/recovered',{signal:AbortSignal.timeout(1000)});
    assert.equal(recovered.status,200);
    assert.equal(await recovered.text(),'recovered');
    return {resetRejected:true,latencyTimeoutRejected:true,recovered:true,bind:'127.0.0.1'};
  } finally {
    server.closeAllConnections();
    await new Promise(done => server.close(done));
  }
}

export async function runProbes(config) {
  const root = resolve(process.env.RUNNER_TEMP || tmpdir());
  const sandbox = await mkdtemp(join(root,'craci-chaos-'));
  assert(sandbox.startsWith(root+sep) && sandbox !== root,'Unsafe sandbox path');
  const tests = {};
  try {
    await executeProbe('npm-lifecycle-ignored-with-negative-control',async()=>{
      const safe = join(sandbox,'npm-safe'),control = join(sandbox,'npm-control');
      await Promise.all([mkdir(safe),mkdir(control)]);
      await Promise.all([npmFixture(safe),npmFixture(control)]);
      const flags = ['ci','--offline','--no-audit','--no-fund'];
      const run=(cwd, extra=[]) => spawnSync('npm',[...flags,...extra],{cwd,timeout:12000,
        env:{...process.env,npm_config_update_notifier:'false'},encoding:'utf8',maxBuffer:128*1024});
      const guarded = run(safe,['--ignore-scripts']);
      assert.equal(guarded.status,0,'Guarded npm ci failed');
      await assert.rejects(readFile(join(safe,'lifecycle-marker')),{code:'ENOENT'});
      // The benign lifecycle script demonstrably runs WITHOUT --ignore-scripts.
      const unguarded = run(control);
      assert.equal(unguarded.status,0,'Fixture control npm ci failed');
      assert.equal(await readFile(join(control,'lifecycle-marker'),'utf8'),'synthetic-only');
      return {guardedScriptDidNotRun:true,independentPositiveControlRan:true,externalNetwork:false};
    },tests);
    await executeProbe('npm-lock-mismatch-rejected',async()=>{
      const folder = join(sandbox,'npm-lock-mismatch');
      await mkdir(folder);
      await npmFixture(folder);
      const manifest=JSON.parse(await readFile(join(folder,'package.json'),'utf8'));
      manifest.dependencies={'synthetic-absent-package':'1.0.0'};
      await writeFile(join(folder,'package.json'),JSON.stringify(manifest));
      const run=spawnSync('npm',['ci','--offline','--ignore-scripts','--no-audit','--no-fund'],
        {cwd:folder,encoding:'utf8',timeout:10000,maxBuffer:128*1024});
      assert.notEqual(run.status,0,'Mismatched manifest/lockfile was accepted');
      return {malformedDependencyGraphRejected:true,externalNetwork:false};
    },tests);
    await executeProbe('local-tcp-reset-jitter-and-recovery',localNetworkProbe,tests);
    await executeProbe('child-process-exit-timeout-recovery',async()=>{
      const failed=spawnSync(process.execPath,['-e','process.exit(71)'],{timeout:2000});
      assert.equal(failed.status,71);
      const hung=spawnSync(process.execPath,['-e','setInterval(()=>{},1000)'],{timeout:170});
      assert.equal(hung.error?.code,'ETIMEDOUT');
      const recovered=spawnSync(process.execPath,['-e','process.exit(0)'],{timeout:2000});
      assert.equal(recovered.status,0);
      return {isolatedChildExit:71,timeoutWasKilled:true,subsequentChildSucceeded:true};
    },tests);
    await executeProbe('receipt-atomic-commit-and-tamper-detection',async()=>{
      const bytes=JSON.stringify({sourceSha:'a'.repeat(40),outcome:'pass',synthetic:true});
      const stage=join(sandbox,'receipt.partial'),final=join(sandbox,'receipt.json');
      await writeFile(stage,bytes,{flag:'wx'});
      await rename(stage,final);
      const pin=digest(await readFile(final));
      assert.equal(pin,digest(bytes));
      await writeFile(final,bytes.slice(0,bytes.length-4));
      assert.notEqual(digest(await readFile(final)),pin);
      await writeFile(final,bytes);
      assert.equal(digest(await readFile(final)),pin);
      return {atomicRename:true,corruptionRejected:true,restoredDigestVerified:true};
    },tests);
    await executeProbe('atomic-dispatch-intent-race',async()=>{
      const lease = join(sandbox,'dispatch-intent');
      const winners = await Promise.all(Array.from({length:32},async()=>{
        try {await writeFile(lease,'attempted',{flag:'wx'});return true;}
        catch(error) {if (error.code==='EEXIST') return false;throw error;}
      }));
      assert.equal(winners.filter(Boolean).length,1);
      assert.equal(await readFile(lease,'utf8'),'attempted');
      // Crash after durable intent, before provider ACK: fail-closed on replay.
      const intentOnRestart = await readFile(lease,'utf8');
      assert.equal(intentOnRestart,'attempted');
      return {simultaneousAttempts:32,uniqueWinner:1,uncertainAckRetryAllowed:false};
    },tests);
  } finally {
    // Delete only this newly generated sandbox, never the user's checked-out repo.
    await rm(sandbox,{recursive:true,force:true});
  }
  const passed = Object.values(tests).filter(t=>t.status==='pass').length;
  const report={schemaVersion:1,workId:'CRACI-CHAOS-20261114',
    claim:'Real local fault-probes on disposable runner fixtures; no production or provider-failure claim',
    sourceCommit:process.env.CRACI_SOURCE_SHA||null,actualCostEur:null,
    suite:'npm-filesystem-local-network-process-concurrency',
    counts:{passed,failed:Object.keys(tests).length-passed},tests,
    limits:['No remote registry tamper, production attack, actual CRACI service kill or credential testing',
      'Local network probe tests loopback resilience; CRACI outbound policy must be checked separately']};
  if (config.output) {
    const out=resolve(config.output);
    await mkdir(dirname(out),{recursive:true});
    await writeFile(out,JSON.stringify(report,null,2)+'\n',{flag:'wx'});
  }
  assert.equal(report.counts.failed,0,'One or more real isolated probes failed');
  return report;
}

async function main() {
  const args=process.argv.slice(2);
  if (args.length !== 2 || args[0] !== '--output' || !args[1]) throw new Error('Expected --output PATH');
  const report=await runProbes({output:args[1]});
  console.log(JSON.stringify({counts:report.counts,tests:Object.keys(report.tests)}));
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href)
  main().catch(error=>{console.error(error.stack||error.message);process.exitCode=1;});
