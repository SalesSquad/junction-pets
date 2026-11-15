import {readFile,writeFile} from 'node:fs/promises';
import {plan,runBatch,replayBatch} from './cell.mjs';
const [mode,arg,seed]=process.argv.slice(2);
try {
  if(mode==='demo'){
    const result=await runBatch(plan(seed===undefined?330:Number(seed)));
    if(arg)await writeFile(arg,JSON.stringify(result,null,2)+'\n',{flag:'wx'});
    console.log(JSON.stringify(arg?{file:arg,source:result.provenance.sourceMain,root:result.root,evaluation:result.evaluation}:result,null,2));
  }else if(mode==='verify' && arg){
    const data=await readFile(arg,'utf8');if(Buffer.byteLength(data)>2_000_000)throw Error('Receipt exceeds 2 MB');
    const result=await replayBatch(JSON.parse(data));console.log(`Verified SYNTHETIC batch ${result.root}; no real action authorization`);
  }else throw Error('Usage: node solutions/intel-physical-ai/batch/cli.mjs demo [NEW_FILE] [SEED] | verify FILE');
}catch(error){console.error(error.message);process.exitCode=1;}
