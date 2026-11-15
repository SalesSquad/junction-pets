import {cents} from '../live/compare.mjs';
import {MERCHANTS,LIMITS,productURL,problem,fingerprint,safeError} from './model.mjs';
const list=x=>x==null?[]:Array.isArray(x)?x:[x];
const tag=x=>typeof x==='string'?x.replace(/^https?:\/\/schema\.org\//,''):null;
function productNodes(input,depth=0,budget={left:2048}){const values=list(input);if(depth>12||values.length>budget.left)throw problem('PROVIDER_SCHEMA');budget.left-=values.length;return values.flatMap(v=>v&&typeof v==='object'?[...(list(v['@type']).includes('Product')?[v]:[]),...productNodes(v['@graph'],depth+1,budget)]:[]);}
const price=x=>cents(typeof x==='number'?String(x):x);
const normalizeText=s=>String(s??'').normalize('NFKD').replace(/\p{M}/gu,'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();
const stop=new Set(['a','an','and','the','for','with','want','find','haluan','etsi','ja','tai','minulle','alle','euroa','eur']);
function knownQuote(extraction,field,markdown){return list(extraction?.evidence).filter(e=>e&&e.field===field&&typeof e.quote==='string'&&e.quote.length>=2&&e.quote.length<=200&&markdown.includes(e.quote)).map(e=>({field,quote:e.quote}));}
function amountEvidence(extraction,field,markdown){
  const expected=price(extraction?.[field]);if(expected===null)return [];
  return knownQuote(extraction,field,markdown).filter(e=>{
    const quote=e.quote.replace(/(?<=\d)[\s\u00a0\u202f]+(?=\d{3}(?:\D|$))/g,'');
    return [...quote.matchAll(/(?<![\d.,])(?:0|[1-9]\d*)(?:[.,]\d{1,2})?(?![\d.,])/g)].some(m=>price(m[0].replace(',','.'))===expected);
  });
}
function scalar(value){return typeof value==='string'?value.slice(0,300):null;}
function ordinary(o){return !o.validForMemberTier&&(!o.eligibleCustomerType?.['@id']||o.eligibleCustomerType['@id']==='https://schema.org/Public');}
export function offerFromResponse(response,url,def){
  const target=productURL(url,def.merchantIds);const body=response.data;
  if(!target||body.url!==target.url||body.markdown?.success!==true||typeof body.markdown.data!=='string'||body.cache_metadata?.age_ms!==0)throw problem('SOURCE_REJECTED');
  if(body.product?.success===true&&body.product.data?.isProductPage===false)throw problem('SOURCE_REJECTED');
  for(const value of [body.metadata?.canonicalUrl,body.metadata?.finalUrl])if(value&&productURL(value,def.merchantIds)?.url!==target.url)throw problem('SOURCE_REJECTED');
  const markdown=body.markdown.data;const extraction=body.json?.success===true&&body.json.data&&typeof body.json.data==='object'?body.json.data:null;
  const extractedProduct=body.product?.success===true&&body.product.data?.isProductPage===true?body.product.data.product:null;
  const nodes=productNodes(body.metadata?.jsonLd);let candidates=nodes;
  if(def.gtin)candidates=nodes.filter(p=>list(p.gtin13??p.gtin??p.gtin14??p.gtin12).includes(def.gtin));
  // Multiple main products are ambiguous; do not choose the cheapest accessory.
  const main=candidates.length===1?candidates[0]:null;
  if(def.gtin&&nodes.length&&!main)throw problem('SOURCE_REJECTED');
  const title=scalar(main?.name)??scalar(extractedProduct?.name)??(knownQuote(extraction,'title',markdown).length?scalar(extraction?.title):null);
  if(!title)throw problem('PROVIDER_SCHEMA');
  let gtin=list(main?.gtin13??main?.gtin??main?.gtin14??main?.gtin12).find(v=>typeof v==='string'&&/^\d{8,14}$/.test(v))??null,textGtin=false;
  if(!gtin&&typeof extraction?.gtin==='string'&&/^\d{8,14}$/.test(extraction.gtin)&&knownQuote(extraction,'gtin',markdown).some(e=>new RegExp('(?<!\\d)'+extraction.gtin+'(?!\\d)').test(e.quote))){gtin=extraction.gtin;textGtin=true;}
  if(def.gtin&&gtin!==def.gtin)throw problem('SOURCE_REJECTED');
  const warnings=[],evidence=[];
  const offers=list(main?.offers).filter(o=>list(o?.['@type']).includes('Offer')&&o.priceCurrency==='EUR'&&ordinary(o));
  const sourcePrices=[...new Set(offers.map(o=>price(o.price)).filter(v=>v!==null))];
  let priceCents=sourcePrices.length===1?sourcePrices[0]:null,memberPriceCents=null,shippingFromCents=null,stockStatus='unknown',condition='unknown',textPrice=false,textStock=false,textMember=false,textCondition=false;
  if(sourcePrices.length>1)warnings.push('Conflicting ordinary prices in the retailer product data.');
  const specs=offers.flatMap(o=>list(o.priceSpecification));const normalSpecs=specs.filter(s=>!s.validForMemberTier&&s.valueAddedTaxIncluded===true&&s.priceCurrency==='EUR');
  if(normalSpecs.some(s=>price(s.price)!==priceCents)){priceCents=null;warnings.push('Ordinary price specifications conflict.');}
  const members=[...new Set(specs.filter(s=>s.validForMemberTier&&s.valueAddedTaxIncluded===true&&s.priceCurrency==='EUR').map(s=>price(s.price)).filter(v=>v!==null))];
  if(members.length===1)memberPriceCents=members[0];
  if(memberPriceCents===priceCents&&!normalSpecs.some(s=>price(s.price)===priceCents)){priceCents=null;warnings.push('Main price may require membership.');}
  if(priceCents===null&&sourcePrices.length===0&&extraction?.currency==='EUR'&&amountEvidence(extraction,'ordinaryPrice',markdown).length){
    priceCents=price(extraction.ordinaryPrice);textPrice=true;evidence.push(...amountEvidence(extraction,'ordinaryPrice',markdown));warnings.push('Price is extracted from page text; verify the offer conditions.');
  }
  if(memberPriceCents===null&&extraction?.currency==='EUR'&&amountEvidence(extraction,'memberPrice',markdown).length){memberPriceCents=price(extraction.memberPrice);textMember=true;evidence.push(...amountEvidence(extraction,'memberPrice',markdown));warnings.push('Member price is a text extraction; verify membership and offer conditions.');}
  const availability=[...new Set(offers.map(o=>tag(o.availability)).filter(Boolean))];
  if(availability.length===1)stockStatus=availability[0]==='InStock'?'in_stock':['OutOfStock','Discontinued','SoldOut'].includes(availability[0])?'out_of_stock':'unknown';
  const conditions=[...new Set(offers.map(o=>tag(o.itemCondition)).filter(Boolean))];if(conditions.length===1)condition=conditions[0]==='NewCondition'?'new':conditions[0]==='RefurbishedCondition'?'refurbished':conditions[0]==='UsedCondition'?'used':'unknown';
  const shipping=offers.flatMap(o=>list(o.shippingDetails)).filter(s=>s.shippingDestination?.addressCountry==='FI'&&s.shippingRate?.currency==='EUR').map(s=>cents(String(s.shippingRate.value),{allowZero:true})).filter(v=>v!==null);
  if(new Set(shipping).size===1)shippingFromCents=shipping[0];
  if(stockStatus==='unknown'&&knownQuote(extraction,'stockStatus',markdown).length&&['in_stock','out_of_stock'].includes(extraction?.stockStatus)){stockStatus=extraction.stockStatus;textStock=true;evidence.push(...knownQuote(extraction,'stockStatus',markdown));warnings.push('Availability is a text extraction, not a stock reservation.');}
  if(condition==='unknown'&&knownQuote(extraction,'condition',markdown).length&&['new','used','refurbished'].includes(extraction?.condition)){condition=extraction.condition;textCondition=true;}
  const tokens=normalizeText(def.query).split(' ').filter(t=>t.length>1&&!stop.has(t));const mainText=normalizeText(title+' '+(main?.description??extractedProduct?.description??''));
  const matchStatus=def.gtin?'exact_gtin':tokens.length&&tokens.every(t=>mainText.includes(t))?'text_match':'needs_review';
  const selectedPriceCents=def.includeMemberPrices&&memberPriceCents!==null?memberPriceCents:priceCents;
  let needsReview=matchStatus==='needs_review'||priceCents===null||textPrice||textStock||textGtin||def.includeMemberPrices&&textMember||def.quantity>1||!!def.requirements.trim()||def.condition==='new'&&(condition!=='new'||textCondition);
  if(def.quantity>1)warnings.push('Available quantity is unconfirmed; InStock does not prove this order quantity.');
  if(def.requirements.trim())warnings.push('Review the detailed requirements; a search match alone does not prove them.');
  if(shippingFromCents===null)warnings.push('Shipping unknown. Item subtotal is not delivered total.');
  const meetsTarget=!needsReview&&selectedPriceCents!==null&&(def.maxPriceCents===null||selectedPriceCents<=def.maxPriceCents)&&(!def.inStockOnly||stockStatus==='in_stock')&&(def.condition==='any'||condition===def.condition);
  return {id:fingerprint(target.url).slice(0,24),title,url:target.url,merchantId:target.merchant.id,merchantName:target.merchant.name,gtin,priceCents,memberPriceCents,selectedPriceCents,itemSubtotalCents:selectedPriceCents===null?null:selectedPriceCents*def.quantity,shippingFromCents,stockStatus,matchStatus,condition,meetsTarget,needsReview,
    evidence:evidence.slice(0,8),requirementsAssessment:scalar(extraction?.requirementsAssessment)??'',warnings,requestId:response.requestId,receivedAt:response.receivedAt,
    extraction:{product:body.product?.success===true,json:body.json?.success===true,jsonLd:!!main}};
}
export function detectChanges(offers,previous){
  const changes=[];for(const offer of offers){const old=previous?.offers?.find(o=>o.id===offer.id);
    const add=(type,before,after)=>changes.push({type,offerId:offer.id,title:offer.title,before,after,url:offer.url});
    if(!old){add('new',null,offer.selectedPriceCents);if(offer.meetsTarget)add('target_reached',null,offer.selectedPriceCents);continue;}
    if(old.selectedPriceCents!==null&&offer.selectedPriceCents!==null&&old.selectedPriceCents!==offer.selectedPriceCents)add(offer.selectedPriceCents<old.selectedPriceCents?'price_drop':'price_rise',old.selectedPriceCents,offer.selectedPriceCents);
    if(old.stockStatus!==offer.stockStatus)add('availability',old.stockStatus,offer.stockStatus);
    if(!old.meetsTarget&&offer.meetsTarget)add('target_reached',old.selectedPriceCents,offer.selectedPriceCents);
  }return changes;
}
export async function executeWatch(claim,{client,beforeCall,signal}){
  const def=claim.definition,endpointUsage=[],creditValues=[],warnings=[];
  const call=async fn=>{const r=await fn({beforeCall,signal});endpointUsage.push({operation:r.operation,requestId:r.requestId});creditValues.push(r.creditsConsumed);return r;};
  const credits=()=>creditValues.length&&creditValues.every(v=>v!==null)?creditValues.reduce((a,b)=>a+b,0):null;
  if(claim.kind==='research'){
    const result=await call(options=>client.research(def,options));
    const sources=list(result.data.sources).filter(url=>productURL(url,def.merchantIds)).slice(0,12);
    if(!result.data.json_content||typeof result.data.json_content!=='object')throw problem('PROVIDER_SCHEMA');
    const raw=JSON.stringify(result.data.json_content);if(raw.length>12_000)throw problem('PROVIDER_SCHEMA');
    return {summary:{offers:[],changes:[],headline:'Product research ready for review',research:{answer:JSON.parse(raw),sources},endpointUsage,warnings:['Research is advisory; verify claims at the cited retailer.']},credits:credits()};
  }
  const found=await call(options=>client.search(def,options));if(!Array.isArray(found.data.results))throw problem('PROVIDER_SCHEMA');
  let urls=found.data.results.map(r=>productURL(r.url,def.merchantIds)).filter(Boolean).map(r=>r.url);
  if(def.expandCatalog){
    const merchant=MERCHANTS.filter(m=>def.merchantIds.includes(m.id)).sort((a,b)=>urls.filter(u=>u.includes(a.domain)).length-urls.filter(u=>u.includes(b.domain)).length)[0];
    try {const mapped=await call(options=>client.map(merchant.domain,def.query,options));urls.push(...list(mapped.data.urls).map(r=>productURL(typeof r==='string'?r:r.url,def.merchantIds)).filter(Boolean).map(r=>r.url));}
    catch(e){if(['PROVIDER_AUTH','PROVIDER_CREDITS_EXHAUSTED','RUN_CANCELLED','RUN_DAY_CHANGED'].includes(safeError(e)))throw e;warnings.push('Catalog expansion incomplete: '+safeError(e));}
  }
  urls=[...new Set(urls)].slice(0,LIMITS.offersPerRun);
  const offers=[];
  for(const url of urls){
    try{const result=await call(options=>client.scrape(url,def.requirements,options));offers.push(offerFromResponse(result,url,def));}
    catch(e){if(['PROVIDER_AUTH','PROVIDER_CREDITS_EXHAUSTED','RUN_CANCELLED','RUN_DAY_CHANGED','REQUEST_LIMIT'].includes(safeError(e)))throw e;warnings.push('Offer could not be verified: '+safeError(e));}
  }
  const changes=detectChanges(offers,claim.previous);
  const headline=offers.length?`${offers.length} fresh offer${offers.length===1?'':'s'} · ${offers.filter(o=>o.meetsTarget).length} meet the confirmed filters`:warnings.length?'Search incomplete; no verified offers':'No matching product pages found';
  return {summary:{offers,changes,research:null,headline,endpointUsage,warnings},credits:credits(),errorCode:!offers.length&&warnings.length?'PROVIDER_FAILED':null};
}
