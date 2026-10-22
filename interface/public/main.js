// Classe Noire — orchestration : connexion, création de personnage, salon 3D, jeu de table.
import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { ARCHETYPES, HAIR_COLORS, EYE_COLORS, ACCENT_COLORS, setOutlines } from './chars.js';
import { Net } from './net.js';
import { createHub } from './hub3d.js';
import { initTable } from './tableui.js';

const $ = id => document.getElementById(id);
const h = (tag, attrs, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === 'class') e.className = v; else if (k === 'text') e.textContent = v; else if (k === 'html') e.innerHTML = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v); else if (v === true) e.setAttribute(k, ''); else if (v !== false && v != null) e.setAttribute(k, v);
  }
  for (const c of kids.flat()) if (c != null && c !== false) e.append(c.nodeType ? c : document.createTextNode(c));
  return e;
};
const store = { get(k, d) { try { return localStorage.getItem(k) ?? d; } catch { return d; } }, set(k, v) { try { localStorage.setItem(k, v); } catch {} } };
const colorOf = id => `hsl(${(id * 67 + 10) % 360} 70% 68%)`;
const isTouch = matchMedia('(pointer: coarse)').matches || 'ontouchstart' in window;

// ------------------------------------------------------------------ qualité
const QUALITIES = {
  low: { label: 'Bas', pr: 1, shadows: 0, lamps: 6, bloom: false, outlines: false, msaa: 0 },
  medium: { label: 'Moyen', pr: 1.5, shadows: 1024, lamps: 10, bloom: true, outlines: true, msaa: 2 },
  high: { label: 'Élevé', pr: 2, shadows: 2048, lamps: 16, bloom: true, outlines: true, msaa: 4 },
};
const qKey = QUALITIES[store.get('cn_q', '')] ? store.get('cn_q') : (isTouch ? 'low' : 'medium');
const quality = QUALITIES[qKey];
setOutlines(quality.outlines);

// ------------------------------------------------------------------ audio
let actx = null, muted = store.get('cn_mute', '0') === '1';
function beep(f, d = 0.12, v = 0.07, type = 'sine') {
  if (muted) return;
  try {
    actx = actx || new (window.AudioContext || window.webkitAudioContext)();
    const t = actx.currentTime, o = actx.createOscillator(), g = actx.createGain();
    o.type = type; o.frequency.value = f; g.gain.setValueAtTime(v, t); g.gain.exponentialRampToValueAtTime(0.001, t + d);
    o.connect(g); g.connect(actx.destination); o.start(t); o.stop(t + d);
  } catch {}
}

// ------------------------------------------------------------------ rendu
let renderer, composer, renderPass, bloom;
const hub = (() => { try { return createHub(); } catch (e) { console.error(e); return null; } })();
renderer = new THREE.WebGLRenderer({ canvas: $('gl'), antialias: !quality.bloom, powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, quality.pr));
renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.05;
if (quality.shadows) { renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap; }
let active = hub;
function vw() { return innerWidth || 1280; } function vh() { return innerHeight || 720; }
if (quality.bloom) {
  const rt = new THREE.WebGLRenderTarget(vw(), vh(), { type: THREE.HalfFloatType, samples: quality.msaa });
  composer = new EffectComposer(renderer, rt);
  renderPass = new RenderPass(hub.scene, hub.camera); composer.addPass(renderPass);
  bloom = new UnrealBloomPass(new THREE.Vector2(vw(), vh()), 0.5, 0.6, 1.2); composer.addPass(bloom);
  composer.addPass(new OutputPass());
}
function resize() {
  renderer.setSize(vw(), vh(), false);
  if (composer) { composer.setPixelRatio(renderer.getPixelRatio()); composer.setSize(vw(), vh()); }
  hub.resize(vw(), vh());
}
addEventListener('resize', resize); resize();
function setActive(a) {
  if (active === a) return;
  active = a; if (renderPass) { renderPass.scene = a.scene; renderPass.camera = a.camera; }
}
hub.setShadows(!!quality.shadows);

