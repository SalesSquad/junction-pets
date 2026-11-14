import { readFileSync } from 'node:fs';
import { SAM31 } from './observation-contract.mjs';
import { FIXTURE } from '../../apps/meta-resume-web/fixture.mjs';

const scene=JSON.parse(readFileSync(new URL('./observation-scene.fixture.json',import.meta.url),'utf8'));
/** Original illustrative pixels and rectangular masks, explicitly NOT SAM execution. */
export function demoObservation({now=new Date().toISOString(),frameIndex=0}={}) {
  return {observation:{schemaVersion:1,kind:'meta.sam31.observation',evidenceMode:'SYNTHETIC',
    episodeId:'camera-bag.synthetic.v1',sessionId:FIXTURE.sessionId,captureGeneration:FIXTURE.captureGeneration,
    runId:'synthetic.scene.v1',trackGeneration:1,sourceThroughFrameIndex:frameIndex,
    frame:{frameIndex,...scene.frame,capturedAt:now},model:{...SAM31},tracks:structuredClone(scene.tracks)},
    image:structuredClone(scene.image)};
}

/** Deterministic transport for source integration; never label as provider execution. */
export async function syntheticObservationTransport(url,options) {
  const body=JSON.parse(options.body), metadata=JSON.parse(body.messages[1].content[0].text);
  const candidate=metadata.tracks.find(t=>t.trackId===metadata.focusTrackId)??
    metadata.tracks.find(t=>metadata.task.nextStep.label.toLowerCase().includes(t.label.toLowerCase()))??metadata.tracks[0];
  const answer={summary:'A visible candidate can help you continue. Its identity still needs your confirmation.',
    observations:candidate?[{trackId:candidate.trackId,text:'The synthetic scene shows this candidate on the table.'}]:[],
    uncertainties:['This is a synthetic example; no physical item has been verified.'],
    nextQuestion:'Is this the item you intend to pack?',nextStepId:candidate?metadata.task.nextStep.stepId:null};
  return new Response(JSON.stringify({model:body.model,usage:{prompt_tokens:120,completion_tokens:100,total_tokens:220},
    choices:[{finish_reason:'stop',message:{role:'assistant',content:JSON.stringify(answer)}}]}),
    {status:200,headers:{'Content-Type':'application/json'}});
}
