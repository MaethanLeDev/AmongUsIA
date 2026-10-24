'use strict';
// spectacle.js : l'état de la partie reconstruit à partir des messages MQTT, pour les spectateurs.
const { test, describe } = require('node:test');
const assert = require('node:assert/strict');
const createSpectacle = require('../spectacle.js');

const PARTIE = 1761200000;

// Un spectacle dont on garde tout ce qu'il diffuse aux navigateurs
function nouveau() {
  const diffuses = [];
  const sp = createSpectacle({ diffuser: m => diffuses.push(m) });
  const recevoir = (topic, obj, retenu = false) => sp.onMqtt(topic, obj, JSON.stringify(obj), retenu);
  const evenements = type => diffuses.filter(m => m.t === 'evt' && (!type || m.type === type));
  return { sp, diffuses, recevoir, evenements, S: () => sp.etat() };
}

const arriver = (r, ...ids) => { for (const id of ids) r.recevoir(`iot/joueurs/${id}`, { id, en_ligne: true }, true); };
const partir = (r, id) => r.recevoir(`iot/joueurs/${id}`, { id, en_ligne: false });
const phase = (r, etat, champs = {}, retenu = false) => r.recevoir('iot/partie/etat', {
  etat, partie: PARTIE, manche: 1, manches_max: 3, joueurs: ['rpi1', 'rpi2', 'rpi3'], vivants: ['rpi1', 'rpi2', 'rpi3'],
  elimines: [], fin: PARTIE + 60, ...champs }, retenu);
const sieges = r => Object.fromEntries(Object.values(r.S().joueurs).map(j => [j.id, j.siege]));

describe('présence et sièges', () => {
  test('le premier joueur prend le siège 0, le suivant le siège opposé', () => {
    const r = nouveau();
    arriver(r, 'rpi1', 'rpi2', 'rpi3');
    assert.deepEqual(sieges(r), { rpi1: 0, rpi2: 6, rpi3: 3 });
  });

  test('nom limité à 16 caractères, id par défaut', () => {
    const r = nouveau();
    r.recevoir('iot/joueurs/rpi1', { id: 'rpi1', en_ligne: true, nom: 'Inspecteur Gadget le Grand' });
    r.recevoir('iot/joueurs/rpi2', { id: 'rpi2', en_ligne: true });
    assert.equal(r.S().joueurs.rpi1.nom, 'Inspecteur Gadge');
    assert.equal(r.S().joueurs.rpi2.nom, 'rpi2');
  });

  test('apparence inconnue remplacée par une apparence choisie d\'après l\'id', () => {
    const r = nouveau();
    r.recevoir('iot/joueurs/rpi1', { id: 'rpi1', en_ligne: true, arch: '<script>' });
    assert.equal(r.S().joueurs.rpi1.arch, 'sourire');   // somme des codes de « rpi1 » = 380, 380 % 6 = 2
  });

  test('seules les couleurs #rrggbb sont gardées, en minuscules', () => {
    const r = nouveau();
    r.recevoir('iot/joueurs/rpi1', { id: 'rpi1', en_ligne: true, couleurs: { cheveux: '#AABBCC', yeux: 'red', accent: 'url(x)' } });
    assert.deepEqual(r.S().joueurs.rpi1.couleurs, { cheveux: '#aabbcc' });
  });

  test('id invalide ignoré', () => {
    const r = nouveau();
    r.recevoir(`iot/joueurs/${'x'.repeat(40)}`, { en_ligne: true });
    assert.deepEqual(r.S().joueurs, {});
  });

  test('un 13e joueur attend une place', () => {
    const r = nouveau();
    arriver(r, ...Array.from({ length: 13 }, (_, i) => `rpi${i + 1}`));
    const pris = Object.values(sieges(r));
    assert.equal(new Set(pris.filter(s => s != null)).size, 12);
    assert.equal(r.S().joueurs.rpi13.siege, null);
  });

  test('départ pendant l\'inscription : le siège est libéré', () => {
    const r = nouveau();
    arriver(r, 'rpi1', 'rpi2');
    r.recevoir('iot/partie/etat', { etat: 'inscription', min: 3, max: 12, debut: null });
    partir(r, 'rpi2');
    assert.deepEqual(Object.keys(r.S().joueurs), ['rpi1']);
  });

  test('départ en pleine partie : le joueur garde sa place, hors ligne', () => {
    const r = nouveau();
    arriver(r, 'rpi1', 'rpi2', 'rpi3');
    phase(r, 'debat');
    const siege = r.S().joueurs.rpi2.siege;
    partir(r, 'rpi2');
    assert.equal(r.S().joueurs.rpi2.en_ligne, false);
    assert.equal(r.S().joueurs.rpi2.siege, siege);
  });

  test('arrivée et départ en direct annoncés aux navigateurs, pas les présences retenues', () => {
    const r = nouveau();
    arriver(r, 'rpi1');                                                  // retenu
    r.recevoir('iot/joueurs/rpi2', { id: 'rpi2', en_ligne: true });      // en direct
    partir(r, 'rpi2');
    assert.deepEqual(r.evenements().map(e => [e.type, e.id]), [['arrivee', 'rpi2'], ['depart', 'rpi2']]);
  });

  for (let n = 3; n <= 12; n++) {
    test(`début de partie à ${n} joueurs : sièges distincts et régulièrement espacés`, () => {
      const r = nouveau();
      const ids = Array.from({ length: n }, (_, i) => `rpi${i + 1}`);
      arriver(r, ...ids);
      phase(r, 'mesures', { joueurs: ids, vivants: ids });
      const pris = ids.map(id => r.S().joueurs[id].siege).sort((a, b) => a - b);
      assert.equal(new Set(pris).size, n);
      const ecarts = pris.map((s, i) => ((pris[(i + 1) % n] - s) + 12) % 12 || 12);
      for (const e of ecarts) assert.ok(e === Math.floor(12 / n) || e === Math.ceil(12 / n), `écart ${e} à ${n} joueurs`);
    });
  }
});

