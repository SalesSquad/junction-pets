const SLUG=/^junction-[a-z0-9]+(?:-[a-z0-9]+)*$/;
export function canonicalOrigin(value) {
  if(typeof value!=='string'||/[\s\\]/.test(value))throw new TypeError('A canonical HTTPS Chibi origin is required');
  const url=new URL(value);
  if(url.protocol!=='https:'||url.username||url.password||url.search||url.hash||url.pathname!=='/')throw new TypeError('Use a bare HTTPS Chibi origin');
  return url.origin;
}
export function petPath(slug,locale='en') {
  if(!SLUG.test(slug)||slug.length>96||!['en','fi'].includes(locale))throw new TypeError('Invalid company or locale');
  return '/'+locale+'/chibi/'+slug;
}
export function publicPetUrl(origin,slug,locale='en') {return canonicalOrigin(origin)+petPath(slug,locale);}
export function signInUrl(origin,slug,locale='en') {return canonicalOrigin(origin)+'/'+locale+'/signin?next='+encodeURIComponent(petPath(slug,locale));}
export function recipientAvailable(config,slug,now=Date.now()) {
  if(typeof config?.verifiedAt!=='string')return false;
  const verifiedAt=Date.parse(config?.verifiedAt);
  if(!config||config.runtimeStatus!=='verified'||!Array.isArray(config.publishedSlugs)||!config.publishedSlugs.includes(slug)||!Number.isFinite(verifiedAt)||verifiedAt>now)return false;
  try{publicPetUrl(config.canonicalOrigin,slug,config.locale);return true;}catch{return false;}
}
