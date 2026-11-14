import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {mkdtemp,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {parseChecksums,verifyInputs,main,MANIFEST_SHA256} from '../src/parquet-m.mjs';
const digest='a'.repeat(64);
test('strict pure Node SHA256SUMS parser: text/binary entries, bounds, duplicates and paths',()=>{
  assert.equal(parseChecksums(Buffer.from(`${digest}  versions-01.parquet\n${digest} *README.md\n`)).size,2);
  for(const text of ['',`${digest}  ../versions-01.parquet\n`,`${digest}  versions-17.parquet\n`,
    `${digest}  versions-00.parquet\n`,`${digest}  versions-01.parquet\n${digest}  versions-01.parquet\n`,
    `bad  versions-01.parquet\n`,'x'.repeat(16385)])assert.throws(()=>parseChecksums(Buffer.from(text)));
  assert.throws(()=>parseChecksums(Buffer.from([255])));
  assert.match(MANIFEST_SHA256,/^[a-f0-9]{64}$/);
});
test('caller-recomputed manifests cannot promote synthetic bytes to the official release',async()=>{
  const dir=await mkdtemp(join(tmpdir(),'chronicle-manifest-'));
  try{
    const manifest=join(dir,'SHA256SUMS');await writeFile(manifest,`${digest}  versions-01.parquet\n`);
    await assert.rejects(verifyInputs(join(dir,'versions-01.parquet'),manifest),/UNTRUSTED_MANIFEST/);
    await assert.rejects(verifyInputs(join(dir,'renamed.parquet'),manifest),/INVALID_SHARD_BASENAME/);
    const out=join(dir,'existing');await writeFile(out,'preserve');
    await assert.rejects(main(['--parquet','x','--sha256sums',manifest,'--page','155','--out',out]),/OUTPUT_EXISTS/);
    await assert.rejects(main(['--parquet','x','--sha256sums',manifest,'--page','0','--out','x']),/INVALID_PAGE_ID/);
  }finally{await rm(dir,{recursive:true,force:true});}
});
const available=spawnSync('python3',['-c','import pyarrow'],{encoding:'utf8'});
test('synthetic Parquet integration and adversarial admission',{
  skip:available.status===0?false:'DEPENDENCY_UNAVAILABLE: python3/pyarrow; pure Node checks still execute'
},()=>{
  const result=spawnSync('python3',[fileURLToPath(new URL('./parquet_m_test.py',import.meta.url))],{encoding:'utf8',maxBuffer:65536});
  assert.equal(result.status,0,result.stdout+'\n'+result.stderr);
});
