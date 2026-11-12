/** Only local previews may be exercised by the browser acceptance harness. */
export function localPreviewBase(input) {
  const base = new URL(input);
  if (!['localhost', '127.0.0.1'].includes(base.hostname) || base.protocol !== 'http:') {
    throw new Error('Browser smoke must target a local, non-production preview.');
  }
  if (base.search || base.hash || base.username || base.password) {
    throw new Error('Browser smoke preview URL must contain only the local mount path.');
  }
  // Do not let an absolute /?pet=... selector silently escape /junction/.
  if (!base.pathname.endsWith('/')) base.pathname += '/';
  return base;
}

/** Keep the browser on the current mount throughout every selection. */
export function previewSelectionUrl(base, query) {
  return new URL(`?${query}`, base);
}
