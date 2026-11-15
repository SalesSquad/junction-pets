import { createHash } from 'node:crypto';
import { TradeError } from './core.mjs';
const digest = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
export function onlyQuery(params, keys) {
  for (const key of params.keys()) {
    if (!keys.includes(key) || params.getAll(key).length !== 1) throw new TradeError('INVALID_QUERY', 'Unknown or repeated query field: ' + key);
  }
}
const limitFor = (params, max = 100) => {
  const raw = params.get('limit');
  if (raw !== null && !/^[1-9][0-9]{0,3}$/.test(raw)) throw new TradeError('INVALID_LIMIT', 'Use a positive bounded integer limit.');
  const limit = raw === null ? 100 : Number(raw);
  if (limit < 1 || limit > max) throw new TradeError('INVALID_LIMIT', 'Page limit exceeds ' + max + '.');
  return limit;
};
function cursorFor(raw) {
  if (raw === null) return null;
  try {
    if (!/^[A-Za-z0-9_-]{1,256}$/.test(raw)) throw Error();
    const cursor = JSON.parse(Buffer.from(raw, 'base64url').toString('utf8'));
    if (Object.keys(cursor).sort().join(',') !== 'digest,index,through,v' || cursor.v !== 1 ||
        !Number.isSafeInteger(cursor.index) || !Number.isSafeInteger(cursor.through) ||
        cursor.index < 0 || cursor.through < cursor.index || !/^[0-9a-f]{64}$/.test(cursor.digest)) throw Error();
    return cursor;
  } catch { throw new TradeError('INVALID_CURSOR', 'Use the opaque cursor returned by the preceding page.'); }
}
const encode = value => Buffer.from(JSON.stringify(value)).toString('base64url');
function page(items, params, { appendOnly = false, tail = false } = {}) {
  const limit = limitFor(params);
  const cursor = cursorFor(params.get('cursor'));
  if (cursor && tail) throw new TradeError('INVALID_QUERY', 'Tail mode and cursor are mutually exclusive.');
  const through = cursor?.through ?? items.length;
  const index = cursor?.index ?? (tail ? Math.max(0, through - limit) : 0);
  const revision = digest(appendOnly ? items.slice(0, through) : items);
  if (through > items.length || (!appendOnly && through !== items.length) || (cursor && cursor.digest !== revision)) {
    throw new TradeError('CURSOR_STALE', 'The source collection changed. Restart paging without a cursor.', 409);
  }
  const end = Math.min(index + limit, through);
  return { items: items.slice(index, end), page: { limit, returned: end - index, snapshotId: revision,
    through, complete: index === 0 && end === through, nextCursor: end < through ?
      encode({ v: 1, index: end, through, digest: revision }) : null } };
}
export function catalogPage(items, params) {
  onlyQuery(params, ['q', 'family', 'lactoseFree', 'deliverBy', 'limit', 'cursor']);
  const needle = params.get('q') ?? '';
  if (needle.length > 160 || /[\u0000-\u001f]/.test(needle)) throw new TradeError('INVALID_QUERY', 'Catalog query must be bounded text.');
  const family = params.get('family'), diet = params.get('lactoseFree'), date = params.get('deliverBy');
  if (family !== null && !['dairy-milk', 'oat-drink'].includes(family)) throw new TradeError('INVALID_QUERY', 'Unknown catalog family.');
  if (diet !== null && !['true', 'false'].includes(diet)) throw new TradeError('INVALID_QUERY', 'lactoseFree must be true or false.');
  if (date !== null && (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !Number.isFinite(Date.parse(date)) ||
      new Date(date).toISOString().slice(0, 10) !== date)) throw new TradeError('INVALID_QUERY', 'Use a valid ISO delivery date.');
  const filtered = items.filter(item => (!family || item.family === family) &&
    (diet !== 'true' || item.lactoseFree === true) && (!date || item.deliverBy <= date) &&
    (item.name + ' ' + item.sku).toLocaleLowerCase('en').includes(needle.toLocaleLowerCase('en')))
    .sort((a, b) => a.sku.localeCompare(b.sku, 'en'));
  const result = page(filtered, params);
  return { mode: 'INVENTED_FIXTURE', products: result.items, page: result.page };
}
export function auditPage(items, params, field = 'receipts') {
  onlyQuery(params, ['limit', 'cursor', 'tail']);
  const tail = params.get('tail');
  if (tail !== null && tail !== '1') throw new TradeError('INVALID_QUERY', 'tail must be1 or omitted.');
  const result = page(items, params, { appendOnly: true, tail: tail === '1' });
  return { [field]: result.items, page: result.page };
}
export function recoveryFor(code, details = null) {
  const transient = details?.retryable === true || ['STATE_BUSY', 'OCR_BUSY', 'EMBEDDING_BACKEND_UNAVAILABLE', 'RETRIEVAL_BACKEND_UNAVAILABLE'].includes(code);
  const action = transient ? 'retry_same_command_key' :
    ['QUOTE_STALE', 'QUOTE_EXPIRED', 'PLAN_STALE', 'PLAN_EXPIRED', 'PROOF_EXPIRED'].includes(code) ? 'prepare_new_purchase_with_original_intent' :
    code === 'INTEGRATION_NOT_CONFIGURED' ? 'operator_configure_read_only_provider_no_model_credential_input' :
    code === 'CURSOR_STALE' ? 'restart_pagination_without_cursor' :
    ['APPROVAL_REQUIRED', 'REVIEW_CONFIRMATION_REQUIRED', 'PAYMENT_APPROVAL_REQUIRED'].includes(code) ? 'request_exact_human_approval' :
    code === 'BUYER_CAPABILITY_REQUIRED' ? 'resume_original_session' :
    ['STATE_CAPACITY', 'SESSION_CAPACITY'].includes(code) ? 'preserve_state_and_request_operator_capacity' :
    code === 'IDEMPOTENCY_CONFLICT' ? 'reconcile_original_command_before_using_a_new_key' : 'correct_request_or_inspect_service';
  return { retryable: transient, ...(transient ? { retryAfterMs: Math.max(1000, Math.min(60000, (details?.retryAfterSeconds ?? 1) * 1000)) } : {}), recovery: { action } };
}
