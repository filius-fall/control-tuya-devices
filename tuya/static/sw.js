const CACHE_NAME = 'tuya-v2';
const prefix = self.location.pathname.replace(/\/static\/sw\.js$/, '');
const ASSETS = [
  prefix + '/static/style.css',
  prefix + '/static/icon.svg',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') {
    return;
  }

  const url = new URL(request.url);
  const isSameOrigin = url.origin === self.location.origin;
  const isDocument = request.mode === 'navigate';

  if (!isSameOrigin) {
    return;
  }

  if (isDocument) {
    event.respondWith(fetch(request));
    return;
  }

  if (url.pathname.startsWith(prefix + '/status') || url.pathname.startsWith(prefix + '/statuses') || url.pathname.startsWith(prefix + '/metrics')) {
    event.respondWith(fetch(request));
    return;
  }

  event.respondWith(
    caches.match(request).then((response) => {
      if (response) return response;
      return fetch(request).then((networkResponse) => {
        if (!networkResponse || networkResponse.status !== 200 || networkResponse.type !== 'basic') {
          return networkResponse;
        }
        const responseToCache = networkResponse.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(request, responseToCache));
        return networkResponse;
      });
    })
  );
});
