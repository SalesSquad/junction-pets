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


await send('Emulation.setDeviceMetricsOverride', {width: 1440, height: 900, deviceScaleFactor: 1, mobile: false});
await load(base + '/', `document.querySelector('#demo-content').textContent.length>20`);
const report = {console: consoleLog, shots: []};
async function shotSel(name, sel){
  const box = await evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(sel)});const r=e.getBoundingClientRect();return {top:r.top+scrollY,bottom:r.bottom+scrollY,text:e.innerText};})()`);
  const y=Math.max(0,box.top-12), h=box.bottom-box.top+24;
  const shot = await send('Page.captureScreenshot', {format:'png', captureBeyondViewport:true, clip:{x:0,y,width:1440,height:h,scale:1}});
  await writeFile(path.join(outDir, name+'-1440.png'), Buffer.from(shot.data,'base64'));
  await writeFile(path.join(textDir, name+'-1440.txt'), box.text); report.shots.push(name);
}
for (const id of ['demo-04','demo-19','demo-20']) {
  await evaluate(`(async()=>{const s=document.querySelector('#demo-note');s.value='${id}';s.dispatchEvent(new Event('change'));})()`);
  for (let i=0;i<40;i++){await sleep(250); if(await evaluate(`document.querySelector('#demo-status').textContent.includes('shown')&&document.querySelector('#demo-content').textContent.includes('${id.toUpperCase()}')`))break;}
  await sleep(500); await shotSel(`14b-gemma-demo-${id}`, '.scribe-try');
}
await evaluate(`(()=>{const s=document.querySelector('#demo-note');s.value='demo-01';document.querySelector('#demo-live').click();})()`);
for (let i=0;i<40;i++){await sleep(250); if(await evaluate(`!document.querySelector('#demo-live').disabled && document.querySelector('#demo-content').textContent.includes('DEMO-01')`))break;}
await sleep(500); await shotSel('14c-gemma-demo-live-fallback', '.scribe-try');
await writeFile(path.join(textDir, 'report.json'), JSON.stringify(report, null, 1));
ws.close(); chrome.kill('SIGTERM'); await sleep(800);
await rm(profile, {recursive: true, force: true}).catch(() => {});
console.log(JSON.stringify({ok: true, console: consoleLog.length}));
