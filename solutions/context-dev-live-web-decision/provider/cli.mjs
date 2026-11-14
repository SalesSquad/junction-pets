import { replay } from './replay.mjs';
const scenario=process.argv[2]??'before';
if(!['before','after','cosmetic'].includes(scenario))throw Error('Use before, after or cosmetic');
console.log(JSON.stringify(await replay(scenario),null,2));
