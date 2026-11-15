/** Synthetic offboard kernel. No I/O, clocks, models, hardware or raw images. */
export const POLICY = Object.freeze({
  sensorFreshMs: 20_000, cameraFreshMs: 10_000, minSlopeSpanMs: 5_000,
  coolingCPerMinute: -0.5, humidityConfoundPoints: 5, minCameraQuality: 0.8,
  intentMaxMs: 900_000, intentDebounceMs: 1_500, intentFreshMs: 2_000,
  stableClearMs: 30_000,
});
export const ASSUMPTIONS = Object.freeze({
  source: 'AUTHORED_UNMEASURED_ASSUMPTIONS', boardWatts: 4,
  cameraWhPerProposal: 0.01, rhoCpKJPerM3K: 1.2,
  airflowM3PerSecond: 0.03, deltaTK: 20, informationHorizonSeconds: 300,
  usefulInformationFraction: 0.01,
});
export const UPPER_PROXY_WATTS = ASSUMPTIONS.rhoCpKJPerM3K * 1000
  * ASSUMPTIONS.airflowM3PerSecond * ASSUMPTIONS.deltaTK;
const finite = (n, lo, hi) => typeof n === 'number' && Number.isFinite(n) && n >= lo && n <= hi;
const timestamp = n => Number.isSafeInteger(n) && n >= 0;
const object = o => o !== null && typeof o === 'object' && !Array.isArray(o);
const exact = (o, keys) => object(o) && Object.keys(o).length === keys.length
  && keys.every(k => Object.hasOwn(o, k));

/** State is kernel-owned, JSON-serializable data; callers must preserve it intact. */
export function initialState() {
  return {
    now: null, startAt: null, samples: [], lastThermoAt: null,
    lastCameraAt: null, lastIntentAt: null, camera: null,
    intent: null, pendingCamera: false, pendingCameraAt: null, pendingQueryId: null,
    queriedEpisode: false,
    stableSince: null, advisedQueryId: null,
    assumedBoardWh: 0, assumedCameraWh: 0, cameraProposals: 0,
  };
}

function thermal(s, now) {
  if (s.samples.length < 2 || now - s.samples.at(-1).at > POLICY.sensorFreshMs) {
    return { status: 'UNKNOWN', coolingRateCPerMinute: null, causeCertified: false };
  }
  const [a, b] = s.samples;
  const span = b.at - a.at;
  const slope = (b.temperature - a.temperature) * 60_000 / span;
  const confounded = Math.abs(b.humidity - a.humidity) > POLICY.humidityConfoundPoints;
  return {
    status: span < POLICY.minSlopeSpanMs ? 'INSUFFICIENT_SPAN'
      : confounded ? 'HUMIDITY_CONFOUND' : slope <= POLICY.coolingCPerMinute
        ? 'COOLING_ANOMALY_HYPOTHESIS' : 'STABLE_OR_WARMING',
    coolingRateCPerMinute: slope, causeCertified: false,
  };
}

/**
 * @typedef {{state:'open'|'closed'|'occluded'|'error',at:number,quality:number,
 * regionOfInterestOnly:true,storedFrames:false,frameFingerprint:string,queryId:number}} SyntheticROI
 * @typedef {{type:'tick'}|{type:'thermo',sample:{at:number,temperature:number,humidity:number}}
 * |{type:'camera',fixture:SyntheticROI}
 * |{type:'intent',at:number,confirmed:true,durationMs:number}} Event
 * @typedef {{schema:string,labels:string[],reason:string,accepted:boolean,
 * measuredEnvironmentalBenefit:false,physicalActuation:false,onDeviceInference:false,
 * networkRequired:false,windowEvidence:string,thermal:object,proposals:object[],energy:object}} Receipt
 *
 * Pure transition using explicit monotonic millisecond clock, no wall-clock reads.
 * Equal clock values are rejected too: callers sequence events strictly.
 * Camera proposals reserve assumed query energy, even if no fixture ever returns.
 * @param {ReturnType<typeof initialState>} previous
 * @param {Event} event
 * @param {number} now
 * @returns {{state:ReturnType<typeof initialState>,receipt:Receipt}}
 */