describe('phases de la partie', () => {
  test('état complet, et champs manquants remplacés par des valeurs neutres', () => {
    const r = nouveau();
    r.recevoir('iot/partie/etat', { etat: 'vote', partie: PARTIE });
    assert.deepEqual(r.S().partie, {
      etat: 'vote', partie: PARTIE, manche: 0, manches_max: 0, joueurs: [], vivants: [], elimines: [], echanges: 5, tours: 0,
      elimine: null, gagnant: null, min: 0, max: 0, debut: null, fin: null,
    });
  });

  test('ids et éliminés invalides filtrés', () => {
    const r = nouveau();
    phase(r, 'vote', { vivants: ['rpi1', 'a b', 42, null], elimines: [{ id: 'rpi2', manche: '1' }, { id: 'x/y' }, null] });
    assert.deepEqual(r.S().partie.vivants, ['rpi1']);
    assert.deepEqual(r.S().partie.elimines, [{ id: 'rpi2', manche: 1 }]);
  });

  test('nouvelle partie : le chat et les verdicts sont vidés', () => {
    const r = nouveau();
    phase(r, 'debat');
    r.recevoir('iot/chat/rpi1', { text: 'Bonjour', partie: PARTIE, manche: 1 });
    r.recevoir('iot/partie/verdict', { partie: PARTIE, manche: 1, elimine: null, egalite: true });
    phase(r, 'mesures', { partie: PARTIE + 1000 });
    assert.deepEqual(r.S().verdicts, []);
    assert.deepEqual(r.sp.init().chat, []);
    assert.ok(r.diffuses.some(m => m.t === 'chat' && m.vider));
  });

  test('nouvelle manche : mesures et votes vidés', () => {
    const r = nouveau();
    phase(r, 'vote');
    r.recevoir('iot/capteurs/rpi1/temperature', { temperature: 12, echange: 1, partie: PARTIE, manche: 1 });
    r.recevoir('iot/votes/rpi1', { suspect: 'rpi2', partie: PARTIE, manche: 1 });
    phase(r, 'mesures', { manche: 2 });
    assert.deepEqual([r.S().mesures, r.S().votes], [{}, {}]);
  });

  test('fin de partie : les éliminés restent affichés', () => {
    const r = nouveau();
    phase(r, 'verdict', { elimines: [{ id: 'rpi2', manche: 1 }] });
    r.recevoir('iot/partie/etat', { etat: 'fini', partie: PARTIE, gagnant: 'capteurs' });
    assert.equal(r.S().partie.etat, 'fini');
    assert.equal(r.S().partie.gagnant, 'capteurs');
    assert.deepEqual(r.S().partie.elimines, [{ id: 'rpi2', manche: 1 }]);
  });

  test('changement de phase en direct annoncé, pas l\'état retenu', () => {
    const r = nouveau();
    phase(r, 'mesures', {}, true);
    phase(r, 'debat');
    assert.deepEqual(r.evenements('phase').map(e => e.etat), ['debat']);
  });

  test('la parole est effacée hors du débat', () => {
    const r = nouveau();
    phase(r, 'debat');
    r.recevoir('iot/partie/parole', { partie: PARTIE, manche: 1, joueur: 'rpi2', tour: 1, tours: 2 });
    phase(r, 'vote');
    assert.equal(r.S().parole, null);
  });

  test('serveur lancé en cours de partie : tout est reconstruit depuis les messages retenus, sans animation', () => {
    const r = nouveau();
    arriver(r, 'rpi1', 'rpi2', 'rpi3');
    phase(r, 'debat', { manche: 2, vivants: ['rpi1', 'rpi3'], elimines: [{ id: 'rpi2', manche: 1 }] }, true);
    r.recevoir('iot/partie/stats', { parties: 3 }, true);
    assert.equal(r.S().partie.manche, 2);
    assert.deepEqual(r.S().partie.vivants, ['rpi1', 'rpi3']);
    assert.deepEqual(r.S().stats, { parties: 3 });
    assert.deepEqual(r.evenements(), []);
  });

  test('navigateur qui arrive en cours de partie : init contient l\'état et le chat', () => {
    const r = nouveau();
    arriver(r, 'rpi1', 'rpi2', 'rpi3');
    phase(r, 'vote');
    r.recevoir('iot/chat/rpi1', { text: 'Rpi2 ment.', partie: PARTIE, manche: 1, tour: 1 });
    r.recevoir('iot/votes/rpi1', { suspect: 'rpi2', raison: 'il ment', partie: PARTIE, manche: 1 });
    const init = r.sp.init();
    assert.equal(init.t, 'init');
    assert.equal(init.sieges, 12);
    assert.equal(typeof init.etat.horloge, 'number');
    assert.deepEqual(Object.keys(init.etat.joueurs), ['rpi1', 'rpi2', 'rpi3']);
    assert.deepEqual(init.etat.votes, { rpi1: { suspect: 'rpi2', raison: 'il ment' } });
    assert.equal(init.chat[0].text, 'Rpi2 ment.');
  });
});

