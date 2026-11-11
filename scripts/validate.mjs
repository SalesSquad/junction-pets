import {fileURLToPath} from 'node:url';
import {loadPackages,collectionDigest} from '../lib/catalog.mjs';
const root=fileURLToPath(new URL('../',import.meta.url));
const packs=await loadPackages(root);
console.log(JSON.stringify({packages:packs.length,evaluationCases:packs.reduce((n,p)=>n+p.evals.cases.length,0),contentSha256:collectionDigest(packs),status:'content-validated',runtime:'not-exercised'},null,2));
