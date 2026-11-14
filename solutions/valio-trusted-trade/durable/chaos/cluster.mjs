/**
 * Explicitly owned disposable PostgreSQL WAL-crash cluster.
 * NEVER targets a host service, an existing PGDATA, or production credentials.
 */
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {mkdtemp,mkdir,readFile,realpath,access,rm} from 'node:fs/promises';
import {join,resolve,isAbsolute} from 'node:path';
import {tmpdir} from 'node:os';

const exec=promisify(execFile);
const SAFE_SOCKET=/^[a-zA-Z0-9_/-]+$/;
const timeout=ms=>new Promise(r=>setTimeout(r,ms));

export async function locatePgBins(explicit=process.env.VALIO_PG_BIN_DIR) {
  const candidates=explicit?[explicit]:[18,17,16,15,14].map(v=>`/usr/lib/postgresql/${v}/bin`);
  for(const d of candidates) {
    if(!isAbsolute(d))continue;
    try {
      const dir=await realpath(d);
      for(const b of ['initdb','pg_ctl','postgres'])await access(join(dir,b));
      return dir;
    }catch{ /* try next installed distribution */ }
  }
  throw new Error('BLOCKED_PG_BIN: initdb/pg_ctl/postgres unavailable; install a PostgreSQL server toolchain in the authorized ephemeral runner.');
}

async function run(bin,args,{timeoutMs=60000}={}) {
  try {
    const {stdout,stderr}=await exec(bin,args,{timeout:timeoutMs,maxBuffer:1024*1024,
      env:{...process.env,LC_ALL:'C'}});
    return {stdout,stderr};
  }catch(e){
    const reason=(String(e.stderr||'')+' '+String(e.stdout||'')).slice(-1200);
    throw new Error(`PostgreSQL tool ${bin.split('/').at(-1)} failed (exit ${e.code||'unknown'}): ${reason}`);
  }
}

export async function createOwnedCluster({binDir,port=55439}={}) {
  if(process.platform!=='linux'||process.getuid?.()===0)
    throw new Error('BLOCKED_HOST: dedicated WAL SIGKILL lab requires a non-root Linux test runner.');
  if(!Number.isInteger(port)||port<1025||port>65535)throw new Error('Invalid isolated Unix-socket port.');
  const verified=binDir||await locatePgBins();
  const prefix=join(tmpdir(),'j26-valio-wal-');
  const root=await mkdtemp(prefix);
  const dataDir=join(root,'data'),socketDir=join(root,'sockets'),logFile=join(root,'postgres.log');
  try {
    await mkdir(dataDir,{mode:0o700});await mkdir(socketDir,{mode:0o700});
    if(!SAFE_SOCKET.test(socketDir)||socketDir.length>90)
      throw new Error('Unsafe or overlong local socket path.');
    const cluster={root,dataDir,socketDir,logFile,binDir:verified,port,
      dsn:`socket:${socketDir}?db=postgres&port=${port}`,startCount:0,crashed:false};
    await run(join(verified,'initdb'),['-D',dataDir,'--no-instructions','--encoding=UTF8',
      '--auth-local=trust','--auth-host=reject'],{timeoutMs:90000});
    return cluster;
  }catch(e){
    // No postgres server has been started; only this newly created empty/failed
    // temporary test cluster is eligible for cleanup.
    await rm(root,{recursive:true,force:false});
    throw e;
  }
}

function serverOpts(c) {
  return `-c listen_addresses= -c unix_socket_directories=${c.socketDir} -c port=${c.port} `+
    '-c fsync=on -c synchronous_commit=on -c full_page_writes=on -c max_connections=48';
}

export async function startOwnedCluster(c) {
  await run(join(c.binDir,'pg_ctl'),['-D',c.dataDir,'-l',c.logFile,
    '-o',serverOpts(c),'-w','-t','45','start'],{timeoutMs:60000});
  c.startCount++;
  return await verifyOwnPostmaster(c);
}

