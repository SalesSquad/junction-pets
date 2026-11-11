import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const root=fileURLToPath(new URL('../',import.meta.url));
const lock=JSON.parse(await readFile(resolve(root,'package-lock.json'),'utf8'));
// Audited browser dependency closure: qrcode's browser entry uses dijkstrajs,
// while its Node-only pngjs/yargs dependencies and test/build tools are not shipped.
// Review this list when changing the browser imports or dependency lock.
const packages=[
  ['react','LICENSE'],
  ['react-dom','LICENSE'],
  ['scheduler','LICENSE'],
  ['qrcode','license'],
  ['dijkstrajs','LICENSE.md'],
];
const blocks=[Buffer.from('Third-party notices for the Junction browser bundle\n\nGenerated from the installed versions pinned by package-lock.json.\nDo not edit this generated file; run the catalogue build to regenerate it.\n')];
const included=[];
for(const [name,licenseFile] of packages){
  const dir=resolve(root,'node_modules',name);
  const pkg=JSON.parse(await readFile(resolve(dir,'package.json'),'utf8'));
  if(pkg.name!==name||pkg.version!==lock.packages['node_modules/'+name]?.version||pkg.license!=='MIT')throw new Error('Review changed browser dependency license: '+name);
  const license=await readFile(resolve(dir,licenseFile));
  if(!license.toString('utf8').trim())throw new Error('Missing browser dependency license: '+name);
  // Keep every upstream license byte, including copyright and permission notices.
  blocks.push(Buffer.from('\n============================================================\n'+name+' '+pkg.version+'\nLicense: '+pkg.license+'\nSource: '+name+'/'+licenseFile+'\n\n'),license,Buffer.from('\n'));
  included.push({name,version:pkg.version,license:pkg.license});
}
const out=resolve(root,'apps/catalog/public');
await mkdir(out,{recursive:true});
await writeFile(resolve(out,'THIRD_PARTY_NOTICES.txt'),Buffer.concat(blocks));
console.log(JSON.stringify({notice:'THIRD_PARTY_NOTICES.txt',packages:included}));
