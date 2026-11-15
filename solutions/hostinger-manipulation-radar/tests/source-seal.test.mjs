import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {mkdtemp,mkdir,readFile,rm,symlink,unlink,writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {exportSource,verifySourceSeal} from '../source-seal.mjs';

const paths=['Dockerfile','compose.yaml','server.mjs','services.mjs','source-seal.mjs','public/app.mjs'];
function git(root,...args){
 const p=spawnSync('git',['-C',root,...args],{encoding:'utf8'});
 if(p.status!==0)throw Error('fixture git failure');
 return p.stdout.trim();
}
async function fixture(t){
 const base=await mkdtemp(join(tmpdir(),'hostinger-seal-test-'));
 t.after(async()=>rm(base,{recursive:true,force:true}));
 const root=join(base,'repo'),product=join(root,'solutions/hostinger-manipulation-radar');
 await mkdir(join(product,'public'),{recursive:true});
 await mkdir(join(product,'research'),{recursive:true});
 await writeFile(join(product,'research','internal-review.txt'),'not intended for deployment\n');
 for(const name of paths)await writeFile(join(product,name),name+'\n',{flag:'wx'});
 git(root,'init','-q');git(root,'add','-A');git(root,'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','immutable source');
 const sha=git(root,'rev-parse','HEAD'),out=join(base,'release');
 return {base,root,sha,out};
}
test('only immutable commit bytes are exported and a new standalone folder verifies',async t=>{
 const f=await fixture(t);
 const result=await exportSource({repoRoot:f.root,sourceRevision:f.sha,out:f.out});
 assert.equal(result.sourceRevision,f.sha);assert.equal(result.fileCount,paths.length);
 await assert.rejects(readFile(join(f.out,'research','internal-review.txt')),{code:'ENOENT'});
 const seal=JSON.parse(await readFile(join(f.out,'SOURCE_SEAL.json'),'utf8'));
 assert.equal(seal.sourceRevision,f.sha);
 assert.equal(seal.productPath,'solutions/hostinger-manipulation-radar');
 const verified=await verifySourceSeal(f.out,f.sha);
 assert.equal(verified.verifiedFiles,paths.length);
 assert.match(verified.status,/NOT_REMOTE_ATTESTATION/);
 await assert.rejects(exportSource({repoRoot:f.root,sourceRevision:f.sha,out:f.out}),{code:'EEXIST'});
});
test('revision mismatch and a changed executable are refused',async t=>{
 const f=await fixture(t);
 await exportSource({repoRoot:f.root,sourceRevision:f.sha,out:f.out});
 await assert.rejects(verifySourceSeal(f.out,'0'.repeat(40)),/SOURCE_REVISION_MISMATCH/);
 await writeFile(join(f.out,'server.mjs'),'tampered\n');
 await assert.rejects(verifySourceSeal(f.out,f.sha),/SOURCE_FILE_MISMATCH/);
});
test('extra runtime assets, symlinks and missing files cannot slip into a sealed Docker context',async t=>{
 const f=await fixture(t);
 await exportSource({repoRoot:f.root,sourceRevision:f.sha,out:f.out});
 await writeFile(join(f.out,'public','injected.js'),'alert(1)\n');
 await assert.rejects(verifySourceSeal(f.out,f.sha),/EXTRA_OR_MISSING_EXPORT_FILE/);
 await unlink(join(f.out,'public','injected.js'));
 await symlink(join(f.out,'server.mjs'),join(f.out,'public','evil-link.mjs'));
 await assert.rejects(verifySourceSeal(f.out,f.sha),/SYMLINK_IN_EXPORT/);
 await unlink(join(f.out,'public','evil-link.mjs'));
 await unlink(join(f.out,'services.mjs'));
 await assert.rejects(verifySourceSeal(f.out,f.sha),/EXTRA_OR_MISSING_EXPORT_FILE/);
});
test('exports refuse invalid commits or writing into the working checkout',async t=>{
 const f=await fixture(t);
 await assert.rejects(exportSource({repoRoot:f.root,sourceRevision:'abc',out:f.out}),/INVALID_SOURCE_REVISION/);
 await assert.rejects(exportSource({repoRoot:f.root,sourceRevision:f.sha,out:join(f.root,'bad')}),/OUTPUT_MUST_BE_OUTSIDE_REPOSITORY/);
});

test('a tracked credential environment file is never exported even if Git committed it',async t=>{
 const f=await fixture(t),product=join(f.root,'solutions/hostinger-manipulation-radar');
 await writeFile(join(product,'.env'),'HOSTINGER_AI_ROUTER_KEY=DO_NOT_COPY\n');
 git(f.root,'add','-f','solutions/hostinger-manipulation-radar/.env');
 git(f.root,'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','introduce forbidden secret');
 await assert.rejects(exportSource({repoRoot:f.root,sourceRevision:git(f.root,'rev-parse','HEAD'),out:f.out}),/CREDENTIAL_FILE_IN_SOURCE/);
});

test('a nested credential-looking file is rejected even outside the release allowlist',async t=>{
 const f=await fixture(t),dir=join(f.root,'solutions/hostinger-manipulation-radar/private');
 await mkdir(dir,{recursive:true});await writeFile(join(dir,'operator.pem'),'FICTIONAL_PUBLIC_TEST_MARKER\n');
 git(f.root,'add','solutions/hostinger-manipulation-radar/private/operator.pem');
 git(f.root,'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','forbidden nested credential filename');
 await assert.rejects(exportSource({repoRoot:f.root,sourceRevision:git(f.root,'rev-parse','HEAD'),out:f.out}),/CREDENTIAL_FILE_IN_SOURCE/);
});
test('an oversized, symlinked or special-file manifest cannot enter the verifier',async t=>{
 const f=await fixture(t);await exportSource({repoRoot:f.root,sourceRevision:f.sha,out:f.out});
 const path=join(f.out,'SOURCE_SEAL.json');
 await writeFile(path,'x'.repeat(300000));await assert.rejects(verifySourceSeal(f.out,f.sha),/INVALID_SOURCE_SEAL/);
 await unlink(path);await symlink(join(f.out,'server.mjs'),path);await assert.rejects(verifySourceSeal(f.out,f.sha));
 await unlink(path);const fifo=spawnSync('mkfifo',[path]);assert.equal(fifo.status,0);
 await assert.rejects(verifySourceSeal(f.out,f.sha),/INVALID_SOURCE_SEAL/);
});
