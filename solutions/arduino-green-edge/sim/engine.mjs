import { evaluate, initialState, POLICY, digest } from '../core.mjs';

/** Offline paired experiment. Units: seconds, watts, watt-seconds; never meter data. */
export const CASES = Object.freeze(['winter', 'summer', 'evening', 'fault']);
export const ASSUMPTIONS = Object.freeze({
  fanWatts: 40, lightWatts: 20, seconds: 86400, stepSeconds: 10,
  scheduleStartHour: 8, scheduleEndHour: 18, maxFallbackFraction: 0.05,
  maxSeeds: 32, epochMs: 1800000000000,
});
const { seconds, stepSeconds, epochMs } = ASSUMPTIONS;
const SLOTS = seconds / stepSeconds;
if (stepSeconds * 1000 > POLICY.maxGapMs) throw new Error('Step exceeds M1 watchdog');

function finite(value, min, max, name) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < min || value > max) {
    throw new RangeError(`${name} must be finite, ${min}..${max}`);
  }
  return value;
}
function integer(value, min, max, name) {
  finite(value, min, max, name);
  if (!Number.isInteger(value)) throw new RangeError(`${name} must be an integer`);
  return value;
}
function validate({ scenario, seed, overheadWatts, shiftHours, sensorBias }) {
  if (!CASES.includes(scenario)) throw new RangeError(`Case must be ${CASES.join(', ')}`);
  integer(seed, 0, 0xffffffff, 'seed');
  finite(overheadWatts, 0, 30, 'overheadWatts');
  // Integer milli-watts permit fractional assumptions without per-slot rounding.
  if (Math.abs(overheadWatts * 1000 - Math.round(overheadWatts * 1000)) > 1e-8) {
    throw new RangeError('overheadWatts supports at most three decimal places');
  }
  finite(shiftHours, -2, 2, 'shiftHours');
  finite(sensorBias, -2, 2, 'sensorBias');
}
function prng(seed) {
  let state = seed >>> 0;
  return () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 4294967296;
  };
}
const clamp = (n, min, max) => Math.min(max, Math.max(min, n));
const rounded = n => Math.round(n * 100) / 100;

/**
 * Single exogenous room path, independent of either controller and of overhead.
 * Hidden truth is ONLY for scoring. Fan/light actions do not alter this path:
 * fan service is not HVAC, cooling, humidity removal or causal comfort benefit.
 * Sensor aggregate contains no identities. The generator never makes a call.
 */
export function createDay({ scenario = 'winter', seed = 1, shiftHours = 0, sensorBias = 0 } = {}) {
  validate({ scenario, seed, shiftHours, sensorBias, overheadWatts: 0 });
  const random = prng(seed);
  const arrivalJitter = (random() - 0.5) * 0.75;
  const disturbance = (random() - 0.5) * 2;
  const seasonal = scenario === 'fault' ? 'summer' : scenario;
  const arrival = (seasonal === 'evening' ? 16 : 9) + arrivalJitter + shiftHours;
  const departure = (seasonal === 'evening' ? 23 : 17) + arrivalJitter + shiftHours;
  const daylightStart = seasonal === 'winter' ? 9 : 5;
  const daylightEnd = seasonal === 'winter' ? 15 : 21;
  const rows = [];
  for (let slot = 0; slot < SLOTS; slot++) {
    const second = slot * stepSeconds;
    const hour = second / 3600;
    const lunch = seasonal !== 'evening' && hour >= 12 + shiftHours && hour < 13 + shiftHours;
    const occupancy = hour >= arrival && hour < departure && !lunch ? 3 : 0;
    const warmth = Math.sin((hour - 8) / 24 * 2 * Math.PI);
    const temperature = rounded((seasonal === 'winter' ? 23.5 : 27) + 2 * warmth + disturbance);
    const humidity = rounded(58 + disturbance + (hour >= 14 && hour < 16 ? 15 : 0));
    const daylight = hour > daylightStart && hour < daylightEnd
      ? Math.sin((hour - daylightStart) / (daylightEnd - daylightStart) * Math.PI) : 0;
    const lux = rounded(70 + 650 * daylight);
    const truth = { occupancy, temperature, humidity, lux };
    // One-slot noise exercises debounce. A fault case includes a sustained,
    // plausible occupied-as-empty error: validity checks cannot detect it.
    const falseEmpty = random() < 0.002 || (scenario === 'fault' && hour >= 10 && hour < 10.5);
    const dropout = scenario === 'fault' && hour >= 11 && hour < 12;
    const stale = scenario === 'fault' && hour >= 14 && hour < 14.5;
    const sample = {
      at: epochMs + second * 1000 - (stale ? 40000 : 0),
      temperature: rounded(temperature + (random() - 0.5) * 0.6 + sensorBias),
      humidity: rounded(clamp(humidity + (random() - 0.5) * 2, 0, 100)),
      occupancy: falseEmpty ? 0 : occupancy,
      lux: rounded(Math.max(0, lux + (random() - 0.5) * 30)), connected: !dropout,
    };
    rows.push({ second, truth, sample, fault: dropout ? 'dropout' : stale ? 'stale' : falseEmpty && occupancy ? 'false-empty' : null });
  }
  return rows;
}

