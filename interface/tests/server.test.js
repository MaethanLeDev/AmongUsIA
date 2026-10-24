'use strict';
// server.js lancé tel quel (processus enfant) : il écoute le faux broker, sert les fichiers, /api/etat et le WebSocket.
const { test, describe, before, after } = require('node:test');
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const crypto = require('node:crypto');
const http = require('node:http');
const net = require('node:net');
const path = require('node:path');
const { fauxBroker, attendre, paquetPublish, correspond } = require('./aides.js');

const PARTIE = 1761200000;
let broker, serveur, port, sortie = '';

// Un port libre pour le serveur HTTP (server.js ne sait pas écouter sur le port 0)
const portLibre = () => new Promise(fin => { const s = net.createServer().listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => fin(p)); }); });

function requete(chemin) {
  return new Promise((fin, echec) => {
    http.get({ host: '127.0.0.1', port, path: chemin }, res => {
      let corps = '';
      res.setEncoding('utf8');
      res.on('data', d => { corps += d; });
      res.on('end', () => fin({ code: res.statusCode, type: res.headers['content-type'], corps }));
    }).on('error', echec);
  });
}
const etatServeur = async () => JSON.parse((await requete('/api/etat')).corps);
// Relit /api/etat jusqu'à ce que condition(etat) soit vraie
async function attendreEtat(condition, quoi) {
  const limite = Date.now() + 3000;
  for (;;) {
    const etat = await etatServeur();
    if (condition(etat)) return etat;
    if (Date.now() > limite) throw new Error(`délai dépassé en attendant ${quoi}`);
  }
}

// Client WebSocket minimal : handshake, lecture des trames du serveur, envoi de trames masquées
function ouvrirWs(entetes = {}) {
  return new Promise((fin, echec) => {
    const cle = crypto.randomBytes(16).toString('base64');
    const req = http.request({ host: '127.0.0.1', port, path: '/', headers: {
      Connection: 'Upgrade', Upgrade: 'websocket', 'Sec-WebSocket-Version': '13', 'Sec-WebSocket-Key': cle, ...entetes } });
    req.on('upgrade', (res, socket, debut) => {
      const ws = { res, cle, socket, trames: [], ferme: false };
      let buf = Buffer.alloc(0);
      const lire = d => {
        buf = Buffer.concat([buf, d]);
        for (;;) {
          if (buf.length < 2) return;
          let n = buf[1] & 127, off = 2;
          if (n === 126) { if (buf.length < 4) return; n = buf.readUInt16BE(2); off = 4; }
          else if (n === 127) { if (buf.length < 10) return; n = Number(buf.readBigUInt64BE(2)); off = 10; }
          if (buf.length < off + n) return;
          ws.trames.push({ op: buf[0] & 15, donnees: buf.subarray(off, off + n) });
          buf = buf.subarray(off + n);
        }
      };
      socket.on('data', lire);
      socket.on('close', () => { ws.ferme = true; });
      socket.on('error', () => {});
      if (debut.length) lire(debut);
      ws.messages = () => ws.trames.filter(t => t.op === 1).map(t => JSON.parse(t.donnees.toString('utf8')));
      ws.envoyer = (op, donnees) => {
        const masque = crypto.randomBytes(4), corps = Buffer.from(donnees);
        for (let i = 0; i < corps.length; i++) corps[i] ^= masque[i & 3];
        socket.write(Buffer.concat([Buffer.from([0x80 | op, 0x80 | corps.length]), masque, corps]));
      };
      fin(ws);
    });
    req.on('response', res => echec(new Error(`pas d'upgrade : HTTP ${res.statusCode}`)));
    req.on('error', echec);
    req.end();
  });
}

