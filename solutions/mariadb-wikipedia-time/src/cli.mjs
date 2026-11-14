#!/usr/bin/env node
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {loadDataset,inspect} from './chronicle.mjs';
try{
  const argv=process.argv.slice(2),args={};
  if(argv.length%2)throw new Error('USAGE: --page ID --at UTC [--compare UTC] [--data FILE]');
  for(let i=0;i<argv.length;i+=2){
    if(!['--page','--at','--compare','--data'].includes(argv[i])||args[argv[i]])
      throw new Error('INVALID_ARGUMENT');
    args[argv[i]]=argv[i+1];
  }
  if(!args['--page']||!args['--at'])throw new Error('USAGE: --page ID --at UTC [--compare UTC]');
  const fixture=fileURLToPath(new URL('../fixtures/synthetic.json',import.meta.url));
  const source=JSON.parse(await readFile(args['--data']||fixture,'utf8'));
  const result=inspect(loadDataset(source),args['--page'],args['--at'],args['--compare']||null);
  process.stdout.write(JSON.stringify(result,null,2)+'\n');
}catch(e){
  process.stderr.write(JSON.stringify({status:'REFUSED',reason:e.message})+'\n');
  process.exitCode=2;
}
