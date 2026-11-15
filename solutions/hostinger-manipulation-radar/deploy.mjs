import {lstat,readFile} from 'node:fs/promises';
import {spawnSync} from 'node:child_process';
import {createConnection} from 'node:net';
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
  return {folder,sourceRevision:values.SIGNAL_SOURCE_REVISION,aiConfigured:Boolean(values.HOSTINGER_AI_ROUTER_KEY)};
}
export function portOccupied(port) {
 return new Promise(resolve=>{
  const socket=createConnection({host:'127.0.0.1',port});
  const finish=value=>{socket.destroy();resolve(value);};
  socket.setTimeout(800,()=>finish(false));socket.once('connect',()=>finish(true));socket.once('error',()=>finish(false));
 });
}
function docker(args,folder,{capture=false}={}) {
 const result=spawnSync('docker',args,{cwd:folder,stdio:capture?'pipe':'inherit',encoding:'utf8',timeout:300000});
 if(result.error)throw Error(result.error.code==='ENOENT'?'Docker is not installed or available in PATH.':'Docker execution failed: '+result.error.code);
 if(result.status!==0)throw Error('Docker operation failed; no successful deployment is claimed.');
 return result.stdout?.trim()||'';
}
if(process.argv[1]&&fileURLToPath(import.meta.url)===process.argv[1]) {
 try {
  const ready=await preflight();
  const appOnly=process.argv.includes('--app-only'),args=['compose',...(appOnly?[]:['--profile','tls'])];
  docker([...args,'config','--quiet'],ready.folder);
  console.log('Preflight passed. AI configuration: '+(ready.aiConfigured?'present, not probed':'absent, local workspaces only')+'.');
  if(!process.argv.includes('--apply'))console.log('Dry run only. Use --apply for the explicitly authorized deployment; --app-only preserves an existing ingress.');
  else {
    if(!appOnly) {
      const ownCaddy=docker([...args,'ps','-q','caddy'],ready.folder,{capture:true});
      if(!ownCaddy&&((await portOccupied(80))||(await portOccupied(443))))throw Error('An existing ingress owns port 80 or 443. Preserve it and use the documented --app-only route.');
    }
    const noBuild=process.argv.includes('--no-build');
    if(noBuild)docker(['image','inspect','signal-desk:'+ready.sourceRevision],ready.folder,{capture:true});
    docker([...args,'up','-d',noBuild?'--no-build':'--build','--wait','--wait-timeout','90',...(appOnly?['signal-desk']:[])],ready.folder);
    console.log('Containers reached their local health/running state. Public HTTPS and one real provider request still require independent verification.');
  }
 }catch(error){console.error(error.code==='ENOENT'?'Create an owner-only .env from .env.example first.':error.message);process.exitCode=1;}
}
