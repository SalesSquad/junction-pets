import {readFile,writeFile,rename,rm} from 'node:fs/promises';
import {createHash,randomUUID} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {compare} from '../../solutions/context-dev-live-web-decision/live/compare.mjs';

// A deterministic, public-only projection. It never refreshes or re-dates a
// saved observation and never exports a current winner or provider credential.
export function projectEvidence(bytes){
  const source=JSON.parse(bytes),captures=source.captures;
  if(source.schemaVersion!==1||!Array.isArray(captures)||captures.length!==2)throw Error('Expected two original public captures');
  const latest=Math.max(...captures.map(c=>Date.parse(c.receivedAt)));
  if(!Number.isFinite(latest))throw Error('Invalid capture timestamp');
  const result=compare(captures,{now:latest});
  if(result.errors.length||result.offers.length!==2)throw Error('Saved comparison did not pass product/price admission');
  return {
    schemaVersion:1,mode:'HISTORICAL_CAPTURE',asOf:new Date(latest).toISOString(),
    sourceCaptureSha256:createHash('sha256').update(bytes).digest('hex'),
    product:result.product,
    offers:result.offers.map(({name,url,priceCents,memberPriceCents,shippingFromCents,availability,receivedAt,requestId})=>({name,url,priceCents,memberPriceCents,shippingFromCents,availability,receivedAt,requestId})),
    limitations:['Tallennettu oikea Context.dev-havainto; tämänhetkinen hinta ja saatavuus on tarkistettava uudelleen.','Jäsenhinta on erillinen. Tuntematon toimituskulu ei ole nolla.','Tallenne ei tee tilausta eikä käynnistä hakuvahtia.']
  };
}
if(process.argv[1]===fileURLToPath(import.meta.url)){
  const bytes=await readFile(new URL('../../solutions/context-dev-live-web-decision/live/capture.json',import.meta.url),'utf8');
  const next=new URL('./.evidence-'+randomUUID()+'.tmp',import.meta.url);
  try{
    await writeFile(next,JSON.stringify(projectEvidence(bytes),null,2)+'\n',{flag:'wx'});
    await rename(next,new URL('./evidence.json',import.meta.url));
  }finally{await rm(next,{force:true});}
}
