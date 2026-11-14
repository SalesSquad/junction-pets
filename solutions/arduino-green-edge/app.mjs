import { evaluate, initialState, synthetic, createLedger, account } from './core.mjs';
const $ = id => document.getElementById(id);
let state, ledger, now, last, trail;
function reset() {
  state = initialState(); ledger = createLedger(); now = 1794650400000; last = null; trail = [];
  for (const id of ['disconnect', 'stale', 'malformed', 'network', 'consent', 'override']) $(id).checked = false;
  $('decision').textContent = 'HOLD'; $('reason').textContent = 'Waiting for your first sample.';
  $('fan').textContent = 'Fan / no action'; $('light').textContent = 'Light / no action';
  $('network-state').textContent = 'Network unused · sensor unverified'; render();
}
function render() {
  $('clock').textContent = new Date(now).toISOString().slice(11, 19) + ' replay UTC';
  const preview = synthetic(now, $('scenario').value);
  $('readings').replaceChildren(...[['Temperature', `${preview.temperature} °C`], ['Humidity', `${preview.humidity} %`], ['Occupancy', `${preview.occupancy} simulated`], ['Ambient light', `${preview.lux} lx`]].map(([label, value]) => { const el = document.createElement('div'); const small = document.createElement('small'); small.textContent = label; const strong = document.createElement('strong'); strong.textContent = value; el.append(small, strong); return el; }));
  for (const [id, key] of [['baseline', 'estimatedBaselineKWh'], ['scenario-energy', 'estimatedScenarioKWh'], ['avoided', 'estimatedAvoidedKWh']]) $(id).textContent = ledger[key].toFixed(6) + ' kWh';
  $('trail').replaceChildren(...trail.map(text => { const li = document.createElement('li'); li.textContent = text; return li; }));
}
function step(watchdog = false) {
  now += watchdog ? 45000 : 10000;
  let sample = watchdog ? last : synthetic(now, $('scenario').value);
  if (!watchdog) {
    sample.connected = !$('disconnect').checked;
    if ($('stale').checked) sample.at -= 40000;
    if ($('malformed').checked) sample.temperature = 'invalid';
    last = sample;
  }
  const result = evaluate(sample, state, { now, optIn: $('consent').checked, override: $('override').checked ? 'off' : 'auto' });
  state = result.state;
  // Overrides are explicit user actions, but still require opt-in for energy simulation.
  if (result.action && $('consent').checked) ledger = account(ledger, { start: now, end: now + 10000, baselineWatts: 60, scenarioWatts: (result.action.fan ? 40 : 0) + (result.action.light ? 20 : 0) });
  $('decision').textContent = result.decision;
  $('reason').textContent = result.reason;
  for (const output of ['fan', 'light']) $(output).textContent = `${output === 'fan' ? 'Fan' : 'Light'} / ${result.action ? (result.action[output] ? 'simulated ON' : 'simulated OFF') : 'no action issued'}`;
  $('network-state').textContent = `${$('network').checked ? 'Network outage' : 'Network unused'} · measurement age ${sample ? (now - sample.at) / 1000 + 's' : 'unknown'} · no physical connection`;
  trail.unshift(`${new Date(now).toISOString()} · ${result.decision} · ${result.inputDigest} · ${result.reason}`);
  trail = trail.slice(0, 8); render();
}
$('step').addEventListener('click', () => step());
$('watchdog').addEventListener('click', () => step(true));
$('reset').addEventListener('click', reset);
$('scenario').addEventListener('change', render);
// Revocation takes effect immediately through a fresh control evaluation; no background actuator.
for (const id of ['consent', 'override', 'disconnect']) $(id).addEventListener('change', () => step());
reset();
