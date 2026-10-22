// Personnages 3D de style anime (cel-shading + contour) construits à la main : aucun asset externe.
// Les personnages regardent vers +Z, mesurent ~1,75 m, origine aux pieds.
import * as THREE from 'three';

export const ARCHETYPES = {
  stratege: { name: 'Le Stratège',  desc: 'Calme, inexpressif. Il voit déjà trois coups d\'avance.', hairStyle: 'side',  outfit: 'uniform', gender: 'm', expr: 'calm',   hair: '#17151c', eyes: '#9aa0b8', accent: '#c1121f', skin: '#f1d6c2' },
  vengeur:  { name: 'Le Vengeur',   desc: 'Regard rouge, cœur de glace. Seul contre tous.',          hairStyle: 'spiky', outfit: 'collar',  gender: 'm', expr: 'cold',   hair: '#0b0b12', eyes: '#e0162b', accent: '#3b5bdb', skin: '#f3dccb', glow: true, tomoe: true },
  sourire:  { name: 'Le Sourire',   desc: 'Toujours aimable. C\'est ce qui fait peur.',               hairStyle: 'messy', outfit: 'coat',    gender: 'm', expr: 'smile',  hair: '#dfe3ee', eyes: '#7048e8', accent: '#7048e8', skin: '#f2d9c6', glasses: true },
  reine:    { name: 'La Reine des Glaces', desc: 'Parfaite, froide, impitoyable.',                   hairStyle: 'long',  outfit: 'uniform', gender: 'f', expr: 'cold',   hair: '#161a2e', eyes: '#74c0fc', accent: '#74c0fc', skin: '#f6e0d2' },
  ombre:    { name: 'L\'Ombre',     desc: 'Capuche, masque, aucun nom. Personne ne la voit venir.',  hairStyle: 'hood',  outfit: 'cloak',   gender: 'f', expr: 'masked', hair: '#201a30', eyes: '#c05cff', accent: '#7048e8', skin: '#efd6c5', glow: true },
  prodige:  { name: 'La Prodige',   desc: 'Sourire en coin, esprit tranchant. Elle joue avec vous.', hairStyle: 'twin',  outfit: 'uniform', gender: 'f', expr: 'smirk',  hair: '#c2255c', eyes: '#f08c00', accent: '#f08c00', skin: '#f5ddcc' },
};
export const HAIR_COLORS = ['#0b0b12', '#17151c', '#3b2a20', '#dfe3ee', '#c2255c', '#e8590c', '#1c7ed6', '#2f9e44', '#862e9c', '#f1c40f'];
export const EYE_COLORS = ['#9aa0b8', '#e0162b', '#7048e8', '#74c0fc', '#f08c00', '#40c057', '#f783ac', '#c05cff'];
export const ACCENT_COLORS = ['#c1121f', '#3b5bdb', '#7048e8', '#74c0fc', '#f08c00', '#2f9e44', '#e64980', '#e8c15a'];
export const COLOR_NAMES = {
  '#0b0b12': 'noir de jais', '#17151c': 'noir', '#3b2a20': 'brun', '#dfe3ee': 'argenté', '#c2255c': 'rose sombre', '#e8590c': 'orange', '#1c7ed6': 'bleu', '#2f9e44': 'vert', '#862e9c': 'violet', '#f1c40f': 'blond',
  '#c1121f': 'rouge', '#3b5bdb': 'bleu roi', '#7048e8': 'violet', '#74c0fc': 'bleu glacier', '#f08c00': 'ambre', '#e64980': 'rose', '#e8c15a': 'doré',
};

