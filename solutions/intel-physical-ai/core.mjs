// Pure, offline synthetic state machine. No device or inference adapter exists.
export const VERSION = 'inspect-cell/1.0.0';
export const POLICY = Object.freeze({ threshold: .5, minConfidence: .9, maxAgeMs: 30000 });
const fixture = (id, label, score, uncertainty, confidence, region, cameras = {top:true, inspection:true}) => ({
  id, label, score, uncertainty, confidence, region, cameras, capturedAt:0,
  evidence:'SYNTHETIC', generator:'drawn-duplo/1', part:'Duplo-style test brick'
});
const fixtures = [
  fixture('clear-01','good',.12,.04,.98,null),
  fixture('scratch-02','defect',.86,.06,.97,{x:62,y:34,w:23,h:9}),
  fixture('ambiguous-03','hold',.49,.08,.95,{x:43,y:45,w:12,h:18}),
  fixture('threshold-touch-06','hold',.5,0,.99,null),
  fixture('low-confidence-04','hold',.1,.02,.64,null),
  fixture('missing-camera-05','hold',.1,.02,.98,null,{top:true,inspection:false})
];
export const FIXTURE_IDS = Object.freeze(fixtures.map(x=>x.id));
export function loadFixture(id) {
  const f = fixtures.find(x=>x.id===id);
  if (!f) throw Error('Unknown built-in synthetic fixture');
  return structuredClone(f);
}
export function canonical(value) {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return '['+value.map(canonical).join(',')+']';
  return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}';
}
export async function digest(value) {
  const bytes = await globalThis.crypto.subtle.digest('SHA-256',new TextEncoder().encode(canonical(value)));
  return [...new Uint8Array(bytes)].map(x=>x.toString(16).padStart(2,'0')).join('');
}
export function createSession(id) {
  return {version:VERSION, fixture:loadFixture(id), policy:{...POLICY}, commands:[], state:{phase:'loaded',now:0,candidate:null,bowl:null,reason:'Awaiting operator anomaly gate',reinspections:0}};
}
function evolve(session, command) {
  if (!command || Object.keys(command).sort().join(',')!=='at,id,type' || (typeof command.id!=='string' || !/^[a-z0-9-]{1,64}$/.test(command.id)) || !Number.isSafeInteger(command.at) || command.at<0 || !['gate','reinspect','review','route','stop','tick'].includes(command.type)) throw Error('Invalid command');
  const prior = session.commands.find(c=>c.id===command.id);
  if (prior) {
    if (canonical(prior)!==canonical(command)) throw Error('Idempotency key conflict');
    return session;
  }
  const next=structuredClone(session), s=next.state, f=next.fixture;
  if (command.at<s.now) throw Error('Clock cannot move backwards');
  if (['stopped','routed'].includes(s.phase)) throw Error('Terminal episode: load a fixture to start again');
  s.now=command.at;
  const stop = reason => Object.assign(s,{phase:'stopped',candidate:null,bowl:null,reason});
  if (command.type==='stop') stop('Manual stop');
  else if (!f.cameras.top || !f.cameras.inspection) stop('Missing camera evidence');
  else if (command.at-f.capturedAt>POLICY.maxAgeMs) stop('Stale capture');
  else if (f.confidence<POLICY.minConfidence) stop('Low confidence');
  else if (command.type==='gate') {
    if (s.phase!=='loaded') throw Error('Gate requires a newly loaded episode');
    const low=Math.max(0,f.score-f.uncertainty), high=Math.min(1,f.score+f.uncertainty);
    s.candidate=high<POLICY.threshold?'good':low>POLICY.threshold?'defect':null;
    s.phase=s.candidate?'gated':'uncertain';
    s.reason=s.candidate?'Conservative synthetic interval clears gate':'Interval touches threshold: reinspection or manual review required';
  } else if (command.type==='reinspect') {
    if(s.phase!=='uncertain' || s.reinspections) throw Error('One reinspection is allowed after an uncertain gate');
    s.reinspections++;
    s.phase='review'; s.reason='Same synthetic capture replayed; uncertainty unchanged. Manual review required';
  } else if (command.type==='review') {
    if(!['uncertain','review'].includes(s.phase)) throw Error('Manual review requires uncertainty');
    s.phase='gated'; s.candidate='hold'; s.reason='Operator acknowledged uncertainty: hold only';
  } else if (command.type==='route') {
    if(s.phase!=='gated' || !s.candidate) throw Error('Operator must complete the anomaly gate first');
    s.phase='routed'; s.bowl=s.candidate; s.reason='Non-actuating bowl simulation complete';
  }
  next.commands.push(structuredClone(command));
  return next;
}
// Rebuild before every transition: caller-mutated policy/state cannot bypass guards.
export function apply(session, command) {
  let trusted=createSession(session.fixture.id);
  for(const c of session.commands) trusted=evolve(trusted,c);
  if(canonical(trusted)!==canonical(session)) throw Error('Session integrity failure');
  return evolve(trusted,command);
}
export async function receipt(session) {
  // Validate the supplied state even for zero-step episodes.
  let replay=createSession(session.fixture.id);
  if (canonical(session.fixture)!==canonical(replay.fixture) || canonical(session.policy)!==canonical(replay.policy) || session.version!==VERSION) throw Error('Input integrity failure');
  const inputDigest=await digest({version:VERSION,fixture:replay.fixture,policy:replay.policy});
  let previous=inputDigest; const steps=[];
  for(const command of session.commands) {
    replay=apply(replay,command);
    const step={sequence:steps.length+1,version:VERSION,producer:'offline-rule-gate/1',command,state:structuredClone(replay.state),previous};
    const hash=await digest(step); steps.push({...step,hash}); previous=hash;
  }
  if(canonical(replay)!==canonical(session)) throw Error('Session integrity failure');
  return {schema:1,version:VERSION,evidence:'SYNTHETIC',actuation:false,inference:false,fixtureId:session.fixture.id,inputDigest,steps,final:replay.state,root:previous};
}
export async function replayReceipt(input) {
  if (!input || !Array.isArray(input.steps) || input.steps.length>256) throw Error('Invalid receipt');
  let session=createSession(input.fixtureId);
  for(const step of input.steps) session=apply(session,step.command);
  if(canonical(await receipt(session))!==canonical(input)) throw Error('Receipt integrity failure');
  return session;
}
