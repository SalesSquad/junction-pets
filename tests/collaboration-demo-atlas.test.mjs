import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {webcrypto} from 'node:crypto';
import {runInNewContext} from 'node:vm';
import {fileURLToPath} from 'node:url';
import {loadPackages} from '../lib/catalog.mjs';
import {projectSolutionTeams} from '../lib/solution-team-projection.mjs';

class Element {
  constructor(tag='div'){
    this.tag=tag;
    this.children=[];
    this.dataset={};
    this.style={setProperty(){}};
    this.className='';
    this.classList={
      entries:new Set(),
      add(name){this.entries.add(name);},
      remove(name){this.entries.delete(name);},
      contains(name){return this.entries.has(name);},
    };
    this.disabled=false;
  }
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=children;}
  addEventListener(){}
  setAttribute(){}
  set textContent(value){this._text=value;this.children=[];}
  get textContent(){return this._text??'';}
}
const descendants=node=>[node,...node.children.flatMap(descendants)];

test('team avatars load when synthetic trace fails and a valid team projection exists',async()=>{
  const root=fileURLToPath(new URL('../',import.meta.url));
  const packages=await loadPackages(root);
  const manifest=JSON.parse(await readFile(new URL('../solutions/valio-trusted-trade/solution.json',import.meta.url),'utf8'));
  const projection=projectSolutionTeams(packages,[{directory:'valio-trusted-trade',manifest}]);
  const source=await readFile(new URL('../apps/collaboration-demo/app.js',import.meta.url),'utf8');
  assert.match(source,/\nsetup\(\);\s*$/);
  const nodes=new Map();
  const fetched=[];
  const requestedImages=[];
  const document={
    getElementById(id){if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);},
    createElement(tag){return new Element(tag);},
    querySelectorAll(){return [];}, // Atlas loads before team cards, so petAvatar paints them.
  };
  class Image {
    addEventListener(name,handler){if(name==='load')this.onLoad=handler;}
    set src(value){requestedImages.push(value);this.onLoad?.();}
  }
  const context={
    document,Image,crypto:webcrypto,TextEncoder,URL,
    window:{
      location:{href:'https://demo.invalid/?solution=valio-trusted-trade'},
      history:{pushState(){}},
      addEventListener(){},
    },
    fetch:async path=>{
      fetched.push(path);
      if(path==='./trace.json')throw new Error('Synthetic fixture unavailable');
      if(path==='./solution-teams.json')return {ok:true,json:async()=>projection};
      throw new Error('Unexpected request');
    },
    setTimeout,clearTimeout,setInterval,clearInterval,
  };
  const executable=source.replace(/setup\(\);\s*$/,'globalThis.__startup=setup();');
  runInNewContext(executable,context,{filename:'apps/collaboration-demo/app.js'});
  await context.__startup;
  assert.deepEqual(fetched,['./trace.json','./solution-teams.json']);
  assert.deepEqual(requestedImages,['./company-mascots.png']);
  assert.equal(nodes.get('solutionPicker').disabled,false);
  const logos=descendants(nodes.get('solutionTeam')).filter(node=>node.className==='pet-logo');
  assert.equal(logos.length,3);
  assert.deepEqual(logos.map(logo=>logo.dataset.artIndex),['1','29','8']);
  assert.ok(logos.every(logo=>logo.classList.contains('has-art')));
  assert.match(nodes.get('teamMeta').textContent,/Not a signed Chibi receipt/);
  assert.equal(nodes.get('play').disabled,true);
});
