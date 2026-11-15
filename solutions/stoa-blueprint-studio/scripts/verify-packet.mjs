import { readFile } from 'node:fs/promises';
import { verifyPacket, engineIdentity, digest } from '../src/evidence.mjs';
if(!process.argv[2])throw new Error('Usage: node scripts/verify-packet.mjs <evidence-packet.json>');
const raw=await readFile(process.argv[2]);if(raw.length>16*1024*1024)throw new Error('Packet exceeds 16 MiB.');
const packet=JSON.parse(raw);
let result;
if(packet?.payload?.schema==='stoa.revision-comparison/v1'){
  if(packet.integrity?.algorithm!=='sha256'||packet.integrity.signed!==false||digest(packet.payload)!==packet.integrity.sha256)throw new Error('Comparison integrity mismatch.');
  result={integrity:'matched',authenticity:'not-verified',beforeRevision:packet.payload.before.revision,afterRevision:packet.payload.after.revision,engineSha256:packet.payload.engine?.sha256??null};
}else result=verifyPacket(packet);
const engine=await engineIdentity();
console.log(JSON.stringify({...result,currentEngineMatches:engine.sha256===result.engineSha256},null,2));
