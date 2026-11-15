import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';

export const canonical = value => {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  return '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + canonical(value[k])).join(',') + '}';
};
export const digest = value => createHash('sha256').update(typeof value === 'string' || Buffer.isBuffer(value) ? value : canonical(value)).digest('hex');
export const sourceRevision = drawing => drawing.sha256 || digest({format:drawing.format,units:drawing.units,entities:drawing.entities});
export const sourceIdentity = drawing => ({revision:sourceRevision(drawing),sha256:drawing.sha256??null,
  sourceKind:drawing.id==='demo'?'synthetic_demo':'user_import',synthetic:drawing.id==='demo'?true:null,filename:drawing.filename,format:drawing.format,units:drawing.unitsLabel});
const files = ['evidence.mjs','review.mjs','revisions.mjs','assignment.mjs','server.mjs','dxf.mjs','grounding.mjs','quantities.mjs','ifc.mjs','ifc-qa.mjs'];
export async function engineIdentity() {
  const hashes = Object.fromEntries(await Promise.all(files.map(async name => [name,digest(await readFile(new URL(name,import.meta.url)))])));
  return {sha256:digest(hashes),files:hashes,identity:'actual-source-bytes',authenticity:'not-signed'};
}
export function resolveEvidence(drawing, citations) {
  const entities = new Map(drawing.entities.map(e=>[e.id,e]));
  const resolved = new Map();
  for (const cite of citations) {
    const e = entities.get(cite.entityId);
    if (!e || e.type !== cite.kind) throw new Error('Citation does not resolve to the current source.');
    resolved.set(e.id,structuredClone(e));
    for (const q of cite.quantitySources??[]) {
      const entity=entities.get(q.entityId);
      if (!entity) throw new Error('Quantity citation does not resolve to the current source.');
      resolved.set(entity.id,structuredClone(entity));
    }
  }
  return [...resolved.values()];
}
export function evidencePacket(drawing, record, engine, review) {
  if (record.sourceRevision !== sourceRevision(drawing)) throw new Error('Stale answer source.');
  const evidence = resolveEvidence(drawing,record.result.evidence);
  const manualIds = review.current?.entityIds??[];
  const byId=new Map(drawing.entities.map(e=>[e.id,e]));
  const payload={schema:'stoa.evidence-packet/v1',source:sourceIdentity(drawing),engine,
    question:record.question,result:structuredClone(record.result),evidence,review:structuredClone(review),
    reviewerEvidence:manualIds.map(id=>{if(!byId.has(id))throw new Error('Unknown review citation.');return structuredClone(byId.get(id));}),
    limits:['Hash integrity is not source authenticity or independent verification.',
      'Reviewer identity is locally declared, not authenticated.',
      'Selected source excerpts may be subject to the original source licence.']};
  if (Buffer.byteLength(canonical(payload)) > 16*1024*1024) throw new Error('Evidence packet exceeds 16 MiB. Narrow the source question before exporting.');
  return {payload,integrity:{algorithm:'sha256',sha256:digest(payload),signed:false}};
}
export function verifyPacket(packet) {
  if (packet?.payload?.schema !== 'stoa.evidence-packet/v1' || packet.integrity?.algorithm !== 'sha256' || packet.integrity.signed !== false || digest(packet.payload)!==packet.integrity.sha256) throw new Error('Evidence packet integrity mismatch.');
  return {integrity:'matched',authenticity:'not-verified',sourceRevision:packet.payload.source.revision,engineSha256:packet.payload.engine.sha256};
}
