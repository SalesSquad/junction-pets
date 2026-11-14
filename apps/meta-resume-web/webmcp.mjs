/** Optional native WebMCP surface; no polyfill, microphone or network request. */
export function registerResumeTools(document, { read, dispatch, onStatus }) {
  const context = document.modelContext;
  if (typeof context?.registerTool !== 'function') {
    onStatus('unavailable');
    return () => {};
  }
  const lifetime = new AbortController();
  let failed = false;
  const fail = () => { failed = true; onStatus('failed'); };
  const cancelled = (signal) => {
    if (signal?.aborted) throw signal.reason ?? new DOMException('Cancelled', 'AbortError');
  };
  const problem = (message) => ({ error: true, message, next_action: 'Read the current local demo state and ask the user to use the visible controls. Never report a step complete.' });
  const specs = [
    {
      name: 'chibi_resume_read_state',
      description: 'Read this synthetic local Resume task. Say what the user confirmed and what remains uncertain. No live glasses or Chibi connection exists.',
      inputSchema: { type: 'object', properties: {}, required: [] },
      annotations: { readOnlyHint: true },
      execute: (args, { signal } = {}) => {
        cancelled(signal);
        if (args === null || typeof args !== 'object' || Array.isArray(args) || Object.keys(args).length) return problem('This tool takes no arguments.');
        return { ...read(), qualification: 'local-synthetic', next_action: 'Briefly explain the next unfinished step and its uncertainty. Stop and talk. Only the visible user confirmation can complete a step.' };
      },
    },
    {
      name: 'chibi_resume_propose_next',
      description: 'Resume an interrupted synthetic local task and propose its next step with no identity evidence. Does not confirm completion, capture an image, or perform an external action.',
      inputSchema: {
        type: 'object',
        properties: {
          taskId: { type: 'string', description: 'The exact task UUID returned by read_state.' },
          commandId: { type: 'string', description: 'A new UUID for this request; reuse it only for an identical retry.' },
          expectedRevision: { type: 'integer', description: 'The exact nonnegative safe-integer revision returned by read_state.' },
        },
        required: ['taskId', 'commandId', 'expectedRevision'],
      },
      execute: (args, { signal } = {}) => {
        cancelled(signal);
        if (args === null || typeof args !== 'object' || Array.isArray(args) || Object.keys(args).length !== 3 ||
            !['taskId', 'commandId', 'expectedRevision'].every((key) => Object.hasOwn(args, key))) return problem('Pass exactly taskId, commandId and expectedRevision.');
        const result = dispatch({ schemaVersion: 1, ...args, operation: 'resume', payload: { evidenceIds: [] } }, { authority: 'webmcp' });
        return { ...result, qualification: 'local-synthetic', next_action: result.error ? result.next_action : 'Explain the proposed next step in one short sentence. Stop and talk; the user must confirm with the visible control.' };
      },
    },
  ];
  onStatus('registered');
  for (const tool of specs) {
    try {
      const handle = context.registerTool(tool, { signal: lifetime.signal });
      if (typeof handle?.then === 'function') handle.then(undefined, fail);
    } catch { fail(); }
  }
  if (!failed) onStatus('registered');
  return () => lifetime.abort();
}
