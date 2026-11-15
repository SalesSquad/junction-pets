import {readFile, mkdir, writeFile} from 'node:fs/promises';
import {resolve, join, dirname, isAbsolute, relative} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';

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
  return text;
}
export async function exportApps(output) {
  const target = resolve(output);
  const rel = relative(root, target);
  if (!rel || (!rel.startsWith('..') && !isAbsolute(rel))) throw new Error('Export must be outside the Junction source tree');
  const catalog = JSON.parse(await readFile(new URL('./catalog.json', import.meta.url), 'utf8'));
  if (catalog.schemaVersion !== 1 || !Array.isArray(catalog.apps)) throw new Error('Invalid app catalog');
  const pets = new Set(), directories = new Set();
  for (const app of catalog.apps) {
    if (!/^junction-[a-z0-9-]+$/.test(app.petSlug) || !app.name || !safe(app.solution) || (app.source !== undefined && !(typeof app.source === 'string' && /^(solutions|apps)\/[a-z0-9-]+$/.test(app.source))) || !safe(app.directory) || !safe(app.entry) || !Array.isArray(app.files) || !app.files.includes(app.entry) || app.files.some(file => !safe(file)) || pets.has(app.petSlug) || directories.has(app.directory)) throw new Error('Invalid app entry');
    pets.add(app.petSlug); directories.add(app.directory);
  }
  // Refuse an existing output rather than removing anything the caller owns.
  await mkdir(target);
  const exported = [];
  for (const app of catalog.apps) {
    for (const file of app.files) {
      const bytes = await readFile(join(root, app.source ?? join('solutions', app.solution), file));
      const dest = join(target, 'apps', app.directory, file);
      await mkdir(dirname(dest), {recursive:true});
      const data = app.adaptation && file.endsWith('.html') || app.adaptation === 'proofmatch' && file === 'app.mjs' ? adapt(app.adaptation, file, bytes.toString('utf8')) : bytes;
      await writeFile(dest, data, {flag:'wx'});
    }
    exported.push({petSlug:app.petSlug,name:app.name,path:`/apps/${app.directory}/${app.entry}`,solution:app.solution});
  }
  await writeFile(join(target, 'catalog.json'), JSON.stringify({schemaVersion:1,apps:exported}, null, 2) + '\n', {flag:'wx'});
  return exported;
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  if (process.argv.length !== 3) throw new Error('Usage: node apps/companion-browser-apps/export.mjs /new/output/directory');
  console.log(`Exported ${(await exportApps(process.argv[2])).length} companion apps to ${resolve(process.argv[2])}`);
}
