import {regionFacts,optimise,equityShare,deathsPostponed,centralParameters,ASSUMPTIONS,sampleParameters,INTERVENTIONS} from '../src/recommend.mjs';
import {quantile} from '../src/stats.mjs';
export {ASSUMPTIONS,INTERVENTIONS};
export function metricRows(app,key){
 const a=app.analysis;
 return a.regions.map(r=>{const row=key==='mortality'?a.mortality.all_cancers.rows.find(x=>x.regionId===r.regionId):a.indicators[key]?.rows.find(x=>x.regionId===r.regionId);
 const valid=row&&!row.suppressed;return {...r,row,value:valid?(key==='mortality'?row.shrunk:row.level):null,low:valid?(key==='mortality'?row.shrunkLow:row.se==null?null:row.level-1.96*row.se):null,high:valid?(key==='mortality'?row.shrunkHigh:row.se==null?null:row.level+1.96*row.se):null};});
}
export function computePortfolio(app,{budget=app.recommendation.budget,epsilon=app.recommendation.epsilon,assumptions=ASSUMPTIONS}={}){
 const facts=regionFacts(app.analysis),result=optimise(facts,{budget,epsilon,assumptions,params:centralParameters(assumptions)});
 const defaults=budget===app.recommendation.budget&&epsilon===app.recommendation.epsilon&&JSON.stringify(assumptions)===JSON.stringify(ASSUMPTIONS);
 // Fixed-portfolio uncertainty: correlated draws preserve overlapping effects.
 const totals=[],shares=[],groups=new Map();for(const p of result.picks){if(!groups.has(p.id))groups.set(p.id,[]);groups.get(p.id).push(p);}
 const samples=new Map([...groups.keys()].map(id=>[id,[]]));
 for(let i=0;i<app.recommendation.draws;i++){
 const params=sampleParameters(9173+i,assumptions);let total=0,highMortality=0;const contributions=new Map([...groups.keys()].map(id=>[id,0]));
 for(const region of facts){const selected=new Set();let prev=0;for(const p of result.picks.filter(x=>x.regionId===region.regionId)){selected.add(p.id);const next=deathsPostponed(region,selected,params).deaths;contributions.set(p.id,contributions.get(p.id)+next-prev);prev=next;}total+=prev;if(region.smr>1)highMortality+=prev;}
 totals.push(total);if(total>0)shares.push(highMortality/total);for(const [id,v] of contributions)samples.get(id).push(v);
 }
 const interval=v=>[quantile([...v].sort((a,b)=>a-b),.025),quantile([...v].sort((a,b)=>a-b),.975)];
 return {result,defaults,range:defaults?[app.recommendation.portfolio.low,app.recommendation.portfolio.high]:interval(totals),equity:equityShare(facts,result),equityRange:interval(shares),groups:[...groups].map(([id,picks])=>({id,picks,cost:picks.reduce((s,p)=>s+p.cost,0),gain:picks.reduce((s,p)=>s+p.gain,0),range:interval(samples.get(id))}))};
}
