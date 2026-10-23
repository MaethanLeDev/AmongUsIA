// Classe Noire · L'espion — vue spectateur : la scène 3D et les panneaux suivent la partie envoyée par le serveur.
import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { ARCHETYPES, setOutlines } from './chars.js';
import { Net } from './net.js';
import { createHub } from './hub3d.js';

const $ = id => document.getElementById(id);
const h = (tag, attrs, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === 'class') e.className = v; else if (k === 'text') e.textContent = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v); else if (v === true) e.setAttribute(k, ''); else if (v !== false && v != null) e.setAttribute(k, v);
  }
  for (const c of kids.flat()) if (c != null && c !== false) e.append(c.nodeType ? c : document.createTextNode(c));
  return e;
};
const store = { get(k, d) { try { return localStorage.getItem(k) ?? d; } catch { return d; } }, set(k, v) { try { localStorage.setItem(k, v); } catch {} } };
const isTouch = matchMedia('(pointer: coarse)').matches || 'ontouchstart' in window;

// ------------------------------------------------------------------ qualité
const QUALITIES = {
  low: { label: 'Bas', pr: 1, shadows: 0, bloom: false, outlines: false, msaa: 0 },
  medium: { label: 'Moyen', pr: 1.5, shadows: 1024, bloom: true, outlines: true, msaa: 2 },
  high: { label: 'Élevé', pr: 2, shadows: 2048, bloom: true, outlines: true, msaa: 4 },
};
const qKey = QUALITIES[store.get('cn_q', '')] ? store.get('cn_q') : (isTouch ? 'low' : 'medium');
const quality = QUALITIES[qKey];
setOutlines(quality.outlines);

// ------------------------------------------------------------------ audio
let actx = null, muted = store.get('cn_mute', '0') === '1';
// Le navigateur n'autorise le son qu'après un premier clic ou une touche sur la page
const reveillerSon = () => { try { actx = actx || new (window.AudioContext || window.webkitAudioContext)(); actx.resume(); } catch {} };
addEventListener('pointerdown', reveillerSon, { once: true }); addEventListener('keydown', reveillerSon, { once: true });
function beep(f, d = 0.12, v = 0.07, type = 'sine') {
  if (muted || !actx || actx.state !== 'running') return;
  try {
    const t = actx.currentTime, o = actx.createOscillator(), g = actx.createGain();
    o.type = type; o.frequency.value = f; g.gain.setValueAtTime(v, t); g.gain.exponentialRampToValueAtTime(0.001, t + d);
    o.connect(g); g.connect(actx.destination); o.start(t); o.stop(t + d);
  } catch {}
}

// ------------------------------------------------------------------ rendu
const hub = createHub();
const renderer = new THREE.WebGLRenderer({ canvas: $('gl'), antialias: !quality.bloom, powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, quality.pr));
renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.05;
if (quality.shadows) { renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap; }
const vw = () => innerWidth || 1280, vh = () => innerHeight || 720;
let composer = null;
if (quality.bloom) {
  const rt = new THREE.WebGLRenderTarget(vw(), vh(), { type: THREE.HalfFloatType, samples: quality.msaa });
  composer = new EffectComposer(renderer, rt);
  composer.addPass(new RenderPass(hub.scene, hub.camera));
  composer.addPass(new UnrealBloomPass(new THREE.Vector2(vw(), vh()), 0.5, 0.6, 1.2));
  composer.addPass(new OutputPass());
}
function resize() {
  renderer.setSize(vw(), vh(), false);
  if (composer) { composer.setPixelRatio(renderer.getPixelRatio()); composer.setSize(vw(), vh()); }
  hub.resize(vw(), vh());
}
addEventListener('resize', resize); resize();
hub.setShadows(!!quality.shadows);

let last = performance.now();
function frame(t) {
  requestAnimationFrame(frame);
  const dt = Math.min(0.05, (t - last) / 1000); last = t;
  hub.update(dt);
  if (composer) composer.render(); else renderer.render(hub.scene, hub.camera);
}
requestAnimationFrame(frame);

