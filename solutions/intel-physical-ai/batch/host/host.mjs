// M6: single-host, local-file durable synthetic admission journal.
// No physical robot, identity provider, hardware E-stop or network listener.
import {mkdir,open,lstat,rmdir} from 'node:fs/promises';
import {constants} from 'node:fs';
import {resolve,join} from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';
import {genesis,verifyLedger,dispatch,MAX_EVENTS} from '../continuity/continuity.mjs';

export const HOST_VERSION='synthetic-local-host/1';
export const JOURNAL_MAX_BYTES=32*1024*1024;
const MAX_DENIED_BYTES=8*1024*1024;
const LOCK_RETRIES=1200;
const LOCK_INTERVAL_MS=12;
const journalName='admitted.jsonl';
const deniedName='denied.jsonl';
const lockName='.exclusive-writer.lock';
const hasOnly=(x,keys)=>x&&typeof x==='object'&&!Array.isArray(x)&&Object.keys(x).sort().join('|')===keys.slice().sort().join('|');
const stop=(code)=>{throw Error(code);};
const isObject=x=>x!==null&&typeof x==='object'&&!Array.isArray(x);

// Only a *trusted owner process* may provide authorize(). Client request JSON
// cannot supply the authorizer. This interface has no real operator identity.
export function localHost(directory,{authorize,afterDurableCommit}={}){
  if(typeof directory!=='string'||!directory.startsWith('/')||!directory.trim())
    stop('INVALID_HOST_DIRECTORY');
  if(authorize!==undefined&&typeof authorize!=='function')stop('INVALID_AUTHORIZER');
  if(afterDurableCommit!==undefined&&typeof afterDurableCommit!=='function')
    stop('INVALID_HOOK');
  const root=resolve(directory);
  const journal=join(root,journalName),denied=join(root,deniedName),lock=join(root,lockName);

  async function checkDir(){
    const st=await lstat(root).catch(e=>e.code==='ENOENT'?null:Promise.reject(e));
    if(!st||!st.isDirectory()||st.isSymbolicLink()||(st.mode&0o077)!==0)
      stop('UNTRUSTED_STORAGE_DIRECTORY');
  }
  async function checkFile(file){
    const st=await lstat(file).catch(e=>e.code==='ENOENT'?null:Promise.reject(e));
    if(st&&(!st.isFile()||st.isSymbolicLink()||(st.mode&0o077)!==0))
      stop('UNTRUSTED_STORAGE_FILE');
    return st;
  }
  async function syncDirectory(){
    let h;
    try{h=await open(root,constants.O_RDONLY);await h.sync();}
    finally{if(h)await h.close();}
  }
  async function exclusive(task){
    await checkDir();
    let owned=false;
    for(let i=0;i<=LOCK_RETRIES;i++){
      try{await mkdir(lock,{mode:0o700});owned=true;break;}
      catch(e){
        if(e.code!=='EEXIST')throw e;
        if(i===LOCK_RETRIES)stop('STORE_LOCK_BUSY_OR_ORPHANED');
        await delay(LOCK_INTERVAL_MS);
      }
    }
    try{return await task();}
    finally{
      if(owned){await rmdir(lock).catch(()=>stop('STORE_LOCK_RELEASE_FAILED'));}
    }
  }
  async function append(file,text,max){
    const previous=await checkFile(file);
    const bytes=Buffer.byteLength(text);
    if(bytes===0||bytes>max||(previous?.size??0)+bytes>max)
      stop('STORAGE_CAPACITY_EXHAUSTED');
    const flags=constants.O_WRONLY|constants.O_APPEND|constants.O_CREAT|constants.O_NOFOLLOW;
    let h;
    try{
      h=await open(file,flags,0o600);
      const b=Buffer.from(text);
      let written=0;
      while(written<b.length){
        const r=await h.write(b,written,b.length-written);
        if(r.bytesWritten<1)stop('STORE_SHORT_WRITE');
        written+=r.bytesWritten;
      }
      await h.sync();
    }finally{if(h)await h.close();}
    if(!previous)await syncDirectory();
  }
  async function readRecords(){
    if(!await checkFile(journal))stop('HOST_NOT_INITIALIZED');
    const h=await open(journal,constants.O_RDONLY|constants.O_NOFOLLOW);
    let content;
    try{
      const s=await h.stat();
      if(s.size>JOURNAL_MAX_BYTES||s.size<4)stop('JOURNAL_CAPACITY_INVALID');
      content=await h.readFile({encoding:'utf8'});
    }finally{await h.close();}
    if(!content.endsWith('\n'))stop('JOURNAL_TORN_OR_TRUNCATED');
    const lines=content.slice(0,-1).split('\n');
    if(lines.length<1||lines.length>MAX_EVENTS+1)stop('JOURNAL_LENGTH_INVALID');
    return lines.map(line=>{
      let parsed;
      try{parsed=JSON.parse(line);}catch{stop('JOURNAL_JSON_INVALID');}
      if(!hasOnly(parsed,['kind','previousRoot','snapshot']))stop('JOURNAL_RECORD_INVALID');
      return parsed;
    });
  }
  async function load(){
    const records=await readRecords();
    let previous=null;
    for(let i=0;i<records.length;i++){
      const item=records[i];
      if((i===0&&item.kind!=='GENESIS')||
         (i>0&&item.kind!=='ADMITTED')||
         item.previousRoot!==(previous?.root??null))
        stop('JOURNAL_LINK_BROKEN');
      const verified=await verifyLedger(item.snapshot);
      if(i===0){
        const g=await genesis();
        if(verified.root!==g.root||verified.state.revision!==0||verified.events.length!==0)
          stop('JOURNAL_GENESIS_INVALID');
      }else if(verified.state.revision!==previous.state.revision+1 ||
               verified.events.length!==previous.events.length+1 ||
               verified.events.at(-1).previous!==previous.root)
        stop('JOURNAL_REVISION_BREAK');
      previous=verified;
    }
    return previous;
  }
  async function storeDenial(reason,current,request){
    // Rejected inputs are not serialized. Persist only a bounded reason +
    // operational root; no raw user text, camera frame or API credentials.
    const safeReason=(typeof reason==='string'&&/^[A-Z_]{2,64}$/.test(reason))?reason:'REFUSED';
    const event=(typeof request?.eventId==='string'&&
      /^[a-z0-9][a-z0-9-]{2,63}$/.test(request.eventId))?request.eventId:null;
    const item={version:HOST_VERSION,status:'DENIED',reason:safeReason,
      operationalRoot:current.root,eventId:event,revision:current.state.revision};
    await append(denied,JSON.stringify(item)+'\n',MAX_DENIED_BYTES);
    return {status:'DENIED',reason:safeReason,state:current,operationalRoot:current.root};
  }
  async function initialize(){
    await mkdir(root,{mode:0o700,recursive:true});
    return exclusive(async()=>{
      if(await checkFile(journal))return load();
      // State exists iff this record is fully written and fsynced. If crash
      // tears the initial record, no automatic cleanup/reinitialization.
      const state=await genesis();
      await append(journal,JSON.stringify({kind:'GENESIS',previousRoot:null,snapshot:state})+'\n',JOURNAL_MAX_BYTES);
      return state;
    });
  }
  async function read(){
    return exclusive(load);
  }
  async function submit(request,{expectedRoot}={}){
    // No network endpoint. The caller must supply the last observed root and
    // M5 expected revision+epoch. Authorization is private host closure only.
    return exclusive(async()=>{
      const current=await load();
      // Idempotent identical retries are safe even if caller never received
      // the durable commit acknowledgement.
      const previous=current.events.find(e=>e.request?.eventId===request?.eventId);
      if(previous){
        const reply=await dispatch(current,request);
        if(reply.status==='CACHED')return reply;
        return storeDenial(reply.reason,current,request);
      }
      if(expectedRoot!==current.root)
        return storeDenial('STALE_HEAD_ROOT',current,request);
      let reply;
      try{reply=await dispatch(current,request,{authorize});}
      catch(e){return storeDenial('UNVERIFIED_REQUEST',current,request);}
      if(reply.status==='DENIED')return storeDenial(reply.reason,current,request);
      if(reply.status==='CACHED')return reply;
      if(reply.status!=='ADMITTED'||!reply.state||reply.previousRoot!==current.root)
        stop('HOST_ADMISSION_INCONSISTENT');
      // Host-wide exclusive lock covers the entire authorize+CAS+fsync cycle.
      // This append becomes authoritative ONLY after file and metadata fsync.
      await append(journal,JSON.stringify({
        kind:'ADMITTED',previousRoot:current.root,snapshot:reply.state
      })+'\n',JOURNAL_MAX_BYTES);
      // Special test hook models lost ACK AFTER durable commit. It must not
      // affect ledger contents; a retry gets CACHED from the journal.
      if(afterDurableCommit)await afterDurableCommit({
        admittedRoot:reply.state.root,previousRoot:current.root
      });
      return reply;
    });
  }
  async function inspectDenied(){
    return exclusive(async()=>{
      const st=await checkFile(denied);
      if(!st)return [];
      if(st.size>MAX_DENIED_BYTES)stop('DENIED_AUDIT_CAPACITY');
      const h=await open(denied,constants.O_RDONLY|constants.O_NOFOLLOW);
      let content;
      try{content=await h.readFile({encoding:'utf8'});}finally{await h.close();}
      if(!content.endsWith('\n'))stop('DENIED_AUDIT_TORN');
      return content.slice(0,-1).split('\n').filter(Boolean).map(x=>{
        let d;try{d=JSON.parse(x);}catch{stop('DENIED_AUDIT_INVALID');}
        if(!hasOnly(d,['version','status','reason','operationalRoot','eventId','revision'])||
           d.version!==HOST_VERSION||d.status!=='DENIED')stop('DENIED_AUDIT_INVALID');
        return d;
      });
    });
  }
  return Object.freeze({initialize,read,submit,inspectDenied});
}
