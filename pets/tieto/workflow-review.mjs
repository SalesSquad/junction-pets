/** Offline consistency review of caller-declared fictional workflow data. */
const ID=/^fictional-[a-z0-9]+(?:-[a-z0-9]+)*$/;
const reject=label=>{throw new TypeError(`Invalid fictional workflow: ${label}`);};
function record(value,keys,label){
  if(!value||typeof value!=='object'||Array.isArray(value))reject(label);
  const actual=Object.keys(value);
  if(actual.length!==keys.length||actual.some(key=>!keys.includes(key)))reject(label);
}
function id(value,label){if(typeof value!=='string'||value.length>64||!ID.test(value))reject(label);}
function nullableId(value,label){if(value!==null)id(value,label);}
function array(value,min,max,label){if(!Array.isArray(value)||value.length<min||value.length>max)reject(label);}
function unique(values,label){if(new Set(values).size!==values.length)reject(label);}
function ids(value,min,max,label){array(value,min,max,label);value.forEach(item=>id(item,label));unique(value,label);}
function integer(value,min,max,label){if(value!==null&&(!Number.isSafeInteger(value)||value<min||value>max))reject(label);}

/** Accepts at most 64 KiB of JSON text; never calls a provider or authorizes work. */
export function reviewWorkflow(jsonText){
  if(typeof jsonText!=='string'||jsonText.length>65536||Buffer.byteLength(jsonText,'utf8')>65536)reject('JSON text size/type');
  let value;
  try{value=JSON.parse(jsonText);}catch{reject('JSON syntax');}
  record(value,['schemaVersion','fictional','workflowId','actors','systems','steps','transfers'],'root fields');
  if(value.schemaVersion!==1||value.fictional!==true)reject('schema/fictional marker');
  id(value.workflowId,'workflowId'); ids(value.actors,1,16,'actors'); ids(value.systems,1,16,'systems');
  array(value.steps,1,16,'steps'); array(value.transfers,0,32,'transfers');
  for(const step of value.steps){
    record(step,['id','system','responsible','accountable','consulted','informed','failureOwner','retry','handoffs'],'step fields');
    id(step.id,'step id'); id(step.system,'step system');
    for(const role of ['responsible','consulted','informed'])ids(step[role],0,16,role);
    nullableId(step.accountable,'accountable'); nullableId(step.failureOwner,'failureOwner');
    record(step.retry,['maxRetries','timeoutSeconds','idempotent'],'retry fields');
    integer(step.retry.maxRetries,0,3,'maxRetries'); integer(step.retry.timeoutSeconds,1,3600,'timeoutSeconds');
    if(step.retry.idempotent!==null&&typeof step.retry.idempotent!=='boolean')reject('idempotent');
    array(step.handoffs,0,16,'handoffs');
    for(const handoff of step.handoffs){
      record(handoff,['toStep','transferId'],'handoff fields');
      id(handoff.toStep,'handoff target'); nullableId(handoff.transferId,'transferId');
    }
    unique(step.handoffs.map(handoff=>handoff.toStep),'duplicate handoff target');
  }
  unique(value.steps.map(step=>step.id),'duplicate step');
  for(const transfer of value.transfers){
    record(transfer,['id','fromStep','toStep','dataCategories','approval','approver'],'transfer fields');
    for(const key of ['id','fromStep','toStep'])id(transfer[key],key);
    ids(transfer.dataCategories,1,16,'dataCategories'); nullableId(transfer.approver,'approver');
    if(!['declared-approved','denied','unknown'].includes(transfer.approval))reject('approval');
  }
  unique(value.transfers.map(transfer=>transfer.id),'duplicate transfer');

  const actors=new Set(value.actors), systems=new Set(value.systems);
  const steps=new Map(value.steps.map(step=>[step.id,step]));
  const transfers=new Map(value.transfers.map(transfer=>[transfer.id,transfer]));
  const usedTransfers=new Set(), issues=[];
  const issue=(scope,code,severity='blocked')=>issues.push({scope,code,severity});
  for(const step of value.steps){
    if(!systems.has(step.system))issue(step.id,'unregistered-system');
    if(!step.responsible.length)issue(step.id,'responsible-missing');
    if(step.accountable===null)issue(step.id,'accountable-unknown','unknown');
    if(step.failureOwner===null)issue(step.id,'failure-owner-unknown','unknown');
    const roleActors=[...step.responsible,...step.consulted,...step.informed,step.accountable,step.failureOwner];
    if(roleActors.some(actor=>actor!==null&&!actors.has(actor)))issue(step.id,'unregistered-actor');
    const retry=step.retry;
    if(retry.maxRetries===null)issue(step.id,'retry-limit-unknown','unknown');
    if(retry.timeoutSeconds===null)issue(step.id,'timeout-unknown','unknown');
    if(retry.maxRetries>0){
      if(retry.idempotent===false)issue(step.id,'retry-not-idempotent');
      else if(retry.idempotent===null)issue(step.id,'retry-idempotency-unknown','unknown');
    }
    for(const handoff of step.handoffs){
      const target=steps.get(handoff.toStep);
      if(!target)issue(step.id,'step-not-declared');
      if(handoff.toStep===step.id)issue(step.id,'self-handoff');
      if(handoff.transferId===null){
        if(target&&target.system!==step.system)issue(step.id,'undeclared-cross-system-transfer');
        continue;
      }
      const transfer=transfers.get(handoff.transferId);
      if(!transfer){issue(step.id,'transfer-not-declared');continue;}
      if(usedTransfers.has(transfer.id))issue(step.id,'transfer-reused');
      usedTransfers.add(transfer.id);
      if(transfer.fromStep!==step.id||transfer.toStep!==handoff.toStep)issue(step.id,'transfer-binding-mismatch');
    }
  }
  for(const transfer of value.transfers){
    if(!usedTransfers.has(transfer.id))issue(transfer.id,'unused-transfer');
    if(!steps.has(transfer.fromStep)||!steps.has(transfer.toStep))issue(transfer.id,'transfer-endpoint-not-declared');
    if(transfer.approval==='denied')issue(transfer.id,'transfer-denied');
    else if(transfer.approval==='unknown')issue(transfer.id,'transfer-approval-unknown','unknown');
    if(transfer.approver===null)issue(transfer.id,'transfer-approver-unknown','unknown');
    else if(!actors.has(transfer.approver))issue(transfer.id,'unregistered-approver');
  }
  return {
    schemaVersion:1,workflowId:value.workflowId,
    status:issues.some(item=>item.severity==='blocked')?'blocked':issues.length?'needs-clarification':'declared-consistent',
    issues,
    responsibilityMap:value.steps.map(({id:stepId,system,responsible,accountable,consulted,informed,failureOwner})=>({
      stepId,system,responsible,accountable,consulted,informed,failureOwner,
    })),
    boundary:{fictionalOnly:true,executionAuthorized:false,transferAuthorized:false,executed:false},
  };
}
