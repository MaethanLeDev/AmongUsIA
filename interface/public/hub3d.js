// Salon 3D : une table ronde sous une lampe, les avatars de tous les joueurs assis autour.
import * as THREE from 'three';
import { createCharacter, makeTag, retag, ARCHETYPES, toon } from './chars.js';

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
  const key = new THREE.SpotLight(0xfff2e0, 24, 14, 0.6, 0.6, 1.5); key.position.set(-1.5, 3.2, 4.2); key.target.position.set(1.15, 1.1, 1.6); key.visible = false; scene.add(key, key.target);
  const rim = new THREE.PointLight(0xc1121f, 10, 14); rim.position.set(-5, 2.5, 4); scene.add(rim);
  const rim2 = new THREE.PointLight(0x4263eb, 8, 14); rim2.position.set(5, 2.5, -4); scene.add(rim2);

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
  // cartes éventail, pion d'échecs, bougie
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
  // chaises (une par place possible)
  const SEATS = 12, R = 2.15, seats = [];
  for (let i = 0; i < SEATS; i++) {
    const a = (i / SEATS) * Math.PI * 2;
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

  // ----- avatars
  const avatars = new Map();        // id -> {char, tag, sig, seat}
  let myId = 0, preview = null, previewChar = null, orbit = 0, drag = 0, camR = 6.6, camH = 3.4;
  const sigOf = l => JSON.stringify([l.arch, l.hair, l.eyes, l.accent]);
  const fullLook = l => Object.assign({}, ARCHETYPES[(l && l.arch) || 'stratege'], l || {});
  function buildAvatar(u) {
    const look = fullLook(u.look), char = createCharacter(look);
    char.setMode('sit'); scene.add(char.group);
    const tag = makeTag(u.name, u.id === myId ? '#ffd0d6' : '#ffffff'); tag.scale.set(1.0, 0.25, 1); scene.add(tag);
    return { char, tag, sig: sigOf(u.look || {}), name: u.name, seat: 0, look, sub: '', subColor: undefined };
  }
  api.setUsers = (users, me) => {
    myId = me;
    const ids = new Set(users.map(u => u.id));
    for (const [id, a] of avatars) if (!ids.has(id)) { scene.remove(a.char.group); scene.remove(a.tag); avatars.delete(id); }
    users.forEach((u, i) => {
      let a = avatars.get(u.id);
      if (!a || a.sig !== sigOf(u.look || {})) { if (a) { scene.remove(a.char.group); scene.remove(a.tag); } a = buildAvatar(u); avatars.set(u.id, a); }
      else if (a.name !== u.name) { a.name = u.name; retag(a.tag, u.name, a.subColor || (u.id === myId ? '#ffd0d6' : '#fff'), a.sub); }
      a.seat = i;
    });
    // répartition équilibrée autour de la table
    const n = users.length;
    users.forEach((u, i) => {
      const a = avatars.get(u.id), s = seats[Math.round((i / Math.max(1, n)) * SEATS) % SEATS];
      a.char.group.position.set(s.x, 0.02, s.z); a.char.group.rotation.y = s.a + Math.PI;
      a.tag.position.set(s.x * 1.12, 1.62 + 0.45, s.z * 1.12);
    });
  };
  // ligne de statut sous le nom (température, vote…) et bulle de dialogue au-dessus d'un personnage
  api.setSub = (id, sub, color) => {
    const a = avatars.get(id); if (!a || (a.sub === sub && a.subColor === color)) return;
    a.sub = sub; a.subColor = color; retag(a.tag, a.name, color || (id === myId ? '#ffd0d6' : '#fff'), sub);
  };
  const bubbles = [];
  api.say = (id, text) => {
    const a = avatars.get(id); if (!a || !text) return;
    const c = document.createElement('canvas'); c.width = 512; c.height = 192; const g = c.getContext('2d');
    g.font = '600 30px "Segoe UI", sans-serif';
    const lines = []; let cur = '';
    for (const w of String(text).split(/s+/)) { if (g.measureText(cur + ' ' + w).width > 450 && cur) { lines.push(cur); cur = w; } else cur = cur ? cur + ' ' + w : w; }
    lines.push(cur); if (lines.length > 4) { lines.length = 4; lines[3] = lines[3].replace(/.{0,3}$/, '…'); }
    const hh = 24 + lines.length * 38;
    g.fillStyle = 'rgba(13,13,19,.93)'; g.strokeStyle = '#d6182c'; g.lineWidth = 4; g.beginPath(); g.roundRect(8, 8, 496, hh, 18); g.fill(); g.stroke();
    g.fillStyle = '#fff'; lines.forEach((l, i) => g.fillText(l, 28, 52 + i * 38));
    const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace;
    const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false, depthTest: false })); s.scale.set(2.2, 0.825, 1); s.center.set(0.5, 1 - (hh + 8) / 192); s.renderOrder = 11; scene.add(s);
    const old = bubbles.findIndex(b => b.id === id); if (old >= 0) { scene.remove(bubbles[old].s); bubbles.splice(old, 1); }
    bubbles.push({ id, s, until: performance.now() + 3500 + String(text).length * 60 });
  };
  api.setPreview = look => {
    if (previewChar) { scene.remove(previewChar.group); scene.remove(previewChar.tag); previewChar = null; }
    preview = look; key.visible = !!look;
    if (look) {
      const c = createCharacter(fullLook(look)); c.group.position.set(1.15, 0.02, 1.6); c.group.rotation.y = Math.PI + 0.35; scene.add(c.group);
      previewChar = { group: c.group, char: c };
    }
    for (const a of avatars.values()) { a.char.group.visible = !look; a.tag.visible = !look; }
    for (const o of [shade, cord, bulb, cl, flame, candle, pawn, cards, felt, rim3, leg, glow, rug, rugRing]) o.visible = true;
  };
  api.setPreviewLook = look => { if (preview) api.setPreview(look); };

  // ----- interaction caméra
  api.pointer = { down(x) { drag = x; }, move(x) { if (drag) { orbit += (x - drag) * 0.006; drag = x; } }, up() { drag = 0; }, wheel(d) { camR = Math.min(9, Math.max(3.5, camR + d * 0.004)); } };

  let t = 0, mode = 'hub', lookY = 1.05;
  api.setMode = m => { mode = m; };
  api.update = dt => {
    t += dt;
    if (!drag) orbit += dt * 0.07;
    for (const a of avatars.values()) a.char.update(dt, 0, t);
    for (let i = bubbles.length - 1; i >= 0; i--) {
      const b = bubbles[i], a = avatars.get(b.id);
      if (!a || performance.now() > b.until) { scene.remove(b.s); bubbles.splice(i, 1); } else b.s.position.set(a.tag.position.x, a.tag.position.y + 0.3, a.tag.position.z);
    }
    if (previewChar) { previewChar.char.update(dt, 0, t); previewChar.group.rotation.y += dt * 0.35; }
    const f = 1 + Math.sin(t * 9) * 0.15 + Math.sin(t * 23) * 0.08;
    flame.scale.setScalar(0.18 * f); cl.intensity = 4.5 + f * 1.5; lamp.intensity = 90 + Math.sin(t * 1.3) * 4;
    glow.material.color.setRGB(2.4 + Math.sin(t * 2) * 0.8 + (mode === 'table' ? 1.5 : 0), 0.25, 0.35);
    cards.rotation.y = Math.sin(t * 0.5) * 0.05;
    dust.rotation.y += dt * 0.01;
    if (preview) { camera.position.set(0.0, 1.35, 6.4); camera.lookAt(0.3, 1.0, 1.6); }
    else {
      lookY += ((mode === 'table' ? -1.1 : 1.05) - lookY) * Math.min(1, dt * 2.5);   // en mode table, la table remonte au-dessus des panneaux
      camera.position.set(Math.sin(orbit) * camR, camH - (mode === 'table' ? 0.9 : 0), Math.cos(orbit) * camR); camera.lookAt(0, lookY, 0);
    }
  };
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
