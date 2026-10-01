// Keeps TinyTalk working without a connection. Fresh files win when online;
// the saved copy is used when offline.
const CACHE = 'tinytalk-v6';
const SHELL = ['./', 'index.html', 'styles.css', 'app.js', 'core.js', 'camera.js', 'cage.js', 'record.js', 'model.json',
  'manifest.webmanifest', 'icons/icon-192.png', 'icons/icon-512.png'];
const VOICE = ['voice/index.json', 'voice/playful_1.wav', 'voice/playful_2.wav', 'voice/sleepy_1.wav', 'voice/sleepy_2.wav', 'voice/hungry_1.wav', 'voice/hungry_2.wav', 'voice/potty_1.wav', 'voice/potty_2.wav', 'voice/sad_1.wav', 'voice/sad_2.wav', 'voice/lonely_1.wav', 'voice/lonely_2.wav', 'voice/anxious_1.wav', 'voice/anxious_2.wav', 'voice/alert_1.wav', 'voice/alert_2.wav', 'voice/content_1.wav', 'voice/content_2.wav', 'voice/stressed_1.wav', 'voice/stressed_2.wav', 'voice/lost_1.wav'];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll([...SHELL, ...VOICE])).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  event.respondWith(fetch(event.request).then((response) => {
    const copy = response.clone();
    if (response.ok) caches.open(CACHE).then((cache) => cache.put(event.request, copy));
    return response;
  }).catch(() => caches.match(event.request, { ignoreSearch: true })));
});
