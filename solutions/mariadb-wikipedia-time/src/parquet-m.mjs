// Offline bridge. Pin obtained from GitHub release asset metadata, 2026-11-15:
// https://github.com/MariaDB/mariadb-wikipedia-datasets/releases/expanded_assets/m-2026-10
import {createHash} from 'node:crypto';
import {open,readFile,lstat} from 'node:fs/promises';
import {basename,resolve} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';
import {loadDataset,inspect,utc} from './chronicle.mjs';
export const MANIFEST_SHA256='7d59a6a28b10f996be3c36fc4d82f5faa97624f8fca7a37cbf5d70e4bb809f68';
export function parseChecksums(raw){
  if(!Buffer.isBuffer(raw)||raw.length>16384)throw new Error('MANIFEST_TOO_LARGE');
  const entries=new Map();
  const text=raw.toString('ascii');
  if(!Buffer.from(text,'ascii').equals(raw))throw new Error('INVALID_MANIFEST');
  const lines=text.split(/\r?\n/);if(lines.at(-1)==='')lines.pop();
  for(const line of lines){
    const m=/^([a-f0-9]{64}) [ *](versions-(?:0[1-9]|1[0-6])\.parquet|README\.md)$/.exec(line);
    if(!m)throw new Error('INVALID_MANIFEST');
    if(entries.has(m[2]))throw new Error('DUPLICATE_MANIFEST_ENTRY');
    entries.set(m[2],m[1]);
  }
  if(!entries.size)throw new Error('EMPTY_MANIFEST');
  return entries;
}
export async function verifyInputs(parquet,manifest){
  const name=basename(parquet);
  if(!/^versions-(?:0[1-9]|1[0-6])\.parquet$/.test(name))throw new Error('INVALID_SHARD_BASENAME');
  const handle=await open(manifest,'r');let raw;
  try{const buffer=Buffer.alloc(16385);const {bytesRead}=await handle.read(buffer,0,buffer.length,0);raw=buffer.subarray(0,bytesRead);}finally{await handle.close();}
  const entries=parseChecksums(raw);
  if(createHash('sha256').update(raw).digest('hex')!==MANIFEST_SHA256)throw new Error('UNTRUSTED_MANIFEST');
  if(!entries.has(name))throw new Error('SHARD_NOT_IN_MANIFEST');
  const hash=createHash('sha256');
  const shard=await open(parquet,'r');
  try{for await(const chunk of shard.createReadStream())hash.update(chunk);}finally{await shard.close();}
  if(hash.digest('hex')!==entries.get(name))throw new Error('SHARD_SHA256_MISMATCH');
  return {shard:name,manifest_sha256:MANIFEST_SHA256};
}
export async function main(argv){
  const args={};
  if(argv.length%2)throw new Error('EXPECTED_FLAG_VALUE_PAIRS');
  for(let i=0;i<argv.length;i+=2){
    if(!['--parquet','--sha256sums','--page','--out','--at','--compare'].includes(argv[i])||args[argv[i]])throw new Error('INVALID_ARGUMENT');
    args[argv[i]]=argv[i+1];
  }
  for(const flag of ['--parquet','--sha256sums','--page','--out'])if(!args[flag])throw new Error('MISSING_'+flag);
  if(!/^[1-9][0-9]{0,9}$/.test(args['--page'])||Number(args['--page'])>4294967295)throw new Error('INVALID_PAGE_ID');
  if(args['--at'])utc(args['--at']);
  if(args['--compare'])utc(args['--compare']);
  if(args['--compare']&&!args['--at'])throw new Error('COMPARE_REQUIRES_AT');
  try{await lstat(args['--out']);throw new Error('OUTPUT_EXISTS');}catch(e){if(e.code!=='ENOENT')throw e;}
  await verifyInputs(args['--parquet'],args['--sha256sums']);
  const script=fileURLToPath(new URL('../scripts/import-parquet-m.py',import.meta.url));
  // Explicit executable, no shell; activate a project-local venv to select its python3.
  const flags=['--parquet','--sha256sums','--page','--out'].flatMap(k=>[k,args[k]]);
  const child=spawnSync('python3',[script,...flags],{encoding:'utf8',maxBuffer:65536});
  if(child.error)throw new Error('PYTHON_UNAVAILABLE: '+child.error.code);
  if(child.status!==0)throw new Error(child.stderr.trim()||'PARQUET_IMPORT_REFUSED');
  const raw=JSON.parse(await readFile(args['--out'],'utf8'));
  const dataset=loadDataset(raw);
  const sourceEvidence={
    source_release_url:raw.intake.source_release_url,
    release_tag:raw.intake.release_tag,
    shard_sha256:raw.intake.shard_sha256,
    manifest_sha256:raw.intake.manifest_sha256,
    attribution:raw.intake.attribution,
    data_license:raw.dataset_license,
    data_license_url:raw.intake.data_license_url,
    coverage_scope:raw.intake.scope,
    verified_live_source:false,
    integrity:'PINNED_RELEASE_BYTES_ONLY_NOT_INDEPENDENT_CLAIM_VERIFICATION'
  };
  const answer=args['--at']?inspect(dataset,args['--page'],args['--at'],args['--compare']||null):null;
  return {status:'IMPORTED_LOCAL_REPLAY',intake:raw.intake,
    ...(answer?{answer:{...answer,source_evidence:sourceEvidence,
      snapshot:{...answer.snapshot,attribution:sourceEvidence.attribution,
        coverage_scope:sourceEvidence.coverage_scope,
        data_license_url:sourceEvidence.data_license_url,
        source_integrity:answer.snapshot.source_integrity||'LOCAL_HASH_ONLY_UNVERIFIED'}}}:{})};
}
if(process.argv[1]&&pathToFileURL(resolve(process.argv[1])).href===import.meta.url){
  try{process.stdout.write(JSON.stringify(await main(process.argv.slice(2)),null,2)+'\n');}
  catch(e){process.stderr.write(JSON.stringify({status:'REFUSED',reason:e.message})+'\n');process.exitCode=2;}
}
