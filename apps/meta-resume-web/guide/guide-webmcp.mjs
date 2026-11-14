/** Optional native WebMCP. Tools can read or propose; visible controls own effects. */
export function registerGuideTools(document, { read, onProposal, isEnabled = () => false, onStatus = () => {} }) {
  if (!isEnabled()) { onStatus('disabled'); return () => {}; }
  const context = document.modelContext;
  if (typeof context?.registerTool !== 'function') { onStatus('unavailable'); return () => {}; }
  const lifetime = new AbortController();
  let failed = false;
  const fail = () => { failed = true; if (!lifetime.signal.aborted && isEnabled()) onStatus('failed'); };
  const error = message => ({ error: true, message, actionAuthorized: false,
    next_action: 'Read the current workbench and ask the user to use its visible controls.' });
  const admitted = signal => {
    if (lifetime.signal.aborted || !isEnabled()) return error('Assistant sharing is off. Ask the user to enable it with the visible control.');
    if (signal?.aborted) throw new DOMException('Cancelled', 'AbortError');
    return null;
  };
  const plain = value => value && typeof value === 'object' && !Array.isArray(value);
  const bound = args => plain(args) && typeof args.sessionId === 'string' && Number.isSafeInteger(args.expectedRevision) && args.expectedRevision >= 0;
  const common = { sessionId: { type: 'string', description: 'Exact sessionId returned by read_state.' },
    expectedRevision: { type: 'integer', minimum: 0, description: 'Exact revision returned by read_state.' } };
  const specs = [{
    name: 'chibi_lens_guide_read_state',
    description: 'Read user-confirmed local metadata and the current task. Historical places are not live locations. No glasses or private host is connected.',
    inputSchema: { type: 'object', properties: {}, additionalProperties: false }, annotations: { readOnlyHint: true },
    execute(args, { signal } = {}) {
      const denied = admitted(signal); if (denied) return denied;
      if (!plain(args) || Object.keys(args).length) return error('This tool takes no arguments.');
      return { state: read(), qualification: 'local-browser-unqualified', actionAuthorized: false,
        next_action: 'Explain the next unfinished step and what the user previously confirmed. Do not claim current identity or location.' };
    },
  }, {
    name: 'chibi_lens_guide_propose_view',
    description: 'Place a visible suggestion for a close-up, side or overview. The user must approve it and separately open the camera. This tool never captures or confirms anything.',
    inputSchema: { type: 'object', properties: { ...common, itemId: { type: 'string' }, reason: { type: 'string', enum: ['close-up', 'side', 'overview'] } },
      required: ['sessionId', 'expectedRevision', 'itemId', 'reason'], additionalProperties: false },
    execute(args, { signal } = {}) {
      const denied = admitted(signal); if (denied) return denied;
      if (!bound(args) || Object.keys(args).length !== 4 || typeof args.itemId !== 'string' || !['close-up', 'side', 'overview'].includes(args.reason)) return error('Use the exact current session, revision, item and supported view reason.');
      return onProposal({ kind: 'view', ...args });
    },
  }, {
    name: 'chibi_lens_guide_propose_resume',
    description: 'Place a visible suggestion to resume a paused local task. Only the user can approve it. No item is confirmed or marked packed.',
    inputSchema: { type: 'object', properties: common, required: ['sessionId', 'expectedRevision'], additionalProperties: false },
    execute(args, { signal } = {}) {
      const denied = admitted(signal); if (denied) return denied;
      if (!bound(args) || Object.keys(args).length !== 2) return error('Use the exact current session and revision.');
      return onProposal({ kind: 'resume', ...args });
    },
  }];
  for (const tool of specs) {
    try { const registration = context.registerTool(tool, { signal: lifetime.signal }); registration?.then?.(undefined, fail); }
    catch { fail(); }
  }
  if (!failed) onStatus('registered');
  return () => {
    lifetime.abort();
    // Abort fences retained/in-flight handles; explicit unregistration also removes
    // the advertised surface on browsers whose registration ignores an options signal.
    for (const { name } of specs) {
      try { context.unregisterTool?.(name)?.then?.(undefined, () => {}); }
      catch { /* The aborted lifetime still denies every retained tool handle. */ }
    }
  };
}
