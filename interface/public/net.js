// Connexion WebSocket partagée par le hub, et la table.
const handlers = new Map();
let ws = null, name = '', look = null, joined = false, retries = 0, wantJoin = false;
const store = { get(k, d) { try { return localStorage.getItem(k) ?? d; } catch { return d; } }, set(k, v) { try { localStorage.setItem(k, v); } catch {} } };

export const Net = {
  id: 0, ping: 0,
  get joined() { return joined; },
  on(type, fn) { if (!handlers.has(type)) handlers.set(type, new Set()); handlers.get(type).add(fn); return () => handlers.get(type).delete(fn); },
  send(o) { if (ws && ws.readyState === 1) ws.send(JSON.stringify(o)); },
  join(n, l) { name = n; look = l; wantJoin = true; connect(); },
  updateLook(n, l) { name = n; look = l; Net.send({ t: 'look', name: n, look: l }); },
};
function emit(type, m) { const h = handlers.get(type); if (h) for (const fn of h) fn(m); const a = handlers.get('*'); if (a) for (const fn of a) fn(m); }

function connect() {
  ws = new WebSocket(`ws://${location.host}`);
  ws.onopen = () => { retries = 0; ws.send(JSON.stringify({ t: 'join', name, look, token: store.get('cn_token', '') })); };
  ws.onmessage = e => {
    let m; try { m = JSON.parse(e.data); } catch { return; }
    if (m.t === 'welcome') { Net.id = m.id; joined = true; store.set('cn_token', m.token); }
    if (m.t === 'pong') Net.ping = Math.round(performance.now() - m.c);
    emit(m.t, m);
  };
  ws.onclose = () => {
    if (joined && retries < 30) { retries++; emit('_reconnecting', {}); setTimeout(connect, 1500); }
    else if (!joined) emit('_failed', {});
  };
}
setInterval(() => Net.send({ t: 'ping', c: performance.now() }), 3000);
