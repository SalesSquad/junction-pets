import {mkdir,writeFile,readFile,copyFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
import {loadPackages,collectionDigest,packageDigest} from '../lib/catalog.mjs';
import {loadSpecialCapabilities,specialCapabilitiesFor} from '../lib/special-capabilities.mjs';
const root=fileURLToPath(new URL('../',import.meta.url)),packs=await loadPackages(root),special=await loadSpecialCapabilities(root);
const out=resolve(root,'apps/catalog/public');await mkdir(out,{recursive:true});
const revision=execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim();
const catalog={schemaVersion:1,collection:{id:'junction-2026',title:'Junction companions',sourceRevision:revision,contentSha256:collectionDigest(packs)},pets:packs.map(p=>({...p.pet,specialCapabilities:specialCapabilitiesFor(special,p.pet.company.slug),packageSha256:packageDigest(p)}))};
await writeFile(resolve(out,'catalog.json'),JSON.stringify(catalog,null,2)+'\n');
await copyFile(resolve(root,'config/host-config.json'),resolve(out,'host-config.json'));
for(const pack of packs){const dir=resolve(out,'packages',pack.pet.company.slug);await mkdir(dir,{recursive:true});await Promise.all([writeFile(resolve(dir,'profile.json'),JSON.stringify(pack.pet,null,2)+'\n'),writeFile(resolve(dir,'AGENTS.md'),pack.instructions),writeFile(resolve(dir,'STORY.md'),pack.story)]);}
console.log(JSON.stringify({packages:packs.length,sourceRevision:revision,contentSha256:catalog.collection.contentSha256}));
