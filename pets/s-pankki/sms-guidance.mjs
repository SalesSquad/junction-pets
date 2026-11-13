// Pure invented cue-declaration review. Does not parse messages or authenticate facts.
const CUES = ['urgentDeadline', 'messageLink', 'credentialRequest', 'paymentRequest', 'attachment', 'displayNameMatch'];
const WARNINGS = ['declared-urgent-deadline', 'declared-message-link', 'declared-credential-request', 'declared-payment-request', 'declared-attachment'];
const ACTIONS = ['guidance', 'open-link', 'account-login', 'make-payment', 'confirm-authenticity'];
function fields(value, keys, name) {
  if (value === null || typeof value !== 'object' || Array.isArray(value) ||
    Object.keys(value).length !== keys.length || keys.some(key => !Object.hasOwn(value, key))) {
    throw new TypeError(`${name} fields must be exactly ${keys.join(', ')}`);
  }
}

export function reviewFictionalSms(text) {
  if (typeof text !== 'string' || text.length > 8192 || new TextEncoder().encode(text).length > 8192) {
    throw new TypeError('expected primitive JSON text of at most 8192 UTF-8 bytes');
  }
  let input;
  try { input = JSON.parse(text); } catch { throw new TypeError('invalid JSON text'); }
  fields(input, ['schemaVersion', 'kind', 'scenarioId', 'cues', 'outsideCheck', 'requestedAction'], 'scenario');
  if (input.schemaVersion !== 1 || input.kind !== 'fictional-sms-safety-scenario' ||
    typeof input.scenarioId !== 'string' || !/^fictional-[a-z0-9][a-z0-9-]{0,63}$/.test(input.scenarioId) ||
    /[\u0000-\u001f\u007f]/.test(input.scenarioId)) throw new TypeError('invalid fictional scenario identity');
  fields(input.cues, CUES, 'cues');
  for (const name of CUES) {
    if (![true, false, null].includes(input.cues[name])) throw new TypeError(`cues.${name} must be boolean or null`);
  }
  if (![null, 'unknown', 'reported-match', 'reported-mismatch'].includes(input.outsideCheck)) throw new TypeError('invalid outsideCheck declaration');
  if (!ACTIONS.includes(input.requestedAction)) throw new TypeError('invalid requestedAction');

  const warningSigns = CUES.slice(0, 5).flatMap((name, index) => input.cues[name] === true ? [{code: WARNINGS[index], field: `cues.${name}`}] : []);
  const unknownFields = CUES.filter(name => input.cues[name] === null).map(name => `cues.${name}`);
  if (input.outsideCheck === 'reported-mismatch') warningSigns.push({code: 'reported-outside-mismatch', field: 'outsideCheck'});
  if (input.outsideCheck === null || input.outsideCheck === 'unknown') unknownFields.push('outsideCheck');
  return {
    schemaVersion: 1, kind: 'fictional-sms-guidance-report', scenarioId: input.scenarioId,
    classification: warningSigns.length ? 'declared-warning-signs' : unknownFields.length ? 'incomplete-declarations' : 'no-listed-warning-declared',
    warningSigns, unknownFields,
    notes: ['branding-is-not-authentication', 'outside-check-is-an-unverified-declaration'],
    guidance: ['do-not-follow-message-links-or-attachments', 'do-not-share-credentials-or-codes', 'verify-through-independently-reached-official-channel'],
    action: 'guidance-only', deniedAction: input.requestedAction === 'guidance' ? null : input.requestedAction,
    boundary: {synthetic: true, senderAuthenticated: false, fraudDetermined: false, accountAccessed: false, financialActionExecuted: false},
  };
}