$('gl').addEventListener('pointerdown', e => hub.pointer.down(e.clientX));
addEventListener('pointermove', e => hub.pointer.move(e.clientX));
addEventListener('pointerup', () => hub.pointer.up());
$('gl').addEventListener('wheel', e => hub.pointer.wheel(e.deltaY), { passive: true });

// ------------------------------------------------------------------ boutons
let camAuto = store.get('cn_cam', '1') === '1';
$('btnRegles').onclick = () => $('regles').classList.remove('hidden');
$('fermerRegles').onclick = () => $('regles').classList.add('hidden');
$('btnSon').textContent = muted ? '🔇' : '🔊';
$('btnSon').onclick = () => { muted = !muted; store.set('cn_mute', muted ? '1' : '0'); $('btnSon').textContent = muted ? '🔇' : '🔊'; };
$('btnCam').classList.toggle('off', !camAuto);
$('btnCam').onclick = () => { camAuto = !camAuto; store.set('cn_cam', camAuto ? '1' : '0'); $('btnCam').classList.toggle('off', !camAuto); majScene(); };
{
  const sel = h('select', { title: 'Qualité graphique' });
  for (const [k, q] of Object.entries(QUALITIES)) sel.append(h('option', { value: k, text: q.label }));
  sel.value = qKey; sel.onchange = () => { store.set('cn_q', sel.value); location.reload(); };
  document.querySelector('.entete .hbtns').prepend(sel);
}

// ------------------------------------------------------------------ état de la partie
let S = null, chat = [], decalage = 0, derniereManche = 0;   // decalage : horloge du navigateur moins celle du serveur
const EN_JEU = ['mesures', 'debat', 'vote', 'verdict'];
const VAINQUEURS = { capteurs: 'Les innocents gagnent', espion: 'L\'espion gagne' };   // "capteurs" dans le protocole (vocabulaire du sujet)
const nom = id => (S && S.joueurs[id] && S.joueurs[id].nom) || id || '?';
const couleur = id => { const j = S && S.joueurs[id]; return (j && (j.couleurs.accent || (ARCHETYPES[j.arch] || {}).accent)) || '#c1121f'; };
const enJeu = () => EN_JEU.includes(S.partie.etat);
const elimines = () => new Set(enJeu() || S.partie.etat === 'fini' ? S.partie.elimines.map(e => e.id) : []);
const resultatCourant = () => (S.partie.etat === 'fini' && S.resultat && S.resultat.partie === S.partie.partie ? S.resultat : null);
const pourcent = c => (c && c.total ? `${c.justes}/${c.total} (${Math.round(100 * c.justes / c.total)} %)` : '—');

Net.on('init', m => {
  S = m.etat; decalage = Date.now() - S.horloge; chat = m.chat;
  $('log').textContent = ''; derniereManche = 0; for (const e of chat) ligne(e, false);
  hub.clearVotes(); hub.clearReveal();
  majScene();
  for (const [votant, v] of Object.entries(S.votes)) hub.vote(votant, v.suspect);
  const r = resultatCourant(); if (r) { hub.reveler(r.espion, r.gagnant); annonceResultat(r); }
  majPanneaux();
});
Net.on('etat', m => {
  const avant = S; S = m.etat; decalage = Date.now() - S.horloge;
  if (avant) {
    if (S.partie.partie !== avant.partie.partie || S.partie.manche !== avant.partie.manche || (avant.partie.etat === 'verdict' && S.partie.etat !== 'verdict')) hub.clearVotes();
    if (avant.partie.etat === 'fini' && S.partie.etat !== 'fini') {
      hub.clearReveal(); cacherAnnonce();
      for (const e of avant.partie.elimines) hub.spawn(e.id);            // les éliminés reprennent leur place
    }
  }
  majScene(); majPanneaux();
});
Net.on('chat', m => {
  if (m.vider) { chat = []; $('log').textContent = ''; derniereManche = 0; return; }
  chat.push(m.entree); ligne(m.entree, true);
});
Net.on('evt', m => {
  if (!S) return;
  switch (m.type) {
    case 'arrivee': hub.spawn(m.id); beep(520, 0.25, 0.05); beep(780, 0.3, 0.03); break;
    case 'mesure': hub.pulse(m.id); break;
    case 'parole': beep(330, 0.06, 0.03); break;
    case 'vote': hub.vote(m.votant, m.suspect); beep(180, 0.15, 0.05, 'triangle'); break;
    case 'verdict': {
      const v = m.verdict;
      if (v.elimine) { hub.eliminer(v.elimine, v.etait_espion); beep(110, 0.9, 0.08, 'sawtooth'); }
      setTimeout(() => annonceVerdict(v), v.elimine ? 1600 : 200);
      break;
    }
    case 'resultat': hub.reveler(m.resultat.espion, m.resultat.gagnant); annonceResultat(m.resultat); beep(m.resultat.gagnant === 'capteurs' ? 660 : 140, 0.8, 0.07); break;
  }
});
Net.on('_ferme', () => { $('phaseTitre').textContent = 'Connexion au serveur perdue'; $('phaseSous').textContent = 'Nouvelle tentative…'; });

