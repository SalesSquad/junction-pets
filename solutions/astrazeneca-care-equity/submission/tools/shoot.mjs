// Section screenshots of the SAMA page through the Chrome DevTools Protocol. One headless Chrome, closed at the end.
// Usage: node shoot.mjs <baseUrl> <outDir> <textDir> [widths comma list]
import {spawn} from 'node:child_process';
import {writeFile, mkdir, rm} from 'node:fs/promises';
import path from 'node:path';

const [base, outDir, textDir, widthArg] = process.argv.slice(2);
const widths = (widthArg || '1440,390').split(',').map(Number);
const port = 9347;
const profile = path.join(textDir, 'chrome-profile');
await mkdir(outDir, {recursive: true}); await mkdir(textDir, {recursive: true});
const chrome = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
  '--headless=new', `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, '--no-first-run',
  '--no-default-browser-check', '--disable-extensions', '--disable-background-networking', '--disable-sync',
  '--hide-scrollbars', '--force-color-profile=srgb', 'about:blank'], {stdio: 'ignore'});
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let target;
for (let i = 0; i < 60 && !target; i++) {
  try { const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json(); target = list.find((t) => t.type === 'page'); } catch {}
  if (!target) await sleep(250);
}
if (!target) { chrome.kill(); throw new Error('chrome did not start'); }
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
let seq = 0; const waiting = new Map(); const events = []; const consoleLog = [];
ws.onmessage = (m) => {
  const msg = JSON.parse(m.data);
  if (msg.id && waiting.has(msg.id)) { const w = waiting.get(msg.id); waiting.delete(msg.id); msg.error ? w.j(new Error(JSON.stringify(msg.error))) : w.r(msg.result); return; }
  if (msg.method === 'Runtime.exceptionThrown') consoleLog.push({kind: 'exception', text: msg.params.exceptionDetails?.exception?.description || msg.params.exceptionDetails?.text});
  if (msg.method === 'Runtime.consoleAPICalled' && ['error', 'warning'].includes(msg.params.type)) consoleLog.push({kind: msg.params.type, text: msg.params.args.map((a) => a.value ?? a.description).join(' ')});
  if (msg.method === 'Log.entryAdded' && ['error', 'warning'].includes(msg.params.entry.level)) consoleLog.push({kind: 'log-' + msg.params.entry.level, text: msg.params.entry.text, url: msg.params.entry.url});
  events.push(msg.method);
};
const send = (method, params = {}) => new Promise((r, j) => { const id = ++seq; waiting.set(id, {r, j}); ws.send(JSON.stringify({id, method, params})); });
const evaluate = async (expr) => { const res = await send('Runtime.evaluate', {expression: expr, awaitPromise: true, returnByValue: true}); if (res.exceptionDetails) throw new Error(res.exceptionDetails.exception?.description || 'eval failed'); return res.result.value; };
await send('Page.enable'); await send('Runtime.enable'); await send('Log.enable');

async function load(url, readyExpr) {
  await send('Page.navigate', {url});
  for (let i = 0; i < 80; i++) { await sleep(250); try { if (await evaluate(readyExpr)) break; } catch {} }
  await sleep(1200);
}

const sections = [
  ['01-hero', 'body > header, body > nav'],
  ['01b-start-here-decision', '#decision'],
  ['02-gap-map', '#gap'],
  ['03-who-how-where', '#who'],
  ['04-county-pathway', '#county'],
  ['05-goal3', '#goal'],
  ['06-action-county-first', '#action > .section-head, #action > p, #process-headline, #first-action'],
  ['07-pilot-satakunta', '#pilot'],
  ['08-safetynet', '#safety-net'],
  ['09-flare-gate', '#comparability-gate'],
  ['10-insight', '#insight'],
  ['11-planner-nemotron', '#plan'],
  ['12-brief', '#brief'],
  ['13-collect', '#collect'],
  ['14-gemma-demo-stored', '.scribe-try'],
  ['15-scribe-results', '#scribe-content'],
  ['16-evidence', '#evidence'],
];
const report = {base, widths: {}, console: consoleLog};
for (const width of widths) {
  const mobile = width < 600, height = mobile ? 844 : 900, dsf = mobile ? 2 : 1;
  await send('Emulation.setDeviceMetricsOverride', {width, height, deviceScaleFactor: dsf, mobile});
  await load(base + '/', `!!document.querySelector('#planner-content') && !/Loading/.test(document.querySelector('#planner-content').textContent) && !document.querySelector('#loading:not([hidden])') && document.querySelector('#demo-content').textContent.length>20`);
  const w = report.widths[width] = {sections: {}};
  w.overflow = await evaluate(`(()=>{const vw=document.documentElement.clientWidth;const out=[];for(const el of document.querySelectorAll('body *')){const r=el.getBoundingClientRect();if(r.width>0&&r.right>vw+1){let p=el.parentElement,clipped=false;while(p&&p!==document.body){const s=getComputedStyle(p);if(/auto|scroll|hidden|clip/.test(s.overflowX)){clipped=true;break;}p=p.parentElement;}if(!clipped)out.push({tag:el.tagName,id:el.id,cls:el.className&&el.className.baseVal!==undefined?el.className.baseVal:el.className,right:Math.round(r.right),text:(el.textContent||'').trim().slice(0,60)});}}return {scrollWidth:document.documentElement.scrollWidth,vw,count:out.length,first:out.slice(0,25)};})()`);
  w.scrollers = await evaluate(`[...document.querySelectorAll('body *')].filter(e=>{const s=getComputedStyle(e);return /auto|scroll/.test(s.overflowX)&&e.scrollWidth>e.clientWidth+1}).map(e=>({tag:e.tagName,id:e.id,cls:String(e.className),sw:e.scrollWidth,cw:e.clientWidth}))`);
  w.loading = await evaluate(`document.querySelector('#loading')?.outerHTML||null`);
  w.hiddenMounts = await evaluate(`[...document.querySelectorAll('.mount-point')].map(e=>({id:e.id,hidden:e.hidden,len:e.textContent.length}))`);
  for (const [name, sel] of sections) {
    const box = await evaluate(`(()=>{const els=[...document.querySelectorAll(${JSON.stringify(sel)})].filter(e=>!e.hidden&&e.getBoundingClientRect().height>0);if(!els.length)return null;let t=1e9,b=-1e9;for(const e of els){const r=e.getBoundingClientRect();t=Math.min(t,r.top+scrollY);b=Math.max(b,r.bottom+scrollY);}return {top:t,bottom:b,text:els.map(e=>e.innerText).join('\\n\\n')};})()`);
    if (!box) { w.sections[name] = {missing: true, sel}; continue; }
    const pad = 12, y = Math.max(0, box.top - pad), h = Math.min(box.bottom - box.top + 2 * pad, 16000);
    const shot = await send('Page.captureScreenshot', {format: 'png', captureBeyondViewport: true, clip: {x: 0, y, width, height: h, scale: 1}});
    const file = path.join(outDir, `${name}-${width}.png`);
    await writeFile(file, Buffer.from(shot.data, 'base64'));
    await writeFile(path.join(textDir, `${name}-${width}.txt`), box.text);
    w.sections[name] = {file, cssHeight: Math.round(h)};
  }
  // research appendix
  await load(base + '/research.html', `!!document.querySelector('#variant-content') && !/Loading/.test(document.querySelector('#variant-content').textContent)`);
  const rh = await evaluate(`document.documentElement.scrollHeight`);
  const shot = await send('Page.captureScreenshot', {format: 'png', captureBeyondViewport: true, clip: {x: 0, y: 0, width, height: Math.min(rh, 16000), scale: 1}});
  const file = path.join(outDir, `17-research-appendix-${width}.png`);
  await writeFile(file, Buffer.from(shot.data, 'base64'));
  await writeFile(path.join(textDir, `17-research-appendix-${width}.txt`), await evaluate('document.body.innerText'));
  w.sections['17-research-appendix'] = {file, cssHeight: rh, overflow: await evaluate(`({sw:document.documentElement.scrollWidth,vw:document.documentElement.clientWidth})`)};
}
await writeFile(path.join(textDir, 'report.json'), JSON.stringify(report, null, 1));
ws.close(); chrome.kill('SIGTERM'); await sleep(800);
await rm(profile, {recursive: true, force: true}).catch(() => {});
console.log(JSON.stringify({ok: true, console: consoleLog.length}));