/** Clock + preset seasonal timers only. No hidden occupancy or future readings. */
export function scheduledAction(second, scenario) {
  const hour = second / 3600;
  const active = hour >= 8 && hour < 18;
  return {
    fan: active && (scenario !== 'winter' || (hour >= 13 && hour < 16)),
    light: active && (scenario === 'winter' || scenario === 'evening' || hour < 9 || hour >= 16),
  };
}
const watts = action => Number(action.fan) * ASSUMPTIONS.fanWatts + Number(action.light) * ASSUMPTIONS.lightWatts;
function service() { return { fanSeconds: 0, lightSeconds: 0 }; }
function unmet(counter, needed, supplied) {
  if (needed.fan && !supplied.fan) counter.fanSeconds += stepSeconds;
  if (needed.light && !supplied.light) counter.lightSeconds += stepSeconds;
}

/** @typedef {'NOT_RECOMMENDED'|'MODEL_ONLY_CANDIDATE'} Recommendation
 * @param {{scenario?:string,seed?:number,overheadWatts?:number,shiftHours?:number,sensorBias?:number,trace?:boolean}} options
 * @returns {object} Synthetic accounting and diagnostic trace, never an actuation receipt.
 */
export function simulate({ scenario = 'winter', seed = 1, overheadWatts = 4, shiftHours = 0, sensorBias = 0, trace = false } = {}) {
  validate({ scenario, seed, overheadWatts, shiftHours, sensorBias });
  if (typeof trace !== 'boolean') throw new TypeError('trace must be boolean');
  const day = createDay({ scenario, seed, shiftHours, sensorBias });
  let state = initialState();
  let baselineWs = 0, edgeLoadWs = 0, fallbackSlots = 0, fallbackEvents = 0, faultSlots = 0;
  let wasFallback = false;
  const baselineUnmet = service(), edgeUnmet = service(), edgeOnlyUnmet = service(), required = service();
  const trail = [], reasons = {};
  const hourly = Array.from({ length: 24 }, (_, hour) => ({ hour, baselineWs: 0, edgeLoadWs: 0, fallbackSeconds: 0, edgeOnlyUnmet: service() }));
  for (const row of day) {
    const { second, sample, truth, fault } = row;
    const baseline = scheduledAction(second, scenario);
    // Crucially, truth never reaches evaluate. Exactly the unmodified M1 API.
    const result = evaluate(sample, state, { now: epochMs + second * 1000, optIn: true, override: 'auto' });
    state = result.state;
    const fallback = result.action === null;
    // A separate WHAT-IF accounting assumption. Never substitute this into
    // result.action or state, and never report a physically executed command.
    const accounted = fallback ? baseline : result.action;
    const bWs = watts(baseline) * stepSeconds, eWs = watts(accounted) * stepSeconds;
    baselineWs += bWs;
    edgeLoadWs += eWs;
    const h = hourly[Math.floor(second / 3600)];
    h.baselineWs += bWs; h.edgeLoadWs += eWs;
    if (fallback) {
      fallbackSlots++;
      if (!wasFallback) fallbackEvents++;
      reasons[result.reason] = (reasons[result.reason] ?? 0) + 1;
      h.fallbackSeconds += stepSeconds;
    }
    if (fault === 'dropout' || fault === 'stale') faultSlots++;
    wasFallback = fallback;
    const needed = {
      fan: truth.occupancy > 0 && (truth.temperature >= 27 || truth.humidity >= 70),
      light: truth.occupancy > 0 && truth.lux < 250,
    };
    if (needed.fan) required.fanSeconds += stepSeconds;
    if (needed.light) required.lightSeconds += stepSeconds;
    unmet(baselineUnmet, needed, baseline);
    unmet(edgeUnmet, needed, accounted);
    const baselineServed = { fan: needed.fan && baseline.fan, light: needed.light && baseline.light };
    unmet(edgeOnlyUnmet, baselineServed, accounted);
    unmet(h.edgeOnlyUnmet, baselineServed, accounted);
    if (trace) trail.push({
      second, hiddenScoringTruth: truth, sensorSample: sample, fault,
      baseline, decision: result.decision, reason: result.reason, action: result.action,
      pendingCount: state.count, accountingSource: fallback ? 'HYPOTHETICAL_SCHEDULE_FALLBACK' : 'M1_SIMULATED_ACTION',
      accounted, required: needed, baselineWs: bWs, edgeLoadWs: eWs, physicalExecution: false,
    });
  }
  const deviceMilliWatts = Math.round(overheadWatts * 1000);
  const deviceWs = deviceMilliWatts * seconds / 1000;
  const grossWs = baselineWs - edgeLoadWs, netWs = grossWs - deviceWs;
  const fallbackFraction = fallbackSlots / SLOTS;
  const recommendationReasons = [];
  if (netWs <= 0) recommendationReasons.push('NON_POSITIVE_NET');
  if (edgeOnlyUnmet.fanSeconds || edgeOnlyUnmet.lightSeconds) recommendationReasons.push('SERVICE_DEGRADATION_VS_BASELINE');
  if (fallbackFraction > ASSUMPTIONS.maxFallbackFraction) recommendationReasons.push('EXCESSIVE_FALLBACK');
  return {
    schema: 'green-edge.synthetic-twin.v1', evidence: 'SYNTHETIC', accounting: 'HYPOTHETICAL', measured: false,
    physicalExecution: false, modelInference: false, eligibilityScope: 'SIMULATION_ONLY',
    scenario, seed, shiftHours, sensorBias, overheadWatts, seconds, stepSeconds, assumptions: ASSUMPTIONS,
    policy: POLICY, disturbanceDigest: digest(day),
    baselineWs, edgeLoadWs, deviceWs, grossWs, netWs, breakEvenDeviceWatts: grossWs / seconds,
    service: { required, baselineUnmet, edgeUnmet, edgeOnlyUnmet,
      interpretation: 'Missed synthetic fan/light service; no thermal, cooling or humidity-removal benefit inferred.' },
    coverage: { totalSlots: SLOTS, actionSlots: SLOTS - fallbackSlots, fallbackSlots, fallbackEvents,
      fallbackSeconds: fallbackSlots * stepSeconds, faultSlots, fallbackFraction,
      actionFraction: 1 - fallbackFraction, reasons,
      fallbackAssumption: 'HOLD has no command. Schedule fallback is hypothetical accounting only, not physical execution.' },
    recommendation: recommendationReasons.length ? 'NOT_RECOMMENDED' : 'MODEL_ONLY_CANDIDATE', recommendationReasons,
    hourly, ...(trace ? { trace: trail } : {}),
  };
}