// ------------------------------------------------------------------ scène
function majScene() {
  if (!S) return;
  const elim = elimines();
  hub.setJoueurs(Object.values(S.joueurs).map(j => ({ ...j, elimine: elim.has(j.id) })));
  hub.setAmbiance(S.partie.etat);
  const p = S.parole;
  if (S.partie.etat === 'debat' && p) { hub.focus(camAuto ? p.joueur : null); hub.thinking(p.parle ? null : p.joueur); }
  else { hub.focus(null); hub.thinking(null); if (S.partie.etat !== 'debat') hub.clearBulles(); }
  const compte = decompte(), r = resultatCourant();
  for (const j of Object.values(S.joueurs)) {
    if (r && r.espion === j.id) continue;                                 // l'étiquette « ESPION » reste
    const temps = (S.mesures[j.id] || []).filter(v => v != null);
    if (['vote', 'verdict'].includes(S.partie.etat) && compte[j.id]) hub.setSub(j.id, `🗳 × ${compte[j.id]}`, '#ff8a96');
    else if (temps.length && enJeu()) hub.setSub(j.id, `${temps[temps.length - 1].toFixed(1)} °C`);
    else hub.setSub(j.id, j.ville || '');
  }
}
function decompte() {
  const c = {};
  for (const v of Object.values(S.votes)) c[v.suspect] = (c[v.suspect] || 0) + 1;
  return c;
}

// ------------------------------------------------------------------ panneaux
function textePhase() {
  const P = S.partie, p = S.parole;
  const n = Object.values(S.joueurs).filter(j => j.en_ligne).length;
  const manche = P.manche ? `Manche ${P.manche}${P.manches_max ? '/' + P.manches_max : ''} · ` : '';
  switch (P.etat) {
    case 'inscription':
      return ['Les IA prennent place', n < P.min ? `Il faut au moins ${P.min} IA (${n} pour l'instant)` : P.debut ? `${n} IA · la partie commence dans {s}` : `${n} IA · le maître du jeu va lancer la partie`];
    case 'mesures': {
      const fait = Math.max(0, ...Object.values(S.mesures).map(l => l.filter(v => v != null).length));
      return [manche + 'Mesures', `Les capteurs publient leurs températures · échange ${fait}/${P.echanges}`];
    }
    case 'debat': return [manche + 'Débat', p ? `Tour ${p.tour}/${p.tours} · ${nom(p.joueur)} ${p.parle ? 'a la parole' : 'réfléchit…'}` : 'Les IA débattent'];
    case 'vote': return [manche + 'Vote', `${Object.keys(S.votes).length}/${P.vivants.length} IA ont voté`];
    case 'verdict': return [manche + 'Verdict', P.elimine ? `${nom(P.elimine)} quitte la table` : 'Égalité : personne n\'est éliminé'];
    case 'fini': {
      const r = resultatCourant();
      return ['Fin de partie', r ? `${VAINQUEURS[r.gagnant] || 'Partie annulée'} · l'espion était ${nom(r.espion)}` : ''];
    }
    default: return ['En attente du maître du jeu', n ? `${n} IA à la table` : 'Aucune IA connectée pour l\'instant'];
  }
}

