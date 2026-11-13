/** Pure, fail-closed catalogue selection. Product URLs are not auth grants. */
const SLUG = /^junction-[a-z0-9]+(?:-[a-z0-9]+)*$/;
const DEFAULT_SLUG = 'junction-mariadb';

export function readSelection(search) {
  const values = new URLSearchParams(search).getAll('pet');
  if (values.length === 0) return {kind: 'default', slug: DEFAULT_SLUG};
  if (values.length !== 1 || values[0].length > 96 || !SLUG.test(values[0])) return {kind: 'invalid'};
  return {kind: 'explicit', slug: values[0]};
}

export function resolveSelection(all, filtered, selection) {
  if (selection.kind === 'invalid') return {pet: null, reason: 'invalid'};
  if (selection.kind === 'explicit') {
    const found = all.find(pet => pet.slug === selection.slug);
    if (!found) return {pet: null, reason: 'unknown'};
    if (!filtered.some(pet => pet.slug === found.slug)) return {pet: null, reason: 'filtered'};
    return {pet: found, reason: null};
  }
  const pet = filtered.find(item => item.slug === DEFAULT_SLUG) ?? filtered[0] ?? null;
  return {pet, reason: pet ? null : 'empty'};
}

/** Construct a shareable URL containing exactly one public, non-secret pet selector. */
export function petHref(currentHref, slug) {
  if (slug.length > 96 || !SLUG.test(slug)) throw new Error('Invalid companion slug');
  const url = new URL(currentHref);
  const localDevelopment = url.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(url.hostname);
  if ((url.protocol !== 'https:' && !localDevelopment) || url.username || url.password) {
    throw new Error('Companion URL must be HTTPS');
  }
  url.search = '';
  url.hash = '';
  url.searchParams.set('pet', slug);
  return url.href;
}
