import {graphScore,verifyModelArtifact} from './core.mjs';
const byId=id=>document.getElementById(id),pct=v=>v===null?'undefined':(100*v).toFixed(1)+'%';
let model;
const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),10000);
try{
 const responses=await Promise.all(['./evaluation.json','./model.json'].map(p=>fetch(p,{signal:controller.signal})));
 if(responses.some(r=>!r.ok))throw new Error('Unavailable');
 const [report,modelText]=await Promise.all([responses[0].json(),responses[1].text()]);model=await verifyModelArtifact(report,modelText);
 const counts=report.counts;
 byId('split').textContent=counts.train.n+' training / '+counts.calibration.n+' calibration / '+counts.test.n+' held-out trend graphs ('+report.byte_identical_duplicates_removed+' byte-identical duplicates removed). No test labels used for fitting or threshold choice.';
 for(const [name,key] of [['Majority baseline','majority'],['Size-only baseline','size_only'],['Topology candidate','topology']]){
  const m=report.held_out[key],row=document.createElement('tr');
  for(const value of [name,pct(m.accuracy),pct(m.precision),pct(m.recall),m.fp+'/'+(m.fp+m.tn)+' ('+pct(m.false_positive_rate)+')']){
   const cell=document.createElement('td');cell.textContent=value;row.append(cell);
  }
  byId('metrics').append(row);
 }
 const t=report.held_out.topology,ci=t.fpr_wilson95;
 byId('qualification').textContent=t.false_positive_rate>.10?'Held-out false alarms exceed the 10% calibration target. Research only; no production qualification.':'This small benchmark does not establish production qualification.';
 byId('uncertainty').textContent='Topology candidate: '+t.tp+' campaigns detected, '+t.fn+' missed; '+t.fp+' organic trends flagged, '+t.tn+' left unflagged. Descriptive 95% false-alarm interval: '+pct(ci[0])+'–'+pct(ci[1])+'. Graph overlap may make this interval optimistic.';
 byId('source').textContent='Source archive SHA-256: '+report.source.sha256;
 byId('analyze').disabled=false;
}catch{byId('split').textContent='Evaluation unavailable. No performance claim can be made.';}
finally{clearTimeout(timeout);}
byId('analyze').addEventListener('click',async()=>{
 byId('result').textContent='';
 try{
  const file=byId('file').files[0];if(!file||file.size>2*1024*1024)throw new Error('Choose a JSON edge list up to 2 MiB.');
  const graph=JSON.parse(await file.text()),r=graphScore(graph,model);
  byId('result').textContent=(r.review?'Review signal: campaign-like topology.':'No review signal at the frozen threshold.')+' Experimental score '+r.score.toFixed(3)+'; '+r.nodes+' active nodes, '+r.edges+' edges. Intent UNKNOWN. This score is not a probability or proof.';
 }catch(error){byId('result').textContent=error instanceof SyntaxError?'Invalid JSON edge list.':error.message;}
});
byId('clear').addEventListener('click',()=>{byId('file').value='';byId('result').textContent='Cleared. No input was stored.';});
