// DOM contract harness; this is not a browser rendering/accessibility qualification.
import test from 'node:test';
import assert from 'node:assert/strict';
import {benchmark} from '../benchmark.mjs';
class Element {
 constructor(tag,text=''){this.tagName=tag;this.children=[];this.attributes={};this._text=text;this._value='';}
 set textContent(value){this._text=String(value);this.children=[];}get textContent(){return this._text+this.children.map(n=>n.textContent||'').join('');}
 append(...children){this.children.push(...children);}replaceChildren(...children){this._text='';this.children=[...children];}
 setAttribute(k,v){this.attributes[k]=v;}get value(){return this._value||this.children.find(n=>n.tagName==='option')?.value||'';}set value(v){this._value=v;}
 click(){this.onclick?.();}
}
const descendants=node=>[node,...node.children.flatMap(descendants)];
test('analyst journey: choose scenario, inspect evidence, ablate, review, reset and export',async t=>{
 const ids=['scenario','sort','scenario-description','event-count','group-count','review-count','findings','detail','notice','export','benchmark','refresh'];const nodes=Object.fromEntries(ids.map(id=>[id,new Element('div')]));nodes.sort.value='score';const store=new Map();let exported;
 const data=await benchmark();const originals=Object.fromEntries(['document','localStorage','fetch'].map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]));const oldCreate=URL.createObjectURL,oldRevoke=URL.revokeObjectURL;
 t.after(()=>{for(const [k,v]of Object.entries(originals)){if(v===undefined)delete globalThis[k];else Object.defineProperty(globalThis,k,v);}URL.createObjectURL=oldCreate;URL.revokeObjectURL=oldRevoke;});
 globalThis.document={getElementById:id=>nodes[id],createElement:tag=>new Element(tag),createTextNode:text=>new Element('#text',text)};globalThis.localStorage={getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v)};globalThis.fetch=async()=>({ok:true,json:async()=>data});URL.createObjectURL=blob=>{exported=blob;return 'blob:synthetic-test';};URL.revokeObjectURL=()=>{};
 await import('../public/app.mjs');await new Promise(resolve=>setImmediate(resolve));assert.equal(nodes['event-count'].textContent,'8');assert.ok(nodes.detail.textContent.includes('Possible coordinated campaign'));assert.ok(nodes.benchmark.textContent.includes('80.0%'));
 let checkbox=descendants(nodes.detail).find(n=>n.tagName==='input');checkbox.checked=true;checkbox.onchange();assert.ok(nodes.detail.textContent.includes('75/100'));
 let select=descendants(nodes.detail).find(n=>n.tagName==='select');select.value='Likely benign';select.onchange();assert.ok(store.get('radar-reviews-v1').includes('Likely benign'));assert.ok(nodes.findings.textContent.includes('Likely benign'));
 nodes.export.click();const report=JSON.parse(await exported.text());assert.equal(report.synthetic,true);assert.equal(report.hostinger,'NOT VERIFIED');assert.equal(report.dispositions['launch-1'],'Likely benign');assert.equal(report.findings[0].score,100);
 descendants(nodes.detail).find(n=>n.tagName==='button'&&n.textContent==='Reset this review').click();assert.equal(JSON.parse(store.get('radar-reviews-v1'))['swarm:launch-1'],undefined);
 nodes.scenario.value='mixed';nodes.scenario.onchange();assert.equal(nodes['group-count'].textContent,'3');assert.equal(nodes['review-count'].textContent,'1');nodes.sort.value='time';nodes.sort.onchange();nodes.findings.children[1].click();assert.ok(nodes.detail.textContent.includes('Attributed syndication'));
 nodes.scenario.value='sparse';nodes.scenario.onchange();assert.ok(nodes.detail.textContent.includes('Insufficient evidence'));
 globalThis.localStorage.setItem=()=>{throw new Error('storage disabled');};select=descendants(nodes.detail).find(n=>n.tagName==='select');select.value='Needs investigation';select.onchange();assert.ok(nodes.notice.textContent.includes('only for this session'));
});
