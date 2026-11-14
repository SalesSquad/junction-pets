import {before,after,cosmetic,failed} from './fixtures.mjs';import {decide,change} from './engine.mjs';
const variant=fn=>{const x=structuredClone(before);fn(x);return x;};
export const cases=[
 {name:'baseline / initial',input:before,expected:'north'},
 {name:'baseline / inventory correction',input:after,expected:'coast'},
 {name:'baseline / cosmetic banner',input:cosmetic,expected:'north'},
 {name:'held-out / failed output',input:failed,expected:null},
 {name:'held-out / north delivery slips',input:variant(x=>x.snapshots[0].leadDays=8),expected:'coast'},
 {name:'held-out / both unaffordable',input:variant(x=>x.snapshots.forEach(s=>s.priceCents=1600)),expected:null},
 {name:'held-out / coast cheaper',input:variant(x=>x.snapshots[1].priceCents=1100),expected:'coast'},
 {name:'held-out / expired observation',input:variant(x=>x.asOf='2026-11-14T10:00:00.000Z'),expected:null}
];
export async function compare(){return Promise.all(cases.map(async c=>{const result=await decide(JSON.stringify(c.input));const naive=[...c.input.snapshots].sort((a,b)=>a.priceCents-b.priceCents)[0].id;return {mode:'SYNTHETIC_REPLAY',case:c.name,expected:c.expected,decision:result.winner,pass:result.winner===c.expected,priceOnlyBaseline:naive,baselinePass:naive===c.expected,textDiffAlarm:before.snapshots.some((s,i)=>s.text!==c.input.snapshots[i].text),semanticChange:before.snapshots.some((s,i)=>change(s,c.input.snapshots[i])==='material')};}));}
if(process.argv[1]?.endsWith('/comparator.mjs'))console.log(JSON.stringify(await compare(),null,2));
