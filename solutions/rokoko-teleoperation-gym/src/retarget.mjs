// Offline, positional retargeting. Declared calibration is an assumption, not a grant.
import {createHash} from "node:crypto";
import {parseCsv} from "./csv.mjs";
import {evaluateEpisode,validateEpisode} from "./engine.mjs";

const axes=["x","y","z"];
const required=["time",...axes,"grip","quality","deadman","reset_ack"];
const fail=reason=>{throw new Error("REFUSED: "+reason);};
const finite=n=>typeof n==="number" && Number.isFinite(n);
const hash=text=>createHash("sha256").update(text).digest("hex");
function keys(o, expected, reason) {
  if (!o || typeof o!=="object" || Array.isArray(o) || Object.keys(o).sort().join()!==[...expected].sort().join()) fail(reason);
}
function bounds(b,scale,reason) {
  keys(b,axes,reason);
  for(const a of axes) if(!Array.isArray(b[a]) || b[a].length!==2 || !b[a].every(finite) ||
    b[a][0]>=b[a][1] || b[a].some(v=>!finite(v*scale) || Math.abs(v*scale)>10)) fail(reason);
}
const inside=(p,b)=>axes.every(a=>p[a]>=b[a][0] && p[a]<=b[a][1]);

export function retargetCsv(csv, configText) {
  if(typeof configText!=="string" || configText.length>100_000) fail("CONFIG_SIZE");
  const c=JSON.parse(configText);
  keys(c,["schema","columns","source","rotation","translation_m","calibration","goal","baseline_ms"],"CONFIG_FIELDS");
  if(c.schema!=="motionbridge.retarget.v1") fail("CONFIG_SCHEMA");
  keys(c.source,["frame_id","position_units","time_units","bounds"],"SOURCE_FIELDS");
  if(typeof c.source.frame_id!=="string" || !/^[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}$/.test(c.source.frame_id)) fail("SOURCE_FRAME_ID");
  const scale={m:1,cm:0.01,mm:0.001}[c.source.position_units];
  if(!finite(scale)) fail("SOURCE_POSITION_UNITS");
  if(!["ms","us"].includes(c.source.time_units)) fail("SOURCE_TIME_UNITS");
  bounds(c.source.bounds,scale,"SOURCE_BOUNDS");
  keys(c.calibration,["frame_id","units","bounds","accepted","assumption_id"],"CALIBRATION_FIELDS");
  if(c.calibration.accepted!==true || c.calibration.frame_id!=="tabletop-v1" || c.calibration.units!=="m" ||
    typeof c.calibration.assumption_id!=="string" || !/^[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}$/.test(c.calibration.assumption_id)) fail("CALIBRATION_NOT_ACCEPTED");
  bounds(c.calibration.bounds,1,"TARGET_BOUNDS");
  keys(c.translation_m,axes,"TRANSLATION_FIELDS");
  if(!axes.every(a=>finite(c.translation_m[a]) && Math.abs(c.translation_m[a])<=10)) fail("UNSAFE_TRANSLATION");
  // rotation[target axis] = signed source axis; determinant must be +1.
  keys(c.rotation,axes,"ROTATION_FIELDS");
  const entries=axes.map(a=>c.rotation[a]);
  if(!entries.every(v=>typeof v==="string" && /^[+-][xyz]$/.test(v))) fail("SIGNED_PERMUTATION_REQUIRED");
  const perm=entries.map(v=>axes.indexOf(v[1]));
  if(new Set(perm).size!==3) fail("DUPLICATE_ROTATION_AXIS");
  let determinant=entries.reduce((s,v)=>s*(v[0]==="+"?1:-1),1);
  for(let i=0;i<3;i++) for(let j=i+1;j<3;j++) if(perm[i]>perm[j]) determinant*=-1;
  if(determinant!==1) fail("AXIS_REFLECTION");
  const {headers,records}=parseCsv(csv);
  if(records.length>2000) fail("FRAME_LIMIT");
  keys(c.columns,required,"POSITIONAL_SIGNALS_REQUIRED");
  if(!required.every(k=>Number.isSafeInteger(c.columns[k]) && c.columns[k]>=0 && c.columns[k]<headers.length)) fail("COLUMN_INDEX");
  if(new Set(Object.values(c.columns)).size!==required.length) fail("DUPLICATE_SOURCE_SIGNAL");
  let previous=-1;
  const steps=records.map((row,i)=>{
    const raw=k=>row[c.columns[k]].trim();
    const number=k=>{
      const v=raw(k);
      if(!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(v) || !finite(Number(v))) fail("NONFINITE_OR_INVALID_SIGNAL "+k+" row "+(i+2));
      return Number(v);
    };
    const bool=k=>{if(!["0","1"].includes(raw(k))) fail("BOOLEAN_SIGNAL "+k);return raw(k)==="1";};
    const t=raw("time");
    if(!/^\d{1,16}$/.test(t)) fail("INTEGER_SOURCE_TIME_REQUIRED");
    const sourceTime=BigInt(t), divisor=c.source.time_units==="us"?1000n:1n;
    if(sourceTime%divisor!==0n) fail("NONINTEGER_MILLISECOND_TIME");
    const at_ms=Number(sourceTime/divisor);
    if(!Number.isSafeInteger(at_ms) || at_ms>120000) fail("TIMESTAMP_RANGE");
    if(at_ms<=previous) fail("TIMESTAMP_NOT_STRICTLY_INCREASING");
    previous=at_ms;
    const source=Object.fromEntries(axes.map(a=>[a,number(a)]));
    if(!inside(source,c.source.bounds)) fail("SOURCE_POSE_OUTSIDE_BOUNDS row "+(i+2));
    const hand=Object.fromEntries(axes.map((a,j)=>[a,source[entries[j][1]]*scale*(entries[j][0]==="+"?1:-1)+c.translation_m[a]]));
    if(!axes.every(a=>finite(hand[a])) || !inside(hand,c.calibration.bounds)) fail("TARGET_POSE_OUTSIDE_WORKSPACE row "+(i+2));
    return {at_ms,hand:{...hand,grip:number("grip")},tracking_quality:number("quality"),deadman:bool("deadman"),reset_ack:bool("reset_ack")};
  });
  const episode={schema:"motionbridge.episode.v1",id:"retargeted-unverified",source_label:"UNVERIFIED_REPLAY",calibration:c.calibration,goal:c.goal,baseline_ms:c.baseline_ms,steps};
  validateEpisode(episode);
  const receipt=evaluateEpisode(episode);
  return {episode,receipt,provenance:{input_csv_sha256:hash(csv),config_sha256:hash(configText),
    source_frame:c.source,target_frame:c.calibration,position_scale_to_m:scale,
    time_divisor_to_ms:c.source.time_units==="us"?1000:1,rotation:c.rotation,rotation_determinant:determinant,
    translation_m:c.translation_m,columns:required.map(signal=>({signal,index:c.columns[signal],header:headers[c.columns[signal]]})),
    source_label:"UNVERIFIED_REPLAY",calibration_status:"OPERATOR_DECLARED_ASSUMPTION",
    source_provenance_verified:false,sdk_integration_verified:false,simulator_calibration_verified:false,
    actuation_authorized:false,training_authorized:false}};
}
