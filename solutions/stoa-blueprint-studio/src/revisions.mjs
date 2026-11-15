import { sourceIdentity, canonical, digest } from './evidence.mjs';
import { assign } from './assignment.mjs';
import { answerDrawingV2 } from './quantities.mjs';
const scales={1:.0254,2:.3048,4:.001,5:.01,6:1};
const roomNumber=/^(?:[A-Z]-\d+|[A-Z]?\d+(?:[.\-]\d+)+)$/;
const fail=message=>{throw new Error(message);};
function rooms(drawing){
  const groups=new Map();
  for(const e of drawing.entities)if(e.layer==='ROOM_TEXT'&&roomNumber.test(e.text?.trim()??'')){
    const key=e.text.trim();if(!groups.has(key))groups.set(key,[]);groups.get(key).push(e);
  }
  if (groups.size>250) fail('Room comparison exceeds 250 room identifiers. Narrow the source before comparing.');
  const points=drawing.entities.reduce((s,e)=>s+(e.points?.length??0),0);
  const texts=drawing.entities.filter(e=>e.layer==='ROOM_TEXT').length;
  if (groups.size*points*(texts+1)>50000000) fail('Room evidence validation exceeds the work budget. Narrow the source before comparing.');
  return new Map([...groups].map(([key,hits])=>{
    const answer=answerDrawingV2(drawing,`What is the area of room ${key}?`);
    const outline=drawing.entities.find(e=>answer.evidence.some(c=>c.entityId===e.id)&&e.points);
    const label=hits[0];
    return [key,{key,id:outline?.id??label.id,labelId:label.id,area:answer.metric?.value??null,
      ambiguous:hits.length!==1,valid:hits.length===1&&answer.status==='supported',reason:answer.explanation,
      shape:outline?geometry(outline,scales[drawing.units]):null,evidence:answer.evidence.map(c=>c.entityId)}];
  }));
}
function geometry(e,scale){
  const num=x=>Math.round(x*scale*1e9)/1e9;
  return {type:e.type,layer:e.layer,points:e.points?.map(p=>[num(p.x),num(p.y)])??null,
    position:Number.isFinite(e.x)&&Number.isFinite(e.y)?[num(e.x),num(e.y)]:null,
    radius:Number.isFinite(e.radius)?num(e.radius):null,start:e.start??null,end:e.end??null,closed:e.closed??false,text:e.text??null};
}
function centre(g){
  if(g.position)return g.position;
  return [g.points.reduce((s,p)=>s+p[0],0)/g.points.length,g.points.reduce((s,p)=>s+p[1],0)/g.points.length];
}
function compareRooms(before,after){
  const old=rooms(before),next=rooms(after),changes=[];
  for(const key of [...new Set([...old.keys(),...next.keys()])].sort()){
    const a=old.get(key),b=next.get(key);
    const status=a?.ambiguous||b?.ambiguous?'ambiguous':!a?'added':!b?'removed':!a.valid||!b.valid?'incomparable':
      Math.abs(a.area-b.area)>1e-6?'area_changed':canonical(a.shape)!==canonical(b.shape)?'geometry_changed':'unchanged';
    changes.push({key,status,beforeId:a?.id??null,afterId:b?.id??null,beforeArea:a?.area??null,afterArea:b?.area??null,
      areaDelta:a?.valid&&b?.valid?Math.round((b.area-a.area)*100)/100:null,
      beforeEvidence:a?.evidence??[],afterEvidence:b?.evidence??[],
      reason:status==='incomparable'?`Before: ${a.reason} After: ${b.reason}`:null});
  }
  return {method:'unique-room-number-and-cross-checked-area/v1',changes};
}
function comparePrimitives(before,after,layer,tolerance){
  if(typeof layer!=='string'||!layer.trim()||layer.length>80)fail('Choose one exact DXF source layer.');
  const prepare=d=>d.entities.filter(e=>e.layer===layer&&!e.unsupportedGeometry&&(e.points?.length||Number.isFinite(e.x))).map(e=>({id:e.id,g:geometry(e,scales[d.units])}));
  const old=prepare(before),next=prepare(after);
  if(old.length>600||next.length>600)fail('Layer exceeds 600 source primitives. Narrow the source before comparing.');
  const edges=[];
  for(const a of old)for(const b of next){
    if(a.g.type!==b.g.type)continue;
    const x=centre(a.g),y=centre(b.g),distance=Math.hypot(x[0]-y[0],x[1]-y[1]);
    if(distance>tolerance)continue;
    const same=canonical(a.g)===canonical(b.g);
    edges.push({oldId:a.id,newId:b.id,cost:same?0:Math.min(1.9,.25+distance/tolerance)});
  }
  const match=assign(old.map(e=>e.id),next.map(e=>e.id),edges);
  const a=new Map(old.map(e=>[e.id,e.g])),b=new Map(next.map(e=>[e.id,e.g]));
  const changes=[...match.pairs.map(p=>({beforeId:p.oldId,afterId:p.newId,status:p.ambiguousCandidates?'ambiguous':canonical(a.get(p.oldId))===canonical(b.get(p.newId))?'unchanged':'changed',cost:p.cost})),
    ...match.unmatchedOld.map(id=>({beforeId:id,afterId:null,status:'unmatched_before'})),...match.unmatchedNew.map(id=>({beforeId:null,afterId:id,status:'unmatched_after'}))];
  return {method:match.method,layer,changes,limits:['Source primitives are not physical door/window instances.','Unmatched does not prove physical addition or removal.','Candidate ambiguity is not a proof of optimal assignment uniqueness.']};
}
function compareIfc(before,after){
  const group=d=>{const m=new Map();for(const e of d.entities)if(e.guid){if(!m.has(e.guid))m.set(e.guid,[]);m.get(e.guid).push(e);}return m;};
  const old=group(before),next=group(after);
  if(!old.size||!next.size)fail('Both IFC sources need native product GUIDs for revision comparison.');
  const keys=[...new Set([...old.keys(),...next.keys()])].sort();
  if(keys.length>2000)fail('IFC comparison exceeds 2,000 product GUIDs.');
  return {method:'native-ifc-guid-record-comparison/v1',limits:['STEP record changes can reflect renumbered references, not physical changes.','No IFC geometry projection or physical identity verification.'],changes:keys.map(key=>{
    const aa=old.get(key)??[],bb=next.get(key)??[],a=aa[0],b=bb[0];
    return {key,beforeId:a?.id??null,afterId:b?.id??null,status:aa.length>1||bb.length>1?'ambiguous':!a?'added':!b?'removed':a.sourceText===b.sourceText?'unchanged':'record_changed'};
  })};
}
export function compareSources(before,after,{mode='rooms',layer='ROOM_OUTLINE',alignmentDeclared=false,toleranceMetres=.25}={}){
  if(before.format!==after.format)fail('Cross-format comparison requires a separately validated alignment and is not supported.');
  let comparison;
  if(before.format==='IFC STEP'){
    if(mode!=='ifc')fail('Use IFC GUID comparison for IFC sources.');comparison=compareIfc(before,after);
  }else{
    if(!scales[before.units]||!scales[after.units])fail('Both drawings need supported units.');
    if(alignmentDeclared!==true)fail('Confirm that the drawings share an origin and orientation. Automatic alignment is not performed.');
    if(!Number.isFinite(toleranceMetres)||toleranceMetres<=0||toleranceMetres>10)fail('Use a matching distance in (0,10] metres.');
    if(mode==='rooms')comparison=compareRooms(before,after);
    else if(mode==='primitives')comparison=comparePrimitives(before,after,layer,toleranceMetres);
    else fail('Unknown comparison mode.');
  }
  const payload={schema:'stoa.revision-comparison/v1',before:sourceIdentity(before),after:sourceIdentity(after),...comparison,
    matchingDistanceMetres:mode==='primitives'?toleranceMetres:null,alignment:{declared:alignmentDeclared,independentlyVerified:false},physicalChangeVerified:false,
    summary:Object.fromEntries([...new Set(comparison.changes.map(c=>c.status))].sort().map(k=>[k,comparison.changes.filter(c=>c.status===k).length]))};
  return {payload,integrity:{algorithm:'sha256',sha256:digest(payload),signed:false}};
}
