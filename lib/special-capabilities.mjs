import {readFile,stat} from 'node:fs/promises';
import {resolve} from 'node:path';
import {EXPECTED_COMPANIES} from './catalog.mjs';

// Every company has a pet with basic capabilities (pets/<company>/pet.json).
// Special capabilities are extra, service-backed abilities that only some pets have.
// They live in one registry so a service is declared once and linked to its pets.
export const SPECIAL_CAPABILITIES_PATH = 'config/special-capabilities.json';
export const STATUSES = Object.freeze(['source-only','offline-demo','needs-host-connection']);
const ID = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

export function validateSpecialCapabilities(registry,{companies=EXPECTED_COMPANIES}={}) {
  if (registry?.schemaVersion!==1 || !Array.isArray(registry.capabilities) || registry.capabilities.length===0) throw new Error('Invalid special capability registry');
  const known=new Set(companies), ids=new Set();
  for (const c of registry.capabilities) {
    const where='special capability '+(c?.id??'?');
    if (typeof c?.id!=='string' || !ID.test(c.id)) throw new Error('Invalid id for '+where);
    if (ids.has(c.id)) throw new Error('Duplicate '+where);
    ids.add(c.id);
    for (const key of ['title','description','service']) if (typeof c[key]!=='string' || c[key].trim().length<3) throw new Error(`Missing ${key} for ${where}`);
    if (!/^services\/[a-z0-9-]+$/.test(c.service)) throw new Error('Service must be a services/<name> directory for '+where);
    if (typeof c.requiresConnection!=='boolean') throw new Error('requiresConnection must be boolean for '+where);
    if (!STATUSES.includes(c.status)) throw new Error('Unknown status for '+where);
    if (c.run!==undefined && (typeof c.run!=='string' || !c.run.trim())) throw new Error('Invalid run command for '+where);
    if (c.pets!=='all') {
      if (!Array.isArray(c.pets) || c.pets.length===0) throw new Error('A special capability needs "all" or at least one pet: '+where);
      if (new Set(c.pets).size!==c.pets.length) throw new Error('Duplicate pet in '+where);
      for (const slug of c.pets) if (!known.has(slug)) throw new Error(`Unknown pet ${slug} in ${where}`);
    }
    const extra=Object.keys(c).filter(k=>!['id','title','description','service','pets','requiresConnection','status','run'].includes(k));
    if (extra.length) throw new Error(`Unexpected field ${extra.join(', ')} in ${where}`);
  }
  return registry;
}

export async function loadSpecialCapabilities(root,options) {
  const registry=validateSpecialCapabilities(JSON.parse(await readFile(resolve(root,SPECIAL_CAPABILITIES_PATH),'utf8')),options);
  for (const c of registry.capabilities) {
    const info=await stat(resolve(root,c.service)).catch(()=>null);
    if (!info?.isDirectory()) throw new Error(`Service ${c.service} for special capability ${c.id} does not exist`);
  }
  return registry;
}

export function specialCapabilitiesFor(registry,slug) {
  return registry.capabilities.filter(c=>c.pets==='all'||c.pets.includes(slug)).map(({pets,...rest})=>rest);
}