describe('messages du jeu', () => {
  test('température rangée à son échange et arrondie au dixième', () => {
    const r = nouveau();
    phase(r, 'mesures');
    r.recevoir('iot/capteurs/rpi1/temperature', { temperature: 12.345, echange: 3, partie: PARTIE, manche: 1 });
    const valeurs = r.S().mesures.rpi1;
    assert.equal(valeurs.length, 3);
    assert.equal(valeurs[2], 12.3);
  });

  test('température d\'une autre manche ou qui n\'est pas un nombre ignorée', () => {
    const r = nouveau();
    phase(r, 'mesures', { manche: 2 });
    r.recevoir('iot/capteurs/rpi1/temperature', { temperature: 12, partie: PARTIE, manche: 1 });
    r.recevoir('iot/capteurs/rpi1/temperature', { temperature: '12', partie: PARTIE, manche: 2 });
    assert.deepEqual(r.S().mesures, {});
  });

  test('échange hors bornes ramené entre 1 et 20', () => {
    const r = nouveau();
    phase(r, 'mesures');
    r.recevoir('iot/capteurs/rpi1/temperature', { temperature: 1, echange: 500, partie: PARTIE, manche: 1 });
    assert.equal(r.S().mesures.rpi1.length, 20);
  });

  test('vote d\'une autre manche ignoré, raison tronquée', () => {
    const r = nouveau();
    phase(r, 'vote', { manche: 2 });
    r.recevoir('iot/votes/rpi1', { suspect: 'rpi2', partie: PARTIE, manche: 1 });
    r.recevoir('iot/votes/rpi3', { suspect: 'rpi2', raison: 'x'.repeat(500), partie: PARTIE, manche: 2 });
    assert.deepEqual(Object.keys(r.S().votes), ['rpi3']);
    assert.equal(r.S().votes.rpi3.raison.length, 200);
  });

  test('vote sans suspect texte ignoré', () => {
    const r = nouveau();
    phase(r, 'vote');
    r.recevoir('iot/votes/rpi1', { suspect: ['rpi2'], partie: PARTIE, manche: 1 });
    assert.deepEqual(r.S().votes, {});
  });

  test('chat : caractères de contrôle retirés, et la bulle « … » disparaît quand il parle', () => {
    const r = nouveau();
    phase(r, 'debat');
    r.recevoir('iot/partie/parole', { partie: PARTIE, manche: 1, joueur: 'rpi2', tour: 1, tours: 2 });
    r.recevoir('iot/chat/rpi2', { text: 'Je\u0000 mens\n pas', partie: PARTIE, manche: 1, tour: 1 });
    assert.equal(r.S().parole.parle, true);
    assert.equal(r.sp.init().chat[0].text, 'Je  mens  pas');
  });

  test('chat d\'une autre partie ou vide ignoré', () => {
    const r = nouveau();
    phase(r, 'debat');
    r.recevoir('iot/chat/rpi1', { text: 'Vieux', partie: PARTIE - 1, manche: 1 });
    r.recevoir('iot/chat/rpi1', { text: '   ', partie: PARTIE, manche: 1 });
    assert.deepEqual(r.sp.init().chat, []);
  });

  test('chat limité aux 120 derniers messages', () => {
    const r = nouveau();
    phase(r, 'debat');
    for (let i = 0; i < 130; i++) r.recevoir('iot/chat/rpi1', { text: `message ${i}`, partie: PARTIE, manche: 1 });
    const chat = r.sp.init().chat;
    assert.equal(chat.length, 120);
    assert.equal(chat[0].text, 'message 10');
  });

  test('parole d\'une autre partie ou pour un id invalide ignorée', () => {
    const r = nouveau();
    phase(r, 'debat');
    r.recevoir('iot/partie/parole', { partie: PARTIE - 1, joueur: 'rpi2' });
    r.recevoir('iot/partie/parole', { partie: PARTIE, joueur: 'a/b' });
    assert.equal(r.S().parole, null);
  });

  test('verdict gardé et ajouté au fil du débat', () => {
    const r = nouveau();
    phase(r, 'verdict');
    r.recevoir('iot/partie/verdict', { partie: PARTIE, manche: 1, votes: { rpi1: 'rpi2' }, compte: { rpi2: 1 }, elimine: 'rpi2', etait_espion: false });
    assert.equal(r.S().verdicts[0].elimine, 'rpi2');
    assert.equal(r.sp.init().chat[0].verdict.elimine, 'rpi2');
    assert.equal(r.evenements('verdict').length, 1);
  });

  test('résultat retenu gardé sans animation, résultat en direct animé', () => {
    const r = nouveau();
    r.recevoir('iot/partie/resultat', { partie: PARTIE - 1, espion: 'rpi4', gagnant: 'espion' }, true);
    assert.equal(r.evenements('resultat').length, 0);
    r.recevoir('iot/partie/resultat', { partie: PARTIE, espion: 'rpi3', gagnant: 'capteurs' });
    assert.equal(r.S().resultat.espion, 'rpi3');
    assert.equal(r.evenements('resultat').length, 1);
  });

  test('messages qui ne sont pas des objets, ou hors de iot/, ignorés', () => {
    const r = nouveau();
    for (const obj of [null, [1, 2], 'texte', 42]) r.sp.onMqtt('iot/partie/etat', obj, String(obj), false);
    r.recevoir('autre/partie/etat', { etat: 'vote' });
    assert.equal(r.S().partie.etat, 'attente');
    assert.deepEqual(r.diffuses, []);
  });
});

