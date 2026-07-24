const CACHE_NAME = 'logistic-hub-v2';
const STATIC_URLS = [
  '/static/css/app.css',
  '/static/js/app.js',
  '/static/manifest.json',
  '/static/img/icon-192.png',
  '/static/img/icon-512.png',
];

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function (cache) {
      return cache.addAll(STATIC_URLS);
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (cacheNames) {
      return Promise.all(
        cacheNames.filter(function (name) {
          return name !== CACHE_NAME;
        }).map(function (name) {
          return caches.delete(name);
        })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', function (event) {
  var url = new URL(event.request.url);

  // Static assets: cache-first
  if (STATIC_URLS.some(function (s) { return url.pathname.startsWith(s); }) || url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(event.request).then(function (response) {
        return response || fetch(event.request);
      })
    );
    return;
  }

  // API calls and navigation pages: network-first, fallback to cache
  event.respondWith(
    fetch(event.request)
      .then(function (response) {
        // Cache a copy of successful responses (for offline fallback)
        var clone = response.clone();
        caches.open(CACHE_NAME).then(function (cache) {
          cache.put(event.request, clone);
        });
        return response;
      })
      .catch(function () {
        return caches.match(event.request).then(function (response) {
          return response || new Response('Offline', { status: 503 });
        });
      })
  );
});