export async function verifyOwnPostmaster(c) {
  const pidLines=(await readFile(join(c.dataDir,'postmaster.pid'),'utf8')).trimEnd().split('\n');
  const pid=Number(pidLines[0]);
  if(!Number.isSafeInteger(pid)||pid<2||resolve(pidLines[1])!==resolve(c.dataDir))
    throw new Error('STOP: PGDATA does not match the task-created test cluster.');
  const [exe,expected,command]=await Promise.all([
    realpath(`/proc/${pid}/exe`),realpath(join(c.binDir,'postgres')),
    readFile(`/proc/${pid}/cmdline`,'utf8')]);
  if(exe!==expected||!command.includes(c.dataDir))
    throw new Error('STOP: postmaster executable/argv did not match owned data directory.');
  return pid;
}

export async function sigkillOwnedPostmaster(c) {
  if(c.crashed||c.startCount!==1)
    throw new Error('STOP: SIGKILL is permitted exactly once for the original isolated cluster.');
  const pid=await verifyOwnPostmaster(c);
  const expected=await realpath(join(c.binDir,'postgres'));
  let listed=[];
  try {
    listed=(await readFile(`/proc/${pid}/task/${pid}/children`,'utf8'))
      .trim().split(/\s+/).map(Number).filter(n=>Number.isSafeInteger(n)&&n>1);
  }catch{ /* no child list; only verified postmaster is eligible */ }
  const verifiedChildren=[];
  for(const child of listed) {
    try {if(await realpath(`/proc/${child}/exe`)===expected)verifiedChildren.push(child);}catch{}
  }
  process.kill(pid,'SIGKILL'); // Exact verified test postmaster, never a host PG service.
  await timeout(150);
  for(const child of verifiedChildren) {
    try {if(await realpath(`/proc/${child}/exe`)===expected)process.kill(child,'SIGKILL');}catch{}
  }
  c.crashed=true;
  await timeout(300);
  return {oldPostmasterPid:pid,verifiedChildrenKilled:verifiedChildren.length,signal:'SIGKILL'};
}

export async function recoverySignals(c) {
  const text=await readFile(c.logFile,'utf8');
  return {
    interrupted:/database system (was interrupted|was not properly shut down)/i.test(text),
    redo:/redo starts at/i.test(text),
    accepting:/database system is ready to accept connections/i.test(text),
    logBytes:Buffer.byteLength(text)
  };
}

export async function closeOwnedCluster(c,{keepData=false}={}) {
  if(!c)return {removed:false};
  let running=false;
  try {await verifyOwnPostmaster(c);running=true;}catch{}
  // Fail closed: an ambiguous PID file or failed restart must not result in
  // recursively deleting PGDATA of an active/unverified process.
  if(!running){
    try {
      const raw=await readFile(join(c.dataDir,'postmaster.pid'),'utf8');
      const pid=Number(raw.split('\n')[0]);
      if(Number.isSafeInteger(pid)&&pid>1){
        try{process.kill(pid,0);return {removed:false,retained:c.root,reason:'PID exists but ownership could not be confirmed.'};}
        catch(e){if(e.code!=='ESRCH')return {removed:false,retained:c.root,reason:'PID ownership or state uncertain.'};}
      }
    }catch{}
  }
  if(c.crashed&&c.startCount===1)
    return {removed:false,retained:c.root,reason:'Crash recovery did not complete; retained isolated cluster for diagnostics.'};
  if(running){
    try {await run(join(c.binDir,'pg_ctl'),['-D',c.dataDir,'-w','-m','immediate','stop'],{timeoutMs:60000});}
    catch {return {removed:false,retained:c.root,reason:'Owned server could not be verified stopped.'};}
  }
  if(keepData)return {removed:false,retained:c.root,reason:'Requested retained disposable test data.'};
  const root=await realpath(c.root),temp=await realpath(tmpdir());
  if(!root.startsWith(join(temp,'j26-valio-wal-')))
    throw new Error('STOP: cleanup path is not an owned temporary WAL lab.');
  await rm(root,{recursive:true,force:false});
  return {removed:true};
}
