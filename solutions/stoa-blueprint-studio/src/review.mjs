import { canonical, digest, sourceRevision } from './evidence.mjs';
const fail = (message,status=422) => {const error=new Error(message);error.status=status;throw error;};
const clone = x=>structuredClone(x);
const exact = (x,keys) => x && typeof x==='object' && !Array.isArray(x) && Object.keys(x).sort().join('|')===[...keys].sort().join('|');
export function createReviewStore(drawing, record) {
  const source=sourceRevision(drawing), ids=new Set(drawing.entities.map(e=>e.id));
  let revision=0,current=null,past=[],future=[];
  const events=[],operations=new Map();
  const snapshot=()=>({sourceRevision:source,answerId:record.id,revision,current:clone(current),events:clone(events),canUndo:past.length>0,canRedo:future.length>0,
    reviewerIdentity:'locally-declared',independentVerification:false});
  return {snapshot,apply(command){
    const common=['operationId','expectedRevision','sourceRevision','kind','reviewer'];
    const keys=command?.kind==='correct'?[...common,'answer','entityIds','note']:command?.kind==='confirm'?[...common,'note']:common;
    if(!exact(command,keys))fail('Invalid review command fields.');
    if(typeof command.operationId!=='string'||!/^[a-zA-Z0-9_-]{8,80}$/.test(command.operationId))fail('Invalid operation ID.');
    const hash=digest(canonical(command));
    if(operations.has(command.operationId)){
      if(operations.get(command.operationId)!==hash)fail('Operation ID already used for different content.',409);
      return snapshot();
    }
    if(command.sourceRevision!==source)fail('Review belongs to a different source revision.',409);
    if(command.expectedRevision!==revision)fail('Review changed. Reload before applying your edit.',409);
    if(events.length>=100)fail('Review history limit reached; export before starting a new review.');
    if(typeof command.reviewer!=='string'||!command.reviewer.trim()||command.reviewer.length>80)fail('Enter a reviewer name (locally declared).');
    if(command.kind==='confirm'||command.kind==='correct'){
      if(typeof command.note!=='string'||command.note.length>1000)fail('Review note exceeds 1,000 characters.');
      if(command.kind==='confirm'&&record.result.status!=='supported')fail('An unsupported engine answer cannot be confirmed. Record a cited correction instead.');
      let entityIds=record.result.evidence.map(e=>e.entityId);
      if(command.kind==='correct'){
        if(typeof command.answer!=='string'||!command.answer.trim()||command.answer.length>400)fail('Enter a correction up to 400 characters.');
        entityIds=command.entityIds;
        if(!Array.isArray(entityIds)||!entityIds.length||entityIds.length>100||new Set(entityIds).size!==entityIds.length||entityIds.some(id=>!ids.has(id)))fail('Correction citations must be unique entities from the current source.');
      }
      past.push(clone(current));future=[];
      current={status:command.kind==='confirm'?'confirmed':'corrected',answer:command.kind==='correct'?command.answer.trim():record.result.answer,
        entityIds:[...entityIds],note:command.note,reviewer:command.reviewer.trim(),independentVerification:false};
    }else if(command.kind==='undo'){
      if(!past.length)fail('Nothing to undo.');future.push(clone(current));current=past.pop();
    }else if(command.kind==='redo'){
      if(!future.length)fail('Nothing to redo.');past.push(clone(current));current=future.pop();
    }else fail('Unknown review operation.');
    revision++;events.push({revision,operationId:command.operationId,kind:command.kind,reviewer:command.reviewer.trim(),state:clone(current)});
    operations.set(command.operationId,hash);
    return snapshot();
  }};
}