// -------------------------------------------------------------- matériaux partagés
const GRAD = (() => {
  const d = new Uint8Array([70, 70, 70, 255, 150, 150, 150, 255, 215, 215, 215, 255, 255, 255, 255, 255]);
  const t = new THREE.DataTexture(d, 4, 1, THREE.RGBAFormat); t.minFilter = t.magFilter = THREE.NearestFilter; t.needsUpdate = true; return t;
})();
const OUTLINE = new THREE.MeshBasicMaterial({ color: 0x07070b, side: THREE.BackSide });
const toonCache = new Map();
export function toon(color) {
  const k = String(color);
  if (!toonCache.has(k)) toonCache.set(k, new THREE.MeshToonMaterial({ color, gradientMap: GRAD }));
  return toonCache.get(k);
}
let glowTex = null;
function glowTexture() {
  if (glowTex) return glowTex;
  const c = document.createElement('canvas'); c.width = c.height = 64;
  const g = c.getContext('2d'), gr = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  gr.addColorStop(0, 'rgba(255,255,255,1)'); gr.addColorStop(0.4, 'rgba(255,255,255,.55)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = gr; g.fillRect(0, 0, 64, 64);
  glowTex = new THREE.CanvasTexture(c); return glowTex;
}

// -------------------------------------------------------------- visage dessiné sur canvas
const faceCache = new Map();
function faceTexture(look, expr) {
  const key = [look.skin, look.eyes, expr, look.tomoe ? 1 : 0, look.brow || ''].join('|');
  if (faceCache.has(key)) return faceCache.get(key);
  const W = 256, H = 128, c = document.createElement('canvas'); c.width = W; c.height = H;
  const g = c.getContext('2d');
  g.fillStyle = look.skin; g.fillRect(0, 0, W, H);
  // joues
  g.fillStyle = 'rgba(255,120,120,.16)';
  for (const x of [58, 198]) { g.beginPath(); g.ellipse(x, 84, 18, 9, 0, 0, 7); g.fill(); }
  const eyeY = 64, ex = [78, 178], ink = '#0b0b12';
  const brow = (x, dir, tilt, thick = 4) => { g.strokeStyle = ink; g.lineWidth = thick; g.lineCap = 'round'; g.beginPath(); g.moveTo(x - 22 * dir, eyeY - 32 + tilt); g.lineTo(x + 22 * dir, eyeY - 32 - tilt); g.stroke(); };
  const iris = (x, y, rx, ry, pupil = 0.45) => {
    g.fillStyle = '#fff'; g.beginPath(); g.ellipse(x, y, rx + 3, ry + 3, 0, 0, 7); g.fill();
    const gr = g.createLinearGradient(0, y - ry, 0, y + ry); gr.addColorStop(0, shade(look.eyes, -0.45)); gr.addColorStop(0.55, look.eyes); gr.addColorStop(1, shade(look.eyes, 0.35));
    g.fillStyle = gr; g.beginPath(); g.ellipse(x, y, rx, ry, 0, 0, 7); g.fill();
    g.fillStyle = ink; g.beginPath(); g.ellipse(x, y, rx * pupil, ry * pupil * 1.2, 0, 0, 7); g.fill();
    g.fillStyle = '#fff'; g.beginPath(); g.arc(x - rx * 0.35, y - ry * 0.38, Math.max(2, rx * 0.22), 0, 7); g.fill();
    if (look.tomoe) {
      g.fillStyle = ink;
      for (let i = 0; i < 3; i++) { const a = (i / 3) * 6.283 - 1.57; g.beginPath(); g.arc(x + Math.cos(a) * rx * 0.62, y + Math.sin(a) * ry * 0.62, rx * 0.13, 0, 7); g.fill(); }
    }
  };
  const lid = (x, sx, thick, drop) => {   // paupière supérieure épaisse (regard mi-clos / dur)
    g.strokeStyle = ink; g.lineWidth = thick; g.lineCap = 'round';
    g.beginPath(); g.moveTo(x - 24 * sx, eyeY - 14 + drop * 0.4); g.quadraticCurveTo(x, eyeY - 24 + drop, x + 24 * sx, eyeY - 14 + drop * 0.4); g.stroke();
  };
  const mouth = (kind) => {
    g.strokeStyle = '#6b3a3a'; g.lineWidth = 3.5; g.lineCap = 'round'; g.beginPath();
    if (kind === 'flat') { g.moveTo(112, 108); g.lineTo(144, 108); }
    else if (kind === 'smile') { g.moveTo(98, 100); g.quadraticCurveTo(128, 128, 158, 98); }
    else if (kind === 'smirk') { g.moveTo(108, 108); g.quadraticCurveTo(138, 114, 152, 96); }
    else if (kind === 'o') { g.ellipse(128, 108, 6, 8, 0, 0, 7); }
    else if (kind === 'frown') { g.moveTo(110, 112); g.quadraticCurveTo(128, 102, 146, 112); }
    g.stroke();
  };
  switch (expr) {
    case 'calm':
      for (const x of ex) { iris(x, eyeY + 2, 15, 13, 0.5); lid(x, 1, 6, 6); }
      brow(ex[0], 1, 1, 3); brow(ex[1], 1, -1, 3); mouth('flat'); break;
    case 'cold':
      for (const x of ex) { iris(x, eyeY + 2, 16, 12, 0.42); lid(x, 1, 7, 4); }
      brow(ex[0], 1, 6, 5); brow(ex[1], 1, -6, 5); mouth('flat'); break;
    case 'smile':
      for (const x of ex) { g.strokeStyle = ink; g.lineWidth = 6; g.lineCap = 'round'; g.beginPath(); g.moveTo(x - 20, eyeY + 6); g.quadraticCurveTo(x, eyeY - 14, x + 20, eyeY + 6); g.stroke(); }
      brow(ex[0], 1, -2, 3); brow(ex[1], 1, 2, 3); mouth('smile'); break;
    case 'smirk':
      for (const x of ex) { iris(x, eyeY + 2, 15, 15, 0.4); lid(x, 1, 5, 2); }
      brow(ex[0], 1, -4, 4); brow(ex[1], 1, 6, 4); mouth('smirk'); break;
    case 'masked':
      for (const x of ex) { iris(x, eyeY + 1, 15, 12, 0.35); lid(x, 1, 6, 3); }
      brow(ex[0], 1, 4, 4); brow(ex[1], 1, -4, 4); break;
    case 'scared':
      for (const x of ex) iris(x, eyeY, 14, 18, 0.28);
      brow(ex[0], 1, -8, 3); brow(ex[1], 1, 8, 3); mouth('o'); break;
    case 'angry':
      for (const x of ex) { iris(x, eyeY + 2, 15, 12, 0.4); lid(x, 1, 8, 6); }
      brow(ex[0], 1, 10, 6); brow(ex[1], 1, -10, 6); mouth('frown'); break;
    default: // neutre (PNJ)
      for (const x of ex) iris(x, eyeY, 14, 16, 0.42);
      brow(ex[0], 1, 0, 3); brow(ex[1], 1, 0, 3); mouth('flat');
  }
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4;
  faceCache.set(key, t); return t;
}
function shade(hex, amt) {
  const c = new THREE.Color(hex); const hsl = {}; c.getHSL(hsl); c.setHSL(hsl.h, hsl.s, Math.min(1, Math.max(0, hsl.l + amt))); return '#' + c.getHexString();
}

// -------------------------------------------------------------- construction
function mesh(geo, mat, outline = true) {
  const m = new THREE.Mesh(geo, mat); m.castShadow = true;
  if (outline && mesh.outlines) { const o = new THREE.Mesh(geo, OUTLINE); o.scale.setScalar(1.07); o.userData.outline = true; m.add(o); }
  return m;
}
mesh.outlines = true;
export function setOutlines(on) { mesh.outlines = on; }

const G_CAPS = {};
const capsule = (r, l) => { const k = r + '/' + l; return G_CAPS[k] || (G_CAPS[k] = new THREE.CapsuleGeometry(r, l, 4, 10)); };

export function createCharacter(look) {
  look = { ...ARCHETYPES.stratege, ...look };
  const root = new THREE.Group();
  const body = new THREE.Group(); root.add(body);
  const skin = toon(look.skin), hairM = toon(look.hair);
  const female = look.gender === 'f';
  const accent = toon(look.accent);
  const parts = { root, body };

  // jambes
  const legGeo = capsule(0.072, 0.7);
  const mkLeg = sx => {
    const piv = new THREE.Group(); piv.position.set(sx * 0.085, 0.92, 0);
    const outfit = look.outfit;
    const pantMat = toon(outfit === 'vest' ? '#3b4252' : outfit === 'suit' ? '#16161d' : outfit === 'collar' ? '#262a3e' : outfit === 'labcoat' || outfit === 'apron' ? '#e9ecef' : '#1c1c26');
    const showSkin = female && (outfit === 'uniform');
    const leg = mesh(legGeo, showSkin ? skin : pantMat); leg.position.y = -0.46; piv.add(leg);
    if (showSkin) { const sock = mesh(capsule(0.076, 0.3), toon('#16161d')); sock.position.y = -0.64; piv.add(sock); }
    const shoe = mesh(new THREE.BoxGeometry(0.12, 0.07, 0.24), toon(outfit === 'vest' ? '#5c4a2a' : '#111116')); shoe.position.set(0, -0.86, 0.04); piv.add(shoe);
    body.add(piv); return piv;
  };
  parts.legL = mkLeg(-1); parts.legR = mkLeg(1);

  // torse
  const torsoColor = { uniform: '#1b1b27', collar: '#1d2340', coat: '#2a2438', cloak: '#1a1626', vest: '#5a6270', suit: '#18181f', labcoat: '#f1f3f5', apron: '#8a8f99', hoodie: '#2b2f3a' }[look.outfit] || '#1b1b27';
  const tw = female ? 0.165 : 0.19;
  const torso = mesh(new THREE.CylinderGeometry(tw, tw * 0.86, 0.54, 14), toon(torsoColor)); torso.scale.z = 0.68; torso.position.y = 1.2; body.add(torso);
  const chest = mesh(new THREE.SphereGeometry(tw * 1.02, 14, 10), toon(torsoColor)); chest.scale.set(1, 0.7, 0.7); chest.position.y = 1.4; body.add(chest);
  // tenue
  const addO = (m) => { body.add(m); return m; };
  switch (look.outfit) {
    case 'uniform': {
      const shirt = mesh(new THREE.BoxGeometry(0.1, 0.26, 0.04), toon('#f1f1f4'), false); shirt.position.set(0, 1.3, 0.14); addO(shirt);
      const tie = mesh(new THREE.BoxGeometry(0.045, 0.24, 0.03), accent, false); tie.position.set(0, 1.27, 0.165); addO(tie);
      const col = mesh(new THREE.TorusGeometry(0.075, 0.018, 6, 14), toon('#f1f1f4'), false); col.rotation.x = Math.PI / 2; col.position.set(0, 1.46, 0.0); addO(col);
      if (female) { const skirt = mesh(new THREE.CylinderGeometry(0.17, 0.3, 0.3, 16, 1, true), toon('#262a3e')); skirt.material = skirt.material.clone(); skirt.material.side = THREE.DoubleSide; skirt.position.y = 0.95; addO(skirt); const bow = mesh(new THREE.OctahedronGeometry(0.05), accent, false); bow.scale.set(1.6, 1, 0.6); bow.position.set(0, 1.42, 0.15); addO(bow); }
      break;
    }
    case 'collar': {
      const c = mesh(new THREE.CylinderGeometry(0.115, 0.14, 0.14, 12, 1, true), toon('#1d2340')); c.material = c.material.clone(); c.material.side = THREE.DoubleSide; c.position.y = 1.5; addO(c);
      const rope = mesh(new THREE.TorusGeometry(0.2, 0.025, 6, 16), accent, false); rope.rotation.x = Math.PI / 2; rope.scale.y = 0.7; rope.position.y = 0.98; addO(rope);
      break;
    }
    case 'coat': case 'cloak': {
      const h = look.outfit === 'cloak' ? 1.1 : 0.78;
      const coat = mesh(new THREE.CylinderGeometry(0.2, look.outfit === 'cloak' ? 0.42 : 0.3, h, 16, 1, true), toon(torsoColor)); coat.material = coat.material.clone(); coat.material.side = THREE.DoubleSide; coat.position.y = 1.4 - h / 2 - 0.02; addO(coat);
      const trim = mesh(new THREE.TorusGeometry(look.outfit === 'cloak' ? 0.41 : 0.29, 0.015, 5, 22), accent, false); trim.rotation.x = Math.PI / 2; trim.position.y = 1.4 - h - 0.02; addO(trim);
      if (look.outfit === 'coat') { const sc = mesh(new THREE.TorusGeometry(0.1, 0.035, 6, 14), accent, false); sc.rotation.x = Math.PI / 2; sc.position.y = 1.47; addO(sc); }
      break;
    }
    case 'vest': {
      const v = mesh(new THREE.CylinderGeometry(tw * 1.05, tw * 0.95, 0.4, 14, 1, true), toon('#f08c00')); v.material = v.material.clone(); v.material.side = THREE.DoubleSide; v.scale.z = 0.72; v.position.y = 1.25; addO(v);
      const st = mesh(new THREE.TorusGeometry(tw * 1.0, 0.02, 5, 18), toon('#f1f1f4'), false); st.rotation.x = Math.PI / 2; st.scale.y = 0.72; st.position.y = 1.2; addO(st);
      break;
    }
    case 'suit': {
      const shirt = mesh(new THREE.BoxGeometry(0.09, 0.26, 0.04), toon('#f1f1f4'), false); shirt.position.set(0, 1.3, 0.14); addO(shirt);
      const tie = mesh(new THREE.BoxGeometry(0.04, 0.22, 0.03), accent, false); tie.position.set(0, 1.28, 0.165); addO(tie);
      break;
    }
    case 'apron': {
      const ap = mesh(new THREE.BoxGeometry(0.26, 0.5, 0.03), toon('#f1f3f5'), false); ap.position.set(0, 1.12, 0.14); addO(ap);
      break;
    }
    case 'labcoat': {
      const lc = mesh(new THREE.CylinderGeometry(0.2, 0.28, 0.72, 16, 1, true), toon('#f8f9fa')); lc.material = lc.material.clone(); lc.material.side = THREE.DoubleSide; lc.position.y = 1.05; addO(lc);
      const cross = mesh(new THREE.BoxGeometry(0.06, 0.06, 0.02), toon('#e03131'), false); cross.position.set(0.1, 1.32, 0.17); addO(cross);
      break;
    }
  }

  // bras
  const armGeo = capsule(0.052, 0.44);
  const sleeve = toon(look.outfit === 'labcoat' ? '#f8f9fa' : look.outfit === 'vest' ? '#5a6270' : torsoColor);
  const mkArm = sx => {
    const piv = new THREE.Group(); piv.position.set(sx * (female ? 0.2 : 0.235), 1.4, 0);
    const arm = mesh(armGeo, sleeve); arm.position.y = -0.3; piv.add(arm);
    const hand = mesh(new THREE.SphereGeometry(0.05, 10, 8), skin, false); hand.position.y = -0.58; piv.add(hand);
    if (look.outfit === 'collar') { const wrap = mesh(new THREE.CylinderGeometry(0.056, 0.056, 0.2, 10), toon('#e9ecef'), false); wrap.position.y = -0.46; piv.add(wrap); }
    piv.rotation.z = sx * 0.08; body.add(piv); return piv;
  };
  parts.armL = mkArm(-1); parts.armR = mkArm(1);

  // cou + tête
  const neck = mesh(new THREE.CylinderGeometry(0.045, 0.05, 0.1, 8), skin, false); neck.position.y = 1.5; body.add(neck);
  const head = new THREE.Group(); head.position.y = 1.66; body.add(head); parts.head = head;
  const hr = 0.16;
  const skull = mesh(new THREE.SphereGeometry(hr, 24, 18), skin); skull.scale.set(1, 1.08, 1.0); head.add(skull);
  const faceGeo = new THREE.SphereGeometry(hr * 1.012, 20, 12, Math.PI / 2 - 0.95, 1.9, Math.PI * 0.28, Math.PI * 0.42); faceGeo.scale(1, 1.08, 1);
  const faceMat = new THREE.MeshToonMaterial({ map: faceTexture(look, look.expr), gradientMap: GRAD });
  const face = new THREE.Mesh(faceGeo, faceMat); head.add(face); parts.face = face;
  const ear = sx => { const e = mesh(new THREE.SphereGeometry(0.03, 8, 6), skin, false); e.position.set(sx * 0.13, -0.005, 0); head.add(e); };
  ear(-1); ear(1);
  // lueurs des yeux
  if (look.glow) {
    const gm = new THREE.SpriteMaterial({ map: glowTexture(), color: new THREE.Color(look.eyes).multiplyScalar(2.4), blending: THREE.AdditiveBlending, depthWrite: false, transparent: true, opacity: 0.85 });
    for (const sx of [-1, 1]) { const s = new THREE.Sprite(gm); s.scale.setScalar(0.07); s.position.set(sx * 0.047, 0.0, hr * 1.04); head.add(s); }
  }
  if (look.glasses) {
    const gl = toon('#d0d4e0');
    for (const sx of [-1, 1]) { const r = new THREE.Mesh(new THREE.TorusGeometry(0.036, 0.005, 6, 16), gl); r.position.set(sx * 0.047, 0.0, hr * 1.02); head.add(r);
      const lens = new THREE.Mesh(new THREE.CircleGeometry(0.034, 14), new THREE.MeshBasicMaterial({ color: 0xbfd4ff, transparent: true, opacity: 0.18, side: THREE.DoubleSide })); lens.position.set(sx * 0.047, 0.0, hr * 1.02); head.add(lens); }
    const br = new THREE.Mesh(new THREE.BoxGeometry(0.03, 0.005, 0.005), gl); br.position.set(0, 0.0, hr * 1.02); head.add(br);
  }
  if (look.expr === 'masked') {
    const mk = mesh(new THREE.SphereGeometry(hr * 1.03, 18, 10, 0, Math.PI * 2, Math.PI * 0.55, Math.PI * 0.3), toon('#14111c'), false); mk.scale.set(1, 1.08, 1); head.add(mk);
  }

  // cheveux
  const hair = new THREE.Group(); head.add(hair); parts.hair = hair;
  const cone = (r, h, x, y, z, rx, ry, rz) => { const m = mesh(new THREE.ConeGeometry(r, h, 6), hairM); m.position.set(x, y, z); m.rotation.set(rx || 0, ry || 0, rz || 0); hair.add(m); return m; };
  const cap = (scale = 1.12, cover = 0.62) => {
    // calotte : dessus complet + arrière/côtés, en laissant le visage (devant, +Z) dégagé
    const top = mesh(new THREE.SphereGeometry(hr * scale, 22, 12, 0, Math.PI * 2, 0, Math.PI * 0.3), hairM); top.scale.y = 1.08; top.position.y = 0.005; hair.add(top);
    const back = mesh(new THREE.SphereGeometry(hr * scale, 22, 14, Math.PI / 2 + 0.95, Math.PI * 2 - 1.9, 0, Math.PI * cover), hairM); back.scale.y = 1.08; back.position.y = 0.005; hair.add(back);
    return top;
  };
  switch (look.hairStyle) {
    case 'side':
      cap(1.1, 0.62);
      cone(0.05, 0.17, 0.07, 0.11, 0.12, 1.9, 0, -0.5); cone(0.05, 0.17, 0.0, 0.12, 0.13, 1.9, 0, 0.1); cone(0.045, 0.15, -0.07, 0.105, 0.12, 1.9, 0, 0.55); cone(0.04, 0.12, 0.115, 0.04, 0.07, 1.7, 0, -1.2);
      break;
    case 'spiky':
      cap(1.1, 0.64);
      for (let i = 0; i < 8; i++) { const a = (i / 8) * Math.PI * 2; cone(0.055, 0.24, Math.cos(a) * 0.09, 0.08 + (i % 2) * 0.03, -0.06 + Math.sin(a) * 0.06 - 0.04, -1.1 + (i % 3) * 0.2, 0, Math.cos(a) * 0.9); }
      cone(0.04, 0.22, 0.12, -0.04, 0.09, 3.0, 0, -0.15); cone(0.04, 0.22, -0.12, -0.04, 0.09, 3.0, 0, 0.15); cone(0.045, 0.14, 0.0, 0.13, 0.13, 1.9, 0, 0);
      break;
    case 'messy':
      cap(1.12, 0.64);
      for (let i = 0; i < 9; i++) { const a = i * 2.4; cone(0.045, 0.16 + (i % 3) * 0.03, Math.cos(a) * 0.1, 0.1 + (i % 2) * 0.03, Math.sin(a) * 0.1, Math.sin(a) * 1.2, 0, -Math.cos(a) * 1.2); }
      break;
    case 'long': {
      cap(1.12, 0.66);
      const back = mesh(new THREE.CylinderGeometry(0.13, 0.1, 0.75, 14, 1, true, Math.PI * 0.55, Math.PI * 0.9), hairM); back.material = back.material.clone(); back.material.side = THREE.DoubleSide; back.position.set(0, -0.35, -0.04); hair.add(back);
      for (const sx of [-1, 1]) { const lock = mesh(new THREE.CapsuleGeometry(0.03, 0.34, 3, 6), hairM); lock.position.set(sx * 0.125, -0.12, 0.04); hair.add(lock); }
      for (let i = -2; i <= 2; i++) cone(0.04, 0.15, i * 0.045, 0.11, 0.13, 1.9, 0, -i * 0.12);
      break;
    }
    case 'twin': {
      cap(1.12, 0.64);
      for (const sx of [-1, 1]) { const tail = mesh(new THREE.CapsuleGeometry(0.04, 0.4, 3, 8), hairM); tail.position.set(sx * 0.17, -0.1, -0.03); tail.rotation.z = sx * 0.25; hair.add(tail); const tie = mesh(new THREE.SphereGeometry(0.035, 8, 6), accent, false); tie.position.set(sx * 0.15, 0.07, -0.02); hair.add(tie); }
      for (let i = -2; i <= 2; i++) cone(0.04, 0.14, i * 0.045, 0.11, 0.13, 1.9, 0, -i * 0.1);
      break;
    }
    case 'bob': {
      cap(1.16, 0.7);
      const b = mesh(new THREE.CylinderGeometry(0.15, 0.14, 0.2, 14, 1, true), hairM); b.material = b.material.clone(); b.material.side = THREE.DoubleSide; b.position.set(0, -0.08, -0.01); hair.add(b);
      for (let i = -2; i <= 2; i++) cone(0.04, 0.13, i * 0.045, 0.11, 0.13, 1.9, 0, -i * 0.1);
      break;
    }
    case 'hood': {
      const hd = mesh(new THREE.SphereGeometry(hr * 1.28, 20, 14, 0, Math.PI * 2, 0, Math.PI * 0.82), toon('#1a1626')); hd.material = hd.material.clone(); hd.material.side = THREE.DoubleSide; hd.scale.set(1, 1.08, 1.05); hd.position.set(0, 0.0, -0.025); hair.add(hd);
      for (let i = -1; i <= 1; i++) cone(0.04, 0.12, i * 0.05, 0.105, 0.125, 1.9, 0, -i * 0.15);
      break;
    }
    case 'short': default:
      cap(1.1, 0.6);
      for (let i = -2; i <= 2; i++) cone(0.04, 0.11, i * 0.045, 0.115, 0.125, 1.9, 0, -i * 0.12);
  }
  if (look.hat === 'helmet') { const hm = mesh(new THREE.SphereGeometry(hr * 1.2, 16, 10, 0, Math.PI * 2, 0, Math.PI * 0.5), toon('#f1c40f')); hm.position.y = 0.04; hair.add(hm); const br = mesh(new THREE.CylinderGeometry(hr * 1.3, hr * 1.3, 0.015, 16), toon('#f1c40f'), false); br.position.set(0, 0.04, 0.02); hair.add(br); }
  if (look.hat === 'cap') { const hm = mesh(new THREE.SphereGeometry(hr * 1.14, 16, 10, 0, Math.PI * 2, 0, Math.PI * 0.5), toon('#1c2c4a')); hm.position.y = 0.035; hair.add(hm); const br = mesh(new THREE.BoxGeometry(0.17, 0.012, 0.1), toon('#1c2c4a'), false); br.position.set(0, 0.04, 0.15); hair.add(br); }

  // animation
  const A = { t: Math.random() * 6, mode: 'stand', walk: 0, blend: 0 };
  const pocketStyle = look.arch === 'stratege' || look.expr === 'calm';
  const api = {
    group: root, parts, look, height: 1.78,
    setExpr(e) { if (api._expr !== e) { api._expr = e; faceMat.map = faceTexture(look, e); faceMat.needsUpdate = true; } },
    setMode(m) { A.mode = m; },
    update(dt, speed = 0, t) {
      A.t += dt; A.walk += dt * (2 + speed * 2.4) * (speed > 0.05 ? 1 : 0);
      const sw = Math.sin(A.walk * 3.2) * Math.min(1, speed) * 0.8;
      const breathe = Math.sin(A.t * 1.8) * 0.012;
      if (A.mode === 'sit') {
        body.position.y = -0.42 + breathe; parts.legL.rotation.x = parts.legR.rotation.x = -1.45;
        parts.armL.rotation.x = parts.armR.rotation.x = -0.5; parts.armL.rotation.z = -0.15; parts.armR.rotation.z = 0.15;
        head.rotation.y = Math.sin(A.t * 0.5) * 0.25;
      } else {
        body.position.y = breathe + Math.abs(sw) * 0.02;
        parts.legL.rotation.x = sw; parts.legR.rotation.x = -sw;
        parts.armL.rotation.x = -sw * 0.8; parts.armR.rotation.x = sw * 0.8;
        parts.armL.rotation.z = -0.08 - (pocketStyle && speed < 0.1 ? 0.12 : 0); parts.armR.rotation.z = 0.08 + (pocketStyle && speed < 0.1 ? 0.12 : 0);
        head.rotation.y = Math.sin(A.t * 0.7) * 0.08 * (1 - Math.min(1, speed));
      }
    },
    setOutline(on) { root.traverse(o => { if (o.userData.outline) o.visible = on; }); },
  };
  api._expr = look.expr;
  return api;
}

// étiquette de nom flottante
export function makeTag(text, color = '#ffffff', sub = '') {
  const c = document.createElement('canvas'); c.width = 384; c.height = 96;
  const g = c.getContext('2d');
  g.font = '700 34px "Segoe UI", sans-serif'; g.textAlign = 'center';
  g.lineWidth = 8; g.strokeStyle = 'rgba(0,0,0,.85)'; g.strokeText(text, 192, sub ? 40 : 58); g.fillStyle = color; g.fillText(text, 192, sub ? 40 : 58);
  if (sub) { g.font = '600 24px "Segoe UI", sans-serif'; g.strokeText(sub, 192, 78); g.fillStyle = 'rgba(255,255,255,.75)'; g.fillText(sub, 192, 78); }
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: t, transparent: true, depthWrite: false, depthTest: false }));
  s.scale.set(1.5, 0.375, 1); s.renderOrder = 10; s.userData.canvas = c; s.userData.tex = t;
  return s;
}
export function retag(sprite, text, color = '#fff', sub = '') {
  const c = sprite.userData.canvas, g = c.getContext('2d');
  g.clearRect(0, 0, c.width, c.height);
  g.font = '700 34px "Segoe UI", sans-serif'; g.textAlign = 'center';
  g.lineWidth = 8; g.strokeStyle = 'rgba(0,0,0,.85)'; g.strokeText(text, 192, sub ? 40 : 58); g.fillStyle = color; g.fillText(text, 192, sub ? 40 : 58);
  if (sub) { g.font = '600 24px "Segoe UI", sans-serif'; g.strokeText(sub, 192, 78); g.fillStyle = 'rgba(255,255,255,.75)'; g.fillText(sub, 192, 78); }
  sprite.userData.tex.needsUpdate = true;
}
