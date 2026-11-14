import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {retargetCsv} from '../src/retarget.mjs';
const root=new URL('../',import.meta.url);
const csv=readFileSync(new URL('fixtures/synthetic-retarget.csv',root),'utf8');
const configText=readFileSync(new URL('fixtures/retarget-map.json',root),'utf8');
const config=()=>JSON.parse(configText);
const run=(c=config(),s=csv)=>retargetCsv(s,JSON.stringify(c));
const reject=(edit,reason)=>{const c=config();edit(c);assert.throws(()=>run(c),reason);};

test('right-handed rotation, mm/us conversion, translation and exact input provenance',()=>{
  const r=retargetCsv(csv,configText);
  assert.deepEqual(r.episode.steps[2].hand,{x:0.12000000000000001,y:0.12,z:0.2,grip:0.2});
  assert.deepEqual(r.episode.steps.map(s=>s.at_ms),[0,50,100]);
  assert.equal(r.provenance.rotation_determinant,1);
  assert.equal(r.provenance.input_csv_sha256,createHash('sha256').update(csv).digest('hex'));
  assert.equal(r.provenance.config_sha256,createHash('sha256').update(configText).digest('hex'));
  assert.equal(r.receipt.accepted_proposals,3);
  assert.equal(r.receipt.synthetic_training_candidate,false);
  assert.equal(r.episode.source_label,'UNVERIFIED_REPLAY');
  assert.equal(r.provenance.actuation_authorized,false);
  assert.equal(r.provenance.simulator_calibration_verified,false);
  assert.ok(r.receipt.trace.every(t=>t.proposal.actuation_authorized===false));
});
test('all 48 signed permutations accept exactly the 24 proper rotations',()=>{
  const perms=[[0,1,2],[0,2,1],[1,0,2],[1,2,0],[2,0,1],[2,1,0]], a=['x','y','z'];
  let accepted=0;
  for(const p of perms) for(let mask=0;mask<8;mask++) {
    const c=config();
    c.rotation=Object.fromEntries(a.map((axis,i)=>[axis,(mask&(1<<i)?'-':'+')+a[p[i]]]));
    c.source.bounds={x:[-500,500],y:[-500,500],z:[-500,500]};
    c.calibration.bounds={x:[-1,1],y:[-1,1],z:[-1,1]};
    let inversions=0;for(let i=0;i<3;i++)for(let j=i+1;j<3;j++)if(p[i]>p[j])inversions++;
    const det=(-1)**(inversions+[0,1,2].filter(i=>mask&(1<<i)).length);
    if(det===1){assert.equal(run(c).provenance.rotation_determinant,1);accepted++;}
    else assert.throws(()=>run(c),/AXIS_REFLECTION/);
  }
  assert.equal(accepted,24);
});
test('malformed rotation and duplicate source signals fail closed',()=>{
  reject(c=>c.rotation.x='+x',/DUPLICATE_ROTATION_AXIS/);
  reject(c=>c.rotation.x='y',/SIGNED_PERMUTATION/);
  reject(c=>c.columns.y=c.columns.x,/DUPLICATE_SOURCE_SIGNAL/);
  reject(c=>c.columns.x='1',/COLUMN_INDEX/);
  reject(c=>delete c.columns.deadman,/POSITIONAL_SIGNALS/);
  reject(c=>c.extra=true,/CONFIG_FIELDS/);
});
test('calibration, source/target bounds, units and unsafe transforms refuse before replay',()=>{
  reject(c=>c.calibration.accepted=false,/CALIBRATION_NOT_ACCEPTED/);
  reject(c=>c.calibration.frame_id='unknown',/CALIBRATION_NOT_ACCEPTED/);
  reject(c=>c.source.frame_id='',/SOURCE_FRAME_ID/);
  reject(c=>c.source.bounds.x=[0,110],/SOURCE_POSE_OUTSIDE_BOUNDS/);
  reject(c=>c.calibration.bounds.x=[0,0.11],/TARGET_POSE_OUTSIDE_WORKSPACE/);
  reject(c=>c.source.bounds.x=[0,1e308],/SOURCE_BOUNDS/);
  reject(c=>c.calibration.bounds.x=[0,11],/TARGET_BOUNDS/);
  reject(c=>c.translation_m.x=Infinity,/UNSAFE_TRANSLATION/);
  reject(c=>c.source.position_units='in',/SOURCE_POSITION_UNITS/);
  reject(c=>c.source.time_units='seconds',/SOURCE_TIME_UNITS/);
});
test('integer time conversion rejects fractions, collisions, reversal and overflow',()=>{
  for(const [time,reason] of [['50001',/NONINTEGER_MILLISECOND/],['50000.0',/INTEGER_SOURCE_TIME/],['0',/TIMESTAMP_NOT_STRICTLY/],['-1',/INTEGER_SOURCE_TIME/],['120001000',/TIMESTAMP_RANGE/],['99999999999999999',/INTEGER_SOURCE_TIME/]]) {
    assert.throws(()=>run(config(),csv.replace('50000,',time+',')),reason);
  }
  const c=config();c.source.time_units='ms';c.source.position_units='cm';
  assert.deepEqual(run(c,csv.replace('50000,','50,').replace('100000,','100,').replaceAll(',100,0,200,',',10,0,20,').replace(',110,-10,200,',',11,-1,20,').replace(',120,-20,200,',',12,-2,20,')).episode.steps.map(s=>s.at_ms),[0,50,100]);
});
test('CSV malformed quotes, ragged rows, nonfinite signals and bounds are rejected',()=>{
  for(const [s,reason] of [[csv.replace('50000,','"50000"oops,'),/malformed CSV/],[csv+'1,2\n',/ragged/],[csv.replace('110,','1e999,'),/NONFINITE/],[csv.replace('110,','NaN,'),/NONFINITE/],[csv.replace('0.99,1,0','0.99,yes,0'),/BOOLEAN_SIGNAL/],['x'.repeat(5_000_001),/bounded/]]) assert.throws(()=>run(config(),s),reason);
});
test('stale, speed, tracking and deadman holds retain M1 non-authority and require explicit rearm',()=>{
  for(const [s,reason] of [[csv.replace('50000,','150000,').replace('100000,','200000,'),'STALE_TRACKING'],[csv.replace('110,-10','300,-10'),'MOTION_RATE_LIMIT'],[csv.replaceAll('0.99','0.1'),'LOW_TRACKING_CONFIDENCE'],[csv.replace('0.99,1,0','0.99,0,0'),'DEADMAN_RELEASED']]) {
    const r=run(config(),s).receipt;
    assert.ok(r.events[0].reasons.includes(reason));
    assert.ok(r.trace.filter(t=>t.status==='HELD').every(t=>t.proposal===null));
    assert.equal(r.command_dispatch_enabled,false);
  }
  const held=csv.replace('0.99,1,0','0.99,0,0');
  assert.equal(run(config(),held).receipt.final_state,'HELD');
  const rearmed=held.trimEnd().replace(/,0$/,',1')+'\n';
  assert.equal(run(config(),rearmed).receipt.rearm_events,1);
});
test('CLI emits provenance and rejects mixed modes; M1 CLI remains executable',()=>{
  const cli=(args)=>spawnSync(process.execPath,['cli.mjs',...args],{cwd:root,encoding:'utf8'});
  const args=['--retarget-csv','fixtures/synthetic-retarget.csv','--retarget-map','fixtures/retarget-map.json'];
  const result=cli(args);assert.equal(result.status,0,result.stderr);
  const r=JSON.parse(result.stdout);assert.equal(r.receipt.accepted_proposals,3);assert.equal(r.provenance.source_label,'UNVERIFIED_REPLAY');
  assert.equal(cli([...args,'--episode','fixtures/episodes.json']).status,1);
  assert.equal(cli(['--episode','fixtures/episodes.json']).status,0);
  assert.equal(cli(['--csv','fixtures/duplicate-columns.csv','--map','fixtures/mapping.json']).status,0);
});
