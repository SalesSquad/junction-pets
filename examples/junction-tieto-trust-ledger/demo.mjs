import {readFileSync} from 'node:fs';
import {evaluateLedger} from './ledger.mjs';

const fixture = JSON.parse(readFileSync(new URL('./fixture.json', import.meta.url), 'utf8'));
const result = evaluateLedger(fixture);
console.log(JSON.stringify(result, null, 2));
