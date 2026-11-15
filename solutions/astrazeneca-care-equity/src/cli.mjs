import { readFileSync } from 'node:fs';
import { assess, exportProposal } from './engine.mjs';
const data = JSON.parse(readFileSync(new URL('../fixtures/regions.json', import.meta.url), 'utf8'));
const [focusId = 'fictional-coastal', peerId = 'fictional-inland', indicatorId = 'timely_referrals'] = process.argv.slice(2);
const result = await assess(data, { focusId, peerId, indicatorId });
process.stdout.write(JSON.stringify({ ...result, exported: exportProposal(result) }, null, 2) + '\n');
