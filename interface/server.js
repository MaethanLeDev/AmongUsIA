'use strict';
// CLASSE NOIRE — hub 3D + jeu de table, relié aux Raspberry Pi (MQTT / API). Serveur autoritatif, aucune dépendance (Node.js seul).
const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const os = require('os');
const createTable = require('./table.js');
const createAgents = require('./agents.js');

const PORT = Number(process.env.PORT) || 3939;
const PUBLIC = path.join(__dirname, 'public');
const MAX_USERS = 12;
const ARCHS = ['stratege', 'vengeur', 'sourire', 'reine', 'ombre', 'prodige'];

const users = new Map();       // id -> user
let nextId = 1;
const hub = { mode: 'hub', hostId: 0, inGame: false, board: [], playing: new Set() };

const cleanText = (s, n = 200) => String(s || '').replace(/[\u0000-\u001f\u007f<>]/g, ' ').trim().slice(0, n);
const hexOk = s => /^#[0-9a-fA-F]{6}$/.test(String(s || ''));
function cleanLook(l) {
  l = l || {};
  const out = { arch: ARCHS.includes(l.arch) ? l.arch : 'stratege' };
  for (const k of ['hair', 'eyes', 'accent']) if (hexOk(l[k])) out[k] = String(l[k]).toLowerCase();
  return out;
}

const host = {
  sendUser(id, obj) { const u = users.get(id); if (u && u.conn && !u.conn.closed) u.conn.send(JSON.stringify(obj)); },
  getUsers: () => [...users.values()],
  hostId: () => hub.hostId,
  setInGame(v) {
    if (hub.inGame !== !!v) { hub.inGame = !!v; hub.playing = new Set(v ? [...users.values()].filter(u => u.connected).map(u => u.id) : []); broadcastHub(); }
  },
  recordWinner(mode, name, score) { hub.board.unshift({ mode, name, score, at: Date.now() }); hub.board = hub.board.slice(0, 8); broadcastHub(); },
};
const table = createTable(host);
// Pont vers les Raspberry Pi (MQTT + API HTTP) : voir AGENTS.md
const agents = createAgents({
  host, table,
  users, newId: () => nextId++, cleanText, cleanLook, ARCHS,
  isInGame: () => hub.inGame,
  broadcastHub: () => broadcastHub(),
  hubChat: (name, text) => sendAllUsers({ t: 'hchat', from: 0, name, text }),
  reassignHost: () => reassignHost(),
});
host.onChat = msg => agents.onTableChat(msg);

function sendAllUsers(obj) { const s = JSON.stringify(obj); for (const u of users.values()) if (u.conn && !u.conn.closed) u.conn.send(s); }
function hubState() {
  return {
    t: 'hub', mode: hub.mode, host: hub.hostId, inGame: hub.inGame, board: hub.board, playing: [...hub.playing],
    users: [...users.values()].filter(u => u.connected).map(u => ({ id: u.id, name: u.name, look: u.look })),
  };
}
function broadcastHub() { sendAllUsers(hubState()); }

function setMode(mode) {
  if (!['hub', 'table'].includes(mode) || hub.mode === mode) return;
  table.close();
  hub.mode = mode; hub.inGame = false; hub.playing = new Set();
  broadcastHub();                        // le client doit connaître le nouveau mode avant de recevoir l'état du moteur
  const list = [...users.values()].filter(u => u.connected);
  if (mode === 'table') table.open(list);
}
function reassignHost() {
  const cur = users.get(hub.hostId);
  if (cur && cur.connected && !cur.ext) return;
  const n = [...users.values()].find(u => u.connected && !u.ext);   // un Raspberry Pi ne peut pas être hôte
  hub.hostId = n ? n.id : 0;
}

function onMessage(conn, text) {
  let m; try { m = JSON.parse(text); } catch { return; }
  if (!m || typeof m !== 'object') return;
  if (m.t === 'ping') return conn.send(JSON.stringify({ t: 'pong', c: m.c }));
  let u = conn.user;

  if (m.t === 'join') {
    if (u) return;
    const tok = String(m.token || '');
    const back = tok && [...users.values()].find(x => x.token === tok);
    if (back) {
      if (back.conn && back.conn !== conn && !back.conn.closed) { back.conn.user = null; back.conn.socket.destroy(); }
      back.conn = conn; back.connected = true; conn.user = back; u = back;
      if (m.name) back.name = cleanText(m.name, 16) || back.name;
      if (m.look) back.look = cleanLook(m.look);
    } else {
      if ([...users.values()].filter(x => x.connected).length >= MAX_USERS) return conn.send(JSON.stringify({ t: 'refused', text: 'Salon plein.' }));
      u = { id: nextId++, name: cleanText(m.name, 16) || 'Élève', token: crypto.randomBytes(8).toString('hex'), conn, connected: true, look: cleanLook(m.look) };
      users.set(u.id, u); conn.user = u;
    }
    reassignHost();
    console.log(`+ ${u.name} (${conn.addr})`);
    conn.send(JSON.stringify({ t: 'welcome', id: u.id, token: u.token }));
    broadcastHub();
    if (hub.mode === 'table') (back ? table.onReconnect(u) : table.addUser(u));
    return;
  }
  if (!u) return;

  const isHost = hub.hostId === u.id;
  switch (m.t) {
    case 'look': u.look = cleanLook(m.look); if (m.name) u.name = cleanText(m.name, 16) || u.name; broadcastHub(); if (hub.mode === 'table') table.addUser(u); return;
    case 'mode': if (isHost && (!hub.inGame || m.force)) setMode(m.mode); return;
    case 'tohub': if (isHost) setMode('hub'); return;
    case 'hchat': { const t = cleanText(m.text); if (t) sendAllUsers({ t: 'hchat', from: u.id, name: u.name, text: t }); return; }
  }
  if (hub.mode === 'table') table.onMessage(u, m);
}

