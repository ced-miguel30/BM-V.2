// BM sin cobertura: la app y los últimos datos consultados quedan guardados en el móvil.
// Con conexión siempre se pide al servidor (datos frescos y versión nueva de BM); sin ella, se usa lo guardado.
const CACHE = 'bm-v1';

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));

async function red(peticion, clave = peticion) {
  const r = await fetch(peticion);
  if (r.ok) (await caches.open(CACHE)).put(clave, r.clone());
  return r;
}

self.addEventListener('fetch', (e) => {
  const r = e.request;
  const url = new URL(r.url);
  if (r.method !== 'GET' || url.origin !== location.origin) return;
  if (url.pathname.startsWith('/assets/')) {
    // Llevan la versión en el nombre: nunca cambian. ponytail: los de versiones viejas se acumulan; purgar si el caché crece.
    e.respondWith(caches.match(r).then((c) => c || red(r)));
    return;
  }
  const clave = r.mode === 'navigate' ? '/' : r;  // cualquier pantalla abre la misma app
  e.respondWith(red(r, clave).catch(() => caches.match(clave).then((c) => c || Response.error())));
});
