// Reproducible, non-overwriting source export; no provider calls or credentials.
import {spawnSync} from 'node:child_process';
import {constants} from 'node:fs';
import {createHash} from 'node:crypto';
import {lstat, mkdir, open, readFile, readdir, realpath, writeFile} from 'node:fs/promises';
import {basename, dirname, isAbsolute, join, posix, relative, resolve, sep} from 'node:path';
import {fileURLToPath} from 'node:url';

const PREFIX='solutions/hostinger-manipulation-radar/';
const REQUIRED=['Dockerfile','compose.yaml','server.mjs','services.mjs','source-seal.mjs'];
const PACKAGE_FILES=new Set(['.dockerignore','.env.example','Caddyfile','Dockerfile','compose.yaml','HOSTINGER_DEPLOYMENT.md','benchmark.mjs','evaluation-v2.mjs','server.mjs','services.mjs','deploy.mjs','source-seal.mjs']);
const PACKAGE_PREFIXES=['public/','fixtures/','stress/'];
const SHA=/^[a-f0-9]{40}$/;
const HASH=/^[a-f0-9]{64}$/;
const MAX_FILES=300, MAX_BYTES=8*1024*1024, MAX_MANIFEST=256*1024;
const digest=buf=>createHash('sha256').update(buf).digest('hex');
const reject=code=>{throw new Error(code);};
const validPath=path=>typeof path==='string'&&path.length>0&&path.length<260&&!path.startsWith('/')&&!path.includes('\\')&&path.split('/').every(x=>x&&x!=='.'&&x!=='..')&&posix.normalize(path)===path;
function git(root,args,maxBuffer=MAX_BYTES+1024) {
 const r=spawnSync('git',['-C',root,...args],{encoding:null,maxBuffer,timeout:20000});
 if(r.error||r.status!==0)reject('SOURCE_GIT_UNAVAILABLE_OR_INVALID');
 return r.stdout;
}
function manifestPaths(files) {
 if(!Array.isArray(files)||files.length<REQUIRED.length||files.length>MAX_FILES)reject('INVALID_SOURCE_SEAL');
 let previous='';
 for(const x of files) {
  if(!x||!validPath(x.path)||x.path<=previous||!HASH.test(x.sha256)||!Number.isSafeInteger(x.bytes)||x.bytes<0||x.bytes>MAX_BYTES)reject('INVALID_SOURCE_SEAL');
  previous=x.path;
 }
 for(const name of REQUIRED)if(!files.some(f=>f.path===name))reject('INCOMPLETE_SOURCE_SEAL');
}
export async function exportSource({repoRoot,sourceRevision,out}) {
 if(!SHA.test(sourceRevision))reject('INVALID_SOURCE_REVISION');
 const root=await realpath(repoRoot);
 const requested=resolve(out),output=join(await realpath(dirname(requested)),basename(requested)),distance=relative(root,output);
 if(!distance||(!distance.startsWith('..'+sep)&&distance!=='..'&&!isAbsolute(distance)))reject('OUTPUT_MUST_BE_OUTSIDE_REPOSITORY');
 if(git(root,['cat-file','-t',sourceRevision]).toString().trim()!=='commit')reject('INVALID_SOURCE_REVISION');
 const tree=git(root,['ls-tree','-r','-z','--long',sourceRevision,'--',PREFIX]);
 const entries=tree.toString('utf8').split('\0').filter(Boolean);
 if(entries.length>MAX_FILES||entries.length<REQUIRED.length)reject('INVALID_SOURCE_TREE');
 const files=[];let total=0;
 for(const line of entries) {
  const split=line.indexOf('\t'),meta=line.slice(0,split).trim().split(/\s+/);
  const path=line.slice(split+1);
  if(split<0||meta.length!==4||!['100644','100755'].includes(meta[0])||meta[1]!=='blob'||!path.startsWith(PREFIX))reject('INVALID_SOURCE_TREE');
  const name=path.slice(PREFIX.length),bytes=Number(meta[3]);
  if(!validPath(name)||name==='SOURCE_SEAL.json'||!Number.isSafeInteger(bytes)||bytes<0||bytes>MAX_BYTES)reject('INVALID_SOURCE_TREE');
  if(name.split('/').some(segment=>/^(?:id_rsa|id_ed25519|token|tokens|cookie|cookies|secret|secrets|credentials?)(?:\.|$)/i.test(segment)||/\.(?:pem|key|p12|pfx|kdbx|sqlite|db)$/i.test(segment)||segment==='.env'||(segment.startsWith('.env.')&&segment!=='.env.example')))reject('CREDENTIAL_FILE_IN_SOURCE');
  if(!PACKAGE_FILES.has(name)&&!PACKAGE_PREFIXES.some(prefix=>name.startsWith(prefix)))continue;
  if(PACKAGE_PREFIXES.some(prefix=>name.startsWith(prefix))&&(!/\.(?:html|css|mjs|json)$/.test(name)||name.split('/').some(x=>x.startsWith('.'))))reject('UNAPPROVED_RUNTIME_ASSET');
  total+=bytes;if(total>MAX_BYTES)reject('SOURCE_EXPORT_TOO_LARGE');
  files.push({path:name,bytes,object:path});
 }
 files.sort((a,b)=>a.path<b.path?-1:a.path>b.path?1:0);
 const entriesToSeal=files.map(({path,bytes})=>({path,bytes,sha256:''}));
 for(const name of REQUIRED)if(!files.some(x=>x.path===name))reject('INCOMPLETE_SOURCE_TREE');
 await mkdir(output,{mode:0o700}); // Existing outputs are never overwritten.
 for(let i=0;i<files.length;i++){
  const x=files[i],bytes=git(root,['show',sourceRevision+':'+x.object]);
  if(bytes.length!==x.bytes)reject('SOURCE_SIZE_CHANGED');
  entriesToSeal[i].sha256=digest(bytes);
  const destination=join(output,x.path);
  await mkdir(dirname(destination),{recursive:true,mode:0o700});
  await writeFile(destination,bytes,{flag:'wx',mode:0o600});
 }
 manifestPaths(entriesToSeal);
 const seal={schemaVersion:1,sourceRevision,productPath:PREFIX.slice(0,-1),files:entriesToSeal};
 await writeFile(join(output,'SOURCE_SEAL.json'),JSON.stringify(seal,null,2)+'\n',{flag:'wx',mode:0o600});
 return {sourceRevision,fileCount:entriesToSeal.length,sourceDigest:digest(Buffer.from(JSON.stringify(seal))),output};
}
async function listFiles(folder,sub='',seen=[]) {
 const items=await readdir(join(folder,sub),{withFileTypes:true});
 for(const item of items) {
  const name=sub?sub+'/'+item.name:item.name;
  if(!validPath(name))reject('INVALID_EXPORT_PATH');
  if(item.isSymbolicLink())reject('SYMLINK_IN_EXPORT');
  if(item.isDirectory())await listFiles(folder,name,seen);
  else if(item.isFile())seen.push(name);
  else reject('UNSUPPORTED_EXPORT_ENTRY');
  if(seen.length>MAX_FILES+2)reject('EXTRA_FILES_IN_EXPORT');
 }
 return seen;
}
export async function verifySourceSeal(folder,sourceRevision) {
 if(!SHA.test(sourceRevision))reject('INVALID_SOURCE_REVISION');
 const handle=await open(join(folder,'SOURCE_SEAL.json'),constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);
 let raw;
 try {
  const stat=await handle.stat();
  if(!stat.isFile()||stat.size>MAX_MANIFEST)reject('INVALID_SOURCE_SEAL');
  const buf=Buffer.alloc(stat.size+1);
  let n=0;
  while(n<buf.length){const r=await handle.read(buf,n,buf.length-n,n);if(!r.bytesRead)break;n+=r.bytesRead;}
  if(n!==stat.size)reject('SOURCE_SEAL_CHANGED_DURING_READ');
  raw=buf.subarray(0,n);
 } finally {await handle.close();}
 let seal;try{seal=JSON.parse(raw);}catch{reject('INVALID_SOURCE_SEAL');}
 if(!seal||seal.schemaVersion!==1||seal.sourceRevision!==sourceRevision||seal.productPath!==PREFIX.slice(0,-1))reject('SOURCE_REVISION_MISMATCH');
 manifestPaths(seal.files);
 const accepted=new Set(seal.files.map(x=>x.path));
 const disk=(await listFiles(folder)).filter(x=>x!=='.env'&&x!=='SOURCE_SEAL.json');
 if(disk.length!==accepted.size||disk.some(x=>!accepted.has(x)))reject('EXTRA_OR_MISSING_EXPORT_FILE');
 for(const x of seal.files) {
  const path=join(folder,x.path),info=await lstat(path);
  if(!info.isFile()||info.isSymbolicLink()||info.size!==x.bytes||info.size>MAX_BYTES)reject('SOURCE_FILE_MISMATCH');
  if(digest(await readFile(path))!==x.sha256)reject('SOURCE_FILE_MISMATCH');
 }
 return {sourceRevision,verifiedFiles:seal.files.length,manifestSha256:digest(raw),status:'LOCAL_EXPORTED_BYTES_MATCH_MANIFEST_NOT_REMOTE_ATTESTATION'};
}
if(process.argv[1]&&fileURLToPath(import.meta.url)===resolve(process.argv[1])){
 try {
  const args=process.argv.slice(2);
  if(args.length!==4||args[0]!=='--commit'||args[2]!=='--out')reject('USAGE: --commit FULL_40_SHA --out NEW_DIRECTORY');
  const sourceRevision=args[1],out=args[3];
  const repoRoot=git(dirname(fileURLToPath(import.meta.url)),['rev-parse','--show-toplevel']).toString().trim();
  const result=await exportSource({repoRoot,sourceRevision,out});
  console.log(JSON.stringify(result));
 }catch(e){console.error(e.message);process.exitCode=1;}
}
