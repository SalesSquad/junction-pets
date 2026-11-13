#!/usr/bin/env node
/** Generate portable, skills-only plugin sources from the canonical pet packages.
 *  Source packages are not installed, published, deployed or connected to Chibi.
 */
import {createHash} from 'node:crypto';
import {readFile,readdir,mkdir,writeFile} from 'node:fs/promises';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';

const ROOT=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const PLUGINS=resolve(ROOT,'plugins');
const CHECK=process.argv.includes('--check');
const NAME=/^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const sha256=input=>createHash('sha256').update(input).digest('hex');

export function buildPlugin(pet,source){
  if(!NAME.test(pet.company.slug)||pet.slug!==`junction-${pet.company.slug}`||pet.id!==`junction.${pet.company.slug}`)throw Error(`invalid pet identity: ${pet.slug}`);
  if(!/^\d+\.\d+\.\d+$/.test(pet.version))throw Error(`invalid SemVer: ${pet.slug}`);
  if(pet.availability.companyEndorsed!==false)throw Error(`company endorsement claim: ${pet.slug}`);
  const pluginName=pet.slug;
  const skillName=`${pluginName}-companion`;
  const safeCompany=pet.company.name.replace(/[<>\r\n]/g,'');
  const defaultPrompt=pet.starterPrompts[0];
  const summary=`Independent ${safeCompany} topic guidance from official sources and redacted user inputs; no official company affiliation or provider execution.`;
  const manifest={
    $schema:'https://agent-plugins.org/schemas/1.0.0/plugin.schema.json',
    name:pluginName, version:pet.version,description:summary,
    author:{name:'Sales Squad Oy'},repository:'https://github.com/SalesSquad/junction-pets',
    extensions:{'com.openai':{interface:{
      displayName:`${safeCompany} Chibi companion`,
      shortDescription:'Independent company guidance',
      longDescription:summary,
      developerName:'Sales Squad Oy',
      capabilities:[],
      defaultPrompt,
    }}},
  };
  if(manifest.extensions['com.openai'].interface.shortDescription.length>30)throw Error('subtitle too long');
  const yamlDescription=`Use for independent ${safeCompany} subject guidance on redacted user-provided inputs. No company endorsement, private data transfer, or provider execution.`.replaceAll('"','\\"');
  const skill=`---\nname: ${skillName}\ndescription: "${yamlDescription}"\n---\n\n# ${safeCompany} companion plugin\n\nThis is a versioned, **skills-only** plugin source for the independent Junction pet '${pet.id}' (package ${pet.version}). It is not an installed ChatGPT/Codex plugin, company-endorsed agent, live AI runtime, privileged account connection, or proof of an official event challenge.\n\nWhen invoked, follow the complete user-facing behavior instructions below. The latest source material and actual model runtime, when connected, remain separately verified. Do not use another user's memory, another company's private collections, or unapproved peer-pet context. Any Chibi account, conversation, provider, voice, agent-to-agent tool, or other effect requires an authenticated host adapter and a fresh authorization check.\n\n## Companion instructions\n\n${source.AGENTS.trim()}\n\n## Package starter prompts\n\n${pet.starterPrompts.map(p=>`- ${p}`).join('\n')}\n\n## Source package contract\n\nThis portable package contains only agent instructions and public citations. It defines no MCP tools, service endpoint, credentials, OAuth scopes or private Chibi implementation. The host owns permissions, account data and execution. Treat any simulation, offline plan or generated output as unexecuted until source-bound receipts prove otherwise.\n`;
  const provenance={schemaVersion:1,petId:pet.id,petVersion:pet.version,companySlug:pet.company.slug,pluginName,skillName,source:{repository:'SalesSquad/junction-pets',commit:null,commitVerified:false,paths:Object.fromEntries(Object.entries(source).map(([kind,content])=>[kind,{path:`pets/${pet.company.slug}/${kind==='AGENTS'?'AGENTS.md':kind==='STORY'?'STORY.md':kind==='EVALS'?'evals.json':'pet.json'}`,sha256:sha256(content)}]))},status:{packageGenerated:true,pluginInstalled:false,mcpConnected:false,liveAgentRunVerified:false},note:'Exact repository commit must be assigned only after readback from the authenticated GitHub task branch; these are file hashes, not live execution evidence.'};
  return {manifest,skill,provenance};
}

async function writeOrCheck(path,content){
  if(CHECK){const actual=await readFile(path,'utf8').catch(()=>null);if(actual!==content)throw Error(`plugin package drift: ${path}`);return;}
  await mkdir(dirname(path),{recursive:true});
  await writeFile(path,content);
}

export async function buildAll({root=ROOT,output=PLUGINS,check=CHECK}={}){
  const dirs=(await readdir(resolve(root,'pets'),{withFileTypes:true})).filter(x=>x.isDirectory()).map(x=>x.name).sort();
  if(dirs.length!==34)throw Error(`expected 34 pet packages, found ${dirs.length}`);
  const emitted=[];
  for(const company of dirs){
    const packageDir=resolve(root,'pets',company);
    const [petRaw,AGENTS,STORY,EVALS]=await Promise.all(['pet.json','AGENTS.md','STORY.md','evals.json'].map(name=>readFile(resolve(packageDir,name),'utf8')));
    const pet=JSON.parse(petRaw);
    if(company!==pet.company.slug)throw Error(`folder identity mismatch ${company}`);
    const {manifest,skill,provenance}=buildPlugin(pet,{PET:petRaw,AGENTS,STORY,EVALS});
    const pluginDir=resolve(output,manifest.name);
    const files=[
      [resolve(pluginDir,'plugin.json'),JSON.stringify(manifest,null,2)+'\n'],
      [resolve(pluginDir,'skills',provenance.skillName,'SKILL.md'),skill],
      [resolve(pluginDir,'assets','source-manifest.json'),JSON.stringify(provenance,null,2)+'\n'],
    ];
    for(const [path,content] of files){
      if(check){const actual=await readFile(path,'utf8').catch(()=>null);if(actual!==content)throw Error(`plugin package drift: ${path}`);}
      else await writeOrCheck(path,content);
    }
    emitted.push({name:manifest.name,version:pet.version,files:files.map(([p])=>p.slice(root.length+1))});
  }
  return emitted;
}

if(process.argv[1]===fileURLToPath(import.meta.url)){
  buildAll().then(emitted=>console.log(JSON.stringify({packages:emitted.length,files:emitted.reduce((n,e)=>n+e.files.length,0),mode:CHECK?'verified':'generated',installed:0,liveMcp:0},null,2))).catch(error=>{console.error(error.message);process.exitCode=1;});
}
