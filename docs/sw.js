/* Service worker de Clan Stats. Su alcance es solo /Clan-stats/ (esta carpeta).
   - Solo guarda la "cascara" estatica (pagina, iconos, imagenes) para poder abrir la app sin conexion.
   - NUNCA toca data/: los datos de guerra, asaltos y cuentas regresivas siempre vienen de la red, asi no se sirven datos viejos. */
const CACHE = "clan-stats-shell-v2";
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const req = e.request, url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== location.origin) return;
  if (!url.pathname.startsWith(new URL("./", self.registration.scope).pathname)) return;
  if (url.pathname.includes("/data/")) return;               // datos: directo a la red, sin cache
  e.respondWith(
    fetch(req).then(res => { if (res.ok) { const c = res.clone(); caches.open(CACHE).then(k => k.put(req, c)); } return res; })
      .catch(() => caches.match(req).then(r => r || (req.mode === "navigate" ? caches.match("./") : Response.error())))
  );
});
