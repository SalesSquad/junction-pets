import {planProcurementPortfolio} from '../src/procurement-planner.mjs';
import catalog from './fixture.mjs';

const form=document.querySelector('#planner'),status=document.querySelector('#status'),results=document.querySelector('#results');
const make=(tag,text,cls)=>{const node=document.createElement(tag);node.textContent=text;if(cls)node.className=cls;return node;};
const euro=cents=>new Intl.NumberFormat('fi-FI',{style:'currency',currency:'EUR'}).format(cents/100);
const labels={cost:'Edullisin',resilience:'Toimitusvarmuus',footprint:'Pienempi päästöarvio'};
form.addEventListener('submit',event=>{
  event.preventDefault();results.replaceChildren();
  try {
    const values=new FormData(form),budget=String(values.get('budget')).replace(',','.');
    if(!/^\d+(?:\.\d{1,2})?$/.test(budget))throw Error('Tarkista budjetti.');
    const [whole,fraction='']=budget.split('.'),budgetCents=Number(whole)*100+Number(fraction.padEnd(2,'0'));
    const requirements=[{family:'dairy-milk',quantityLitres:Number(values.get('milk')),lactoseFree:true,deliverBy:'2026-11-16'},
      {family:'oat-drink',quantityLitres:Number(values.get('oat')),lactoseFree:true,deliverBy:'2026-11-16'}];
    const plan=planProcurementPortfolio({catalog,requirements,budgetCents});
    status.textContent='Laskettu kuvitteellisilla tiedoilla. Tarkista kunkin vaihtoehdon budjetti.';
    for(const option of plan.options){
      const card=make('article','','card');card.append(make('h2',labels[option.id]));
      card.append(make('p',euro(option.totalCents),'price'));
      card.append(make('p',option.withinBudget?'Budjetin sisällä':'Ylittää budjetin',option.withinBudget?'ok':'over'));
      card.append(make('p',`Toimittajia ${option.supplierCount} · kuvitteellinen päästöarvio ${option.carbonKgEstimate} kg`));
      if(option.equivalentTo)card.append(make('p',`Sama kori kuin vaihtoehdossa ${labels[option.equivalentTo]}.`));
      const list=document.createElement('ul');
      for(const line of option.lines)list.append(make('li',`${line.sku}: ${line.quantityLitres} l · ${euro(line.totalCents)}`));
      card.append(list);results.append(card);
    }
  } catch(error) {
    status.textContent=error?.code==='BUDGET_EXCEEDED'?'Yksikään esimerkkikori ei mahdu budjettiin.':error?.code==='INSUFFICIENT_AVAILABILITY'?'Esimerkkivarastossa ei ole riittävästi vastaavia tuotteita.':`Laskentaa ei voitu tehdä: ${error?.message??'tarkista syötteet'}`;
  }
});
form.requestSubmit();
