/** Fresh bounded Hungarian implementation. Costs are caller-defined; matches are proposals. */
export function assign(oldIds,newIds,edges,{unmatchedCost=1,maxComponent=80,maxEdges=20000}={}) {
  if(!Array.isArray(oldIds)||!Array.isArray(newIds)||!Array.isArray(edges)||oldIds.length>1000||newIds.length>1000||edges.length>maxEdges||
     new Set(oldIds).size!==oldIds.length||new Set(newIds).size!==newIds.length||!oldIds.every(x=>typeof x==='string')||!newIds.every(x=>typeof x==='string')||!Number.isFinite(unmatchedCost)||unmatchedCost<=0||unmatchedCost>1e6||!Number.isInteger(maxComponent)||maxComponent<2||maxComponent>200||!Number.isInteger(maxEdges)||maxEdges<0||maxEdges>20000)throw new Error('Invalid or over-budget assignment.');
  const old=new Set(oldIds),next=new Set(newIds),adj=new Map(),costs=new Map();
  const add=(a,b)=>{if(!adj.has(a))adj.set(a,[]);adj.get(a).push(b);};
  for(const e of edges){
    if(!old.has(e.oldId)||!next.has(e.newId)||!Number.isFinite(e.cost)||e.cost<0)throw new Error('Invalid assignment edge.');
    const key=JSON.stringify([e.oldId,e.newId]);if(costs.has(key))throw new Error('Duplicate assignment edge.');costs.set(key,e.cost);
    if(e.cost>=2*unmatchedCost)continue; // Equal-gain matching never forces an observation to have an identity.
    add('o:'+e.oldId,'n:'+e.newId);add('n:'+e.newId,'o:'+e.oldId);
  }
  const seen=new Set(),pairs=[];
  for(const start of oldIds.map(id=>'o:'+id)){
    if(seen.has(start)||!adj.has(start))continue;
    const queue=[start];seen.add(start);
    for(let k=0;k<queue.length;k++)for(const v of adj.get(queue[k])??[])if(!seen.has(v)){seen.add(v);queue.push(v);}
    if(queue.length>maxComponent)throw new Error('Assignment component exceeds the work budget; narrow the comparison.');
    const left=queue.filter(x=>x.startsWith('o:')).map(x=>x.slice(2)).sort(),right=queue.filter(x=>x.startsWith('n:')).map(x=>x.slice(2)).sort();
    const n=left.length,m=right.length+n,blocked=(n+m+1)*unmatchedCost*10;
    const c=left.map(id=>[...right.map(other=>{const cost=costs.get(JSON.stringify([id,other]));return cost!=null&&cost<2*unmatchedCost?cost-unmatchedCost:blocked;}),...left.map(()=>unmatchedCost)]);
    const u=Array(n+1).fill(0),v=Array(m+1).fill(0),p=Array(m+1).fill(0),way=Array(m+1).fill(0);
    for(let i=1;i<=n;i++){
      p[0]=i;let j0=0;const min=Array(m+1).fill(Infinity),used=Array(m+1).fill(false);
      do{
        used[j0]=true;const i0=p[j0];let delta=Infinity,j1=0;
        for(let j=1;j<=m;j++)if(!used[j]){const cur=c[i0-1][j-1]-u[i0]-v[j];if(cur<min[j]){min[j]=cur;way[j]=j0;}if(min[j]<delta){delta=min[j];j1=j;}}
        for(let j=0;j<=m;j++){if(used[j]){u[p[j]]+=delta;v[j]-=delta;}else min[j]-=delta;}j0=j1;
      }while(p[j0]!==0);
      do{const j1=way[j0];p[j0]=p[j1];j0=j1;}while(j0);
    }
    for(let j=1;j<=right.length;j++)if(p[j]){const oldId=left[p[j]-1],newId=right[j-1],cost=costs.get(JSON.stringify([oldId,newId]));if(cost!=null&&cost<2*unmatchedCost)pairs.push({oldId,newId,cost,ambiguousCandidates:(adj.get('o:'+oldId)?.length??0)>1||(adj.get('n:'+newId)?.length??0)>1});}
  }
  const matchedOld=new Set(pairs.map(p=>p.oldId)),matchedNew=new Set(pairs.map(p=>p.newId));
  return {pairs:pairs.sort((a,b)=>a.oldId.localeCompare(b.oldId)),unmatchedOld:oldIds.filter(id=>!matchedOld.has(id)),unmatchedNew:newIds.filter(id=>!matchedNew.has(id)),
    physicalIdentityVerified:false,method:'bounded-minimum-cost-one-to-one-with-unmatched/v1'};
}
