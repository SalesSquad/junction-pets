/**
 * Recovery Compass: local, voluntary general wellbeing support after a course of care.
 * NOT clinical treatment, diagnostics, relapse prediction, TMS maintenance or emergency assessment.
 * Demo data only. No network, persistence, provider access, or sensor profiling.
 */
const ACTIONS = Object.freeze({
  pause: Object.freeze({ id: 'pause', title: 'A quiet two-minute pause', description: 'Find a comfortable place and take a short break if that feels right.' }),
  movement: Object.freeze({ id: 'movement', title: 'A gentle movement break', description: 'If it feels comfortable, consider standing or moving a little.' }),
  contact: Object.freeze({ id: 'contact', title: 'Connect with someone you choose', description: 'You can decide whether and when to reach out to a trusted person.' }),
  outdoors: Object.freeze({ id: 'outdoors', title: 'Step toward daylight', description: 'If you want to and it is accessible, consider a brief moment outside or by a window.' }),
});
const levels = new Set(['lower', 'steady', 'higher', 'prefer-not-to-say']);
const wants = new Set(Object.keys(ACTIONS));
const shareableFields = new Set(['energy', 'chosenAction']);
const status = (result, reason) => ({ ok: result, reason });
const cleanLabel = (value) => typeof value === 'string' && /^[\p{L}\p{N} .'-]{1,60}$/u.test(value.trim());
const copy = (s) => structuredClone(s);

export const actions = Object.values(ACTIONS);
export function newSession() {
  return {
    schemaVersion: 'wellbeing-local-v1',
    sourceKind: 'SYNTHETIC_PRODUCT_DEMO',
    processing: 'VOLUNTARY_USER_CHOICE_ONLY',
    mode: 'IN_MEMORY_NO_PERSISTENCE',
    checkin: null,
    action: null,
    draft: null,
    hasOutboundTransport: false,
    dataReleaseAuthorized: false,
    clinicalInferencePerformed: false,
    erased: false,
  };
}
function active(s) { return s?.schemaVersion === 'wellbeing-local-v1' && !s?.erased; }
export function checkIn(s, { energy, wish }={}) {
  if (!active(s)) return status(false, 'NO_ACTIVE_SESSION');
  if (!levels.has(energy) || !wants.has(wish)) return status(false, 'INVALID_USER_CHOICE');
  const next=copy(s);
  next.checkin={ energy, wish };
  next.action=null;
  next.draft=null; // A later check-in invalidates any earlier share draft.
  return { ok: true, session: next, guidance: 'This is your preference, not an estimate of symptoms or risk.' };
}
export function proposeAction(s) {
  if (!active(s) || !s.checkin) return status(false, 'CHECK_IN_REQUIRED');
  return { ok: true, proposal: { ...ACTIONS[s.checkin.wish], requiresUserApproval: true, clinicalClaim: false, sensorEvidence: 'NONE' } };
}
export function chooseAction(s, { confirmed }={}) {
  if (!active(s) || !s.checkin) return status(false, 'CHECK_IN_REQUIRED');
  if (confirmed !== true) return status(false, 'EXPLICIT_CHOICE_REQUIRED');
  const next=copy(s);next.action={id:s.checkin.wish,status:'CHOSEN_BY_USER',automatedExecution:false};
  next.draft=null;
  return { ok: true, session: next };
}
export function previewShare(s, { fields, recipient }={}) {
  if (!active(s) || !s.checkin || !s.action) return status(false, 'USER_ACTION_REQUIRED');
  if (!Array.isArray(fields) || !fields.length || new Set(fields).size !== fields.length || fields.some(f=>!shareableFields.has(f)))
    return status(false, 'UNSAFE_SHARE_SCOPE');
  if (!cleanLabel(recipient)) return status(false, 'INVALID_LOCAL_RECIPIENT_LABEL');
  const safe={};if(fields.includes('energy'))safe.energy=s.checkin.energy;
  if(fields.includes('chosenAction'))safe.chosenAction=ACTIONS[s.action.id].title;
  return { ok: true, preview: { recipientLabel: recipient.trim(), fields:safe, source:'USER_CHOSEN_LOCAL_DEMO', purpose:'Optional wellbeing discussion', effect:'PREVIEW_ONLY', receiverConnected:false, clinicalRiskPrediction:false } };
}
export function consentDraft(s, request={}) {
  const result=previewShare(s,request);if(!result.ok)return result;
  if(request.explicitConsent!==true) return status(false, 'EXPLICIT_CONSENT_REQUIRED');
  const next=copy(s);
  next.draft={...result.preview,effect:'UNSENT_LOCAL_DRAFT',revoked:false,consented:true};
  next.dataReleaseAuthorized=false; // Explicitly NO network send even after local approval.
  return { ok:true, session:next };
}
export function revoke(s) {
  if (!active(s))return status(false,'NO_ACTIVE_SESSION');
  const next=copy(s);
  next.draft=null; // No prior exported/shared copy exists: no outbound transport.
  return { ok:true, session:next, proof:'LOCAL_DRAFT_DISCARDED_NOT_REMOTE_REVOCATION' };
}
export function clearAll(s) {
  if (!active(s))return status(false,'NO_ACTIVE_SESSION');
  const next=newSession();next.erased=true;
  return { ok:true, session:next, proof:'IN_MEMORY_STATE_CLEARED' };
}
export function publicSafetyHelp() {
  return {
    scope:'GENERAL_INFORMATION_NOT_EMERGENCY_MONITORING',
    advice:'If you may be in immediate danger, contact your local emergency service now. This app cannot monitor emergencies or arrange care.',
    emergencyNumberInFinland:'112',
    nonEmergency:'For mental-health care decisions, contact your existing clinician or health-care service.',
  };
}