let last = performance.now();
function frame(t) {
  requestAnimationFrame(frame);
  const dt = Math.min(0.05, (t - last) / 1000); last = t;
  hub.update(dt);
  if (composer) composer.render(); else renderer.render(active.scene, active.camera);
}
requestAnimationFrame(frame);

// interaction souris avec le salon
$('gl').addEventListener('pointerdown', e => { if (active === hub) hub.pointer.down(e.clientX); });
addEventListener('pointermove', e => { if (active === hub) hub.pointer.move(e.clientX); });
addEventListener('pointerup', () => hub.pointer.up());
$('gl').addEventListener('wheel', e => { if (active === hub) hub.pointer.wheel(e.deltaY); }, { passive: true });

// ------------------------------------------------------------------ création de personnage
let look = (() => { try { return JSON.parse(store.get('cn_look', '')) || null; } catch { return null; } })();
const defLook = arch => ({ arch, hair: ARCHETYPES[arch].hair, eyes: ARCHETYPES[arch].eyes, accent: ARCHETYPES[arch].accent });
if (!look || !ARCHETYPES[look.arch]) look = defLook('stratege');
let editing = false;
$('name').value = store.get('cn_name', '');

function buildCreator() {
  const grid = $('archGrid'); grid.textContent = '';
  for (const [k, a] of Object.entries(ARCHETYPES)) {
    grid.append(h('button', { class: 'arch' + (look.arch === k ? ' sel' : ''), type: 'button', onclick: () => { look = defLook(k); buildCreator(); hub.setPreviewLook(look); } },
      h('b', { text: a.name }), h('small', { text: a.desc })));
  }
  const sw = (id, list, key) => {
    const box = $(id); box.textContent = '';
    for (const c of list) box.append(h('button', { type: 'button', class: 'swatch' + ((look[key] || '').toLowerCase() === c ? ' sel' : ''), style: `background:${c}`, onclick: () => { look[key] = c; buildCreator(); hub.setPreviewLook(look); } }));
  };
  sw('swHair', HAIR_COLORS, 'hair'); sw('swEyes', EYE_COLORS, 'eyes'); sw('swAccent', ACCENT_COLORS, 'accent');
}
buildCreator(); hub.setPreview(look);

$('join').onclick = () => {
  const name = $('name').value.trim() || 'Élève';
  store.set('cn_name', name); store.set('cn_look', JSON.stringify(look)); beep(300, 0.08, 0.04);
  if (editing) { Net.updateLook(name, look); closeEditor(); return; }
  $('join').disabled = true; $('loginMsg').textContent = 'Connexion…';
  Net.join(name, look);
};
$('name').addEventListener('keydown', e => { if (e.key === 'Enter') $('join').click(); });
function openEditor() { editing = true; $('login').classList.remove('hidden'); $('join').textContent = 'APPLIQUER'; $('cancelEdit').classList.remove('hidden'); hub.setPreview(look); }
function closeEditor() { editing = false; $('login').classList.add('hidden'); hub.setPreview(null); hub.setUsers(users, Net.id); }
$('cancelEdit').onclick = closeEditor;
$('btnChar').onclick = openEditor;
Net.on('_failed', () => { $('join').disabled = false; $('loginMsg').textContent = 'Impossible de joindre le serveur.'; });
Net.on('refused', m => { $('join').disabled = false; $('loginMsg').textContent = m.text; });
Net.on('_reconnecting', () => { $('ping').textContent = 'reconnexion…'; });

// ------------------------------------------------------------------ règles / son
$('btnRules').onclick = $('tRules').onclick = () => $('rules').classList.remove('hidden');
$('closeRules').onclick = () => $('rules').classList.add('hidden');
$('btnSound').textContent = muted ? '🔇' : '🔊';
$('btnSound').onclick = () => { muted = !muted; store.set('cn_mute', muted ? '1' : '0'); $('btnSound').textContent = muted ? '🔇' : '🔊'; };
{ // qualité
  const sel = h('select', { id: 'qsel', title: 'Qualité graphique' }); for (const [k, q] of Object.entries(QUALITIES)) sel.append(h('option', { value: k, text: q.label }));
  sel.value = qKey; sel.onchange = () => { store.set('cn_q', sel.value); location.reload(); }; document.querySelector('.hubtop .hbtns').prepend(sel);
}

