'use strict';
// mqtt.js : le client MQTT 3.1.1 écrit à la main, face à un faux broker sur un port libre de cette machine.
const { test, describe, beforeEach, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const createMqtt = require('../mqtt.js');
const { fauxBroker, attendre, paquetPublish, filtresAbonnement } = require('./aides.js');

let broker, client, recus, etats;

// Connecte un client au faux broker et attend son CONNACK (sauf si attendreConnexion est faux)
async function connecter({ attendreConnexion = true, ...options } = {}) {
  // Les tableaux de ce test : le client d'un test précédent signale encore sa fermeture après stop()
  const mesRecus = recus, mesEtats = etats;
  client = createMqtt({
    hosts: ['127.0.0.1'], port: broker.port, clientId: 'test', keepAlive: 30,
    onMessage: (topic, obj, raw, retenu) => mesRecus.push({ topic, obj, raw, retenu }),
    onState: (connecte, hote) => mesEtats.push([connecte, hote]),
    ...options,
  });
  if (attendreConnexion) await attendre(() => client.connected, 3000, 'la connexion');
  return client;
}

beforeEach(async () => {
  recus = []; etats = [];
  broker = await fauxBroker().demarrer();
});
afterEach(async () => {
  if (client) client.stop();
  client = null;
  await broker.fermer();
});

describe('connexion', () => {
  test('CONNECT : MQTT 3.1.1, clean session, keep-alive et identifiant', async () => {
    await connecter();
    const attendu = Buffer.from([0x10, 16, 0, 4, ...Buffer.from('MQTT'), 4, 0x02, 0, 30, 0, 4, ...Buffer.from('test')]);
    assert.deepEqual(broker.de(1)[0].brut, attendu);
  });

  test('connexion signalée avec l\'hôte', async () => {
    await connecter();
    assert.deepEqual(etats, [[true, '127.0.0.1']]);
    assert.equal(client.host, '127.0.0.1');
  });

  test('connexion refusée par le broker : pas de connexion', async () => {
    await broker.fermer();
    broker = await fauxBroker({ codeConnack: 5 }).demarrer();
    const journal = [];
    await connecter({ attendreConnexion: false, log: m => journal.push(m) });
    await attendre(() => journal.length, 3000, 'le refus');
    assert.match(journal[0], /connexion refusée \(code 5\)/);
    assert.equal(client.connected, false);
    assert.deepEqual(etats, []);
  });

  test('perte du broker signalée', async () => {
    await connecter();
    broker.couper();
    await attendre(() => etats.length === 2, 3000, 'la déconnexion');
    assert.deepEqual(etats[1], [false, '127.0.0.1']);
  });

  test('reconnexion automatique après 3 s, avec les mêmes abonnements', async t => {
    t.mock.timers.enable({ apis: ['setTimeout', 'setInterval'] });
    await connecter();
    client.subscribe('iot/partie/etat');
    await attendre(() => broker.abonnements().length === 1, 3000, 'l\'abonnement');
    broker.couper();
    await attendre(() => etats.length === 2, 3000, 'la déconnexion');
    t.mock.timers.tick(3000);
    await attendre(() => broker.de(1).length === 2 && broker.abonnements().length === 2, 3000, 'la reconnexion');
    assert.deepEqual(broker.abonnements(), ['iot/partie/etat', 'iot/partie/etat']);
  });
});

describe('abonnements et publications', () => {
  test('abonnement demandé avant la connexion envoyé après le CONNACK', async () => {
    await connecter({ attendreConnexion: false });
    client.subscribe('iot/joueurs/+');
    await attendre(() => broker.de(8).length === 1, 3000, 'le SUBSCRIBE');
    const subscribe = broker.de(8)[0];
    assert.equal(subscribe.drapeaux, 2);   // SUBSCRIBE : drapeaux réservés 0010
    assert.deepEqual(filtresAbonnement(subscribe.corps), ['iot/joueurs/+']);
    assert.equal(subscribe.corps[subscribe.corps.length - 1], 0);   // QoS 0 demandée
  });

  test('chaque abonnement a son identifiant de paquet', async () => {
    await connecter();
    client.subscribe('a'); client.subscribe('b');
    await attendre(() => broker.de(8).length === 2, 3000, 'les SUBSCRIBE');
    const ids = broker.de(8).map(p => p.corps.readUInt16BE(0));
    assert.notEqual(ids[0], ids[1]);
  });

  test('publication refusée tant que la connexion n\'est pas établie', async () => {
    await connecter({ attendreConnexion: false });
    assert.equal(client.publish('iot/x', { a: 1 }), false);
  });

  test('publication en JSON, retenue si demandé', async () => {
    await connecter();
    assert.equal(client.publish('iot/test', { a: 'é' }, true), true);
    await attendre(() => broker.de(3).length === 1, 3000, 'le PUBLISH');
    assert.deepEqual(broker.de(3)[0].brut, paquetPublish('iot/test', { a: 'é' }, { retenu: true }));
  });
});

describe('réception des messages', () => {
  test('PUBLISH QoS 0 décodé en JSON', async () => {
    await connecter();
    broker.envoyer(paquetPublish('iot/partie/etat', { etat: 'vote' }));
    await attendre(() => recus.length === 1, 3000, 'le message');
    assert.deepEqual(recus[0], { topic: 'iot/partie/etat', obj: { etat: 'vote' }, raw: '{"etat":"vote"}', retenu: false });
  });

  test('drapeau retenu transmis', async () => {
    await connecter();
    broker.envoyer(paquetPublish('iot/partie/stats', { parties: 1 }, { retenu: true }));
    await attendre(() => recus.length === 1, 3000, 'le message');
    assert.equal(recus[0].retenu, true);
  });

  test('PUBLISH QoS 1 acquitté, identifiant hors du message', async () => {
    await connecter();
    broker.envoyer(paquetPublish('iot/votes/rpi1', { suspect: 'rpi2' }, { qos: 1, id: 0x0a0b }));
    await attendre(() => recus.length === 1 && broker.de(4).length === 1, 3000, 'le PUBACK');
    assert.deepEqual(broker.de(4)[0].brut, Buffer.from([0x40, 2, 0x0a, 0x0b]));
    assert.deepEqual(recus[0].obj, { suspect: 'rpi2' });
  });

  test('message qui n\'est pas du JSON : texte brut, objet null', async () => {
    await connecter();
    broker.envoyer(paquetPublish('iot/x', 'pas du json'));
    await attendre(() => recus.length === 1, 3000, 'le message');
    assert.equal(recus[0].obj, null);
    assert.equal(recus[0].raw, 'pas du json');
  });

  test('paquet coupé en deux morceaux reçu une seule fois', async () => {
    await connecter();
    const paquet = paquetPublish('iot/chat/rpi1', { text: 'Bonjour à tous' });
    broker.envoyer(paquet.subarray(0, 5));
    await new Promise(fin => setTimeout(fin, 30));
    assert.equal(recus.length, 0);
    broker.envoyer(paquet.subarray(5));
    await attendre(() => recus.length === 1, 3000, 'le message');
    assert.equal(recus[0].obj.text, 'Bonjour à tous');
  });

  test('plusieurs paquets dans un même envoi', async () => {
    await connecter();
    broker.envoyer(Buffer.concat([paquetPublish('a', { n: 1 }), paquetPublish('b', { n: 2 }), paquetPublish('c', { n: 3 })]));
    await attendre(() => recus.length === 3, 3000, 'les messages');
    assert.deepEqual(recus.map(m => m.topic), ['a', 'b', 'c']);
  });

  test('message long (taille sur plusieurs octets)', async () => {
    await connecter();
    const texte = 'x'.repeat(20000);
    broker.envoyer(paquetPublish('iot/chat/rpi1', { text: texte }));
    await attendre(() => recus.length === 1, 3000, 'le message');
    assert.equal(recus[0].obj.text, texte);
  });

  test('une erreur dans onMessage n\'empêche pas de lire la suite', async t => {
    t.mock.method(console, 'error', () => {});
    await connecter({ onMessage: (topic, obj) => { if (topic === 'a') throw new Error('boum'); recus.push(obj); } });
    broker.envoyer(Buffer.concat([paquetPublish('a', {}), paquetPublish('b', { ok: true })]));
    await attendre(() => recus.length === 1, 3000, 'le second message');
    assert.deepEqual(recus[0], { ok: true });
  });
});
