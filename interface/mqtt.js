'use strict';
// Client MQTT 3.1.1 minimal, sans dépendance (Node.js seul). QoS 0 uniquement : suffisant pour le TP.
// Usage : const c = createMqtt({ host, port, clientId, onMessage(topic, obj, raw), onState(connecté) }); c.subscribe('iot/#'); c.publish(topic, obj);
const net = require('net');

const str = s => { const b = Buffer.from(s, 'utf8'); return Buffer.concat([Buffer.from([b.length >> 8, b.length & 255]), b]); };
function remLen(n) { const out = []; do { let d = n % 128; n = Math.floor(n / 128); if (n > 0) d |= 128; out.push(d); } while (n > 0); return Buffer.from(out); }
const packet = (first, body) => Buffer.concat([Buffer.from([first]), remLen(body.length), body]);

module.exports = function createMqtt({ host, port = 1883, clientId = 'classe-noire', keepAlive = 30, onMessage, onState, log = () => {} }) {
  let sock = null, buf = Buffer.alloc(0), ok = false, pid = 1, timer = null, ping = null, stopped = false;
  const subs = new Set();

  function send(p) { if (sock && !sock.destroyed) sock.write(p); }
  function subscribePacket(topic) { return packet(0x82, Buffer.concat([Buffer.from([pid >> 8, pid & 255]), str(topic), Buffer.from([0])])); }

  function connect() {
    if (stopped) return;
    sock = net.connect({ host, port });
    sock.setNoDelay(true);
    sock.on('connect', () => {
      // CONNECT : protocole MQTT 4, clean session, keep-alive
      send(packet(0x10, Buffer.concat([str('MQTT'), Buffer.from([4, 2, keepAlive >> 8, keepAlive & 255]), str(clientId)])));
    });
    sock.on('data', d => { buf = Buffer.concat([buf, d]); parse(); });
    sock.on('error', e => log(`MQTT : ${e.code || e.message}`));
    sock.on('close', () => {
      const was = ok; ok = false; clearInterval(ping); buf = Buffer.alloc(0);
      if (was && onState) onState(false);
      if (!stopped) timer = setTimeout(connect, 3000);      // reconnexion automatique
    });
  }

  function parse() {
    for (;;) {
      if (buf.length < 2) return;
      let mul = 1, len = 0, i = 1, b;
      do { if (i >= buf.length) return; b = buf[i++]; len += (b & 127) * mul; mul *= 128; } while (b & 128);
      if (buf.length < i + len) return;
      const type = buf[0] >> 4, flags = buf[0] & 15, body = buf.subarray(i, i + len);
      buf = buf.subarray(i + len);
      if (type === 2) {                                           // CONNACK
        if (body[1] !== 0) { log(`MQTT : connexion refusée (code ${body[1]})`); sock.destroy(); return; }
        ok = true; if (onState) onState(true);
        for (const t of subs) { send(subscribePacket(t)); pid = (pid % 65534) + 1; }
        clearInterval(ping); ping = setInterval(() => send(Buffer.from([0xc0, 0])), keepAlive * 500);
      } else if (type === 3) {                                    // PUBLISH
        const tl = body.readUInt16BE(0), topic = body.toString('utf8', 2, 2 + tl);
        let off = 2 + tl; const qos = (flags >> 1) & 3;
        if (qos > 0) { const id = body.readUInt16BE(off); off += 2; send(Buffer.from([0x40, 2, id >> 8, id & 255])); }
        const raw = body.toString('utf8', off); let obj = null;
        try { obj = JSON.parse(raw); } catch { /* message non JSON : on garde le texte brut */ }
        try { onMessage(topic, obj, raw); } catch (e) { console.error('Erreur MQTT :', e); }
      }
    }
  }

  connect();
  return {
    get connected() { return ok; },
    subscribe(topic) { subs.add(topic); if (ok) { send(subscribePacket(topic)); pid = (pid % 65534) + 1; } },
    publish(topic, obj, retain = false) {
      if (!ok) return false;
      const payload = Buffer.from(typeof obj === 'string' ? obj : JSON.stringify(obj), 'utf8');
      send(packet(0x30 | (retain ? 1 : 0), Buffer.concat([str(topic), payload])));
      return true;
    },
    stop() { stopped = true; clearTimeout(timer); clearInterval(ping); if (sock) sock.destroy(); },
  };
};
