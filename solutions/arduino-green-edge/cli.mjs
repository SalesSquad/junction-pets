import { evaluate, initialState, synthetic, createLedger, account } from './core.mjs';
const allowed = ['warm', 'daylight', 'empty', 'humid', 'dropout', 'stale', 'malformed', 'offline'];
const scenario = process.argv[2] ?? 'warm';
if (!allowed.includes(scenario)) { console.error(`Use: node cli.mjs ${allowed.join('|')} [--opt-in]`); process.exitCode = 1; }
else {
  let state = initialState(), ledger = createLedger();
  for (let i = 0; i < 4; i++) {
    const now = 1794650400000 + i * 10000;
    const sample = synthetic(now, ['dropout', 'stale', 'malformed', 'offline'].includes(scenario) ? 'warm' : scenario);
    if (i >= 2 && scenario === 'dropout') sample.connected = false;
    if (scenario === 'stale') sample.at -= 40000;
    if (scenario === 'malformed') sample.temperature = '28';
    const result = evaluate(sample, state, { now, optIn: process.argv.includes('--opt-in') });
    state = result.state;
    if (result.action) ledger = account(ledger, { start: now, end: now + 10000, baselineWatts: 60, scenarioWatts: (result.action.fan ? 40 : 0) + (result.action.light ? 20 : 0) });
    console.log(JSON.stringify(result));
  }
  console.log(JSON.stringify({ syntheticAssumptions: '40W fan + 20W light; baseline both on; no measured savings', ledger }));
}
