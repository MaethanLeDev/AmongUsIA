'use strict';
// CLASSE NOIRE · L'espion — interface spectateur : la table 3D où les IA des Raspberry Pi débattent.
// Le serveur écoute le broker MQTT (en lecture seule) et retransmet la partie aux navigateurs par WebSocket.
// Aucune dépendance : Node.js seul (Three.js est fourni dans public/vendor/).
const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const os = require('os');
const createMqtt = require('./mqtt.js');
const createSpectacle = require('./spectacle.js');

const PORT = Number(process.env.PORT) || 5050;
const PUBLIC = path.join(__dirname, 'public');
const BROKERS = (process.env.MQTT_HOST || 'amongus.local,10.109.150.215').split(',').map(s => s.trim()).filter(Boolean);
const MQTT_PORT = Number(process.env.MQTT_PORT) || 1883;
// Tout sauf iot/role/+ : l'interface ne doit jamais connaître l'espion avant le résultat
const TOPICS = ['iot/joueurs/+', 'iot/partie/etat', 'iot/partie/parole', 'iot/partie/verdict', 'iot/partie/resultat',
  'iot/partie/stats', 'iot/capteurs/+/temperature', 'iot/chat/+', 'iot/votes/+'];

const conns = new Set();
function sendAll(obj) { const s = JSON.stringify(obj); for (const c of conns) c.send(s); }
const log = s => console.log('  ' + s);
const spectacle = createSpectacle({ diffuser: sendAll, log });

// ---------------------------------------------------------------- WebSocket minimal (RFC 6455)
class Conn {
  constructor(socket) {
    this.socket = socket; this.buf = Buffer.alloc(0); this.frags = []; this.closed = false;
    socket.setNoDelay(true); socket.setKeepAlive(true, 15000);
    socket.on('data', d => this.feed(d));
    socket.on('close', () => this.close());
    socket.on('error', () => { socket.destroy(); this.close(); });
  }
  close() { if (!this.closed) { this.closed = true; conns.delete(this); } }
  feed(chunk) {
    this.buf = Buffer.concat([this.buf, chunk]);
    for (;;) {
      const b = this.buf;
      if (b.length < 2) return;
      const fin = !!(b[0] & 0x80), op = b[0] & 0x0f, masked = !!(b[1] & 0x80);
      let len = b[1] & 0x7f, off = 2;
      if (len === 126) { if (b.length < 4) return; len = b.readUInt16BE(2); off = 4; }
      else if (len === 127) { if (b.length < 10) return; len = Number(b.readBigUInt64BE(2)); off = 10; }
      if (len > 1 << 16) { this.socket.destroy(); return; }   // un spectateur n'envoie que des pings
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
        if (fin) { const t = Buffer.concat(this.frags).toString('utf8'); this.frags = []; this.onText(t); }
      }
    }
  }
  onText(t) {
    let m; try { m = JSON.parse(t); } catch { return; }
    if (m && m.t === 'ping') this.send(JSON.stringify({ t: 'pong', c: m.c }));
  }
  raw(first, payload) {
    if (this.socket.destroyed) return;
    const n = payload.length; let head;
    if (n < 126) head = Buffer.from([first, n]);
    else if (n < 65536) head = Buffer.from([first, 126, n >> 8, n & 255]);
    else { head = Buffer.alloc(10); head[0] = first; head[1] = 127; head.writeBigUInt64BE(BigInt(n), 2); }
    this.socket.write(Buffer.concat([head, payload]));
  }
  send(str) { if (this.closed || this.socket.writableLength > 2 * 1024 * 1024) return; this.raw(0x81, Buffer.from(str)); }
}

// ---------------------------------------------------------------- HTTP statique (+ /api/etat pour déboguer)
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon', '.json': 'application/json' };
const server = http.createServer((req, res) => {
  let url; try { url = decodeURIComponent((req.url || '/').split('?')[0]); } catch { res.writeHead(400); return res.end(); }
  if (url === '/api/etat') { res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' }); return res.end(JSON.stringify(spectacle.etat(), null, 2)); }
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
  const c = new Conn(socket); conns.add(c);
  c.send(JSON.stringify(spectacle.init()));
});
server.on('error', e => { console.error(`\n  Port ${PORT} indisponible (${e.code}). Essaie :  set PORT=4141 && node server.js\n`); process.exit(1); });
server.listen(PORT, '0.0.0.0', () => {
  console.log('\n  🕵  CLASSE NOIRE · L\'espion — interface spectateur lancée\n');
  console.log(`  Sur cet ordi :      http://localhost:${PORT}`);
  const skip = /vmware|virtualbox|vethernet|wsl|docker|loopback|bluetooth/i;
  for (const [name, l] of Object.entries(os.networkInterfaces())) {
    if (skip.test(name)) continue;
    for (const a of l || []) if (a.family === 'IPv4' && !a.internal) console.log(`  Depuis le réseau :  http://${a.address}:${PORT}   (${name})`);
  }
  console.log(`\n  Broker MQTT : ${BROKERS.join(' ou ')}:${MQTT_PORT}   (autre broker : set MQTT_HOST=<ip>)`);
  console.log('  Ctrl+C pour arrêter.\n');

  const mqtt = createMqtt({
    hosts: BROKERS, port: MQTT_PORT, clientId: 'interface-' + crypto.randomBytes(3).toString('hex'), log,
    onMessage: spectacle.onMqtt,
    onState: (up, hote) => { log(up ? `connecté au broker ${hote}:${MQTT_PORT}` : `broker ${hote} perdu, nouvelle tentative…`); spectacle.setBroker(hote, up); },
  });
  for (const t of TOPICS) mqtt.subscribe(t);
});
process.on('uncaughtException', e => console.error('Exception :', e));
