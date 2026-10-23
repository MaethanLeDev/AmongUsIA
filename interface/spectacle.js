'use strict';
// Miroir de la partie : reconstruit l'état du jeu à partir des messages MQTT (docs/protocole.md) pour les spectateurs.
// Il ne lit jamais iot/role : l'espion n'est connu qu'avec le résultat.
const SIEGES = 12;
const ARCHS = ['stratege', 'vengeur', 'sourire', 'reine', 'ombre', 'prodige'];
const ID_RE = /^[^\s/#+]{1,32}$/;
const HEX_RE = /^#[0-9a-fA-F]{6}$/;
const CHAT_MAX = 120;
const EN_JEU = ['mesures', 'debat', 'vote', 'verdict'];

const texte = (s, n) => String(s ?? '').replace(/[\u0000-\u001f\u007f]/g, ' ').trim().slice(0, n);
const archParDefaut = id => ARCHS[[...id].reduce((a, c) => a + c.charCodeAt(0), 0) % ARCHS.length];
const ids = l => (Array.isArray(l) ? l : []).filter(i => typeof i === 'string' && ID_RE.test(i));
function couleurs(c) {
  const out = {};
  if (c && typeof c === 'object') for (const k of ['cheveux', 'yeux', 'accent']) if (HEX_RE.test(String(c[k]))) out[k] = String(c[k]).toLowerCase();
  return out;
}

module.exports = function createSpectacle({ diffuser, log = () => {} }) {
  const S = {
    broker: { hote: '', connecte: false },
    joueurs: {},             // id -> { id, nom, arch, couleurs, ville, modele, strategie, en_ligne, siege }
    partie: { etat: 'attente' },   // dernier iot/partie/etat (attente = jamais reçu)
    mesures: {},             // id -> températures de la manche en cours, par échange
    parole: null,            // dernier iot/partie/parole, + parle: true quand il a répondu
    votes: {},               // votant -> { suspect, raison } pour la manche en cours
    verdicts: [],            // verdicts de la partie en cours
    resultat: null,          // dernier iot/partie/resultat
    stats: null,             // iot/partie/stats
  };
  const chat = [];           // envoyé à part : à la connexion, puis message par message
  let minuteur = null;
  const pousser = () => { if (!minuteur) minuteur = setTimeout(() => { minuteur = null; diffuser({ t: 'etat', etat: { ...S, horloge: Date.now() } }); }, 60); };
  const evenement = (type, data) => diffuser({ t: 'evt', type, ...data });
  const enJeu = () => EN_JEU.includes(S.partie.etat);
  const dePartie = m => m.partie == null || m.partie === S.partie.partie;
  const deManche = m => dePartie(m) && (m.manche == null || m.manche === S.partie.manche);

  // ------------------------------------------------------------ sièges : chacun garde le sien toute la partie
  const ecart = (a, b) => { const d = Math.abs(a - b) % SIEGES; return Math.min(d, SIEGES - d); };
  function attribuerSiege(j) {
    // Le siège libre le plus éloigné des autres : la table se remplit de façon équilibrée
    if (j.siege != null) return;
    const pris = Object.values(S.joueurs).map(x => x.siege).filter(s => s != null);
    let meilleur = null, distance = -1;
    for (let s = 0; s < SIEGES; s++) {
      if (pris.includes(s)) continue;
      const d = pris.length ? Math.min(...pris.map(p => ecart(s, p))) : SIEGES;
      if (d > distance) { meilleur = s; distance = d; }
    }
    j.siege = meilleur;                                       // plus de 12 joueurs : les suivants attendent une place
  }
  function repartir(participants) {
    // Au début d'une partie, les joueurs se placent à intervalles réguliers, dans l'ordre où ils étaient assis
    const tries = participants.filter(id => S.joueurs[id]).sort((a, b) => (S.joueurs[a].siege ?? 99) - (S.joueurs[b].siege ?? 99));
    if (!tries.length) return;
    const depart = S.joueurs[tries[0]].siege ?? 0;
    for (const j of Object.values(S.joueurs)) j.siege = null;
    tries.forEach((id, i) => { S.joueurs[id].siege = (depart + Math.round(i * SIEGES / tries.length)) % SIEGES; });
    for (const j of Object.values(S.joueurs)) if (j.en_ligne) attribuerSiege(j);
  }
  function libererSieges() {
    const garde = new Set(enJeu() ? S.partie.joueurs : []);   // un joueur parti en pleine partie garde sa place (hors ligne)
    for (const j of Object.values(S.joueurs)) if (!j.en_ligne && !garde.has(j.id)) delete S.joueurs[j.id];
    for (const j of Object.values(S.joueurs)) if (j.siege == null && j.en_ligne) attribuerSiege(j);
  }

  // ------------------------------------------------------------ messages du jeu
  function presence(id, p, retenu) {
    let j = S.joueurs[id];
    if (p.en_ligne === false) {
      if (j && j.en_ligne) { j.en_ligne = false; log(`- ${id}`); if (!retenu) evenement('depart', { id }); libererSieges(); }
      return;
    }
    const arrive = !j || !j.en_ligne;
    if (!j) j = S.joueurs[id] = { id, siege: null };
    Object.assign(j, {
      nom: texte(p.nom, 16) || id, arch: ARCHS.includes(p.arch) ? p.arch : archParDefaut(id), couleurs: couleurs(p.couleurs),
      ville: texte(p.ville, 30), modele: texte(p.modele, 40), strategie: texte(p.strategie, 12), en_ligne: true,
    });
    attribuerSiege(j);
    if (arrive) { log(`+ ${id} (siège ${j.siege})`); if (!retenu) evenement('arrivee', { id }); }
  }

  function etat(e, retenu) {
    const avant = S.partie;
    if (e.etat === 'fini' && e.partie === avant.partie) e = { ...avant, ...e, fin: null };   // on garde les éliminés pour l'écran de fin
    const nouvellePartie = e.partie != null && e.partie !== avant.partie;
    if (nouvellePartie) { S.verdicts = []; chat.length = 0; diffuser({ t: 'chat', vider: true }); }
    if (nouvellePartie || e.manche !== avant.manche || e.etat === 'inscription') { S.mesures = {}; S.votes = {}; }
    if (e.etat !== 'debat') S.parole = null;
    S.partie = {
      etat: texte(e.etat, 20) || 'attente', partie: e.partie ?? null, manche: Number(e.manche) || 0, manches_max: Number(e.manches_max) || 0,
      joueurs: ids(e.joueurs), vivants: ids(e.vivants),
      elimines: (Array.isArray(e.elimines) ? e.elimines : []).filter(x => x && ID_RE.test(String(x.id))).map(x => ({ id: String(x.id), manche: Number(x.manche) || 0 })),
      echanges: Number(e.echanges) || 5, tours: Number(e.tours) || 0, elimine: e.elimine ?? null, gagnant: e.gagnant ?? null,
      min: Number(e.min) || 0, max: Number(e.max) || 0, debut: Number(e.debut) || null, fin: Number(e.fin) || null,
    };
    libererSieges();
    if (nouvellePartie && EN_JEU.includes(S.partie.etat)) repartir(S.partie.joueurs);
    if (!retenu && S.partie.etat !== avant.etat) evenement('phase', { etat: S.partie.etat, manche: S.partie.manche });
  }

  function ajouterChat(entree) {
    chat.push(entree); if (chat.length > CHAT_MAX) chat.shift();
    diffuser({ t: 'chat', entree });
  }

  function onMqtt(topic, obj, raw, retenu) {
    const t = topic.split('/');
    if (t[0] !== 'iot' || !obj || typeof obj !== 'object' || Array.isArray(obj)) return;
    const id = t[2];
    if (t[1] === 'joueurs' && ID_RE.test(id || '')) presence(id, obj, retenu);
    else if (t[1] === 'partie' && id === 'etat') etat(obj, retenu);
    else if (t[1] === 'partie' && id === 'stats') S.stats = obj;
    else if (t[1] === 'partie' && id === 'resultat') { S.resultat = obj; if (!retenu) evenement('resultat', { resultat: obj }); }
    else if (t[1] === 'partie' && id === 'parole') {
      if (!dePartie(obj) || !ID_RE.test(String(obj.joueur))) return;
      S.parole = { joueur: String(obj.joueur), tour: Number(obj.tour) || 1, tours: Number(obj.tours) || 1, rang: Number(obj.rang) || 1, sur: Number(obj.sur) || 1, delai: Number(obj.delai) || 0, fin: Number(obj.fin) || null, parle: false };
      evenement('parole', { joueur: S.parole.joueur });
    } else if (t[1] === 'partie' && id === 'verdict') {
      if (!dePartie(obj)) return;
      const v = { manche: Number(obj.manche) || 0, votes: obj.votes || {}, compte: obj.compte || {}, elimine: obj.elimine ?? null, egalite: !!obj.egalite, etait_espion: obj.etait_espion ?? null };
      S.verdicts.push(v);
      ajouterChat({ verdict: v, ts: Date.now() });
      evenement('verdict', { verdict: v });
    } else if (t[1] === 'capteurs' && t[3] === 'temperature' && ID_RE.test(id || '')) {
      if (!deManche(obj) || typeof obj.temperature !== 'number') return;
      const l = S.mesures[id] || (S.mesures[id] = []);
      const i = Math.max(0, Math.min(19, (Number(obj.echange) || l.length + 1) - 1));
      l[i] = Math.round(obj.temperature * 10) / 10;
      evenement('mesure', { id, temperature: l[i] });
    } else if (t[1] === 'chat' && ID_RE.test(id || '')) {
      const txt = texte(obj.text, 500); if (!txt || !dePartie(obj)) return;
      if (S.parole && S.parole.joueur === id) S.parole.parle = true;
      ajouterChat({ id, text: txt, manche: Number(obj.manche) || S.partie.manche, tour: Number(obj.tour) || 0, ts: Date.now() });
    } else if (t[1] === 'votes' && ID_RE.test(id || '')) {
      if (!deManche(obj) || typeof obj.suspect !== 'string') return;
      S.votes[id] = { suspect: obj.suspect, raison: texte(obj.raison, 200) };
      evenement('vote', { votant: id, suspect: obj.suspect });
    } else return;
    pousser();
  }

  return {
    onMqtt,
    setBroker(hote, connecte) { S.broker = { hote, connecte }; pousser(); },
    init: () => ({ t: 'init', etat: { ...S, horloge: Date.now() }, chat, sieges: SIEGES }),
    etat: () => S,
  };
};
