import {readFile,writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {capturePublic,compare} from './compare.mjs';

export async function importCaptures(paths,output) {
  if(paths.length!==2)throw Error('Provide exactly two Context.dev response envelope files.');
  const captures=[];
  for(const path of paths){
    const raw=await readFile(path);if(raw.length>1_048_576)throw Error('Response envelope too large.');
    const {body,...meta}=JSON.parse(raw);captures.push(capturePublic(body,meta));
  }
  const asOf=Math.max(...captures.map(c=>Date.parse(c.receivedAt)));
  const result=compare(captures,{now:asOf});
  if(result.errors.length)throw Error('Incomplete source capture.');
  await writeFile(output,JSON.stringify({schemaVersion:1,captures},null,2)+'\n',{flag:'wx'});
  return {status:result.status,winner:result.winner,offers:result.offers.map(o=>({id:o.id,priceCents:o.priceCents,memberPriceCents:o.memberPriceCents,requestId:o.requestId})),asOf:new Date(asOf).toISOString()};
}
if(process.argv[1]===fileURLToPath(import.meta.url)){
  try{const [first,second,output]=process.argv.slice(2);if(!output)throw Error('Usage: node live/import-capture.mjs first.json second.json new-output.json');console.log(JSON.stringify(await importCaptures([first,second],output),null,2));}
  catch{console.error('Capture import refused: check the two response envelopes, source identity and new output path.');process.exitCode=1;}
}