function majPanneaux() {
  if (!S) return;
  const [titre, sous] = textePhase();
  $('phaseTitre').textContent = titre; $('phaseSous').dataset.modele = sous; $('phaseSous').textContent = sous.replace('{s}', '…');
  $('reseau').textContent = S.broker.connecte ? '' : '⚠ broker injoignable';
  majTimer(true);

  // cartes des IA : les joueurs de la partie d'abord, par siège
  const P = S.partie, elim = elimines(), r = resultatCourant(), compte = decompte();
  const dansPartie = id => P.joueurs.includes(id);
  const liste = Object.values(S.joueurs).sort((a, b) => (dansPartie(b.id) - dansPartie(a.id)) || (a.siege ?? 99) - (b.siege ?? 99));
  const box = $('cartes'); box.textContent = '';
  if (!liste.length) box.append(h('p', { class: 'dim', text: 'Aucune IA pour l\'instant. Lancez joueur.py sur un Raspberry Pi : elle apparaîtra ici et à la table.' }));
  for (const j of liste) {
    const temps = S.mesures[j.id] || [], vote = S.votes[j.id], e = P.elimines.find(x => x.id === j.id);
    const chips = [];
    if (r && r.espion === j.id) chips.push(['🕵 espion', 'warn']);
    if (!j.en_ligne) chips.push(['hors ligne', '']);
    else if (elim.has(j.id)) chips.push([`éliminé · manche ${e ? e.manche : '?'}`, '']);
    else if (S.parole && S.parole.joueur === j.id) chips.push([S.parole.parle ? '💬 parle' : '… réfléchit', 'ok']);
    else if (P.etat === 'vote' && dansPartie(j.id)) chips.push([vote ? '🗳 a voté' : 'vote…', vote ? 'ok' : '']);
    else if (enJeu() && !dansPartie(j.id)) chips.push(['prochaine partie', '']);
    if (compte[j.id] && ['vote', 'verdict'].includes(P.etat)) chips.push([`${compte[j.id]} vote${compte[j.id] > 1 ? 's' : ''} contre`, 'warn']);
    box.append(h('div', { class: 'pcard' + (elim.has(j.id) || !j.en_ligne ? ' off' : '') + (S.parole && S.parole.joueur === j.id ? ' parle' : '') },
      h('div', { class: 'top' }, h('span', { class: 'dot', style: `background:${couleur(j.id)}` }), h('span', { class: 'nm', text: j.nom }),
        ...chips.map(([t, c]) => h('span', { class: 'chip ' + c, text: t }))),
      h('div', { class: 'sub', title: 'Ville du capteur · modèle Ollama de l\'IA · façon de voter (LLM, ou calcul sans LLM)',
        text: [j.ville && '📍 ' + j.ville, j.modele && '🧠 ' + j.modele, j.strategie === 'ecart' ? '🧮 vote par calcul' : j.strategie === 'llm' ? '💬 vote par LLM' : ''].filter(Boolean).join('  ·  ') }),
      enJeu() && dansPartie(j.id) && !elim.has(j.id) ? h('div', { class: 'temps' },
        Array.from({ length: P.echanges }, (_, i) => h('i', { class: temps[i] == null ? 'vide' : '', text: temps[i] == null ? '' : temps[i].toFixed(1) }))) : null,
      vote && ['vote', 'verdict'].includes(P.etat) ? h('div', { class: 'vote' }, '🗳 contre ', h('b', { text: nom(vote.suspect) }), vote.raison ? h('div', { class: 'tiny', text: vote.raison }) : null) : null));
  }

  // décompte des votes
  const dc = $('decompte'), tri = Object.entries(compte).sort((a, b) => b[1] - a[1]);
  dc.classList.toggle('hidden', !(['vote', 'verdict'].includes(P.etat) && tri.length));
  if (tri.length) {
    dc.textContent = ''; dc.append(h('div', { class: 'label first', text: 'Votes' }));
    const max = Math.max(...tri.map(x => x[1]), P.vivants.length / 2);
    for (const [id, n] of tri) dc.append(h('div', { class: 'barre' }, h('span', { text: nom(id) }), h('div', {}, h('i', { style: `width:${100 * n / max}%;background:${couleur(id)}` })), h('b', { text: n })));
  }

  // bilan de l'extension du TP : LLM contre calcul
  const st = S.stats;
  $('bilan').textContent = st && st.parties + st.votes.llm.total + st.votes.calcul.total
    ? `Votes justes · LLM : ${pourcent(st.votes.llm)} · calcul sans LLM : ${pourcent(st.votes.calcul)} · ${st.parties} partie${st.parties > 1 ? 's' : ''} (innocents ${st.victoires.capteurs}, espion ${st.victoires.espion})`
    : '';
}

