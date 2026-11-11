import {readFile,readdir} from 'node:fs/promises';
import {resolve,basename} from 'node:path';
import Ajv from 'ajv';
import {canonicalJson,sha256,safeHttps} from './artifact.mjs';

const schema = JSON.parse(await readFile(new URL('../schemas/pet.schema.json',import.meta.url),'utf8'));
const validateShape = new Ajv({allErrors:true,strict:true}).compile(schema);
export const EXPECTED_COMPANIES = Object.freeze(['hostinger','valio-aimo','s-pankki','aalto-university','cala','city-of-espoo','exa','mariadb','afterquery','bahn-express','astrazeneca','stoa','intel','context-dev','rokoko','ignite-next','meta','tieto','openai-codex','nvidia','featherless','modal','qualia','craci','atech-dev','scailab','ironshard','cloudinary','wendy','aiven','oxylabs','arduino','verda','google-deepmind']);

export function validatePet(pet) {
  if (!validateShape(pet)) throw new Error('Invalid pet: '+JSON.stringify(validateShape.errors));
  if (pet.id !== 'junction.'+pet.company.slug || pet.slug !== 'junction-'+pet.company.slug) throw new Error('Company identity mismatch');
  if (!safeHttps(pet.company.website) || pet.sources.some(s=>!safeHttps(s.url))) throw new Error('Invalid official source URL');
  if (new Set(pet.capabilities.map(c=>c.id)).size !== pet.capabilities.length || new Set(pet.sources.map(s=>s.id)).size !== pet.sources.length) throw new Error('Duplicate local identity');
  if (pet.capabilities.some(c=>c.kind==='connection-required'&&!c.requiresConnection)) throw new Error('Connection-required capability cannot claim no connection');
  for (const source of pet.sources) if (!Number.isFinite(Date.parse(source.checkedAt+'T00:00:00Z'))) throw new Error('Invalid source date');
  return pet;
}

export function validateCollection(pets,{expected=EXPECTED_COMPANIES}={}) {
  pets.forEach(validatePet);
  for (const key of ['id','slug','agentName','artIndex']) if (new Set(pets.map(p=>p[key])).size !== pets.length) throw new Error('Duplicate '+key);
  const companies=pets.map(p=>p.company.slug).sort();
  if (canonicalJson(companies)!==canonicalJson([...expected].sort())) throw new Error('Collection does not match the evidenced roster');
  return pets;
}

export async function loadPackages(root) {
  const dir=resolve(root,'pets');
  const entries=(await readdir(dir,{withFileTypes:true})).filter(e=>e.isDirectory());
  const packages=await Promise.all(entries.map(async entry=>{
    const path=resolve(dir,entry.name);
    const pet=validatePet(JSON.parse(await readFile(resolve(path,'pet.json'),'utf8')));
    if (pet.company.slug!==basename(path)) throw new Error('Package directory mismatch');
    const instructions=await readFile(resolve(path,'AGENTS.md'),'utf8');
    const story=await readFile(resolve(path,'STORY.md'),'utf8');
    const evals=JSON.parse(await readFile(resolve(path,'evals.json'),'utf8'));
    if (instructions.trim().length<600 || [...instructions].length>16000 || story.trim().length<200) throw new Error('Incomplete or oversized company guidance: '+pet.id);
    if (evals.schemaVersion!==1 || evals.petId!==pet.id || !Array.isArray(evals.cases) || evals.cases.length<3 || evals.cases.some(c=>!c.id||typeof c.prompt!=='string'||!Array.isArray(c.mustInclude)||!Array.isArray(c.mustNotClaim))) throw new Error('Incomplete evaluation cases: '+pet.id);
    return {pet,instructions,story,evals};
  }));
  packages.sort((a,b)=>a.pet.artIndex-b.pet.artIndex);
  validateCollection(packages.map(p=>p.pet));
  return packages;
}

export function packageDigest(pack) {return sha256(canonicalJson({pet:pack.pet,instructions:pack.instructions,story:pack.story,evals:pack.evals}));}
export function collectionDigest(packages) {return sha256(canonicalJson(packages.map(p=>({id:p.pet.id,sha256:packageDigest(p)}))));}
