import {plan,runBatch,replayBatch} from '../cell.mjs';
export const MAX_BYTES=2*1024*1024;
export const REASONS=Object.freeze(['Conservative simulation requested','Operator inspection required','Pause for handling review','Stop for evidence review']);
export function seedValue(value) {
  if(typeof value!=='string' || !/^\d{1,10}$/.test(value) || Number(value)>0xffffffff) throw Error('Enter a whole seed from 0 to 4294967295.');
  return Number(value);
}
// UI reasons are constrained; imported M2 receipts retain their original valid reasons.
export class Studio {
  constructor(){this.request=null;this.receipt=null;this.verified=false;this.revision=0;}
  invalidate(){this.receipt=null;this.verified=false;this.revision++;}
  generate(seed){this.invalidate();this.request=null;this.request=plan(seedValue(seed));return this.request;}
  edit(index,decision,reason){
    this.invalidate();
    if(!this.request?.episodes[index] || !['continue','stop'].includes(decision) || !REASONS.includes(reason)) throw Error('Choose an operator decision and reason.');
    this.request.episodes[index].operator={decision,reason};
  }
  async run(){
    this.invalidate();const revision=this.revision;
    if(!this.request)throw Error('Generate a batch first.');
    const result=await runBatch(structuredClone(this.request));
    const verified=await replayBatch(result);
    if(this.revision!==revision)throw Error('Batch changed during execution. Run again.');
    this.receipt=verified;this.verified=true;return verified;
  }
  async importText(text){
    this.invalidate();this.request=null;const revision=this.revision;
    if(new TextEncoder().encode(text).byteLength>MAX_BYTES)throw Error('Receipt exceeds 2 MiB.');
    const verified=await replayBatch(JSON.parse(text));
    if(this.revision!==revision)throw Error('Batch changed during verification. Import again.');
    this.request=structuredClone(verified.request);this.receipt=verified;this.verified=true;return verified;
  }
  exportText(){if(!this.verified || !this.receipt)throw Error('Run or import and verify a batch first.');return JSON.stringify(this.receipt,null,2)+'\n';}
}