// ------------------------------------------------------------------ état du salon
let users = [], hubState = null, curMode = '';
const table = initTable({ Net, beep });

Net.on('welcome', () => {
  $('login').classList.add('hidden'); hub.setPreview(null); $('hubUI').classList.remove('hidden'); beep(440, 0.15, 0.06);
});
Net.on('hub', m => {
  hubState = m; users = m.users;
  hub.setUsers(users, Net.id);
  if (!editing && Net.joined) hub.setPreview(null);
  const spectating = m.inGame && !m.playing.includes(Net.id);      // arrivé en cours de partie : on attend
  const eff = spectating ? 'hub' : m.mode;
  if (eff !== curMode) switchMode(eff);
  renderHub();
});
Net.on('hchat', m => {
  const d = h('div', { class: 'm' }, h('span', { class: 'who', style: `color:${colorOf(m.from)}`, text: m.name }), ': ' + m.text);
  const box = $('hubLog'); box.append(d); while (box.children.length > 80) box.firstChild.remove(); box.scrollTop = box.scrollHeight;
  if (m.from !== Net.id) beep(560, 0.06, 0.04);
});
$('hubForm').addEventListener('submit', e => { e.preventDefault(); const t = $('hubMsg').value.trim(); if (t) Net.send({ t: 'hchat', text: t }); $('hubMsg').value = ''; });
setInterval(() => { $('ping').textContent = Net.ping ? Net.ping + ' ms' : ''; }, 2000);

function switchMode(mode) {
  const prev = curMode; curMode = mode;
  $('tableUI').classList.add('hidden');
  table.hide(); hub.setMode(mode);
  if (mode === 'hub') { $('hubUI').classList.toggle('hidden', !Net.joined); setActive(hub); }
  else if (mode === 'table') { $('hubUI').classList.add('hidden'); setActive(hub); table.show(); }
}

function renderHub() {
  if (!hubState) return;
  const m = hubState, isHost = m.host === Net.id;
  const us = $('hubUsers'); us.textContent = '';
  for (const u of m.users) us.append(h('div', { class: 'urow' }, h('span', { class: 'dot', style: `background:${colorOf(u.id)}` }), h('span', { class: 'nm', text: (m.host === u.id ? '👑 ' : '') + (u.ext ? '📡 ' : '') + u.name + (u.id === Net.id ? ' (toi)' : '') }), h('small', { text: ARCHETYPES[(u.look || {}).arch || 'stratege'].name })));
  $('hubStatus').textContent = m.inGame ? '⏳ Partie en cours — tu rejoindras au prochain tour' : m.users.length < 3 ? 'Il faut au moins 3 joueurs (ou des pions 🤖 à la table)' : 'Choisis ce que vous allez jouer';
  const modes = $('hubModes'); modes.textContent = '';
  const card = (ic, title, text, mode) => h('button', { class: 'modecard', disabled: !isHost || m.inGame, onclick: () => Net.send({ t: 'mode', mode }) }, h('div', { class: 'ic', text: ic }), h('b', { text: title }), h('small', { text }));
  modes.append(
    card('🃏', 'LA TABLE', 'Table ronde : pactes, trahisons, faux coupables. Les agents IA des Raspberry Pi y discutent.', 'table'));
  if (!isHost) modes.append(h('div', { class: 'waithost', text: 'L\'hôte (👑) choisit le mode de jeu.' }));
  const bd = $('board'); bd.textContent = '';
  if (!m.board.length) bd.append(h('span', { class: 'dim', text: 'Aucune partie pour l\'instant.' }));
  for (const b of m.board) bd.append(h('div', { class: 'brow' }, h('span', { text: '👑 ' + b.name }), h('small', { text: `${b.mode} · ${b.score} pts` })));
}

window.__cn = { get mode() { return curMode; }, get active() { return active.name; }, net: Net };
