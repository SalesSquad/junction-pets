// MotionBridge's offline proposal-only engine. This module cannot actuate a robot.
// Event timestamps are monotonic milliseconds within a single calibrated frame.
const SCHEMA = "motionbridge.episode.v1";
const LIMITS = Object.freeze({ minQuality: 0.8, maxGapMs: 120, maxSpeedMps: 1.6, goalToleranceM: 0.03, gripTolerance: 0.08 });

function refuse(message) {
  throw new Error("REFUSED: " + message);
}
function finite(n) {
  return typeof n === "number" && Number.isFinite(n);
}
function inRange(n, bounds) {
  return finite(n) && n >= bounds[0] && n <= bounds[1];
}
function distance(a, b) {
  return Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z);
}

export function validateEpisode(e) {
  if (!e || e.schema !== SCHEMA) refuse("unknown episode schema");
  if (typeof e.id !== "string" || !/^[a-z0-9][a-z0-9-]{1,70}$/.test(e.id)) refuse("invalid episode id");
  if (!["SYNTHETIC_FIXTURE", "UNVERIFIED_REPLAY"].includes(e.source_label)) refuse("unverified source label");
  if (!e.calibration || e.calibration.frame_id !== "tabletop-v1" || e.calibration.units !== "m") refuse("calibration/frame or units unknown");
  const b = e.calibration.bounds;
  if (!b || !["x","y","z"].every(k => Array.isArray(b[k]) && b[k].length === 2 && b[k].every(finite) && b[k][0] < b[k][1])) refuse("invalid workspace");
  if (!e.goal || !["x","y","z"].every(k => inRange(e.goal[k], b[k])) || !inRange(e.goal.grip, [0,1])) refuse("goal outside calibrated workspace");
  if (!Array.isArray(e.steps) || e.steps.length < 3 || e.steps.length > 2000) refuse("episode must have 3 to 2000 frames");
  if (!finite(e.baseline_ms) || e.baseline_ms <= 0 || e.baseline_ms > 120000) refuse("invalid reference baseline");
  let previous = -1;
  for (let i=0;i<e.steps.length;i++) {
    const s=e.steps[i];
    if (!s || !Number.isSafeInteger(s.at_ms) || s.at_ms < 0 || s.at_ms > 120000 || s.at_ms <= previous) refuse("frame timestamp not strictly increasing at " + i);
    previous=s.at_ms;
    if (!s.hand || !["x","y","z"].every(k => finite(s.hand[k])) || !inRange(s.hand.grip,[0,1])) refuse("nonfinite position/grip at " + i);
    if (!inRange(s.tracking_quality,[0,1])) refuse("invalid tracking confidence at " + i);
    if (typeof s.deadman !== "boolean" || (s.reset_ack !== undefined && typeof s.reset_ack !== "boolean")) refuse("deadman/ack invalid at " + i);
  }
  return e;
}

export function evaluateEpisode(episode) {
  const e=validateEpisode(episode);
  const b=e.calibration.bounds;
  const events=[];
  const trace=[];
  let held=false, consecutiveHealthy=0, accepted=0, maxSpeed=0, pathM=0, lastAccepted=null;
  let prev=null;
  for (const frame of e.steps) {
    const hazards=[];
    let speed=0;
    if (prev) {
      const dt=frame.at_ms-prev.at_ms;
      speed=distance(frame.hand,prev.hand)/(dt/1000);
      maxSpeed=Math.max(maxSpeed,speed);
      pathM+=distance(frame.hand,prev.hand);
      if (dt>LIMITS.maxGapMs) hazards.push("STALE_TRACKING");
      if (speed>LIMITS.maxSpeedMps) hazards.push("MOTION_RATE_LIMIT");
    }
    if (frame.tracking_quality<LIMITS.minQuality) hazards.push("LOW_TRACKING_CONFIDENCE");
    if (!frame.deadman) hazards.push("DEADMAN_RELEASED");
    if (!["x","y","z"].every(k=>inRange(frame.hand[k],b[k]))) hazards.push("WORKSPACE_LIMIT");
    let status="PROPOSAL_ONLY";
    let proposal=null;
    if (hazards.length) {
      if (!held) events.push({at_ms:frame.at_ms,code:"SAFETY_HOLD",reasons:hazards});
      held=true;
      consecutiveHealthy=0;
      status="HELD";
    } else if (held) {
      consecutiveHealthy++;
      if (consecutiveHealthy>=2 && frame.reset_ack===true) {
        held=false;
        status="REARMED_PROPOSAL_ONLY";
        events.push({at_ms:frame.at_ms,code:"REARMED_AFTER_ACK",reasons:[]});
      } else {
        status="HELD";
      }
    }
    if (!held) {
      accepted++;
      lastAccepted=frame.hand;
      proposal={frame_id:e.calibration.frame_id,units:"m",target:{...frame.hand},actuation_authorized:false};
    }
    trace.push({at_ms:frame.at_ms,status,speed_mps:Number(speed.toFixed(4)),tracking_quality:frame.tracking_quality,hazards,proposal});
    prev=frame;
  }
  const stopCount=events.filter(x=>x.code==="SAFETY_HOLD").length;
  const last=e.steps[e.steps.length-1];
  const goalErrorM=lastAccepted?distance(lastAccepted,e.goal):null;
  const gripError=lastAccepted?Math.abs(lastAccepted.grip-e.goal.grip):null;
  const reached=!!lastAccepted && lastAccepted===last.hand &&
    goalErrorM<=LIMITS.goalToleranceM && gripError<=LIMITS.gripTolerance;
  const durationMs=last.at_ms-e.steps[0].at_ms;
  const comparisonPct=Number(((e.baseline_ms-durationMs)/e.baseline_ms*100).toFixed(1));
  const trainingEligible=e.source_label==="SYNTHETIC_FIXTURE" && reached && stopCount===0;
  return {
    schema:"motionbridge.episode-receipt.v1",
    episode_id:e.id,
    source_label:e.source_label,
    environment:"OFFLINE_DETERMINISTIC",
    hardware_connected:false,
    physical_success_measured:false,
    command_dispatch_enabled:false,
    calibration:e.calibration.frame_id,
    limits:LIMITS,
    observed_frames:e.steps.length,
    accepted_proposals:accepted,
    safety_holds:stopCount,
    rearm_events:events.filter(x=>x.code==="REARMED_AFTER_ACK").length,
    final_state:held?"HELD":(reached?"TARGET_REACHED_IN_SIMULATION":"INCOMPLETE"),
    simulated_target_reached:reached,
    synthetic_training_candidate:trainingEligible,
    duration_ms:durationMs,
    synthetic_reference_ms:e.baseline_ms,
    reference_delta_percent:comparisonPct,
    total_path_m:Number(pathM.toFixed(4)),
    max_speed_mps:Number(maxSpeed.toFixed(4)),
    target_error_m:goalErrorM===null?null:Number(goalErrorM.toFixed(4)),
    grip_error:gripError===null?null:Number(gripError.toFixed(4)),
    events,trace,
    next_dependency:"licensed Rokoko SDK source + calibrated robot/simulator adapter + measured live baseline"
  };
}

export function compareEpisodes(episodes) {
  if (!Array.isArray(episodes) || episodes.length===0 || episodes.length>20) refuse("select 1 to 20 episodes");
  const ids=new Set();
  return episodes.map(e=>{
    if (ids.has(e.id)) refuse("duplicate episode id");
    ids.add(e.id);
    return evaluateEpisode(e);
  });
}