describe('secret de l\'espion', () => {
  test('un message iot/role ne change rien et n\'est jamais diffusé', () => {
    const r = nouveau();
    arriver(r, 'rpi1', 'rpi2', 'rpi3');
    phase(r, 'mesures');
    const avant = JSON.stringify(r.S());
    const diffuses = r.diffuses.length;
    r.recevoir('iot/role/rpi2', { role: 'espion', partie: PARTIE });
    assert.equal(JSON.stringify(r.S()), avant);
    assert.equal(r.diffuses.length, diffuses);
  });

  test('l\'état ne nomme l\'espion qu\'une fois le résultat publié', () => {
    const r = nouveau();
    arriver(r, 'rpi1', 'rpi2', 'rpi3');
    phase(r, 'vote');
    r.recevoir('iot/role/rpi2', { role: 'espion', partie: PARTIE });
    assert.ok(!JSON.stringify(r.sp.init()).includes('espion'));
  });
});

describe('diffusion aux navigateurs', () => {
  test('plusieurs messages rapprochés donnent une seule diffusion de l\'état, 60 ms plus tard', t => {
    t.mock.timers.enable({ apis: ['setTimeout'] });
    const r = nouveau();
    arriver(r, 'rpi1', 'rpi2', 'rpi3');
    phase(r, 'mesures');
    const etats = () => r.diffuses.filter(m => m.t === 'etat');
    assert.equal(etats().length, 0);
    t.mock.timers.tick(60);
    assert.equal(etats().length, 1);
    assert.deepEqual(Object.keys(etats()[0].etat.joueurs), ['rpi1', 'rpi2', 'rpi3']);
  });

  test('changement de broker diffusé', t => {
    t.mock.timers.enable({ apis: ['setTimeout'] });
    const r = nouveau();
    r.sp.setBroker('10.109.150.215', true);
    t.mock.timers.tick(60);
    assert.deepEqual(r.diffuses[0].etat.broker, { hote: '10.109.150.215', connecte: true });
  });
});
