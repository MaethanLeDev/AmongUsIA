// Panneau de la partie du TP (espion) : manche, températures, votes, résultat. Les Pi sont déjà des personnages du salon 3D.
export function initEspion({ Net, hub, isHost }) {
  const box = document.getElementById('espionUI');
  let st = null, visible = false, subs = [];
  const colorOf = id => `hsl(${(id * 67 + 10) % 360} 70% 68%)`;
  const h = (tag, attrs, ...kids) => {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) { if (k === 'class') e.className = v; else if (k === 'text') e.textContent = v; else if (k.startsWith('on')) e.addEventListener(k.slice(2), v); else if (v != null && v !== false) e.setAttribute(k, v); }
    for (const c of kids.flat()) if (c != null && c !== false) e.append(c.nodeType ? c : document.createTextNode(c));
    return e;
  };
  const PHASES = { attente: 'En attente des capteurs…', en_cours: 'Échange des températures', vote: 'Les capteurs votent', fini: 'Partie terminée' };

  Net.on('e_state', m => { st = m; if (visible) render(); });

  function render() {
    if (!st) return;
    box.textContent = '';
    box.append(h('div', { class: 'label first', text: 'La partie du TP — l\'espion' }), h('div', { class: 'big', text: PHASES[st.phase] || st.phase }),
      h('div', { class: 'edots' }, Array.from({ length: st.manches }, (_, i) => h('i', { class: i < st.manche ? 'on' : '' }))),
      h('div', { class: 'tiny', text: `Manche ${st.manche}/${st.manches} · ${st.players.filter(p => p.on).length} capteur(s) en ligne` }));
    if (!st.players.length) box.append(h('p', { class: 'dim', text: 'Aucun Raspberry Pi connecté. Ils apparaissent ici dès qu\'ils s\'annoncent sur le broker.' }));
    const spyId = st.resultat && st.resultat.espion, newSubs = [];
    for (const p of st.players) {
      const isSpy = p.id === spyId;
      box.append(h('div', { class: 'ecard' + (p.on ? '' : ' off') + (isSpy ? ' spy' : '') },
        h('div', { class: 'top' }, h('b', { style: `color:${colorOf(p.user)}`, text: (isSpy ? '🕵 ' : '📡 ') + p.name }), h('small', { text: p.ville || '' })),
        h('div', { class: 'etemp', text: p.last == null ? '—' : p.last + ' °C' }),
        p.temps.length ? h('div', { class: 'tiny', text: p.temps.join(' · ') }) : null,
        p.vote ? h('div', { class: 'evote' }, '🗳 soupçonne ', h('b', { text: p.vote.name }), p.vote.raison ? h('div', { class: 'tiny', text: p.vote.raison }) : null) : null));
      hub.setSub(p.user, isSpy ? '🕵 ESPION' : p.vote ? '🗳 ' + p.vote.name : p.last == null ? '' : p.last + ' °C', isSpy ? '#ff4d5e' : undefined);
      newSubs.push(p.user);
    }
    for (const id of subs) if (!newSubs.includes(id)) hub.setSub(id, '');
    subs = newSubs;
    if (st.tally.length) box.append(h('div', { class: 'label', text: st.resultat ? 'Votes' : 'Votes (provisoire)' }), h('div', { class: 'tiny', text: st.tally.map(t => `${t.name} ×${t.n}`).join(' · ') }));
    if (st.resultat) box.append(h('div', { class: 'eres ' + (st.resultat.gagnant === 'capteurs' ? 'pos' : 'neg'), text: `🏁 ${st.resultat.gagnant === 'capteurs' ? 'Les capteurs gagnent' : 'L\'espion gagne'} — espion : ${st.resultat.espionName}` }));
    if (isHost()) box.append(h('button', { class: 'ghost small', onclick: () => Net.send({ t: 'tohub' }), text: '← Salon' }));
  }

  return {
    show() { visible = true; box.classList.remove('hidden'); render(); },
    hide() { visible = false; box.classList.add('hidden'); for (const id of subs) hub.setSub(id, ''); subs = []; },
  };
}
