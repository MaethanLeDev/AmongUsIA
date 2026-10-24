'use strict';
// Outils des tests de l'interface : un faux broker MQTT sur un port libre de cette machine, et de quoi attendre un événement.
// Aucune dépendance : node:net seulement. Ce fichier n'est pas un test (node --test ne lance que les *.test.js).
const net = require('node:net');

// Découpe un paquet MQTT complet en tête de buf, ou null s'il n'est pas encore arrivé en entier
function extraire(buf) {
  if (buf.length < 2) return null;
  let taille = 0, mult = 1, i = 1, octet;
  do { if (i >= buf.length) return null; octet = buf[i++]; taille += (octet & 127) * mult; mult *= 128; } while (octet & 128);
  if (buf.length < i + taille) return null;
  return { type: buf[0] >> 4, drapeaux: buf[0] & 15, corps: buf.subarray(i, i + taille), brut: buf.subarray(0, i + taille), reste: buf.subarray(i + taille) };
}

function tailleRestante(n) {
  const octets = [];
  do { let d = n % 128; n = Math.floor(n / 128); if (n > 0) d |= 128; octets.push(d); } while (n > 0);
  return Buffer.from(octets);
}
const chaine = s => { const b = Buffer.from(s, 'utf8'); return Buffer.concat([Buffer.from([b.length >> 8, b.length & 255]), b]); };

// Paquet PUBLISH envoyé par le broker à un client
function paquetPublish(topic, contenu, { qos = 0, retenu = false, id = 1 } = {}) {
  const message = Buffer.isBuffer(contenu) ? contenu : Buffer.from(typeof contenu === 'string' ? contenu : JSON.stringify(contenu), 'utf8');
  const corps = Buffer.concat([chaine(topic), qos ? Buffer.from([id >> 8, id & 255]) : Buffer.alloc(0), message]);
  return Buffer.concat([Buffer.from([0x30 | (qos << 1) | (retenu ? 1 : 0)]), tailleRestante(corps.length), corps]);
}

// Les filtres d'un paquet SUBSCRIBE
function filtresAbonnement(corps) {
  const filtres = [];
  for (let pos = 2; pos < corps.length;) { const n = corps.readUInt16BE(pos); filtres.push(corps.toString('utf8', pos + 2, pos + 2 + n)); pos += 2 + n + 1; }
  return filtres;
}

// Un filtre MQTT (+ et #) correspond-il au topic ?
function correspond(filtre, topic) {
  const f = filtre.split('/'), t = topic.split('/');
  for (let i = 0; i < f.length; i++) {
    if (f[i] === '#') return true;
    if (i >= t.length || (f[i] !== '+' && f[i] !== t[i])) return false;
  }
  return f.length === t.length;
}

// Faux broker : note les paquets reçus, répond CONNACK (code réglable), et envoie ce qu'on lui demande au dernier client
function fauxBroker({ codeConnack = 0 } = {}) {
  const b = { paquets: [], clients: [], port: 0 };
  const serveur = net.createServer(sock => {
    b.clients.push(sock);
    let buf = Buffer.alloc(0);
    sock.on('data', d => {
      buf = Buffer.concat([buf, d]);
      for (let p = extraire(buf); p; p = extraire(buf)) {
        buf = p.reste; b.paquets.push(p);
        if (p.type === 1) sock.write(Buffer.from([0x20, 2, 0, codeConnack]));
      }
    });
    sock.on('error', () => {});
  });
  b.demarrer = () => new Promise(fin => serveur.listen(0, '127.0.0.1', () => { b.port = serveur.address().port; fin(b); }));
  b.envoyer = buf => b.clients[b.clients.length - 1].write(buf);
  b.couper = () => { for (const s of b.clients) s.destroy(); };
  b.fermer = () => new Promise(fin => { b.couper(); serveur.close(() => fin()); });
  b.de = type => b.paquets.filter(p => p.type === type);
  b.abonnements = () => b.de(8).flatMap(p => filtresAbonnement(p.corps));
  return b;
}

// Attend que condition() soit vraie (sans setTimeout, qu'un test peut simuler avec mock.timers)
async function attendre(condition, delai = 3000, quoi = 'la condition') {
  const limite = Date.now() + delai;
  while (!condition()) {
    if (Date.now() > limite) throw new Error(`délai dépassé en attendant ${quoi}`);
    await new Promise(fin => setImmediate(fin));
  }
}

module.exports = { extraire, tailleRestante, chaine, paquetPublish, filtresAbonnement, correspond, fauxBroker, attendre };
