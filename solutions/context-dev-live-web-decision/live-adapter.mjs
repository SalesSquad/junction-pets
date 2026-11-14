// Source-only integration seam. No SDK dependency, fetch implementation, or default live targets.
// Operator must configure exact public HTTPS URLs in trusted source, never from page/user data.
export const LIVE_TARGETS=Object.freeze({});
export const schema={type:'object',additionalProperties:false,required:['priceCents','inventory','leadDays','confidence','currency'],properties:{priceCents:{type:'integer',minimum:1},inventory:{type:'integer',minimum:0},leadDays:{type:'integer',minimum:0},confidence:{type:'integer',minimum:0,maximum:100},currency:{const:'EUR'}}};
export async function extractLive({mode,sourceId,client,env=process.env}) {
  if(mode!=='LIVE'||!env.CONTEXT_DEV_API_KEY)throw new Error('explicit-live-mode-and-key-required');
  const target=LIVE_TARGETS[sourceId];
  if(!target)throw new Error('no-preconfigured-live-target');
  const url=new URL(target);
  if(url.protocol!=='https:'||url.username||url.password||url.port||url.hash||url.search||url.href!==target)throw new Error('unsafe-target');
  // Injected trusted SDK client is constructed by the operator with env key.
  const response=await client.web.scrape({url:target,formats:{json:true},jsonParams:{schema},sharedParams:{maxAgeMs:0}});
  return validateOutput(response);
}
export function validateOutput(response){
  if(!response||JSON.stringify(response).length>32768||response.page?.json?.success!==true)throw new Error('json-output-failed');
  const data=response.page.json.data;
  if(!data||Object.keys(schema.properties).some(k=>!Object.hasOwn(data,k))||Object.keys(data).some(k=>!Object.hasOwn(schema.properties,k))||data.currency!=='EUR'||!['priceCents','inventory','leadDays','confidence'].every(k=>Number.isSafeInteger(data[k]))||data.priceCents<=0||data.inventory<0||data.leadDays<0||data.confidence<0||data.confidence>100)throw new Error('partial-or-invalid-output');
  return {mode:'LIVE_UNVERIFIED',data}; // Must acquire trusted observation/redirect/cache provenance before decision admission.
}