export function transition(previous, event, now) {
  const s = structuredClone(previous);
  let reason = 'ACCEPTED', accepted = true;
  const proposals = [];
  const fail = code => {
    accepted = false; reason = code;
    s.samples = []; s.camera = null; s.pendingCamera = false; s.pendingCameraAt = null; s.pendingQueryId = null;
    // An invalid packet cannot re-arm a spent anomaly episode.
  };
  if (!timestamp(now) || (s.now !== null && now <= s.now)) {
    fail('CLOCK_ROLLBACK_OR_DUPLICATE');
  } else {
    if (s.now !== null) s.assumedBoardWh += ASSUMPTIONS.boardWatts * (now - s.now) / 3_600_000;
    s.startAt ??= now;
    s.now = now;
    if (s.intent && now >= s.intent.expiresAt) s.intent = null;
    if (s.camera && now - s.camera.at > POLICY.cameraFreshMs) s.camera = null;
    if (s.samples.length && now - s.samples.at(-1).at > POLICY.sensorFreshMs) {
      s.samples = []; s.camera = null; s.pendingCamera = false; s.pendingCameraAt = null; s.pendingQueryId = null;
    }
    if (!object(event)) fail('INVALID_EVENT');
    else if (event.type === 'tick' && exact(event, ['type'])) reason = 'TICK';
    else if (event.type === 'thermo' && exact(event, ['type', 'sample'])) {
      const p = event.sample;
      if (!exact(p, ['at', 'temperature', 'humidity']) || !timestamp(p.at)
        || !finite(p.temperature, -40, 85) || !finite(p.humidity, 0, 100)) fail('INVALID_THERMO');
      else if (p.at > now || now - p.at > POLICY.sensorFreshMs) fail('STALE_OR_FUTURE_THERMO');
      else if (s.lastThermoAt !== null && p.at <= s.lastThermoAt) fail('DUPLICATE_OR_OUT_OF_ORDER_THERMO');
      else {
        s.lastThermoAt = p.at;
        // Jittery sub-5s samples must not destroy the last valid slope/window query.
        if (!s.samples.length || p.at - s.samples.at(-1).at >= POLICY.minSlopeSpanMs) {
          s.samples = [...s.samples, { at: p.at, temperature: p.temperature, humidity: p.humidity }].slice(-2);
        } else reason = 'THERMO_ACCEPTED_SLOPE_WINDOW_UNCHANGED';
      }
    } else if (event.type === 'camera' && exact(event, ['type', 'fixture'])) {
      const p = event.fixture;
      if (!exact(p, ['state', 'at', 'quality', 'regionOfInterestOnly',
        'storedFrames', 'frameFingerprint', 'queryId'])
        || !['open', 'closed', 'occluded', 'error'].includes(p.state)
        || !timestamp(p.at) || !finite(p.quality, 0, 1)
        || p.regionOfInterestOnly !== true || p.storedFrames !== false
        || typeof p.frameFingerprint !== 'string' || !/^[a-f0-9]{16,64}$/.test(p.frameFingerprint)
        || !Number.isSafeInteger(p.queryId) || p.queryId < 1) fail('INVALID_CAMERA_SCHEMA_OR_PRIVACY');
      else if (!s.pendingCamera || p.queryId !== s.pendingQueryId) fail('UNISSUED_QUERY_ID');
      else if (p.at <= s.pendingCameraAt || p.at > now || now - p.at > POLICY.cameraFreshMs) {
        fail('STALE_OR_FUTURE_CAMERA_OR_QUERY');
      } else if (s.lastCameraAt !== null && p.at <= s.lastCameraAt) fail('OUT_OF_ORDER_CAMERA');
      else {
        // Caller-supplied frameFingerprint is format-checked but NEVER retained.
        // Only a currently issued, single-use queryId can match an observation.
        // Real producer authenticity and region isolation remain unverified.
        s.lastCameraAt = p.at;
        if (p.state === 'occluded' || p.state === 'error' || p.quality < POLICY.minCameraQuality) {
          fail('UNUSABLE_CAMERA_UNKNOWN');
        } else if (thermal(s, now).status !== 'COOLING_ANOMALY_HYPOTHESIS') {
          fail('NO_FRESH_THERMAL_QUERY');
        } else {
          s.camera = { state: p.state, at: p.at, quality: p.quality };
          s.pendingCamera = false; s.pendingCameraAt = null; s.pendingQueryId = null;
        }
      }
    } else if (event.type === 'intent' && exact(event, ['type', 'at', 'confirmed', 'durationMs'])) {
      if (event.confirmed !== true || !timestamp(event.at) || !finite(event.durationMs, 1, POLICY.intentMaxMs)
        || !Number.isInteger(event.durationMs)) fail('INVALID_OR_UNCONFIRMED_INTENT');
      else if (event.at > now || now - event.at > POLICY.intentFreshMs) fail('STALE_OR_FUTURE_INTENT');
      else if (s.lastIntentAt !== null && event.at <= s.lastIntentAt) fail('OUT_OF_ORDER_INTENT');
      else if (s.lastIntentAt !== null && event.at - s.lastIntentAt < POLICY.intentDebounceMs) {
        reason = 'INTENT_DEBOUNCED';
      } else {
        s.lastIntentAt = event.at;
        s.intent = event.at + event.durationMs > now
          ? { durationMs: event.durationMs, expiresAt: event.at + event.durationMs } : null;
        if (s.intent) { s.pendingCamera = false; s.pendingCameraAt = null; s.pendingQueryId = null; s.camera = null; }
        reason = s.intent ? 'EXPLICIT_INTENT_ACCEPTED' : 'INTENT_ALREADY_EXPIRED';
      }
    } else fail('INVALID_EVENT_SCHEMA');
  }
  const effectiveNow = s.now ?? 0;
  const hypothesis = thermal(s, effectiveNow);
  const anomalous = hypothesis.status === 'COOLING_ANOMALY_HYPOTHESIS';
  // Only sustained stable evidence clears a spent anomaly. RH confounds do not rearm.
  if (accepted && hypothesis.status === 'STABLE_OR_WARMING' && s.samples.length === 2) {
    s.stableSince ??= now;
    if (now - s.stableSince >= POLICY.stableClearMs) {
      s.queriedEpisode = false; s.pendingCamera = false; s.pendingCameraAt = null; s.pendingQueryId = null; s.camera = null;
    }
  } else s.stableSince = null;
  // Authored utility discount, NOT a fitted probability, physical model or savings estimate.
  const severityDiscount = anomalous ? Math.min(1,
    Math.max(0, (POLICY.coolingCPerMinute - hypothesis.coolingRateCPerMinute) / 0.5)) : 0;
  const freshnessDiscount = anomalous ? Math.max(0,
    1 - (effectiveNow - s.samples.at(-1).at) / POLICY.sensorFreshMs) : 0;
  const assumedInformationValueWh = UPPER_PROXY_WATTS * ASSUMPTIONS.informationHorizonSeconds
    / 3600 * ASSUMPTIONS.usefulInformationFraction * severityDiscount * freshnessDiscount;
  if (accepted && anomalous && !s.intent && !s.queriedEpisode
    && assumedInformationValueWh > ASSUMPTIONS.cameraWhPerProposal) {
    s.pendingCamera = true; s.pendingCameraAt = now; s.queriedEpisode = true;
    s.cameraProposals++; s.pendingQueryId = s.cameraProposals;
    s.assumedCameraWh += ASSUMPTIONS.cameraWhPerProposal;
    proposals.push({ type: 'SELECTIVE_CAMERA_QUERY_PROPOSAL', queryId: s.pendingQueryId,
      regionOfInterestOnly: true,
      storedFrames: false, assumedInformationValueWh, assumedQueryWh: ASSUMPTIONS.cameraWhPerProposal,
      executed: false });
  }
  if (accepted && anomalous && s.camera?.state === 'open' && !s.intent
    && s.advisedQueryId !== s.cameraProposals) {
    s.advisedQueryId = s.cameraProposals;
    proposals.push({ type: 'HUMAN_ADVISORY_BUZZER_LED_PROPOSAL', executed: false,
      message: 'Synthetic ROI suggests open; cooling cause unknown. Please inspect if airing was unintended.' });
  }
  const receipt = {
    schema: 'open-window.synthetic-event.v1', labels: ['SYNTHETIC', 'HYPOTHETICAL'],
    at: s.now, accepted, reason, measuredEnvironmentalBenefit: false,
    physicalActuation: false, onDeviceInference: false, networkRequired: false,
    thermal: hypothesis, informationAuction: { assumedInformationValueWh,
      assumedQueryWh: ASSUMPTIONS.cameraWhPerProposal, severityDiscount, freshnessDiscount,
      measured: false },
    windowEvidence: accepted && s.camera ? `SYNTHETIC_${s.camera.state.toUpperCase()}_ROI` : 'UNKNOWN',
    causalHeatLossCertified: false, independentCameraObservationsCertified: false,
    intent: s.intent ? { ...s.intent } : null, proposals,
    energy: { source: ASSUMPTIONS.source, boardAssumedWatts: ASSUMPTIONS.boardWatts,
      boardAssumedWh: s.assumedBoardWh, cameraAssumedWh: s.assumedCameraWh,
      cameraProposals: s.cameraProposals, totalAssumedWh: s.assumedBoardWh + s.assumedCameraWh,
      prospectiveScenarioIllustration: s.intent ? {
        assumedHeatTransferWatts: UPPER_PROXY_WATTS,
        userDeclaredDurationMs: s.intent.durationMs,
        unverifiedPotentialHeatExposureWh: UPPER_PROXY_WATTS * s.intent.durationMs / 3_600_000,
        evidenceStatus: 'UNVERIFIED_ASSUMPTIONS_ONLY',
        physicalUpperBound: false, observedVentilationAirflow: false,
        interpretation: 'Illustrative scenario only; NOT a physical bound, causal loss, avoided saving or emissions.'
      } : null },
    watchdog: 'FUTURE_MCU_INTERFACE_NOT_IMPLEMENTED',
  };
  return { state: s, receipt };
}

export default Object.freeze({ initialState, transition, POLICY, ASSUMPTIONS });