before(async () => {
  broker = await fauxBroker().demarrer();
  port = await portLibre();
  serveur = spawn(process.execPath, [path.join(__dirname, '..', 'server.js')], {
    env: { ...process.env, PORT: String(port), MQTT_HOST: '127.0.0.1', MQTT_PORT: String(broker.port) },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  serveur.stdout.on('data', d => { sortie += d; });
  serveur.stderr.on('data', d => { sortie += d; });
  await attendre(() => broker.abonnements().length >= 9, 5000, 'les abonnements du serveur');
});
after(async () => {
  serveur.kill();
  await broker.fermer();
});

describe('MQTT en lecture seule', () => {
  test('aucun abonnement ne donne accès à iot/role', () => {
    const filtres = broker.abonnements();
    assert.equal(filtres.length, 9);
    for (const f of filtres) assert.ok(!correspond(f, 'iot/role/rpi1'), `${f} laisserait voir le rôle`);
  });

  test('abonné à tous les messages du jeu', () => {
    for (const topic of ['iot/joueurs/rpi1', 'iot/partie/etat', 'iot/partie/parole', 'iot/partie/verdict', 'iot/partie/resultat',
      'iot/partie/stats', 'iot/capteurs/rpi1/temperature', 'iot/chat/rpi1', 'iot/votes/rpi1']) {
      assert.ok(broker.abonnements().some(f => correspond(f, topic)), topic);
    }
  });

  test('identifiant client propre à l\'interface (pas celui du maître du jeu)', () => {
    const corps = broker.de(1)[0].corps;
    const n = corps.readUInt16BE(10);
    assert.match(corps.toString('utf8', 12, 12 + n), /^interface-[0-9a-f]{6}$/);
  });

  test('ne publie rien', () => {
    assert.equal(broker.de(3).length, 0);
  });
});

describe('HTTP', () => {
  test('/api/etat : en attente du maître du jeu au démarrage', async () => {
    const etat = await etatServeur();
    assert.equal(etat.partie.etat, 'attente');
    assert.deepEqual(etat.broker, { hote: '127.0.0.1', connecte: true });
  });

  test('/api/etat suit les messages du broker', async () => {
    broker.envoyer(paquetPublish('iot/joueurs/rpi1', { id: 'rpi1', en_ligne: true, nom: 'Sherlock' }, { retenu: true }));
    broker.envoyer(paquetPublish('iot/partie/etat', { etat: 'inscription', min: 3, max: 12, debut: null }, { retenu: true }));
    const etat = await attendreEtat(e => e.partie.etat === 'inscription', 'la phase d\'inscription');
    assert.equal(etat.joueurs.rpi1.nom, 'Sherlock');
  });

  test('/api/etat ne révèle pas un rôle, même envoyé par erreur par le broker', async () => {
    broker.envoyer(paquetPublish('iot/role/rpi1', { role: 'espion', partie: PARTIE }));
    broker.envoyer(paquetPublish('iot/partie/stats', { parties: 0 }));
    const etat = await attendreEtat(e => e.stats, 'les statistiques');   // reçues après le rôle : le rôle a été traité
    assert.ok(!JSON.stringify(etat).includes('espion'));
  });

  test('page d\'accueil', async () => {
    const r = await requete('/');
    assert.equal(r.code, 200);
    assert.equal(r.type, 'text/html; charset=utf-8');
  });

  test('fichier introuvable', async () => {
    assert.equal((await requete('/absent.js')).code, 404);
  });

  test('sortie du dossier public interdite', async () => {
    assert.equal((await requete('/../server.js')).code, 403);
    assert.equal((await requete('/%2e%2e/server.js')).code, 403);
  });

  test('adresse mal encodée', async () => {
    assert.equal((await requete('/%E0%A4%A')).code, 400);
  });
});

describe('WebSocket', () => {
  test('handshake : Sec-WebSocket-Accept calculé selon la RFC 6455', async () => {
    const ws = await ouvrirWs();
    const attendu = crypto.createHash('sha1').update(ws.cle + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest('base64');
    assert.equal(ws.res.statusCode, 101);
    assert.equal(ws.res.headers['sec-websocket-accept'], attendu);
    ws.socket.destroy();
  });

  test('le navigateur reçoit tout l\'état dès sa connexion', async () => {
    const ws = await ouvrirWs();
    await attendre(() => ws.messages().length, 3000, 'le message init');
    const init = ws.messages()[0];
    assert.equal(init.t, 'init');
    assert.equal(init.sieges, 12);
    assert.ok(init.etat.joueurs.rpi1);
    ws.socket.destroy();
  });

  test('ping applicatif : le serveur répond pong avec la même valeur', async () => {
    const ws = await ouvrirWs();
    ws.envoyer(1, JSON.stringify({ t: 'ping', c: 42 }));
    await attendre(() => ws.messages().some(m => m.t === 'pong'), 3000, 'le pong');
    assert.deepEqual(ws.messages().find(m => m.t === 'pong'), { t: 'pong', c: 42 });
    ws.socket.destroy();
  });

  test('ping WebSocket : le serveur répond pong avec les mêmes octets', async () => {
    const ws = await ouvrirWs();
    ws.envoyer(9, 'coucou');
    await attendre(() => ws.trames.some(t => t.op === 10), 3000, 'la trame pong');
    assert.equal(ws.trames.find(t => t.op === 10).donnees.toString(), 'coucou');
    ws.socket.destroy();
  });

  test('les messages du jeu sont retransmis aux navigateurs connectés', async () => {
    const ws = await ouvrirWs();
    broker.envoyer(paquetPublish('iot/joueurs/rpi2', { id: 'rpi2', en_ligne: true, nom: 'Mimi' }));
    await attendre(() => ws.messages().some(m => m.t === 'etat' && m.etat.joueurs.rpi2), 3000, 'l\'état diffusé');
    assert.ok(ws.messages().some(m => m.t === 'evt' && m.type === 'arrivee' && m.id === 'rpi2'));
    ws.socket.destroy();
  });

  test('trame trop grande : connexion coupée', async () => {
    const ws = await ouvrirWs();
    const entete = Buffer.alloc(14);
    entete[0] = 0x81; entete[1] = 0x80 | 127; entete.writeBigUInt64BE(100000n, 2);
    ws.socket.write(entete);
    await attendre(() => ws.ferme, 3000, 'la fermeture');
  });

  test('upgrade sans clé refusé', async () => {
    const socket = net.connect(port, '127.0.0.1');
    let ferme = false;
    socket.on('close', () => { ferme = true; });
    socket.on('error', () => {});
    socket.write('GET / HTTP/1.1\r\nHost: x\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n\r\n');
    await attendre(() => ferme, 3000, 'la fermeture');
  });

  test('le serveur ne plante pas (aucune exception dans sa sortie)', () => {
    assert.doesNotMatch(sortie, /Exception|Error/);
    assert.equal(serveur.exitCode, null);
  });
});
