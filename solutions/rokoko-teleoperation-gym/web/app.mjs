import {evaluateEpisode} from "../src/engine.mjs";
const byId=id=>document.getElementById(id);
const text=(id,value)=>{byId(id).textContent=String(value);};
let records=[];
let current=0;

function xy(p) {
  return {x:32+(p.x+0.5)*376,y:240-p.y/0.6*218};
}
function svgNode(name,attrs,parent) {
  const el=document.createElementNS("http://www.w3.org/2000/svg",name);
  for (const [k,v] of Object.entries(attrs)) el.setAttribute(k,String(v));
  parent.append(el);
  return el;
}
function draw(e,r) {
  const layer=byId("trace-layer");
  layer.replaceChildren();
  const pts=e.steps.map(s=>xy(s.hand));
  const g=xy(e.goal);
  const points=pts.map(p=>p.x.toFixed(1)+","+p.y.toFixed(1)).join(" ");
  svgNode("polyline",{points,fill:"none",stroke:"#a7f6d0","stroke-width":3,"stroke-linecap":"round","stroke-linejoin":"round"},layer);
  for(let i=0;i<pts.length;i++) {
    const unsafe=r.trace[i].status==="HELD";
    svgNode("circle",{cx:pts[i].x,cy:pts[i].y,r:unsafe?7:4,fill:unsafe?"#ffa172":"#a7f6d0",stroke:"#0c1d22","stroke-width":1},layer);
  }
  svgNode("circle",{cx:g.x,cy:g.y,r:13,fill:"none",stroke:"#b4a6ff","stroke-width":2},layer);
  svgNode("path",{d:"M"+(g.x-7)+","+g.y+"H"+(g.x+7)+" M"+g.x+","+(g.y-7)+"V"+(g.y+7),stroke:"#b4a6ff","stroke-width":1.5},layer);
}
function renderTimeline(receipt) {
  const bar=byId("timeline");
  bar.replaceChildren();
  for(const entry of receipt.trace) {
    const segment=document.createElement("div");
    segment.className="timeline-cell "+(entry.status==="HELD"?"bad":entry.status==="REARMED_PROPOSAL_ONLY"?"rearmed":"good");
    segment.title=entry.at_ms+" ms · "+entry.status;
    segment.setAttribute("aria-label",entry.at_ms+" milliseconds: "+entry.status.replaceAll("_"," ").toLowerCase());
    bar.append(segment);
  }
}
function render(index) {
  current=index;
  const e=records[index];
  const receipt=evaluateEpisode(e);
  const isHeld=receipt.safety_holds>0;
  for(const [i,btn] of [...byId("episode-list").querySelectorAll("button")].entries()) {
    btn.setAttribute("aria-pressed",String(i===index));
    btn.classList.toggle("selected",i===index);
  }
  text("status-badge",isHeld?"HOLD RECORDED":"CLEAN REPLAY");
  byId("status-badge").classList.toggle("caution",isHeld);
  text("frame-count",receipt.observed_frames+" FRAMES");
  text("time-range","0 — "+receipt.duration_ms+" MS");
  text("verdict-heading",receipt.synthetic_training_candidate?"Ready for offline review":isHeld?"Interrupted, safely held":"Needs another demonstration");
  text("verdict-description",receipt.synthetic_training_candidate?
    "The synthetic replay reached its calibrated target without a safety hold. Candidate for offline evaluation only.":
    "The controller withheld action proposals until two fresh frames and an explicit re-arm. This recording is excluded from the synthetic training candidate set.");
  text("stat-holds",receipt.safety_holds);
  text("stat-accepted",receipt.accepted_proposals+"/"+receipt.observed_frames);
  text("stat-duration",receipt.duration_ms+" ms");
  text("stat-delta",(receipt.reference_delta_percent>0?"+":"")+receipt.reference_delta_percent+"%");
  text("stat-speed",receipt.max_speed_mps+" m/s");
  text("stat-error",receipt.target_error_m===null?"not measured":receipt.target_error_m+" m");
  const events=byId("event-list");
  events.replaceChildren();
  if(receipt.events.length===0) {
    const li=document.createElement("li");
    li.textContent="No safety holds in this synthetic trace.";
    events.append(li);
  } else {
    for(const event of receipt.events) {
      const li=document.createElement("li");
      const strong=document.createElement("strong");
      strong.textContent=event.at_ms+" ms · "+event.code.replaceAll("_"," ");
      li.append(strong,document.createTextNode(" — "+(event.reasons.join(", ")||"explicit operator acknowledgement")));
      events.append(li);
    }
  }
  draw(e,receipt);
  renderTimeline(receipt);
}
async function boot() {
  try {
    const res=await fetch("../fixtures/episodes.json",{cache:"no-store"});
    if(!res.ok) throw new Error("fixture response "+res.status);
    const packet=await res.json();
    if(!Array.isArray(packet.episodes) || packet.episodes.length!==2) throw new Error("expected two fixtures");
    records=packet.episodes;
    const list=byId("episode-list");
    records.forEach((e,i)=>{
      evaluateEpisode(e);
      const btn=document.createElement("button");
      btn.type="button";
      btn.className="episode-button";
      btn.setAttribute("aria-pressed","false");
      const number=document.createElement("span");
      number.className="episode-number";
      number.textContent="0"+(i+1);
      const content=document.createElement("span");
      const title=document.createElement("strong");
      title.textContent=i===0?"Fragile pick / clean":"Dropout / operator recovery";
      const subtitle=document.createElement("small");
      subtitle.textContent=i===0?"7 frames · no interruption":"7 frames · explicit safety hold";
      content.append(title,subtitle);
      btn.append(number,content);
      btn.addEventListener("click",()=>render(i));
      list.append(btn);
    });
    byId("export-button").addEventListener("click",()=>{
      const episode=records[current];
      const payload={receipt:evaluateEpisode(episode),source:episode,notice:"SYNTHETIC / NON-ACTUATING / UNVERIFIED REAL PROVIDER"};
      const blob=new Blob([JSON.stringify(payload,null,2)],{type:"application/json"});
      const url=URL.createObjectURL(blob);
      const a=document.createElement("a");
      a.href=url;
      a.download="motionbridge-"+episode.id+"-receipt.json";
      a.click();
      setTimeout(()=>URL.revokeObjectURL(url),1000);
    });
    render(0);
  } catch(err) {
    text("status-badge","DATA UNAVAILABLE");
    text("verdict-heading","Replay safely blocked");
    text("verdict-description",String(err.message||err));
    byId("export-button").disabled=true;
  }
}
boot();
