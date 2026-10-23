// Salle 3D : une table ronde sous une lampe, les IA assises autour.
// Animations : arrivée d'une IA, parole (caméra, bulle, « … »), mesures, votes, élimination, révélation de l'espion.
import * as THREE from 'three';
import { createCharacter, makeTag, retag, ARCHETYPES, toon } from './chars.js';

export const SIEGES = 12;
const R = 2.15;                       // rayon des sièges
const TETE = 1.24, TAG_Y = 2.07;      // hauteur de la tête d'un personnage assis, de son étiquette
const ease = p => p * p * (3 - 2 * p);
const easeOutBack = p => 1 + 2.7 * Math.pow(p - 1, 3) + 1.7 * Math.pow(p - 1, 2);
const angleVers = (de, a) => { let d = (a - de) % (Math.PI * 2); if (d > Math.PI) d -= Math.PI * 2; if (d < -Math.PI) d += Math.PI * 2; return d; };

export function createHub() {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x07070d);
  scene.fog = new THREE.FogExp2(0x07070d, 0.045);
  const camera = new THREE.PerspectiveCamera(48, 16 / 9, 0.1, 80);
  const api = { scene, camera, name: 'hub' };

  // ----- lumières
  scene.add(new THREE.HemisphereLight(0x8a94e0, 0x2a1420, 1.15));
  for (let i = 0; i < 4; i++) { const a = (i / 4) * Math.PI * 2 + 0.6, f = new THREE.PointLight(0xffd7b8, 22, 9, 1.6); f.position.set(Math.sin(a) * 3.6, 2.4, Math.cos(a) * 3.6); scene.add(f); }
  const lamp = new THREE.SpotLight(0xffd7a6, 90, 14, 0.75, 0.6, 1.4); lamp.position.set(0, 4.6, 0); lamp.target.position.set(0, 0.7, 0); lamp.castShadow = true;
  lamp.shadow.mapSize.set(1024, 1024); lamp.shadow.bias = -0.0005; scene.add(lamp, lamp.target);
  const rim = new THREE.PointLight(0xc1121f, 10, 14); rim.position.set(-5, 2.5, 4); scene.add(rim);
  const rim2 = new THREE.PointLight(0x4263eb, 8, 14); rim2.position.set(5, 2.5, -4); scene.add(rim2);
  const projo = new THREE.SpotLight(0xffe2b0, 0, 9, 0.32, 0.55, 1.2); projo.position.set(0, 4.2, 0); scene.add(projo, projo.target);   // sur celui qui parle
  const lueurEspion = new THREE.PointLight(0xff2030, 0, 3.5, 1.4); scene.add(lueurEspion);

  // ----- salle
  const floor = new THREE.Mesh(new THREE.CircleGeometry(11, 48), new THREE.MeshStandardMaterial({ color: 0x1a141a, roughness: 0.55, metalness: 0.25 })); floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; scene.add(floor);
  const rug = new THREE.Mesh(new THREE.CircleGeometry(3.6, 48), new THREE.MeshStandardMaterial({ color: 0x3a0d14, roughness: 0.95 })); rug.rotation.x = -Math.PI / 2; rug.position.y = 0.01; rug.receiveShadow = true; scene.add(rug);
  const rugRing = new THREE.Mesh(new THREE.RingGeometry(3.3, 3.45, 64), new THREE.MeshBasicMaterial({ color: 0x8a1626, side: THREE.DoubleSide })); rugRing.rotation.x = -Math.PI / 2; rugRing.position.y = 0.012; scene.add(rugRing);
  const wall = new THREE.Mesh(new THREE.CylinderGeometry(11, 11, 7, 48, 1, true), new THREE.MeshStandardMaterial({ color: 0x15111c, side: THREE.BackSide, roughness: 0.9 })); wall.position.y = 3.5; scene.add(wall);
  // fenêtres sur la ville nocturne
  const winMat = new THREE.MeshBasicMaterial({ color: new THREE.Color(0.35, 0.5, 1.1), toneMapped: false });
  for (let i = 0; i < 7; i++) {
    const a = (i / 7) * Math.PI * 2 + 0.2;
    const w = new THREE.Mesh(new THREE.PlaneGeometry(3.2, 3.6), winMat); w.position.set(Math.sin(a) * 10.85, 3.2, Math.cos(a) * 10.85); w.lookAt(0, 3.2, 0); scene.add(w);
    const frame = new THREE.Mesh(new THREE.BoxGeometry(0.16, 3.7, 0.16), toon(0x0a0a10)); frame.position.copy(w.position); frame.lookAt(0, 3.2, 0); scene.add(frame);
    for (let k = 0; k < 7; k++) { const b = new THREE.Mesh(new THREE.BoxGeometry(0.3 + Math.random() * 0.4, 0.8 + Math.random() * 1.6, 0.05), new THREE.MeshBasicMaterial({ color: 0x0a0c18 })); b.position.copy(w.position).multiplyScalar(0.995); b.position.y = 1.6 + Math.random() * 0.4; b.position.x += (Math.random() - 0.5) * 2.6 * Math.cos(a); b.position.z += (Math.random() - 0.5) * 2.6 * -Math.sin(a); b.lookAt(0, b.position.y, 0); scene.add(b); }
  }

  // ----- table
  const felt = new THREE.Mesh(new THREE.CylinderGeometry(1.45, 1.45, 0.06, 40), new THREE.MeshStandardMaterial({ color: 0x4a0e18, roughness: 0.95 })); felt.position.y = 0.78; felt.castShadow = felt.receiveShadow = true; scene.add(felt);
  const rim3 = new THREE.Mesh(new THREE.TorusGeometry(1.45, 0.07, 8, 48), new THREE.MeshStandardMaterial({ color: 0x1c1119, roughness: 0.4, metalness: 0.5 })); rim3.rotation.x = Math.PI / 2; rim3.position.y = 0.8; scene.add(rim3);
  const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.5, 0.78, 16), new THREE.MeshStandardMaterial({ color: 0x120c12, roughness: 0.5 })); leg.position.y = 0.39; leg.castShadow = true; scene.add(leg);
  const glow = new THREE.Mesh(new THREE.RingGeometry(0.6, 0.66, 48), new THREE.MeshBasicMaterial({ color: new THREE.Color(3, 0.3, 0.4), toneMapped: false, side: THREE.DoubleSide })); glow.rotation.x = -Math.PI / 2; glow.position.y = 0.815; scene.add(glow);
  // cartes en éventail, pion d'échecs, bougie
  const cardMat = new THREE.MeshStandardMaterial({ color: 0xe9e4da, roughness: 0.6 }), backMat = new THREE.MeshStandardMaterial({ color: 0x15101a, roughness: 0.6 });
  const cards = new THREE.Group(); cards.position.set(0.4, 0.83, 0.2);
  for (let i = 0; i < 6; i++) { const c = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.004, 0.24), [cardMat, cardMat, i % 2 ? cardMat : backMat, cardMat, cardMat, cardMat]); c.rotation.y = -0.6 + i * 0.22; c.position.y = i * 0.004; c.castShadow = true; cards.add(c); }
  scene.add(cards);
  const pawn = new THREE.Group();
  const pm = new THREE.MeshStandardMaterial({ color: 0x0b0b10, roughness: 0.25, metalness: 0.7 });
  const pb = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.08, 0.05, 16), pm), pbody = new THREE.Mesh(new THREE.ConeGeometry(0.05, 0.16, 16), pm), ph = new THREE.Mesh(new THREE.SphereGeometry(0.045, 16, 12), pm);
  pb.position.y = 0.025; pbody.position.y = 0.13; ph.position.y = 0.25; pawn.add(pb, pbody, ph); pawn.position.set(-0.25, 0.81, -0.1); pawn.traverse(o => { o.castShadow = true; }); scene.add(pawn);
  const candle = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.14, 10), new THREE.MeshStandardMaterial({ color: 0xe8e0d0 })); candle.position.set(-0.7, 0.88, 0.5); scene.add(candle);
  const flame = new THREE.Sprite(new THREE.SpriteMaterial({ color: new THREE.Color(4, 1.8, 0.5), blending: THREE.AdditiveBlending, depthWrite: false, transparent: true, map: glowSprite() })); flame.scale.setScalar(0.18); flame.position.set(-0.7, 1.0, 0.5); scene.add(flame);
  const cl = new THREE.PointLight(0xff9a4a, 5, 5); cl.position.copy(flame.position); scene.add(cl);
  // lampe suspendue
  const shade = new THREE.Mesh(new THREE.ConeGeometry(0.7, 0.45, 24, 1, true), new THREE.MeshStandardMaterial({ color: 0x0f0b12, side: THREE.DoubleSide, roughness: 0.4, metalness: 0.6 })); shade.position.y = 4.4; scene.add(shade);
  const cord = new THREE.Mesh(new THREE.CylinderGeometry(0.01, 0.01, 3, 4), new THREE.MeshBasicMaterial({ color: 0x050508 })); cord.position.y = 5.9; scene.add(cord);
  const bulb = new THREE.Mesh(new THREE.SphereGeometry(0.1, 12, 10), new THREE.MeshBasicMaterial({ color: new THREE.Color(5, 3.4, 1.8), toneMapped: false })); bulb.position.y = 4.35; scene.add(bulb);
  // chaises : une par siège, toujours à la même place
  const seats = [];
  for (let i = 0; i < SIEGES; i++) {
    const a = (i / SIEGES) * Math.PI * 2;
    const chair = new THREE.Group(); chair.position.set(Math.sin(a) * (R + 0.2), 0, Math.cos(a) * (R + 0.2)); chair.rotation.y = a + Math.PI;
    const seat = new THREE.Mesh(new THREE.BoxGeometry(0.55, 0.06, 0.55), new THREE.MeshStandardMaterial({ color: 0x1a1219, roughness: 0.5 })); seat.position.y = 0.46; seat.castShadow = true; chair.add(seat);
    const back = new THREE.Mesh(new THREE.BoxGeometry(0.55, 0.6, 0.05), new THREE.MeshStandardMaterial({ color: 0x1a1219, roughness: 0.5 })); back.position.set(0, 0.8, -0.27); back.castShadow = true; chair.add(back);
    scene.add(chair); seats.push({ a, x: Math.sin(a) * R, z: Math.cos(a) * R });
  }
  // poussières
  const dustN = 220, dustPos = new Float32Array(dustN * 3);
  for (let i = 0; i < dustN; i++) { dustPos[i * 3] = (Math.random() - 0.5) * 16; dustPos[i * 3 + 1] = Math.random() * 6; dustPos[i * 3 + 2] = (Math.random() - 0.5) * 16; }
  const dg = new THREE.BufferGeometry(); dg.setAttribute('position', new THREE.BufferAttribute(dustPos, 3));
  const dust = new THREE.Points(dg, new THREE.PointsMaterial({ color: 0xffe4c0, size: 0.04, transparent: true, opacity: 0.45, depthWrite: false })); scene.add(dust);

  // ----- effets passagers : objet ajouté à la scène, mis à jour avec p de 0 à 1, puis retiré
  const effets = [];
  function effet(obj, duree, maj, fin) { scene.add(obj); effets.push({ obj, t: 0, duree, maj, fin }); return obj; }
  function jeter(obj) { scene.remove(obj); obj.traverse(o => { if (o.geometry && !o.isSprite) o.geometry.dispose(); if (o.material && !o.material.userData.partage) o.material.dispose(); }); }
  const additif = (color, opacity = 1) => new THREE.MeshBasicMaterial({ color, transparent: true, opacity, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide, toneMapped: false });
  function colonne(s, color, duree, rayon = 0.45) {
    const m = new THREE.Mesh(new THREE.CylinderGeometry(rayon, rayon, 5, 28, 1, true), additif(color, 0)); m.position.set(s.x, 2.5, s.z);
    return effet(m, duree, p => { m.material.opacity = Math.sin(p * Math.PI) * 0.55; m.scale.set(1 - p * 0.4, 1, 1 - p * 0.4); });
  }
  function anneau(x, y, z, color, duree, taille = 4) {
    const m = new THREE.Mesh(new THREE.RingGeometry(0.28, 0.36, 48), additif(color)); m.rotation.x = -Math.PI / 2; m.position.set(x, y, z);
    return effet(m, duree, p => { m.scale.setScalar(1 + p * taille); m.material.opacity = 1 - p; });
  }

  // ----- avatars
  const avatars = new Map();          // id -> { char, tag, sig, siege, nom, sub, subColor, accent, anim, t }
  const fantomes = new Map();         // id -> étiquette laissée sur la chaise d'une IA éliminée
  let espionRevele = null;            // id de l'espion une fois la partie finie
  const aFaireApparaitre = new Set(); // arrivées annoncées avant que l'avatar n'existe
  let derniereListe = [];
  const lookOf = j => { const a = ARCHETYPES[j.arch] || ARCHETYPES.stratege, c = j.couleurs || {}; return { ...a, arch: j.arch, hair: c.cheveux || a.hair, eyes: c.yeux || a.eyes, accent: c.accent || a.accent }; };
  const tagPos = s => new THREE.Vector3(s.x * 1.12, TAG_Y, s.z * 1.12);

  function construire(j) {
    const look = lookOf(j), char = createCharacter(look), s = seats[j.siege];
    char.setMode('sit'); char.group.position.set(s.x, 0.02, s.z); char.group.rotation.y = s.a + Math.PI; scene.add(char.group);
    const tag = makeTag(j.nom, '#ffffff'); tag.scale.set(1.0, 0.25, 1); tag.position.copy(tagPos(s)); scene.add(tag);
    const a = { id: j.id, char, tag, sig: sigOf(j), siege: j.siege, nom: j.nom, sub: '', subColor: '', couleur: '#ffffff', accent: look.accent, anim: null, t: 0 };
    avatars.set(j.id, a);
    if (aFaireApparaitre.delete(j.id)) apparaitre(a);
    return a;
  }
  const sigOf = j => JSON.stringify([j.arch, j.couleurs, j.siege]);
  function retirer(id) { const a = avatars.get(id); if (!a) return; scene.remove(a.char.group); jeter(a.tag); avatars.delete(id); }
  function redessiner(a) { retag(a.tag, a.nom, a.subColor || a.couleur, a.sub); }

  // liste : [{ id, nom, arch, couleurs, siege, en_ligne, elimine }] ; un éliminé n'a plus d'avatar, seulement une étiquette fantôme
  api.setJoueurs = liste => {
    derniereListe = liste;
    const assis = new Set();
    for (const j of liste) {
      if (j.siege == null || j.siege >= SIEGES) continue;
      const a = avatars.get(j.id);
      if (a && a.anim === 'elimination') continue;             // l'animation retirera l'avatar elle-même
      if (j.elimine) { if (a) retirer(j.id); fantome(j, j.id === espionRevele ? "🕵 c'était l'espion" : undefined); continue; }
      if (fantomes.has(j.id)) { jeter(fantomes.get(j.id)); fantomes.delete(j.id); }
      assis.add(j.id);
      let b = a;
      if (!b || b.sig !== sigOf(j)) { const deplace = !!b; if (b) retirer(j.id); b = construire(j); if (deplace) apparaitre(b); }
      const couleur = j.en_ligne ? '#ffffff' : '#6c6c78';
      if (b.nom !== j.nom || b.couleur !== couleur) { b.nom = j.nom; b.couleur = couleur; redessiner(b); }
    }
    for (const id of [...avatars.keys()]) if (!assis.has(id) && avatars.get(id).anim !== 'elimination') retirer(id);
    const fant = new Set(liste.filter(j => j.elimine && j.siege != null).map(j => j.id));
    for (const [id, tag] of fantomes) if (!fant.has(id)) { jeter(tag); fantomes.delete(id); }
  };
  function fantome(j, sub = '✝ éliminé') {
    let tag = fantomes.get(j.id);
    if (!tag) { tag = makeTag(j.nom, '#6c6c78', sub); tag.scale.set(1.0, 0.25, 1); tag.position.copy(tagPos(seats[j.siege])).setY(1.25); scene.add(tag); fantomes.set(j.id, tag); }
    else if (tag.userData.texte !== j.nom + sub) retag(tag, j.nom, '#6c6c78', sub);
    tag.userData.texte = j.nom + sub;
  }

  // ----- arrivée : colonne de lumière, l'IA se matérialise sur sa chaise
  function apparaitre(a) {
    const s = seats[a.siege];
    a.anim = 'arrivee'; a.t = 0; a.char.group.scale.setScalar(0.01);
    colonne(s, a.accent, 1.8); anneau(s.x, 0.03, s.z, a.accent, 1.4, 3);
  }
  api.spawn = id => { const a = avatars.get(id); if (a) apparaitre(a); else aFaireApparaitre.add(id); };

  // ----- statut sous le nom (température, votes…)
  api.setSub = (id, sub, color = '') => { const a = avatars.get(id); if (!a || (a.sub === sub && a.subColor === color)) return; a.sub = sub; a.subColor = color; redessiner(a); };

  // ----- bulle de dialogue au-dessus d'un personnage
  const bulles = [];
  api.clearBulles = () => { for (const b of bulles) jeter(b.s); bulles.length = 0; };
  api.say = (id, text) => {
    const a = avatars.get(id); if (!a || !text) return;
    const c = document.createElement('canvas'); c.width = 640; c.height = 256; const g = c.getContext('2d');
    g.font = '600 30px "Segoe UI", sans-serif';
    const lignes = []; let cur = '';
    for (const w of String(text).split(/\s+/)) { if (cur && g.measureText(cur + ' ' + w).width > 580) { lignes.push(cur); cur = w; } else cur = cur ? cur + ' ' + w : w; }
    lignes.push(cur); if (lignes.length > 5) { lignes.length = 5; lignes[4] = lignes[4].replace(/.{0,3}$/, '…'); }
    const hh = 24 + lignes.length * 38;
    g.fillStyle = 'rgba(13,13,19,.93)'; g.strokeStyle = a.accent || '#d6182c'; g.lineWidth = 4; g.beginPath(); g.roundRect(8, 8, 624, hh, 18); g.fill(); g.stroke();
    g.fillStyle = '#fff'; lignes.forEach((l, i) => g.fillText(l, 28, 52 + i * 38));
    const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace;
    const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false, depthTest: false })); s.scale.set(2.2, 0.88, 1); s.center.set(0.5, 1 - (hh + 8) / 256); s.renderOrder = 11; scene.add(s);
    for (const b of bulles) b.until = Math.min(b.until, performance.now() + 400);   // la bulle précédente s'efface
    bulles.push({ id, s, until: performance.now() + 4000 + String(text).length * 70 });
  };

  // ----- « … » au-dessus de celui qui réfléchit
  const points = new THREE.Group(); points.visible = false; scene.add(points);
  const pointMat = new THREE.SpriteMaterial({ map: glowSprite(), color: new THREE.Color(2.2, 2.2, 2.6), blending: THREE.AdditiveBlending, depthWrite: false, depthTest: false, transparent: true });
  for (let i = 0; i < 3; i++) { const p = new THREE.Sprite(pointMat); p.scale.setScalar(0.13); p.position.x = (i - 1) * 0.16; p.renderOrder = 10; points.add(p); }
  let reflechit = null;
  api.thinking = id => { reflechit = id; };

  // ----- caméra : orbite lente, ou cadrage sur celui qui parle
  let focusId = null, orbit = 0, drag = 0, manuel = 0, camR = 6.6, rayonVoulu = 6.6, camH = 3.4;
  const vise = new THREE.Vector3(0, 1.05, 0), viseVoulu = new THREE.Vector3();
  api.focus = id => { if (id || ![...avatars.values()].some(a => a.anim === 'elimination')) focusId = id; };   // l'élimination garde la caméra
  api.pointer = { down(x) { drag = x; manuel = 8; }, move(x) { if (drag) { orbit += (x - drag) * 0.006; drag = x; manuel = 8; } }, up() { drag = 0; }, wheel(d) { rayonVoulu = Math.min(9, Math.max(3.5, rayonVoulu + d * 0.004)); manuel = 8; } };

  // ----- mesure publiée : une onde sur la table devant le capteur
  api.pulse = id => { const a = avatars.get(id); if (!a) return; const s = seats[a.siege]; anneau(s.x * 0.6, 0.83, s.z * 0.6, '#5fd3ff', 0.9, 1.6); };

  // ----- votes : un arc rouge du votant vers le suspect
  const arcs = [];
  const arcMat = additif(new THREE.Color(1.8, 0.08, 0.14));   // rouge sans bloom, lumineux avec arcMat.userData.partage = true;
  api.vote = (de, vers) => {
    const a = avatars.get(de), b = avatars.get(vers); if (!a || !b) return;
    const sa = seats[a.siege], sb = seats[b.siege];
    const p0 = new THREE.Vector3(sa.x * 0.9, TETE, sa.z * 0.9), p2 = new THREE.Vector3(sb.x * 0.9, TETE, sb.z * 0.9);
    const p1 = p0.clone().add(p2).multiplyScalar(0.25).setY(2.3);
    const geo = new THREE.TubeGeometry(new THREE.QuadraticBezierCurve3(p0, p1, p2), 48, 0.014, 6, false);
    const m = new THREE.Mesh(geo, arcMat); m.renderOrder = 5; geo.setDrawRange(0, 0); scene.add(m);
    const bout = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowSprite(), color: new THREE.Color(4, 0.4, 0.5), blending: THREE.AdditiveBlending, depthWrite: false, transparent: true })); bout.scale.setScalar(0.22); bout.position.copy(p0); scene.add(bout);
    const courbe = geo.parameters.path;
    arcs.push({ m, bout, courbe, t: 0, total: geo.index.count });
  };
  api.clearVotes = () => { for (const v of arcs) { jeter(v.m); jeter(v.bout); } arcs.length = 0; };

  // ----- élimination : l'IA se lève et est aspirée vers la lampe
  api.eliminer = (id, etaitEspion) => {
    const a = avatars.get(id); if (!a) return;
    a.anim = 'elimination'; a.t = 0; a.espion = !!etaitEspion;
    a.char.setExpr('scared'); a.char.setMode('stand');
    a.char.group.position.set(seats[a.siege].x * 1.08, 0.02, seats[a.siege].z * 1.08);   // il recule de sa chaise
    colonne(seats[a.siege], etaitEspion ? '#ff2030' : '#7cc4ff', 3.4, 0.55);
    focusId = id;
  };

  // ----- fin de partie : l'espion est démasqué (ou se dévoile s'il a gagné)
  api.reveler = (id, gagnant) => {
    espionRevele = id;
    const a = avatars.get(id);
    if (a) { a.char.setExpr(gagnant === 'espion' ? 'smirk' : 'angry'); api.setSub(id, '🕵 ESPION', '#ff4d5e'); colonne(seats[a.siege], '#ff2030', 2.5); }
    else if (fantomes.has(id)) { const j = derniereListe.find(x => x.id === id); if (j) fantome(j, '🕵 c\'était l\'espion'); }
    for (const [aid, b] of avatars) if (aid !== id) b.char.setExpr(gagnant === 'capteurs' ? 'smile' : 'scared');
  };
  api.clearReveal = () => {
    espionRevele = null;
    for (const a of avatars.values()) { a.char.setExpr(a.char.look.expr); a.sub = ''; a.subColor = ''; redessiner(a); }
    for (const id of fantomes.keys()) { const j = derniereListe.find(x => x.id === id); if (j) fantome(j); }
  };

  // ----- ambiance selon la phase (anneau lumineux de la table)
  const AMBIANCES = { mesures: [0.4, 1.6, 3], debat: [3, 1.2, 0.3], vote: [3.5, 0.2, 0.3], verdict: [4, 0.1, 0.2], fini: [3, 2.2, 0.6] };
  let ambiance = [2.4, 0.25, 0.35];
  api.setAmbiance = etat => { ambiance = AMBIANCES[etat] || [2.4, 0.25, 0.35]; };

  // ----- animation
  let t = 0, horloge = performance.now();
  api.update = dt => {
    t += dt;
    const maintenant = performance.now(), dtr = Math.min(0.5, (maintenant - horloge) / 1000); horloge = maintenant;
    for (const a of avatars.values()) {
      a.char.update(dt, 0, t);
      if (a.anim === 'arrivee') {
        a.t += dtr; const p = Math.min(1, a.t / 1.2);
        a.char.group.scale.setScalar(Math.max(0.01, easeOutBack(p)));
        if (p >= 1) { a.anim = null; a.char.group.scale.setScalar(1); }
      } else if (a.anim === 'elimination') {
        a.t += dtr; const g = a.char.group;
        if (a.t < 0.9) g.position.x += Math.sin(t * 60) * 0.004;                 // il tremble
        else {
          const p = Math.min(1, (a.t - 0.9) / 2.3);
          g.position.y = 0.02 + ease(p) * p * 3.6; g.rotation.y += dt * (2 + p * 14); g.scale.setScalar(Math.max(0.02, 1 - p * 0.9));
          a.tag.material.opacity = 1 - p;
          if (p >= 1) { a.anim = null; retirer(a.id); api.setJoueurs(derniereListe); if (focusId === a.id) focusId = null; }
        }
      }
    }
    for (let i = bulles.length - 1; i >= 0; i--) {
      const b = bulles[i], a = avatars.get(b.id);
      if (!a || performance.now() > b.until) { jeter(b.s); bulles.splice(i, 1); } else b.s.position.set(a.tag.position.x, a.tag.position.y + 0.25, a.tag.position.z);
    }
    for (let i = effets.length - 1; i >= 0; i--) {
      const e = effets[i]; e.t += dtr; const p = Math.min(1, e.t / e.duree); e.maj(p);
      if (p >= 1) { jeter(e.obj); effets.splice(i, 1); if (e.fin) e.fin(); }
    }
    for (const v of arcs) {
      if (v.t >= 1) continue;
      v.t = Math.min(1, v.t + dtr / 0.7); const p = ease(v.t);
      v.m.geometry.setDrawRange(0, Math.floor(v.total * p / 3) * 3); v.courbe.getPoint(p, v.bout.position);
    }
    // « … » au-dessus de celui qui réfléchit
    const r = reflechit && avatars.get(reflechit);
    points.visible = !!r;
    if (r) { points.position.copy(r.tag.position).setY(r.tag.position.y + 0.32); points.children.forEach((p, i) => { p.position.y = Math.max(0, Math.sin(t * 6 - i * 0.8)) * 0.08; }); }
    // projecteur sur celui qui parle (ou qui est éliminé)
    const f = focusId && avatars.get(focusId);
    if (f) { const s = seats[f.siege]; projo.position.set(s.x * 0.7, 4.2, s.z * 0.7); projo.target.position.set(s.x, 1, s.z); projo.color.set(f.anim === 'elimination' ? (f.espion ? 0xff3040 : 0x9fd0ff) : 0xffe2b0); }
    projo.intensity += ((f ? 35 : 0) - projo.intensity) * Math.min(1, dt * 4);
    const e = espionRevele && avatars.get(espionRevele);
    if (e) { const s = seats[e.siege]; lueurEspion.position.set(s.x, 2.1, s.z); }
    lueurEspion.intensity += ((e ? 14 + Math.sin(t * 5) * 4 : 0) - lueurEspion.intensity) * Math.min(1, dt * 3);
    // caméra
    if (!drag) manuel -= dt;
    if (f && manuel <= 0) {
      const s = seats[f.siege];
      orbit += angleVers(orbit, s.a + Math.PI) * Math.min(1, dt * 1.4);   // de l'autre côté de la table, face à lui
      camR += (5.3 - camR) * Math.min(1, dt * 1.5);
      viseVoulu.set(s.x * 0.6, 1.2, s.z * 0.6);
    } else {
      if (!drag && manuel <= 0) orbit += dt * 0.07;
      camR += (rayonVoulu - camR) * Math.min(1, dt * 1.5);
      viseVoulu.set(0, 1.05, 0);
    }
    vise.lerp(viseVoulu, Math.min(1, dt * 2));
    camera.position.set(Math.sin(orbit) * camR, camH, Math.cos(orbit) * camR); camera.lookAt(vise);
    // décor
    const fl = 1 + Math.sin(t * 9) * 0.15 + Math.sin(t * 23) * 0.08;
    flame.scale.setScalar(0.18 * fl); cl.intensity = 4.5 + fl * 1.5; lamp.intensity = 90 + Math.sin(t * 1.3) * 4;
    const pulse = 0.8 + Math.sin(t * 2) * 0.2;
    glow.material.color.setRGB(ambiance[0] * pulse, ambiance[1] * pulse, ambiance[2] * pulse);
    cards.rotation.y = Math.sin(t * 0.5) * 0.05;
    dust.rotation.y += dt * 0.01;
  };
  api.avatars = avatars;   // pour déboguer depuis la console : __cn.hub.avatars
  api.resize = (w, h) => { camera.aspect = w / h; camera.updateProjectionMatrix(); };
  api.setShadows = on => { lamp.castShadow = on; };
  return api;
}

let _gs = null;
function glowSprite() {
  if (_gs) return _gs;
  const c = document.createElement('canvas'); c.width = c.height = 64; const g = c.getContext('2d'), gr = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  gr.addColorStop(0, 'rgba(255,255,255,1)'); gr.addColorStop(0.35, 'rgba(255,255,255,.5)'); gr.addColorStop(1, 'rgba(255,255,255,0)'); g.fillStyle = gr; g.fillRect(0, 0, 64, 64);
  return (_gs = new THREE.CanvasTexture(c));
}
