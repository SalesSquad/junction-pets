// Only app-shell assets; no candidate input, drafts or third-party resources.
const CACHE = 'proofmatch-espoo-shell-v1';
const ASSETS = ['./', './index.html', './styles.css', './app.mjs', './matcher.mjs', './data.mjs', './benchmark.mjs'];
self.addEventListener('install', event => event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS))));
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin || !ASSETS.some(path => new URL(path, self.registration.scope).pathname === url.pathname)) return;
  event.respondWith(fetch(event.request).catch(() => caches.match(event.request, { ignoreSearch: true }).then(cached => cached || Response.error())));
});
