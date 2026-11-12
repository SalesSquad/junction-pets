import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {Script} from 'node:vm';

// Inline the existing private dashboard for an owner-only Space Page. The
// generated artifact is a static, timestamped snapshot, never a live Cloud
// provider read or a public deployment.
const root=fileURLToPath(new URL('../',import.meta.url));
const source=resolve(root,'apps/mission-control');
const output=resolve(root,'dist/mission-control/page-embed.html');
const [shell,style,model,projection,app,statusText]=await Promise.all([
  readFile(resolve(source,'index.html'),'utf8'),
  readFile(resolve(source,'style.css'),'utf8'),
  readFile(resolve(source,'status-model.mjs'),'utf8'),
  readFile(resolve(source,'server-projection.mjs'),'utf8'),
  readFile(resolve(source,'app.js'),'utf8'),
  readFile(resolve(root,'dist/mission-control/status.json'),'utf8')
]);
const status=JSON.parse(statusText);
if(status.schemaVersion!==1||status.pets?.length!==34||status.summary?.total!==34){
  throw new Error('Owner Page embed requires the validated 34-pet source snapshot');
}
const importPattern=/^import\s*\{[\s\S]*?\}\s*from\s*['"]\.\/status-model\.mjs['"];\s*/;
const projectionImportPattern=/^import\s*\{[^\n]+\}\s*from\s*['"]\.\/server-projection\.mjs['"];\s*/m;
const modelImportPattern=/^import\s*\{sourceCommit\}\s*from\s*['"]\.\/status-model\.mjs['"];\s*/m;
const fetchPattern=/const response = await fetch\('\.\/status\.json', \{cache: 'no-store', headers: \{'Accept': 'application\/json'\}\}\);\s*if \(!response\.ok\) throw new Error\(`Registry request returned HTTP \$\{response\.status\}`\);\s*const payload = await response\.json\(\);/;
if(!importPattern.test(app)||!projectionImportPattern.test(app)||
   !modelImportPattern.test(projection)||!fetchPattern.test(app)||
   !app.includes('await readOptionalServerProjection();')){
  throw new Error('Dashboard source contract changed; review embed generator');
}
const inlineApp=app.replace(importPattern,'').replace(projectionImportPattern,'')
  .replace(fetchPattern,
    "const payload = JSON.parse(document.getElementById('junction-status-data').textContent);")
  .replace('await readOptionalServerProjection();',
    "put('projection-status','Embedded owner snapshot · no authenticated backend feed');");
const inlineModel=model.replace(/^export\s+/gm,'');
const inlineProjection=projection.replace(modelImportPattern,'').replace(/^export\s+/gm,'');
// The projection module declares SHA/SLUG locally, which deliberately do not
// shadow the source model's same-named constants in this self-contained Page.
const wrappedProjection='const {advisoryCloudLabel,advisoryEvidenceLabel,normalizeServerProjection}='+
  '(()=>{\n'+inlineProjection+'\nreturn {advisoryCloudLabel,advisoryEvidenceLabel,normalizeServerProjection};\n})();';
new Script(inlineModel+'\n'+wrappedProjection+'\n'+inlineApp,
  {filename:'mission-control-page-embed.js'});
const safeJson=JSON.stringify(status).replace(/</g,'\\u003c').replace(/>/g,'\\u003e');
if([style,inlineModel,wrappedProjection,inlineApp].some(value=>/<\/(script|style)>/i.test(value))){
  throw new Error('Inline asset contains a closing HTML script/style tag');
}
let html=shell.replace(/<meta http-equiv="Content-Security-Policy"[^>]*>/,
  `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">`);
html=html.replace('<link rel="stylesheet" href="./style.css">',`<style>${style}</style>`);
html=html.replace('<script type="module" src="./app.js"></script>',
  `<script type="application/json" id="junction-status-data">${safeJson}</script>\n<script type="module">${inlineModel}\n${wrappedProjection}\n${inlineApp}</script>`);
// Page embeds have no status feed: the button re-reads the same embedded JSON.
html=html.replace('aria-label="Reload status snapshot">↻ <span>Refresh</span>',
  'aria-label="Re-read embedded snapshot (not live)">↻ <span>Re-read snapshot</span>');
// A relative dev-server link would be broken inside the Space Page sandbox.
html=html.replace('href="../collaboration-demo/index.html"',
  'href="https://github.com/SalesSquad/junction-pets/tree/codex/junction-pets-orchestration-20261112/apps/collaboration-demo"');
if(/(?:src|href)="\.\//.test(html))throw new Error('Unexpected relative asset remained in self-contained Page embed');
if(Buffer.byteLength(html,'utf8')>256*1024)throw new Error('Owner Page embed exceeds 256 KiB limit');
await mkdir(resolve(root,'dist/mission-control'),{recursive:true});
await writeFile(output,html,'utf8');
console.log(JSON.stringify({output,bytes:Buffer.byteLength(html),pets:status.pets.length,
  generatedAt:status.generatedAt,source:status.source,privateSnapshot:true}));
