// Connexion WebSocket au serveur. Le spectateur ne fait que recevoir la partie ; reconnexion automatique.
const handlers = new Map();
let ws = null, essais = 0;

export const Net = {
  ping: 0, connecte: false,
  on(type, fn) { if (!handlers.has(type)) handlers.set(type, new Set()); handlers.get(type).add(fn); return () => handlers.get(type).delete(fn); },
};
function emit(type, m) { const h = handlers.get(type); if (h) for (const fn of h) fn(m); }

function connect() {
  ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}`);
  ws.onopen = () => { essais = 0; Net.connecte = true; emit('_ouvert', {}); };
  ws.onmessage = e => {
    let m; try { m = JSON.parse(e.data); } catch { return; }
    if (m.t === 'pong') Net.ping = Math.round(performance.now() - m.c);
    emit(m.t, m);
  };
  ws.onclose = () => { Net.connecte = false; emit('_ferme', {}); setTimeout(connect, Math.min(10000, 1000 * ++essais)); };
}
connect();
setInterval(() => { if (ws && ws.readyState === 1) ws.send(JSON.stringify({ t: 'ping', c: performance.now() })); }, 3000);
