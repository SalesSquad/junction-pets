import test from "node:test";
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import {evaluateEpisode,compareEpisodes} from "../src/engine.mjs";
import {parseCsv,previewMappedCsv} from "../src/csv.mjs";

const load=async()=>JSON.parse(await readFile(new URL("../fixtures/episodes.json",import.meta.url),"utf8")).episodes;
const copy=e=>structuredClone(e);

test("clean synthetic path reaches target as non-actuating proposal",async()=>{
  const [e]=await load(), r=evaluateEpisode(e);
  assert.equal(r.simulated_target_reached,true);
  assert.equal(r.synthetic_training_candidate,true);
  assert.equal(r.hardware_connected,false);
  assert.equal(r.command_dispatch_enabled,false);
  assert.equal(r.safety_holds,0);
  assert.equal(r.accepted_proposals,7);
  assert.equal(r.reference_delta_percent,28.6);
  assert.ok(r.trace.every(t=>t.proposal?.actuation_authorized===false));
});
test("tracking dropout holds until two safe samples AND explicit ack",async()=>{
  const [,e]=await load(), r=evaluateEpisode(e);
  assert.equal(r.safety_holds,1);
  assert.equal(r.rearm_events,1);
  assert.equal(r.trace[3].status,"HELD");
  assert.equal(r.trace[4].status,"HELD");
  assert.equal(r.trace[5].status,"REARMED_PROPOSAL_ONLY");
  assert.equal(r.trace[3].proposal,null);
  assert.equal(r.synthetic_training_candidate,false);
});
test("rearm cannot occur without operator acknowledgement",async()=>{
  const [,e]=await load(), c=copy(e);
  delete c.steps[5].reset_ack;
  const r=evaluateEpisode(c);
  assert.equal(r.final_state,"HELD");
  assert.equal(r.rearm_events,0);
  assert.ok(r.trace.slice(3).every(t=>t.proposal===null));
});
test("out-of-bounds data fails closed, even with strong tracking",async()=>{
  const [e]=await load(), c=copy(e);
  c.steps[3].hand.x=0.6;
  const r=evaluateEpisode(c);
  assert.ok(r.events[0].reasons.includes("WORKSPACE_LIMIT"));
  assert.equal(r.synthetic_training_candidate,false);
});
test("speed rate limit and timestamps enforce motion guards",async()=>{
  const [e]=await load(), c=copy(e);
  c.steps[1].hand.x=0.45;
  assert.ok(evaluateEpisode(c).events[0].reasons.includes("MOTION_RATE_LIMIT"));
  c.steps[1].at_ms=0;
  assert.throws(()=>evaluateEpisode(c),/strictly increasing/);
});
test("deadman release causes hold even if pose remains valid",async()=>{
  const [e]=await load(), c=copy(e);
  c.steps[2].deadman=false;
  assert.ok(evaluateEpisode(c).events[0].reasons.includes("DEADMAN_RELEASED"));
});
test("unexpected units, schemas and non-finite coordinates refuse",async()=>{
  const [e]=await load();
  for(const changed of [
    {schema:"wrong"},{calibration:{...e.calibration,units:"mm"}},
    {steps:e.steps.map((s,i)=>i===2?{...s,hand:{...s.hand,x:Infinity}}:s)},
    {source_label:"LIVE_R0K0K0"}
  ]) assert.throws(()=>evaluateEpisode({...e,...changed}),/REFUSED/);
});
test("duplicate identifiers across evaluation cohort are rejected",async()=>{
  const [e]=await load();
  assert.throws(()=>compareEpisodes([e,copy(e)]),/duplicate episode/);
});
test("valid CSV retains duplicate header identity and explicit index mapping",async()=>{
  const csv=await readFile(new URL("../fixtures/duplicate-columns.csv",import.meta.url),"utf8");
  const m=JSON.parse(await readFile(new URL("../fixtures/mapping.json",import.meta.url),"utf8"));
  const p=previewMappedCsv(csv,m.columns,m.calibration,m.goal,m.baseline_ms);
  assert.equal(p.duplicate_header_count,1);
  assert.equal(p.episode.steps[1].hand.x,0.03);
  assert.equal(p.episode.source_label,"UNVERIFIED_REPLAY");
  assert.equal(evaluateEpisode(p.episode).synthetic_training_candidate,false);
  assert.equal(p.columns.find(x=>x.signal==="x").index,1);
  assert.equal(p.columns.find(x=>x.signal==="y").index,3);
});
test("CSV rejects ragged rows, unknown boolean, repeated index mapping and overflow",async()=>{
  const csv=await readFile(new URL("../fixtures/duplicate-columns.csv",import.meta.url),"utf8");
  const m=JSON.parse(await readFile(new URL("../fixtures/mapping.json",import.meta.url),"utf8"));
  assert.throws(()=>parseCsv(csv+"1,2\n"),/ragged/);
  assert.equal(parseCsv(csv.replace(/,0.97,1/,",0.97,yes")).records[1][7],"yes"); // lexical CSV accepts text; strict signal importer must refuse
  assert.throws(()=>previewMappedCsv(csv.replace(/,0.97,1/,",0.97,yes"),m.columns,m.calibration,m.goal,m.baseline_ms),/deadman/);
  assert.throws(()=>previewMappedCsv(csv,{...m.columns,y:1},m.calibration,m.goal,m.baseline_ms),/same column/);
  assert.throws(()=>parseCsv("x".repeat(5_000_001)),/bounded/);
});
test("RFC4180 quoted duplicate headers are preserved, malformed quotes refuse",()=>{
  const csv='"time","pose","pose"\r\n"0","0","1"\r\n"1","2","3"\r\n"2","4","5"\r\n';
  assert.deepEqual(parseCsv(csv).headers,["time","pose","pose"]);
  assert.throws(()=>parseCsv('"unterminated,field'),/unterminated/);
});