// chronomètre de la phase (barre sous l'en-tête)
let finTimer = null, dureeTimer = 1;
function majTimer(nouvelEtat) {
  if (nouvelEtat) {
    const P = S.partie;
    const fin = P.etat === 'debat' && S.parole ? S.parole.fin : P.etat === 'inscription' ? P.debut : P.fin;
    const finLocale = fin ? fin * 1000 + decalage : null;
    if (finLocale !== finTimer) { finTimer = finLocale; dureeTimer = Math.max(1, (finLocale || 0) - Date.now()); }
  }
  const reste = finTimer ? Math.max(0, finTimer - Date.now()) : 0;
  $('timerFill').style.width = finTimer ? `${100 * reste / dureeTimer}%` : '0';
  const modele = $('phaseSous').dataset.modele || '';
  if (modele.includes('{s}')) $('phaseSous').textContent = modele.replace('{s}', `${Math.ceil(reste / 1000)} s`);
}
setInterval(() => { if (S) majTimer(false); }, 250);

// ------------------------------------------------------------------ fil du débat
function ligne(e, enDirect) {
  const log = $('log');
  if (e.verdict) {
    const v = e.verdict;
    log.append(h('div', { class: 'm sys verdict' }, v.elimine
      ? `⚖ ${nom(v.elimine)} quitte la table (${v.compte[v.elimine] || '?'} votes) : ${v.etait_espion ? 'c\'était l\'espion !' : 'ce n\'était pas l\'espion.'}`
      : '⚖ Égalité : personne ne quitte la table.'));
  } else {
    if (e.manche && e.manche !== derniereManche) { derniereManche = e.manche; log.append(h('div', { class: 'sep', text: `Manche ${e.manche}` })); }
    log.append(h('div', { class: 'm' }, h('span', { class: 'who', style: `color:${couleur(e.id)}`, text: nom(e.id) }), ' ', e.text));
    if (enDirect) { hub.say(e.id, e.text); beep(560, 0.05, 0.03); }
  }
  while (log.children.length > 150) log.firstChild.remove();
  log.scrollTop = log.scrollHeight;
}

// ------------------------------------------------------------------ annonces au centre de l'écran
let minuterieAnnonce = null;
function annonce(sur, titre, texte, stats, duree, classe = '') {
  clearTimeout(minuterieAnnonce);
  $('annonceSur').textContent = sur; $('annonceTitre').textContent = titre; $('annonceTexte').textContent = texte; $('annonceStats').textContent = stats || '';
  const a = $('annonce'); a.className = classe; void a.offsetWidth; a.classList.add('visible');
  if (duree) minuterieAnnonce = setTimeout(cacherAnnonce, duree);
}
function cacherAnnonce() { clearTimeout(minuterieAnnonce); $('annonce').className = 'hidden'; }
function annonceVerdict(v) {
  if (v.elimine) annonce(`Manche ${v.manche}`, `${nom(v.elimine)} quitte la table`, v.etait_espion ? 'C\'était l\'espion !' : 'Ce n\'était pas l\'espion… la partie continue.', '', 6000, v.etait_espion ? 'pos' : 'neg');
  else annonce(`Manche ${v.manche}`, 'Égalité', 'Personne ne quitte la table.', '', 4000);
}
function annonceResultat(r) {
  const titre = VAINQUEURS[r.gagnant] || 'Partie annulée';
  const st = S.stats, stats = st ? `Depuis le début, votes justes · LLM : ${pourcent(st.votes.llm)} · calcul sans LLM : ${pourcent(st.votes.calcul)}` : '';
  annonce('Fin de partie', titre, `L'espion était ${nom(r.espion)}${r.raison ? ' · ' + r.raison : ''}`, stats, 0, r.gagnant === 'capteurs' ? 'pos' : 'neg');
}

window.__cn = { get etat() { return S; }, hub };
