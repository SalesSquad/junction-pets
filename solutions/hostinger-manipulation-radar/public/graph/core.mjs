// Experimental LEN graph screen. No network, storage, text or identity features.
export const FEATURES=['log_nodes','log_edges','density','zero_in_fraction','zero_out_fraction','reciprocal_fraction','in_gini','out_gini','max_in_share','max_out_share','in_hhi','out_hhi'];
const fail=(reason='Outside research range: 100–8,355 active nodes and 203–10,608 unique directed edges.')=>{throw new Error('Invalid edge list: '+reason);};
function gini(values){const a=[...values].sort((a,b)=>a-b),total=a.reduce((a,b)=>a+b,0);return a.reduce((s,v,i)=>s+(2*(i+1)-a.length-1)*v,0)/(a.length*total);}
export function graphFeatures(input,{enforceDomain=true}={}){
 if(!input||Array.isArray(input)||typeof input!=='object'||Object.keys(input).length!==1||!Array.isArray(input.edges))fail('Use an object containing only an edges array.');
 if(!input.edges.length||input.edges.length>10608)fail('Supply between 203 and 10,608 edges.');
 const incoming=new Map(),outgoing=new Map(),nodes=new Set(),edges=new Set(),pairs=[];
 const id=v=>{if((typeof v!=='string'&&typeof v!=='number')||(typeof v==='number'&&!Number.isSafeInteger(v))||(typeof v==='string'&&(!v.length||v.length>128)))fail('References must be nonempty strings up to 128 characters or safe integers.');return JSON.stringify(v);};
 for(const pair of input.edges){if(!Array.isArray(pair)||pair.length!==2)fail('Each edge must be exactly [source, target].');const [a,b]=pair.map(id),key=JSON.stringify([a,b]);if(edges.has(key))fail('Duplicate directed pair; include each edge once.');edges.add(key);pairs.push([a,b]);nodes.add(a);nodes.add(b);incoming.set(b,(incoming.get(b)||0)+1);outgoing.set(a,(outgoing.get(a)||0)+1);}
 const n=nodes.size,m=edges.size;if(n<2||(enforceDomain&&(n<100||n>8355||m<203)))fail();
 const iv=[...nodes].map(v=>incoming.get(v)||0),ov=[...nodes].map(v=>outgoing.get(v)||0);
 const zero=a=>a.filter(v=>v===0).length/n,hhi=a=>a.reduce((s,v)=>s+(v/m)**2,0);
 const x=[Math.log1p(n),Math.log1p(m),m/(n*n),zero(iv),zero(ov),pairs.filter(([a,b])=>a!==b&&edges.has(JSON.stringify([b,a]))).length/m,gini(iv),gini(ov),Math.max(...iv)/m,Math.max(...ov)/m,hhi(iv),hhi(ov)];
 return {x,nodes:n,edges:m};
}
export function graphScore(input,model){
 if(!model||model.schema!=='signal-desk-len-model-v1'||JSON.stringify(model.features)!==JSON.stringify(FEATURES)||!Number.isFinite(model.threshold)||model.threshold<0||model.threshold>1.000000001)throw new Error('Model unavailable.');
 for(const key of ['means','scales','weights'])if(!Array.isArray(model[key])||model[key].length!==FEATURES.length||!model[key].every(Number.isFinite))throw new Error('Model unavailable.');
 if(!model.scales.every(v=>v>0)||!Number.isFinite(model.intercept))throw new Error('Model unavailable.');
 const graph=graphFeatures(input);
 const z=model.intercept+graph.x.reduce((s,v,i)=>s+model.weights[i]*(v-model.means[i])/model.scales[i],0);
 if(!Number.isFinite(z))throw new Error('Model unavailable.');
 const score=z>=0?1/(1+Math.exp(-z)):Math.exp(z)/(1+Math.exp(z));
 return {score,review:score>=model.threshold,nodes:graph.nodes,edges:graph.edges,intent:'UNKNOWN',status:'EXPERIMENTAL'};
}
