// Pure, provider-free human curation. A response is evidence, never instructions.
export const CURATED='USER_CURATED_NOT_VERIFIED';
const copy=x=>JSON.parse(JSON.stringify(x));
function text(x,max,name){if(typeof x!=='string'||!x.trim()||x.length>max)throw new Error(`${name}: enter 1–${max} characters`);return x;}
function date(x){return typeof x==='string'&&Number.isFinite(Date.parse(x))&&Date.parse(x)<=Date.now();}
export function createCuration(response,goal){
 text(goal,500,'Goal');
 if(response?.mode!=='LIVE'||response.state!=='LIVE_EVIDENCE_ONLY'||response.sponsorAPI!=='SEARCH_CONTENTS_OBSERVED')throw new Error('Actual LIVE response required; replay cannot be curated as LIVE');
 if(!Array.isArray(response.sources)||!response.sources.length||response.sources.length>5)throw new Error('Invalid sources');
 if(!Array.isArray(response.requestIds)||response.requestIds.length!==2||response.requestIds.some(x=>x!==null&&(typeof x!=='string'||x.length>500)))throw new Error('Invalid request IDs');
 const ids=new Set(),urls=new Set();
 for(const s of response.sources){
  text(s.id,100,'Source ID');text(s.title,200,'Title');text(s.text,4000,'Source text');text(s.provenance,1000,'Provenance');
  const u=new URL(text(s.url,2048,'URL'));
  if(u.protocol!=='https:'||u.username||u.password||u.port||u.hash||!['hackjunction.app','slush.org','www.slush.org','exa.ai'].includes(u.hostname)||ids.has(s.id)||urls.has(u.href)||s.mode!=='LIVE'||!date(s.observedAt)||!date(s.publishedAt))throw new Error('Invalid or duplicate LIVE source/date');
  ids.add(s.id);urls.add(u.href);
 }
 // Capture the exact response once; callers cannot replace its source ledger later.
 const evidence=copy(response),originalGoal=goal;
 function assemble(input){
  if(input.goal!==originalGoal)throw new Error('Goal changed; retrieve new evidence');
  if(!Array.isArray(input.records)||!input.records.length||input.records.length>5)throw new Error('Select 1–5 sources');
  const seen=new Set();
  const records=input.records.map(r=>{
   const source=evidence.sources.find(s=>s.id===r.sourceId);
   if(!source||seen.has(r.sourceId))throw new Error('Unknown or duplicate selected source');seen.add(r.sourceId);
   text(r.excerpt,4000,'Exact excerpt');if(!source.text.includes(r.excerpt))throw new Error(`Excerpt must exist exactly in ${r.sourceId}`);
   return {sourceId:r.sourceId,excerpt:r.excerpt,observation:text(r.observation,2000,'Your observation'),nextAction:text(r.nextAction,2000,'Your source-linked next action'),status:CURATED};
  });
  return {schema:'exa-human-curation/v1',mode:'LIVE',goal:originalGoal,evidence:copy(evidence),records,draft:text(input.draft,10000,'Draft'),uncertainties:text(input.uncertainties,3000,'Uncertainties'),status:CURATED,unknowns:['Publisher claims not independently verified','Eligibility and current availability unknown unless separately checked','Missing request IDs remain null'],externalEffects:[],executesRealWorldTask:false};
 }
 function approve(input,ack){if(ack!==true)throw new Error('Explicit uncertainty acknowledgement required');const p=assemble(input);return {scope:'LOCAL_ONLY',at:new Date().toISOString(),reviewed:JSON.stringify(p)};}
 function exportPacket(input,approval){const p=assemble(input);if(approval?.scope!=='LOCAL_ONLY'||approval.reviewed!==JSON.stringify(p)||!date(approval.at))throw new Error('Approval missing or invalidated by edits');return {...p,approval:{scope:'LOCAL_ONLY',at:approval.at,uncertaintiesAcknowledged:true},warning:'Human notes, actions and draft are USER_CURATED_NOT_VERIFIED. No message sent or task executed.'};}
 return {assemble,approve,exportPacket};
}
