import {decide,memo,change} from './engine.mjs';
import {scenarios,before} from './fixtures.mjs';
const $=id=>document.getElementById(id);const money=n=>'€'+(n/100).toFixed(2);
let current,version=0;
function el(tag,text,className){const e=document.createElement(tag);e.textContent=text;if(className)e.className=className;return e;}
async function render(name){
 const run=++version,input=scenarios[name],result=await decide(JSON.stringify(input));if(run!==version)return;current=result;
 document.querySelectorAll('[data-case]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.case===name)));
 $('result').replaceChildren();const verdict=el('div','','verdict');verdict.append(el('div',result.winner?'↳':'!','mark'));const copy=el('div','');copy.append(el('h2',result.winner?`Review ${result.winner==='north'?'North Supply':'Coast Trading'}`:'Pause the sourcing decision'));
 const reasons={before:'Both suppliers qualify. North is €60 cheaper for 40 units.',after:'North fell from 80 to 12 units. Coast is the only supplier that can fill this order.',cosmetic:'Only a promotional banner changed. North remains the lowest eligible total.',failed:'Coast returned HTTP 200 with a failed JSON output. Refresh complete evidence before comparing.'};copy.append(el('p',reasons[name]));verdict.append(copy);$('result').append(verdict);
 $('cards').replaceChildren();$('rows').replaceChildren();
 for(const s of input.snapshots){const candidate=result.candidates.find(c=>c.id===s.id),card=el('article','','card'+(result.winner===s.id?' selected':''));card.append(el('p','SYNTHETIC_REPLAY · '+(result.winner===s.id?'REVIEW CANDIDATE':'SOURCE CARD'),'eyebrow'),el('h3',s.id==='north'?'North Supply':'Coast Trading'),el('div',money(s.priceCents)+' / unit','price'));const facts=el('div','','facts');for(const [label,value] of [['Inventory',s.inventory+' units'],['Lead time',s.leadDays+' days'],['Confidence',s.confidence+'%']]){const f=el('div',label);f.append(el('b',value));facts.append(f);}card.append(facts,el('p','Observed '+s.observedAt+' · '+change(before.snapshots.find(x=>x.id===s.id),s),'muted'),el('p',candidate?(candidate.constraints.join(' · ')||'Within all fixed constraints'):'Not evaluated: '+result.reason,'note'));$('cards').append(card);const tr=el('tr','');for(const value of [s.id,candidate?money(candidate.totalCents):'Unknown',s.inventory,s.leadDays+' days',candidate?(candidate.constraints.join(', ')||'Eligible'):'Refused'])tr.append(el('td',String(value)));$('rows').append(tr);}
 $('inspector').textContent=JSON.stringify({label:'SYNTHETIC_REPLAY',input,result},null,2);$('memo').textContent=memo(result);$('memo-section').hidden=true;
}
document.querySelectorAll('[data-case]').forEach(b=>b.addEventListener('click',()=>render(b.dataset.case)));
$('review').addEventListener('click',()=>{$('memo-section').hidden=false;$('memo-section').focus();});
$('download').addEventListener('click',()=>{const url=URL.createObjectURL(new Blob([memo(current)],{type:'text/plain;charset=utf-8'}));const a=el('a','');a.href=url;a.download='SupplyPulse-SYNTHETIC_REPLAY-memo.txt';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
render('after');
