import {readFile, mkdir, writeFile} from 'node:fs/promises';
import {resolve, join, dirname, isAbsolute, relative} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';

const root = fileURLToPath(new URL('../../', import.meta.url));
const safe = value => typeof value === 'string' && value.length > 0 && !isAbsolute(value) && !value.split('/').some(part => !part || part === '.' || part === '..' || part.includes('\\'));
function replaceOnce(text, before, after) {
  if (text.split(before).length !== 2) throw new Error('Expected adaptation anchor is missing or ambiguous');
  return text.replace(before, after);
}
function adapt(kind, file, text) {
  if (kind === 'proofmatch' && file === 'index.html') return replaceOnce(text, 'Works without internet through the local Node server.', 'The demo uses fictional data in this browser.');
  if (kind === 'proofmatch' && file === 'app.mjs') return replaceOnce(text, 'Offline shell cached on this localhost origin. Proposals remain in memory only.', 'Offline shell cached in this browser. Proposals remain in memory only.');
  if (kind === 'spread' && file === 'index.html') {
    text = replaceOnce(text, '<div class="toolbar"><label', '<div class="toolbar"><button type="button" id="example">Use synthetic example</button><label');
    text = replaceOnce(text, 'Run <code>python3 optimizer.py demo --seed 11 --level 8 --output demo.json</code>, then load demo.json above. Change seed or level in the CLI to inspect another scenario. Load compare.json to review fixed and held-out runs.', 'Choose the synthetic example above, or load an offline audit JSON file to review another scenario.');
    return replaceOnce(text, "$('file').onchange=async()=>", "$('example').onclick=async()=>{try{const response=await fetch('./demo.json');if(!response.ok)throw Error('Example unavailable');audit=await response.json();render();$('download').disabled=false;$('error').textContent=''}catch(e){audit=null;$('download').disabled=true;$('ledger').replaceChildren();$('error').textContent=e.message}};\n$('file').onchange=async()=>");
  }
  if (kind === 'lumo' && file === 'web/index.html') {
    text = replaceOnce(text, 'href="/web/styles.css"', 'href="./styles.css"');
    return replaceOnce(text, 'src="/web/app.mjs"', 'src="./app.mjs"');
  }
  if (kind === 'meta' && file === 'observation-client.mjs') {
    for (const endpoint of ['config','demo-observation','observe']) text = replaceOnce(text, `'/api/${endpoint}'`, `'./api/${endpoint}'`);
    return text;
  }
  if (kind === 'meta' && file === 'index.html') {
    text = replaceOnce(text, 'href="./" class="brand"', 'href="./index.html" class="brand"');
    return replaceOnce(text, 'href="./guide/"', 'href="./guide/index.html"');
  }
  if (kind === 'meta' && file === 'guide/index.html') {
    if (text.split('href="../"').length !== 3 || text.split('href="./"').length !== 3) throw new Error('Expected guide navigation anchors are missing or ambiguous');
    return text.replaceAll('href="../"','href="../index.html"').replaceAll('href="./"','href="./index.html"');
  }
  if (kind === 'recovery' && file === 'web/index.html') {
    text = replaceOnce(text, 'href="/styles.css"', 'href="./styles.css"');
    text = replaceOnce(text, 'src="/app.mjs"', 'src="./app.mjs"');
    return replaceOnce(text, '<head>', `<head><meta http-equiv="Content-Security-Policy" content="default-src 'self'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">`);
  }
  if (kind === 'recovery' && file === 'web/app.mjs') {
    text = replaceOnce(text, "from '/src/compass.mjs'", "from '../src/compass.mjs'");
    return replaceOnce(text, "from '/src/vault.mjs'", "from '../src/vault.mjs'");
  }
  if (kind === 'traffic' && file === 'public/traffic/index.html') {
    text = replaceOnce(text, 'href="/traffic/style.css"', 'href="./style.css"');
    text = replaceOnce(text, 'src="/traffic/app.mjs"', 'src="./app.mjs"');
    text = replaceOnce(text, '<a href="/">◉ SIGNAL DESK</a>', '<span>◉ SIGNAL DESK</span>');
    return replaceOnce(text, '<head>', `<head><meta http-equiv="Content-Security-Policy" content="default-src 'self'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">`);
  }
  if (kind === 'intel-batch' && file === 'batch/studio/index.html') return replaceOnce(text, 'href="/" aria-label="Inspect / Action home"', 'href="./index.html" aria-label="Inspect / Action home"');
  if (kind === 'supplypulse' && file === 'index.html') {
    text = replaceOnce(text, 'href="/style.css"', 'href="./style.css"');
    text = replaceOnce(text, 'src="/app.mjs"', 'src="./app.mjs"');
    text = replaceOnce(text, 'href="/" class="brand"', 'href="./index.html" class="brand"');
    return replaceOnce(text, '<meta charset="utf-8">', `<meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'self'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">`);
  }
  if (kind === 'stoa' && file === 'public/index.html') {
    text = replaceOnce(text, 'href="/style.css"', 'href="./style.css"');
    text = replaceOnce(text, 'src="/app.js"', 'src="./app.js"');
    text = replaceOnce(text, 'inspect its original source region.', 'inspect its original source region. Drawings stay in this browser; the example is synthetic. This version supports exact room labels, validated room areas and unit outlines; other questions are refused.');
    return replaceOnce(text, '<head>', `<head><meta http-equiv="Content-Security-Policy" content="default-src 'self'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">`);
  }
  if (kind === 'stoa' && file === 'public/app.js') return `import {createStoaLocalApi} from '../adapter/stoa-local-api.mjs';\nconst fetch=createStoaLocalApi();\n${text}`;
  if (kind === 'stoa' && file === 'src/dxf.mjs') return replaceOnce(text, "Buffer.byteLength(input, 'utf8')", 'new TextEncoder().encode(input).byteLength');
  if (kind === 'chronicle' && file === 'studio/index.html') {
    text = replaceOnce(text, 'href="/style.css"', 'href="./style.css"');
    text = replaceOnce(text, 'src="/app.js"', 'src="./app.js"');
    text = replaceOnce(text, '<option value="real">Admitted local Wikipedia snapshot</option>', '');
    text = replaceOnce(text, 'Data never leaves this loopback app.', 'This synthetic demonstration runs in your browser. Live Wikipedia snapshots and MariaDB are not connected.');
    return replaceOnce(text, '<head>', `<head><meta http-equiv="Content-Security-Policy" content="default-src 'self'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">`);
  }
  if (kind === 'chronicle' && file === 'studio/app.js') return `import {createChronicleLocalApi} from '../adapter/chronicle-local-api.mjs';\nconst fetch=createChronicleLocalApi();\n${text}`;
  if (kind === 'chronicle' && file === 'src/chronicle.mjs') {
    text = replaceOnce(text, "import {createHash} from 'node:crypto';", "import {sha256} from '../adapter/fixture-hashes.mjs';");
    text = replaceOnce(text, "import {admitSnapshot} from './wikipedia.mjs';", "const admitSnapshot=()=>{throw new Error('REAL_SNAPSHOT_UNAVAILABLE_IN_BROWSER');};");
    return replaceOnce(text, "export const sha256 = s => createHash('sha256').update(s,'utf8').digest('hex');", 'export {sha256};');
  }
  if (kind === 'sama' && (file === 'web/index.html' || file === 'web/research.html')) {
    text = replaceOnce(text, 'href="/icon.svg"', 'href="./icon.svg"');
    text = replaceOnce(text, 'href="/styles.css"', 'href="./styles.css"');
    text = replaceOnce(text, file.endsWith('research.html')?'src="/research.mjs"':'src="/app.mjs"', file.endsWith('research.html')?'src="./research.mjs"':'src="./app.mjs"');
    text = text.replaceAll('href="/"','href="./index.html"');
    if(file.endsWith('/index.html')) {
      text = replaceOnce(text,'href="/research.html"','href="./research.html"');
      text = replaceOnce(text,'<main>','<main><p role="note"><strong>Research demonstration:</strong> patient notes are synthetic; the model outputs and public-data snapshot are saved examples. Live model calls and source verification are unavailable here. Do not enter patient information. Not for clinical decisions.</p>');
    }
    return replaceOnce(text,'<head>',`<head><meta http-equiv="Content-Security-Policy" content="default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'">`);
  }
  if (kind === 'sama' && (file === 'web/app.mjs' || file === 'web/research.mjs')) {
    text = text.replaceAll("fetch('/data/app.json'", "fetch('./data/app.json'").replaceAll("fetch('/data/counties.geo.json'", "fetch('./data/counties.geo.json'");
    if(file === 'web/app.mjs') {
      text = replaceOnce(text,"from '/src/decisions.mjs'","from '../src/decisions.mjs'");
      text = replaceOnce(text,"from '/src/claims.mjs'","from '../src/claims.mjs'");
      for(const data of ['planner/plans-v1.json','scribe/demo/demo-notes.json','scribe/demo/demo-outputs.json']) text=replaceOnce(text,`fetch('/data/${data}'`,`fetch('../data/${data}'`);
      for(const endpoint of ['scribe','scribe/second','verify-claims']) text=replaceOnce(text,`fetch('/api/${endpoint}'`,`unavailable('/api/${endpoint}'`);
      text=`import {unavailable} from '../adapter/unavailable.mjs';\n${text}`;
    }
    return text;
  }
  if (kind === 'roundlens' && file === 'public/index.html') {
    text = replaceOnce(text, 'href="/style.css"', 'href="./style.css"');
    text = replaceOnce(text, 'src="/app.mjs"', 'src="./app.mjs"');
    text = replaceOnce(text, 'href="/" aria-label="RoundLens home"', 'href="./index.html" aria-label="RoundLens home"');
    return replaceOnce(text, '<head>', `<head><meta http-equiv="Content-Security-Policy" content="default-src 'self'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">`);
  }
  if (kind === 'roundlens' && file === 'public/app.mjs') {
    text = replaceOnce(text, "from '/fixture.mjs'", "from '../fixture.mjs'");
    return replaceOnce(text, "from '/core.mjs'", "from '../core.mjs'");
  }
  if (kind === 'roundlens' && file === 'core.mjs') {
    text = replaceOnce(text, "import { PRODUCT_SOURCE_DIGEST }", "import { PRODUCT_SOURCE_DIGEST, EMBEDDED_CLIENT_DIGEST }");
    text = replaceOnce(text, "schema:'roundlens.shortlist.v1'", "schema:'roundlens.shortlist.embedded.v1'");
    return replaceOnce(text, 'productSourceDigest:PRODUCT_SOURCE_DIGEST', 'upstreamProductSourceDigest:PRODUCT_SOURCE_DIGEST, embeddedClientDigest:EMBEDDED_CLIENT_DIGEST');
  }
  return text;
}
export async function exportApps(output) {
  const target = resolve(output);
  const rel = relative(root, target);
  if (!rel || (!rel.startsWith('..') && !isAbsolute(rel))) throw new Error('Export must be outside the Junction source tree');
  const catalog = JSON.parse(await readFile(new URL('./catalog.json', import.meta.url), 'utf8'));
  if (catalog.schemaVersion !== 1 || !Array.isArray(catalog.apps)) throw new Error('Invalid app catalog');
  const directories = new Set();
  for (const app of catalog.apps) {
    if (!/^junction-[a-z0-9-]+$/.test(app.petSlug) || !app.name || !safe(app.solution) || (app.source !== undefined && !(typeof app.source === 'string' && /^(solutions|apps)\/[a-z0-9-]+$/.test(app.source))) || !safe(app.directory) || !safe(app.entry) || !Array.isArray(app.files) || !app.files.includes(app.entry) || app.files.some(file => !safe(file)) || directories.has(app.directory)) throw new Error('Invalid app entry');
    directories.add(app.directory);
  }
  // Refuse an existing output rather than removing anything the caller owns.
  await mkdir(target);
  const exported = [];
  for (const app of catalog.apps) {
    if (app.solution === 'valio-trusted-trade' && app.directory === 'aimo-trade') {
      const {verifyBrowserBuild} = await import('../../solutions/valio-trusted-trade/browser/verify.mjs');
      await verifyBrowserBuild();
    }
    for (const file of app.files) {
      const bytes = await readFile(join(root, app.source ?? join('solutions', app.solution), file));
      const dest = join(target, 'apps', app.directory, file);
      await mkdir(dirname(dest), {recursive:true});
      const data = app.adaptation && (file.endsWith('.html') || file.endsWith('.mjs') || file.endsWith('.js')) ? adapt(app.adaptation, file, bytes.toString('utf8')) : bytes;
      await writeFile(dest, data, {flag:'wx'});
    }
    if (app.adaptation === 'stoa') {
      const dest=join(target,'apps',app.directory,'adapter/stoa-local-api.mjs');
      await mkdir(dirname(dest),{recursive:true});
      await writeFile(dest,await readFile(new URL('./adapters/stoa-local-api.mjs',import.meta.url)),{flag:'wx'});
    }
    if (app.adaptation === 'chronicle') {
      const fixture=JSON.parse(await readFile(join(root,'solutions/mariadb-wikipedia-time/fixtures/synthetic.json'),'utf8'));
      if (fixture.provenance !== 'SYNTHETIC' || !Array.isArray(fixture.revisions)) throw new Error('Chronicle requires the synthetic fixture');
      const hashes=Object.fromEntries(fixture.revisions.map(revision=>[revision.body,createHash('sha256').update(revision.body,'utf8').digest('hex')]));
      const adapterDir=join(target,'apps',app.directory,'adapter');
      await mkdir(adapterDir,{recursive:true});
      await writeFile(join(adapterDir,'fixture.mjs'),`export default ${JSON.stringify(fixture)};\n`,{flag:'wx'});
      await writeFile(join(adapterDir,'fixture-hashes.mjs'),`const hashes=new Map(${JSON.stringify(Object.entries(hashes))});\nexport function sha256(value){if(!hashes.has(value))throw new Error('UNKNOWN_FIXTURE_BODY');return hashes.get(value);}\n`,{flag:'wx'});
      const server=await readFile(join(root,'solutions/mariadb-wikipedia-time/studio/server.mjs'),'utf8');
      const start='export function makeCatalog(dataset) {';
      const end='function json(res, status, body) {';
      if (server.split(start).length!==2 || server.split(end).length!==2 || server.indexOf(end)<server.indexOf(start)) throw new Error('Chronicle server functions changed');
      const functions=server.slice(server.indexOf(start),server.indexOf(end));
      const template=await readFile(new URL('./adapters/chronicle-local-api.mjs',import.meta.url),'utf8');
      await writeFile(join(adapterDir,'chronicle-local-api.mjs'),replaceOnce(template,'/* STUDIO_FUNCTIONS */',functions),{flag:'wx'});
    }
    if (app.adaptation === 'sama') {
      const dest=join(target,'apps',app.directory,'adapter/unavailable.mjs');
      await mkdir(dirname(dest),{recursive:true});
      await writeFile(dest,await readFile(new URL('./adapters/sama-unavailable.mjs',import.meta.url)),{flag:'wx'});
    }
    if (app.adaptation === 'valio-planner') {
      const base=join(target,'apps',app.directory);
      for(const file of ['procurement-planner.mjs','purchase-units.mjs']) {
        const dest=join(base,'src',file);
        await mkdir(dirname(dest),{recursive:true});
        await writeFile(dest,await readFile(join(root,'solutions/valio-trusted-trade/src',file)),{flag:'wx'});
      }
      const {FIXTURE_CATALOG}=await import(pathToFileURL(join(root,'solutions/valio-trusted-trade/src/core.mjs')).href);
      if(!Array.isArray(FIXTURE_CATALOG)||FIXTURE_CATALOG.some(item=>!String(item.sku).startsWith('DEMO-'))) throw new Error('Expected only the fictional Valio fixture');
      await writeFile(join(base,'valio-planner/fixture.mjs'),`export default ${JSON.stringify(FIXTURE_CATALOG)};\n`,{flag:'wx'});
    }
    if (app.adaptation === 'roundlens') {
      // The embedded client differs from the original local-server package. Its
      // exported artifact names both the original package digest and a digest
      // over exactly these adapted browser bytes, never the old digest as its own.
      const names=['core.mjs','fixture.mjs','public/app.mjs','public/index.html','public/style.css'];
      const entries=await Promise.all(names.map(async name=>`${name}\0${createHash('sha256').update(await readFile(join(target,'apps',app.directory,name))).digest('hex')}\n`));
      const digest=createHash('sha256').update(entries.join('')).digest('hex');
      const meta=join(target,'apps',app.directory,'source-meta.mjs');
      const original=await readFile(meta,'utf8');
      await writeFile(meta,`${original}\nexport const EMBEDDED_CLIENT_DIGEST = '${digest}';\n`);
    }
    // Verify the bytes actually copied, including their exported manifest.
    if (app.solution === 'valio-trusted-trade' && app.directory === 'aimo-trade') {
      const {verifyBrowserBuild} = await import('../../solutions/valio-trusted-trade/browser/verify.mjs');
      await verifyBrowserBuild({distRoot:join(target,'apps',app.directory,'browser/dist')});
    }
    exported.push({petSlug:app.petSlug,name:app.name,path:`/apps/${app.directory}/${app.entry}`,solution:app.solution});
  }
  const esc = text => String(text).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const items = exported.map(app => `<li><a href="${esc('.' + app.path)}">${esc(app.name)}</a> <small>${esc(app.petSlug)}</small></li>`).join('\n');
  await writeFile(join(target, 'index.html'), `<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Junction companion apps</title></head><body><main><h1>Junction companion apps</h1><p>Independent browser demonstrations with synthetic or fictional data. Not sponsor connections or production services.</p><ul>\n${items}\n</ul></main></body></html>\n`, {flag:'wx'});
  await writeFile(join(target, 'catalog.json'), JSON.stringify({schemaVersion:1,apps:exported}, null, 2) + '\n', {flag:'wx'});
  return exported;
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  if (process.argv.length !== 3) throw new Error('Usage: node apps/companion-browser-apps/export.mjs /new/output/directory');
  console.log(`Exported ${(await exportApps(process.argv[2])).length} companion apps to ${resolve(process.argv[2])}`);
}
