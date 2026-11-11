import type {Catalogue,HostConfig,Pet,RoleFilter} from './types';

const slugPattern = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
function verifiedInPast(value:unknown):boolean {
  if(typeof value !== 'string') return false;
  const time=Date.parse(value);
  return Number.isFinite(time) && time<=Date.now();
}
export function safeHttps(value:string): string | null {
  try {const url = new URL(value);return url.protocol === 'https:' && !url.username && !url.password ? url.href : null;} catch {return null;}
}
export function parseHost(value:unknown):HostConfig {
  const c = value as Partial<HostConfig> | null;
  if(!c || typeof c.canonicalOrigin !== 'string' || /[\s\\]/.test(c.canonicalOrigin) || !safeHttps(c.canonicalOrigin)) throw new Error('The Chibi destination could not be verified.');
  const url = new URL(c.canonicalOrigin);
  if(url.pathname !== '/' || url.search || url.hash || !['en','fi'].includes(c.locale || '')) throw new Error('The Chibi destination is invalid.');
  if(!Array.isArray(c.publishedSlugs) || c.publishedSlugs.some(v=>typeof v !== 'string' || !slugPattern.test(v))) throw new Error('The publication list is invalid.');
  if(c.runtimeStatus !== 'verified' && c.runtimeStatus !== 'unverified') throw new Error('The Chibi availability could not be verified.');
  if(c.runtimeStatus === 'verified' && !verifiedInPast(c.verifiedAt)) throw new Error('The Chibi availability has no valid verification date.');
  return {...c,canonicalOrigin:url.origin} as HostConfig;
}
export function parseCatalogue(value:unknown):Catalogue {
  const c=value as Catalogue;
  if(!c || c.schemaVersion !== 1 || !c.collection || !Array.isArray(c.pets) || !c.pets.length) throw new Error('The companion collection is not available yet.');
  const seen=new Set<string>();
  for(const pet of c.pets) {
    if(!pet || pet.schemaVersion!==1 || !slugPattern.test(pet.slug) || !pet.company || !slugPattern.test(pet.company.slug) || !pet.company.name || seen.has(pet.slug) || !Array.isArray(pet.capabilities) || !Array.isArray(pet.starterPrompts) || !Array.isArray(pet.sources) || !Number.isInteger(pet.artIndex) || pet.artIndex<0 || pet.artIndex>33) throw new Error('A companion profile needs to be checked before it can be shown.');
    seen.add(pet.slug);
  }
  return c;
}
export function petUrl(config:HostConfig,pet:Pet):string {
  if(!slugPattern.test(pet.slug)) throw new Error('Invalid companion link.');
  return `${config.canonicalOrigin}/${config.locale}/chibi/${encodeURIComponent(pet.slug)}`;
}
export function petAvailable(config:HostConfig,pet:Pet):boolean {
  return config.runtimeStatus==='verified' && config.publishedSlugs.includes(pet.slug) && verifiedInPast(config.verifiedAt);
}
export function matches(pet:Pet,query:string,role:RoleFilter):boolean {
  const normalize=(v:string)=>v.normalize('NFKD').replace(/\p{Diacritic}/gu,'').toLocaleLowerCase('en');
  const roleMatches=role==='all' || (role==='more' ? ['main','collaborator'].includes(pet.company.role) : role===pet.company.role);
  return roleMatches && normalize(`${pet.company.name} ${pet.displayName} ${pet.tagline}`).includes(normalize(query.trim()));
}
export async function copyText(value:string):Promise<boolean> {
  try {await navigator.clipboard.writeText(value);return true;} catch {return false;}
}