/** Bounded shifted cohort: cycles all four cases, shifted arrivals + sensor bias.
 * The selected case runs first; seeds is the TOTAL cases, not seeds per case.
 * A cohort verdict refuses if any member refuses; no cherry-picked averages.
 */
export function stress({ scenario = 'winter', seed = 1, overheadWatts = 4, seeds = 12 } = {}) {
  validate({ scenario, seed, overheadWatts, shiftHours: 0, sensorBias: 0 });
  integer(seeds, 4, ASSUMPTIONS.maxSeeds, 'seeds');
  const start = CASES.indexOf(scenario);
  const cases = Array.from({ length: seeds }, (_, i) => simulate({
    scenario: CASES[(start + i) % CASES.length], seed: (seed + i) >>> 0, overheadWatts,
    // Rotate shifts each group so a season is not tied to one arrival shift.
    shiftHours: [-2, -0.5, 1, 2][(i + Math.floor(i / 4)) % 4],
    sensorBias: [-1, 0.5, -0.5, 1][Math.floor(i / 4) % 4],
  }));
  const sorted = cases.map(r => r.netWs).sort((a, b) => a - b);
  const mid = Math.floor(seeds / 2);
  return {
    schema: 'green-edge.synthetic-stress.v1', evidence: 'SYNTHETIC', accounting: 'HYPOTHETICAL', measured: false,
    physicalExecution: false, eligibilityScope: 'SIMULATION_ONLY', scenario, seed, overheadWatts, seeds,
    cohortRule: 'Selected case first, cyclic winter/summer/evening/fault; shifts -2/-0.5/+1/+2 h rotate each group of four; sensor bias cycles in groups of four.',
    worstNetWs: sorted[0], meanNetWs: sorted.reduce((a, b) => a + b, 0) / seeds,
    medianNetWs: seeds % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2,
    negativeCases: cases.filter(r => r.netWs < 0).length,
    nonPositiveCases: cases.filter(r => r.netWs <= 0).length,
    degradedCases: cases.filter(r => r.service.edgeOnlyUnmet.fanSeconds || r.service.edgeOnlyUnmet.lightSeconds).length,
    excessiveFallbackCases: cases.filter(r => r.coverage.fallbackFraction > ASSUMPTIONS.maxFallbackFraction).length,
    recommendation: cases.every(r => r.recommendation === 'MODEL_ONLY_CANDIDATE') ? 'MODEL_ONLY_CANDIDATE' : 'NOT_RECOMMENDED',
    cases,
  };
}