function onClose(conn) {
  if (conn.closed) return; conn.closed = true;
  const u = conn.user; if (!u) return;
  if (u.conn !== conn) return;
  u.connected = false;
  console.log(`- ${u.name}`);
  if (hub.mode === 'table') table.onDisconnect(u);
  reassignHost();
  const humansLeft = () => [...users.values()].some(x => x.connected && !x.ext);
  if (!humansLeft()) { table.close(); hub.mode = 'hub'; hub.inGame = false; setTimeout(() => { if (!humansLeft()) agents.keepOnlyAgents(); }, 60000); }
  broadcastHub();
  setTimeout(() => { if (!u.connected && !hub.inGame && users.get(u.id) === u) { users.delete(u.id); broadcastHub(); } }, 25000);
}

// ---------------------------------------------------------------- WebSocket minimal (RFC 6455)
class Conn {
  constructor(socket, addr) {
    this.socket = socket; this.addr = addr; this.buf = Buffer.alloc(0); this.frags = []; this.user = null; this.closed = false;
    socket.setNoDelay(true); socket.setKeepAlive(true, 15000);
    socket.on('data', d => this.feed(d));
    socket.on('close', () => onClose(this));
    socket.on('error', () => { socket.destroy(); onClose(this); });
  }
  feed(chunk) {
    this.buf = Buffer.concat([this.buf, chunk]);
    for (;;) {
      const b = this.buf;
      if (b.length < 2) return;
      const fin = !!(b[0] & 0x80), op = b[0] & 0x0f, masked = !!(b[1] & 0x80);
      let len = b[1] & 0x7f, off = 2;
      if (len === 126) { if (b.length < 4) return; len = b.readUInt16BE(2); off = 4; }
      else if (len === 127) { if (b.length < 10) return; len = Number(b.readBigUInt64BE(2)); off = 10; }
      if (len > 1 << 18) { this.socket.destroy(); return; }
      const total = off + (masked ? 4 : 0) + len;
      if (b.length < total) return;
      const payload = Buffer.from(b.subarray(off + (masked ? 4 : 0), total));
      if (masked) { const mk = b.subarray(off, off + 4); for (let i = 0; i < payload.length; i++) payload[i] ^= mk[i & 3]; }
      this.buf = b.subarray(total);
      if (op === 0x8) { this.socket.end(); return; }
      if (op === 0x9) { this.raw(0x8a, payload); continue; }
      if (op === 0xa) continue;
      if (op === 0x1 || op === 0x0) {
        this.frags.push(payload);
        if (fin) { const t = Buffer.concat(this.frags).toString('utf8'); this.frags = []; try { onMessage(this, t); } catch (e) { console.error('Erreur message :', e); } }
      }
    }
  }
  raw(first, payload) {
    if (this.socket.destroyed) return;
    const n = payload.length; let head;
    if (n < 126) head = Buffer.from([first, n]);
    else if (n < 65536) head = Buffer.from([first, 126, n >> 8, n & 255]);
    else { head = Buffer.alloc(10); head[0] = first; head[1] = 127; head.writeBigUInt64BE(BigInt(n), 2); }
    this.socket.write(Buffer.concat([head, payload]));
  }
  send(str) { if (this.socket.writableLength > 2 * 1024 * 1024) return; this.raw(0x81, Buffer.from(str)); }
}

// ---------------------------------------------------------------- HTTP statique
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon', '.json': 'application/json' };
const server = http.createServer((req, res) => {
  let url; try { url = decodeURIComponent((req.url || '/').split('?')[0]); } catch { res.writeHead(400); return res.end(); }
  if (url.startsWith('/api/')) return agents.http(req, res, url);
  if (url === '/') url = '/index.html';
  const file = path.normalize(path.join(PUBLIC, url));
  if (!file.startsWith(PUBLIC + path.sep)) { res.writeHead(403); return res.end('Interdit'); }
  fs.readFile(file, (err, data) => {
    if (err) { res.writeHead(404); return res.end('Introuvable'); }
    res.writeHead(200, { 'Content-Type': MIME[path.extname(file)] || 'application/octet-stream', 'Cache-Control': url.startsWith('/vendor/') ? 'max-age=86400' : 'no-cache' });
    res.end(data);
  });
});
server.on('upgrade', (req, socket) => {
  const key = req.headers['sec-websocket-key'];
  if (!key || (req.headers.upgrade || '').toLowerCase() !== 'websocket') { socket.destroy(); return; }
  const accept = crypto.createHash('sha1').update(key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest('base64');
  socket.write('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n' + `Sec-WebSocket-Accept: ${accept}\r\n\r\n`);
  new Conn(socket, (req.socket.remoteAddress || '').replace('::ffff:', ''));
});
server.on('error', e => { console.error(`\n  Port ${PORT} indisponible (${e.code}). Essaie :  set PORT=4141 && node server.js\n`); process.exit(1); });
server.listen(PORT, '0.0.0.0', () => {
  console.log('\n  ♟  CLASSE NOIRE — serveur lancé\n');
  console.log(`  Toi (cet ordi) :   http://localhost:${PORT}`);
  const skip = /vmware|virtualbox|vethernet|wsl|docker|loopback|bluetooth/i;
  for (const [name, l] of Object.entries(os.networkInterfaces())) {
    if (skip.test(name)) continue;
    for (const a of l || []) if (a.family === 'IPv4' && !a.internal) console.log(`  Tes amis (${name}) :  http://${a.address}:${PORT}`);
  }
  console.log('\n  Ctrl+C pour arrêter.\n');
  agents.start();
});
process.on('uncaughtException', e => console.error('Exception :', e));
