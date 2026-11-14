// Offline, non-actuating batch safety supervisor. No camera, robot or model integration.
import {loadFixture, POLICY, digest, canonical} from '../../core.mjs';
import {runBatch, replayBatch} from '../cell.mjs';

export const VERSION = 'synthetic-batch-safety-supervisor/1';
export const SOURCE_MAIN = '16947f0ccd33d6e3895f08619b7ba425bf453a59';
const copy = v => structuredClone(v);
const freeze = v => {
  if (v && typeof v === 'object') { for (const item of Object.values(v)) freeze(item); Object.freeze(v); }
  return v;
};
const isRecord = v => v !== null && typeof v === 'object' && !Array.isArray(v);

// Do not read the fixture's synthetic ground-truth label or evaluator output.
function interlockFault(e) {
  const fixture = loadFixture(e.fixtureId);
  if (!e.grip) return 'GRIP_LOSS';
  if (!e.cameraAgreement) return 'CAMERA_DISAGREEMENT';
  if (!fixture.cameras.top || !fixture.cameras.inspection) return 'CAMERA_MISSING';
  if (e.at - fixture.capturedAt > POLICY.maxAgeMs) return 'CAPTURE_STALE';
  if (fixture.confidence < POLICY.minConfidence) return 'PERCEPTION_LOW_CONFIDENCE';
  return null;
}

export function prepareSupervisedBatch(request, control = {}) {
  if (!isRecord(control) || Object.keys(control).some(k => k !== 'globalStopEpisodeId')) {
    throw Error('Unknown supervisor control');
  }
  if (!isRecord(request) || !Array.isArray(request.episodes) ||
      request.episodes.length < 1 || request.episodes.length > 64) throw Error('Invalid source batch');
  const sourceRequest = copy(request), supervisedRequest = copy(request);
  const {globalStopEpisodeId = null} = control;
  if (globalStopEpisodeId !== null &&
      (typeof globalStopEpisodeId !== 'string' ||
       request.episodes.filter(e => e?.id === globalStopEpisodeId).length !== 1)) {
    throw Error('Global STOP must reference one existing episode');
  }

  // The original M2 validates each episode. This layer only admits safety control
  // after checking identifiers; no label, score or simulator truth is a control.
  const seen = new Set(), audit = [];
  let trip = null;
  for (const [index, original] of sourceRequest.episodes.entries()) {
    if (!isRecord(original) || !/^[a-z0-9-]{1,64}$/.test(original.id) || seen.has(original.id)) {
      throw Error('Invalid or duplicate episode identifier');
    }
    seen.add(original.id);
    const current = supervisedRequest.episodes[index];
    if (trip) {
      current.operator = {decision:'stop',
        reason:`Batch-wide safety latch after ${trip.episodeId}: ${trip.reason}`};
      audit.push({episodeId:current.id,index,state:'LATCHED_BLOCK',reason:trip.reason});
      continue;
    }
    const globalStop = original.id === globalStopEpisodeId;
    const fault = interlockFault(original);
    if (globalStop) {
      current.operator = {decision:'stop',reason:'Operator global emergency STOP'};
      trip = {episodeId:original.id,index,reason:'GLOBAL_OPERATOR_STOP'};
      audit.push({episodeId:original.id,index,state:'TRIP',reason:trip.reason});
    } else if (fault) {
      trip = {episodeId:original.id,index,reason:fault};
      audit.push({episodeId:original.id,index,state:'TRIP',reason:fault});
    } else if (original.operator?.decision === 'stop') {
      // A normal per-item STOP is intentionally not a global emergency STOP.
      audit.push({episodeId:original.id,index,state:'LOCAL_STOP',reason:'LOCAL_OPERATOR_STOP'});
    } else {
      audit.push({episodeId:original.id,index,state:'CLEAR',reason:null});
    }
  }
  return {sourceRequest,supervisedRequest,control:{globalStopEpisodeId},trip,audit};
}

function softwareBowlPlacements(receipt, afterIndex) {
  const steps = receipt.steps.filter(s => s.stage === 'operator-decision');
  return steps.filter((s,i) => i > afterIndex && s.data.coreReceipt.final.bowl !== null).length;
}

export async function runSupervisedBatch(request, control = {}) {
  const prepared = prepareSupervisedBatch(request, control);
  // Compare against the unchanged M2's own per-episode STOP. Neither receipt
  // executes a robot motion. This comparator can be less safe by design.
  const baseline = await runBatch(prepared.sourceRequest);
  const supervisedBatch = await runBatch(prepared.supervisedRequest);
  await replayBatch(supervisedBatch);
  const decisions = supervisedBatch.steps.filter(s => s.stage === 'operator-decision');
  for (const a of prepared.audit) {
    const bowl = decisions[a.index].data.coreReceipt.final.bowl;
    const routed = supervisedBatch.evaluation.rows[a.index].conservative;
    if (a.state === 'LATCHED_BLOCK' &&
        (bowl !== null || routed !== 'stop')) throw Error('Safety latch was bypassed');
    if (a.state === 'TRIP' && bowl !== null) throw Error('Fault routed to a software bowl');
  }
  const summary = {
    episodes:prepared.audit.length,
    globalLatchTrips:prepared.trip ? 1 : 0,
    subsequentBlocked:prepared.audit.filter(a => a.state === 'LATCHED_BLOCK').length,
    localStops:prepared.audit.filter(a => a.state === 'LOCAL_STOP').length,
    // Count software bowl outputs only; these are NOT physical motions.
    baselinePostTripSoftwareBowls:prepared.trip ? softwareBowlPlacements(baseline,prepared.trip.index) : 0,
    supervisedPostTripSoftwareBowls:prepared.trip ? softwareBowlPlacements(supervisedBatch,prepared.trip.index) : 0,
    baselineTotalSorted:baseline.evaluation.conservative.sorted,
    supervisedTotalSorted:supervisedBatch.evaluation.conservative.sorted,
  };
  const provenance = {
    version:VERSION,sourceMain:SOURCE_MAIN,evidence:'SYNTHETIC',
    mode:'OFFLINE_NONACTUATING',realActuation:false,modelInference:false,
    safety:'BATCH_SCOPED_LATCH_NO_CROSS_BATCH_REARM_OR_PHYSICAL_ESTOP',
    comparison:'UNCHANGED_M2_PER_ITEM_STOP'
  };
  const packet = {
    schema:1,provenance,sourceRequest:prepared.sourceRequest,
    supervisedRequest:prepared.supervisedRequest,
    control:prepared.control,trip:prepared.trip,audit:prepared.audit,
    summary,baselineRoot:baseline.root,supervisedBatch
  };
  return freeze({...packet,root:await digest(packet)});
}

export async function replaySupervisedBatch(receipt) {
  if (!isRecord(receipt) || receipt.schema !== 1 || !isRecord(receipt.sourceRequest) ||
      !isRecord(receipt.control) || !Array.isArray(receipt.audit) ||
      receipt.audit.length > 64 || !isRecord(receipt.supervisedBatch)) {
    throw Error('Invalid supervisor receipt');
  }
  const rebuilt = await runSupervisedBatch(receipt.sourceRequest,receipt.control);
  if (canonical(receipt) !== canonical(rebuilt)) throw Error('Supervisor receipt integrity failure');
  return rebuilt;
}
