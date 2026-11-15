// Dependency-free DOM smoke: hostile audit strings must remain text nodes.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class Element{constructor(){this.children=[];this.value='all';this.files=[]}append(e){this.children.push(e)}replaceChildren(){this.children=[]}click(){}}
const ids=Object.fromEntries(['ledger','stats','file','filter','download','error'].map(x=>[x,new Element()]));
const doc={getElementById:x=>ids[x],createElement:()=>new Element()};
const html=fs.readFileSync(__dirname+'/index.html','utf8');
assert(!/innerHTML|document.write|fetch\(|XMLHttpRequest|https?:\/\//.test(html));
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
const context=vm.createContext({document:doc,Blob,URL,setTimeout});vm.runInContext(script,context);
(async()=>{const evil='<img src=x onerror=alert(1)>';ids.file.files=[{size:100,text:async()=>JSON.stringify({mode:'SYNTHETIC_OFFLINE',rows:[{requestId:evil,decision:'ABSTAIN',reasons:[evil]}]})}];await ids.file.onchange();assert.equal(ids.ledger.children[0].children[1].textContent,evil+' · ABSTAIN');assert.equal(ids.download.disabled,false);ids.file.files=[{size:2000001}];await ids.file.onchange();assert.equal(ids.download.disabled,true);console.log('UI DOM smoke passed: inert hostile strings, offline only, oversized input rejected');})();
