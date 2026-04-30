const CACHE = 'bfd-hydrants-v46';
const SHELL = ['./','./index.html','./manifest.json'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  const url = e.request.url;
  // Never cache external API calls — always live
  if (url.includes('maps.googleapis.com') ||
      url.includes('maps.gstatic.com') ||
      url.includes('gisportal.boston.gov') ||
      url.includes('bostonplans.org') ||
      url.includes('boston_buildings.json') ||
      url.includes('boston_hydrants.json') ||
      url.includes('boston_districts.json') ||
      url.includes('boston_boxes.json') ||
      url.includes('running_cards.json') ||
      url.includes('/running_cards/')) {
    return;
  }
  e.respondWith(
    caches.match(e.request).then(cached => cached || fetch(e.request))
  );
});
