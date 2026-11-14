import {scenarios} from './fixtures.mjs';
import {decide,memo} from './engine.mjs';
const name=process.argv[2]??'after';
if(!Object.hasOwn(scenarios,name)){console.error('Use before, after, cosmetic or failed');process.exitCode=1;}else console.log(memo(await decide(JSON.stringify(scenarios[name]))));
