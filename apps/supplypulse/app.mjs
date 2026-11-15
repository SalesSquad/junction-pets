const $=id=>document.getElementById(id);
const element=(tag,text='',className)=>{const e=document.createElement(tag);e.textContent=text;if(className)e.className=className;return e;};
const money=value=>Number.isSafeInteger(value)&&value>=0?new Intl.NumberFormat('fi-FI',{style:'currency',currency:'EUR'}).format(value/100):'Ei tiedossa';
const timestamp=value=>typeof value==='string'&&Number.isFinite(Date.parse(value))?new Intl.DateTimeFormat('fi-FI',{year:'numeric',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',timeZone:'Europe/Helsinki',timeZoneName:'short'}).format(new Date(value)):'Havaintoaika ei tiedossa';
const retailerHosts=new Set(['www.gigantti.fi','gigantti.fi','www.proshop.fi','proshop.fi','www.verkkokauppa.com','verkkokauppa.com']);
function retailerLink(url,label){try{const u=new URL(url);if(u.protocol!=='https:'||!retailerHosts.has(u.hostname)||u.username||u.password)throw Error();const a=element('a',label);a.href=u.href;a.target='_blank';a.rel='noopener noreferrer';return a;}catch{return element('span','Lähdelinkki ei saatavilla','muted');}}
function fact(label,value){const wrap=element('div');wrap.append(element('dt',label),element('dd',value));return wrap;}
function render(data){
 if(data?.schemaVersion!==1||!data.product||!Array.isArray(data.offers)||data.offers.length!==2)throw Error('EVIDENCE_INVALID');
 $('product-name').textContent=typeof data.product.name==='string'?data.product.name:'Tallennettu tuote';
 $('product-identity').textContent=[data.product.mpn?'Valmistajan tunniste '+data.product.mpn:'',data.product.gtin?'EAN '+data.product.gtin:''].filter(Boolean).join(' · ');
 $('observation-time').textContent='Aineiston havaintohetki '+timestamp(data.asOf);
 $('offers').replaceChildren();$('source-records').replaceChildren();
 for(const offer of data.offers){
  const article=element('article','','offer');article.append(element('p','HISTORIALLINEN HAVAINTO','eyebrow'),element('h3',typeof offer.name==='string'?offer.name:'Kauppa'),element('p',money(offer.priceCents),'ordinary-price'),element('p','Tavallinen kappalehinta havaintohetkellä · toimitus erikseen','price-caption'));
  const facts=element('dl');facts.append(fact('Jäsenhinta tuolloin',offer.memberPriceCents===null||offer.memberPriceCents===undefined?'Ei ilmoitettu':money(offer.memberPriceCents)),fact('Toimituskulut alkaen',money(offer.shippingFromCents)));article.append(facts);
  const observed=element('time','Havaittu '+timestamp(offer.receivedAt),'observation');if(typeof offer.receivedAt==='string')observed.dateTime=offer.receivedAt;article.append(observed,retailerLink(offer.url,'Tarkista nykyiset tiedot kaupasta ↗'));$('offers').append(article);
  const record=element('div','','source-record');record.append(element('b',typeof offer.name==='string'?offer.name:'Kauppa'),element('p','Havaittu '+timestamp(offer.receivedAt)));if(typeof offer.requestId==='string')record.append(element('p','Haun tunniste: '+offer.requestId));record.append(retailerLink(offer.url,'Alkuperäinen tuotesivu ↗'));$('source-records').append(record);
 }
 $('limitations').replaceChildren();
 const limits=['Tämä on tallennettu havainto, ei uusi verkkohaku tai tämänhetkinen tarjous.','Jäsenhinta edellyttää kyseisen kaupan jäsenyyttä ja tarjouksen ehtojen täyttymistä.','Tuntemattomia toimituskuluja ei käsitellä nollana. Kappalehinta ei ole toimitettu kokonaishinta.','Saatavuus, määrät ja toimituspäivät on tarkistettava kaupasta uudelleen.'];
 for(const text of limits)$('limitations').append(element('li',text));
 $('evidence-status').textContent='Kaksi tallennettua lähdehavaintoa. Uudet haut tehdään vain avaamassasi paikallisessa hakuvahdissa.';
}
async function loadEvidence(){
 try{const response=await fetch(new URL('./evidence.json',import.meta.url),{cache:'no-store'});if(!response.ok)throw Error('EVIDENCE_UNAVAILABLE');render(await response.json());}
 catch{$('product-name').textContent='Tallennettua vertailua ei saatu ladattua.';$('evidence-status').textContent='Voit avata paikallisen hakuvahdin yllä olevasta linkistä. Tämä sivu ei tarkista paikallisen palvelimen tilaa eikä käynnistä hakuja.';}
}
loadEvidence();
