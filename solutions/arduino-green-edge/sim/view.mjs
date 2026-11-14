import { simulate, stress } from './engine.mjs';

const byId = id => document.getElementById(`twin-${id}`);
const put = (id, value) => { byId(id).textContent = value; };
const kWh = ws => `${(ws / 3600000).toFixed(4)} kWh`;
const signed = ws => `${ws > 0 ? '+' : ''}${kWh(ws)}`;
const minutes = seconds => `${(seconds / 60).toFixed(1)} min`;
const clock = seconds => `${String(Math.floor(seconds / 3600)).padStart(2, '0')}:${String(Math.floor(seconds % 3600 / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
const reasonLabels = {
  NON_POSITIVE_NET: 'Device cost cancels or exceeds load savings.',
  SERVICE_DEGRADATION_VS_BASELINE: 'The edge misses required service that the schedule supplies.',
  EXCESSIVE_FALLBACK: 'More than 5% of the day relies on hypothetical fallback.',
};
let current;

function row(parent, values) {
  const tr = document.createElement('tr');
  values.forEach((value, i) => {
    const cell = document.createElement(i ? 'td' : 'th');
    if (!i) cell.scope = 'row';
    cell.textContent = value;
    tr.append(cell);
  });
  parent.append(tr);
}
function inspect() {
  if (!current?.trace) return;
  const entry = current.trace[Number(byId('slot').value)];
  put('time', clock(entry.second));
  put('diagnostic', JSON.stringify(entry, null, 2));
}
function showDay(day, shifted = false) {
  current = day;
  put('day-label', `${shifted ? 'First shifted case' : 'Single day'} · ${day.scenario} · seed ${day.seed} · arrival shift ${day.shiftHours} h · sensor bias ${day.sensorBias} °C`);
  put('baseline', kWh(day.baselineWs));
  put('edge', kWh(day.edgeLoadWs));
  put('device', `${kWh(day.deviceWs)} / ${day.overheadWatts} W all day`);
  put('gross', signed(day.grossWs));
  put('net', signed(day.netWs));
  put('break-even', `${day.breakEvenDeviceWatts.toFixed(3)} W`);
  const body = byId('services');
  body.replaceChildren();
  for (const [name, key] of [['Fan service', 'fanSeconds'], ['Light service', 'lightSeconds']]) {
    row(body, [name, minutes(day.service.required[key]), minutes(day.service.baselineUnmet[key]), minutes(day.service.edgeUnmet[key]), minutes(day.service.edgeOnlyUnmet[key])]);
  }
  put('coverage', `${(day.coverage.actionFraction * 100).toFixed(2)}% M1 action coverage. ${minutes(day.coverage.fallbackSeconds)} hypothetical fallback across ${day.coverage.fallbackEvents} episodes; ${day.coverage.faultSlots} dropout/stale slots.`);
  put('risk', day.recommendationReasons.map(reason => reasonLabels[reason]).join(' ') || 'Positive net, no additional missed service versus the schedule, and fallback within 5% in this model only.');
  const hours = byId('hours');
  hours.replaceChildren();
  day.hourly.forEach(h => row(hours, [
    `${String(h.hour).padStart(2, '0')}:00`, kWh(h.baselineWs), kWh(h.edgeLoadWs),
    minutes(h.fallbackSeconds), `${minutes(h.edgeOnlyUnmet.fanSeconds)} / ${minutes(h.edgeOnlyUnmet.lightSeconds)}`,
  ]));
  byId('inspector').hidden = !day.trace;
  if (day.trace) { byId('slot').value = '0'; inspect(); }
}
function run(cohort) {
  try {
    const options = { scenario: byId('case').value, overheadWatts: Number(byId('overhead').value), seed: 1 };
    if (!byId('overhead').value.trim()) throw new Error('Enter assumed device watts from 0 to 30.');
    let verdict;
    byId('cohort').hidden = !cohort;
    if (cohort) {
      const result = stress({ ...options, seeds: 12 });
      verdict = result.recommendation;
      showDay(result.cases[0], true);
      put('cohort-summary', `12 shifted days · worst ${signed(result.worstNetWs)} · median ${signed(result.medianNetWs)} · mean ${signed(result.meanNetWs)}. ${result.negativeCases}/12 negative; ${result.nonPositiveCases}/12 non-positive; ${result.degradedCases}/12 with additional service missed; ${result.excessiveFallbackCases}/12 above 5% fallback.`);
      const cases = byId('cases');
      cases.replaceChildren();
      result.cases.forEach(c => row(cases, [
        `${c.scenario} / ${c.seed}`, `${c.shiftHours} h / ${c.sensorBias} °C`, signed(c.netWs),
        `${minutes(c.service.edgeOnlyUnmet.fanSeconds)} / ${minutes(c.service.edgeOnlyUnmet.lightSeconds)}`,
        `${(c.coverage.fallbackFraction * 100).toFixed(2)}%`, c.recommendation,
      ]));
    } else {
      const result = simulate({ ...options, trace: true });
      verdict = result.recommendation;
      showDay(result);
    }
    byId('results').hidden = false;
    put('status', `SYNTHETIC / HYPOTHETICAL / NOT MEASURED · ${verdict} · ${cohort ? '12 shifted days' : '24 hours'} complete`);
  } catch (error) {
    put('status', `Run refused: ${error.message}`);
    byId('results').hidden = true;
    current = undefined;
  }
}
byId('single').addEventListener('click', () => run(false));
byId('stress').addEventListener('click', () => run(true));
byId('slot').addEventListener('input', inspect);
for (const id of ['case', 'overhead']) byId(id).addEventListener('input', () => {
  byId('results').hidden = true;
  current = undefined;
  put('status', 'Assumptions changed. Run again to compare this setup.');
});
