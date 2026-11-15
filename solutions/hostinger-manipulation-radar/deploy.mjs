import {lstat,readFile} from 'node:fs/promises';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {dirname} from 'node:path';

export async function preflight(folder=dirname(fileURLToPath(import.meta.url))) {
  const path=folder+'/.env',info=await lstat(path);
  if(!info.isFile()||info.isSymbolicLink()||(info.mode&0o077)!==0)throw Error('The .env file must be a regular owner-only file (chmod 600 .env).');
  const values={};
  for(const line of (await readFile(path,'utf8')).split(/\r?\n/)) {
    if(!line.trim()||line.trim().startsWith('#'))continue;
    const match=/^([A-Z][A-Z0-9_]*)=([^\r\n]*)$/.exec(line);
    if(!match)throw Error('Use simple KEY=value environment entries; no quotes or expansion.');
    if(/[$\x00-\x1f]/.test(match[2]))throw Error('Environment values must not contain expansion or control characters.');
    values[match[1]]=match[2];
  }
  if(!/^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$/.test(values.SIGNAL_DOMAIN||'')||!(values.SIGNAL_DOMAIN||'').includes('.'))throw Error('Set a verified SIGNAL_DOMAIN hostname.');
  if(values.SIGNAL_PUBLIC_ORIGIN!=='https://'+values.SIGNAL_DOMAIN)throw Error('The exact public HTTPS origin must match SIGNAL_DOMAIN.');
  if(values.SIGNAL_DEPLOYMENT_PROVIDER!=='hostinger')throw Error('This entrypoint is for an owner-verified Hostinger VPS only.');
  if(!/^[a-f0-9]{40}$/.test(values.SIGNAL_SOURCE_REVISION||''))throw Error('Set the exact deployed 40-character source revision.');
  if(Boolean(values.HOSTINGER_AI_ROUTER_KEY)!==Boolean(values.HOSTINGER_AI_MODEL))throw Error('Configure both AI key and exact model ID, or leave both empty.');
  return {folder,aiConfigured:Boolean(values.HOSTINGER_AI_ROUTER_KEY)};
}
if(process.argv[1]&&fileURLToPath(import.meta.url)===process.argv[1]) {
 try {
  const ready=await preflight();
  const appOnly=process.argv.includes('--app-only'),args=['compose',...(appOnly?[]:['--profile','tls'])];
  const check=spawnSync('docker',[...args,'config','--quiet'],{cwd:ready.folder,stdio:'inherit'});
  if(check.status!==0)throw Error('Docker Compose configuration is not valid.');
  console.log('Preflight passed. AI configuration: '+(ready.aiConfigured?'present, not probed':'absent, local workspaces only')+'.');
  if(!process.argv.includes('--apply'))console.log('Dry run only. Use --apply for the explicitly authorized deployment; --app-only preserves an existing ingress.');
  else {
    const deployed=spawnSync('docker',[...args,'up','-d','--build',...(appOnly?['signal-desk']:[])],{cwd:ready.folder,stdio:'inherit'});
    process.exitCode=deployed.status??1;
  }
 }catch(error){console.error(error.code==='ENOENT'?'Create an owner-only .env from .env.example first.':error.message);process.exitCode=1;}
}
