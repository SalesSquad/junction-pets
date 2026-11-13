/** Fictional, declared sample coverage only. No model, dataset, sensor or provider is executed. */
const WEATHER = ['clear', 'rain', 'fog', 'snow'];
const OCCLUSION = ['none', 'partial', 'heavy'];
const fail = message => {throw new TypeError(`Invalid fictional coverage input: ${message}`);};

function record(value, keys, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) fail(`${label} must be a record`);
  const actual = Object.keys(value);
  if (actual.length !== keys.length || actual.some(key => !keys.includes(key))) fail(`${label} keys`);
}

function axis(value, allowed, label) {
  if (!Array.isArray(value) || value.length < 1 || value.length > allowed.length ||
      value.some(item => !allowed.includes(item)) || new Set(value).size !== value.length) fail(label);
  return allowed.filter(item => value.includes(item));
}

function count(value, nullable, label) {
  if (nullable && value === null) return;
  if (!Number.isSafeInteger(value) || value < (nullable ? 0 : 1) || value > 1000000) fail(label);
}

export function reviewPerceptionCoverage(jsonText) {
  if (typeof jsonText !== 'string' || jsonText.length > 32768 ||
      new TextEncoder().encode(jsonText).length > 32768) fail('expected at most 32768 UTF-8 bytes of JSON text');
  let input;
  try {input = JSON.parse(jsonText);} catch {fail('malformed JSON');}
  record(input, ['schemaVersion', 'fictional', 'scenarioId', 'requiredWeather',
    'requiredOcclusion', 'minimumSamples', 'realEvaluationSplit', 'strata'], 'root');
  if (input.schemaVersion !== 1 || input.fictional !== true) fail('schemaVersion or fictional marker');
  if (typeof input.scenarioId !== 'string' || !/^[a-z0-9][a-z0-9-]{0,63}$/.test(input.scenarioId)) fail('scenarioId');
  const weather = axis(input.requiredWeather, WEATHER, 'requiredWeather');
  const occlusion = axis(input.requiredOcclusion, OCCLUSION, 'requiredOcclusion');
  record(input.minimumSamples, ['synthetic', 'real'], 'minimumSamples');
  count(input.minimumSamples.synthetic, false, 'minimum synthetic samples');
  count(input.minimumSamples.real, false, 'minimum real samples');
  if (![null, 'held-out', 'training-overlap'].includes(input.realEvaluationSplit)) fail('realEvaluationSplit');
  if (!Array.isArray(input.strata) || input.strata.length > 12) fail('strata');
  const declarations = new Map();
  for (const row of input.strata) {
    record(row, ['weather', 'occlusion', 'syntheticSamples', 'realSamples'], 'stratum');
    if (!weather.includes(row.weather) || !occlusion.includes(row.occlusion)) fail('stratum outside required axes');
    count(row.syntheticSamples, true, 'syntheticSamples');
    count(row.realSamples, true, 'realSamples');
    const key = `${row.weather}:${row.occlusion}`;
    if (declarations.has(key)) fail('duplicate stratum');
    declarations.set(key, row);
  }

  const summary = {requiredStrata: weather.length * occlusion.length,
    declaredStrata: declarations.size, missingStrata: 0, unknownStrata: 0,
    belowMinimumStrata: 0, coveredDeclaredStrata: 0};
  const findings = [];
  if (input.realEvaluationSplit === null) findings.push({code: 'real-split-unknown'});
  if (input.realEvaluationSplit === 'training-overlap') findings.push({code: 'real-split-training-overlap'});
  const strata = [];
  for (const condition of weather) for (const obstruction of occlusion) {
    const row = declarations.get(`${condition}:${obstruction}`);
    const location = {weather: condition, occlusion: obstruction};
    if (!row) {
      summary.missingStrata++;
      strata.push({...location, syntheticSamples: null, realSamples: null, status: 'missing'});
      findings.push({code: 'missing-stratum', ...location});
      continue;
    }
    let unknown = false;
    let deficient = false;
    for (const source of ['synthetic', 'real']) {
      const samples = row[`${source}Samples`];
      if (samples === null) {
        unknown = true;
        findings.push({code: `${source}-count-unknown`, ...location});
      } else if (samples < input.minimumSamples[source]) {
        deficient = true;
        findings.push({code: `${source}-below-minimum`, ...location});
      }
    }
    const status = unknown ? 'unknown' : deficient ? 'below-minimum' : 'covered-declared';
    if (unknown) summary.unknownStrata++;
    else if (deficient) summary.belowMinimumStrata++;
    else summary.coveredDeclaredStrata++;
    strata.push({...location, syntheticSamples: row.syntheticSamples, realSamples: row.realSamples, status});
  }
  return {schemaVersion: 1, kind: 'fictional-perception-coverage', scenarioId: input.scenarioId,
    status: findings.length ? 'needs-attention' : 'declared-coverage-complete', summary,
    minimumSamples: {...input.minimumSamples}, realEvaluationSplit: input.realEvaluationSplit,
    strata, findings,
    boundary: {fictional: true, countsUserDeclared: true, realDataInspected: false,
      mlPerformanceMeasured: false, simToRealTransferVerified: false, safetyValidated: false,
      providerExecuted: false}};
}
