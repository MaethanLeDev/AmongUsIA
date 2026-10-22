// Interface du jeu de TABLE (cartes de manipulation), intégrée au salon.
export function initTable({ Net, beep }) {
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
  const colorOf = id => `hsl(${(id * 67 + 10) % 360} 70% 68%)`;
  const send = o => Net.send(o);

  let st = null, recvAt = 0, phaseKey = '', phaseTotal = 1;
  let intel = null, reveal = null, final = null;
  let myPact = null, reqs = [], lockedAct = null, rumorUsed = false, readySent = false;
  const sel = { a: 'coop', target: 0, scapegoat: 0 };
  let accSel;
  const nameOf = id => { const p = st && st.players.find(x => x.id === id); return p ? p.name : '?'; };
  const myId = () => Net.id;

  // ------------------------------------------------------------ messages
  let pending = null;
  Net.on('state', m => { if (!visible) { pending = m; return; } onState(m); });
  Net.on('chat', m => { if (visible) addLog(m); if (m.kind === 'whisper' && m.from !== myId()) beep(520, 0.08, 0.05); });
  Net.on('pactReq', m => { reqs.push({ from: m.from, name: m.name }); beep(660, 0.15, 0.08); beep(880, 0.2, 0.06); renderStage(); });
  Net.on('pact', m => { myPact = { with: m.with, name: m.name }; reqs = []; beep(440, 0.25, 0.08); renderStage(); renderPlayers(); });
  Net.on('locked', m => { lockedAct = m.act; renderStage(); });
  Net.on('intel', m => { intel = m; beep(180, 0.3, 0.1, 'sawtooth'); renderStage(); });
  Net.on('reveal', m => { reveal = m; renderStage(); });
  Net.on('final', m => { final = m; renderStage(); beep(392, 0.2, 0.1); setTimeout(() => beep(523, 0.4, 0.1), 200); });
  let visible = false;

  function onState(m) {
    const prev = st; st = m; recvAt = performance.now();
    const key = m.phase + ':' + m.round;
    if (key !== phaseKey) {
      phaseKey = key; phaseTotal = Math.max(1000, m.rem);
      if (m.phase === 'negotiate') { myPact = null; reqs = []; intel = null; reveal = null; lockedAct = null; rumorUsed = false; readySent = false; sel.a = 'coop'; sel.target = 0; sel.scapegoat = 0; accSel = undefined; }
      if (m.phase === 'decide') lockedAct = null;
      if (m.phase === 'accuse') accSel = undefined;
      if (m.phase === 'reveal') readySent = false;
      if (m.phase === 'lobby') { final = null; intel = null; reveal = null; myPact = null; }
      if (prev && prev.phase !== m.phase) beep(m.phase === 'decide' ? 240 : 330, 0.15, 0.07);
    }
    renderPlayers(); renderStage(); renderTo();
  }

  // ------------------------------------------------------------ chat
  function addLog(m) {
    const box = $('log');
    const d = h('div', { class: 'm ' + m.kind });
    if (m.kind === 'pub') d.append(h('span', { class: 'who', style: `color:${colorOf(m.from)}`, text: m.name }), ': ' + m.text);
    else if (m.kind === 'whisper') {
      const mine = m.from === myId();
      d.append('🤫 ', h('span', { class: 'who', style: `color:${colorOf(m.from)}`, text: mine ? 'toi' : m.name }), ' → ', h('span', { class: 'who', text: mine ? m.toName : 'toi' }), ' : ' + m.text);
    } else if (m.kind === 'rumor') d.append('📢 Rumeur anonyme : « ' + m.text + ' »');
    else d.textContent = m.text;
    box.append(d);
    while (box.children.length > 300) box.firstChild.remove();
    box.scrollTop = box.scrollHeight;
  }
  function renderTo() {
    const s = $('to'), cur = s.value || '0';
    s.textContent = '';
    s.append(h('option', { value: '0', text: 'À tous' }));
    if (st) for (const p of st.players) if (p.id !== myId()) s.append(h('option', { value: String(p.id), text: '🤫 ' + p.name }));
    s.value = [...s.options].some(o => o.value === cur) ? cur : '0';
    $('rumorBtn').disabled = !(st && st.phase === 'negotiate') || rumorUsed;
  }
  $('composer').addEventListener('submit', e => {
    e.preventDefault();
    const text = $('msg').value.trim(); if (!text) return;
    const to = Number($('to').value);
    send(to ? { t: 'whisper', to, text } : { t: 'chat', text });
    $('msg').value = '';
  });
  $('rumorBtn').onclick = () => {
    const text = $('msg').value.trim();
    if (!text) { $('msg').focus(); $('msg').placeholder = 'Écris ta rumeur ici, puis reclique…'; return; }
    send({ t: 'rumor', text }); rumorUsed = true; $('msg').value = ''; $('msg').placeholder = 'Dire quelque chose…'; renderTo();
  };
  $('tBack').onclick = () => { if (st && ['negotiate', 'decide', 'accuse', 'reveal'].includes(st.phase) && !confirm('Quitter la partie en cours pour tout le monde ?')) return; send({ t: 'mode', mode: 'hub', force: true }); };

  // ------------------------------------------------------------ joueurs
  function renderPlayers() {
    if (!st) return;
    const box = $('players'); box.textContent = '';
    $('tBack').style.display = st.host === myId() ? '' : 'none';
    const nego = st.phase === 'negotiate';
    for (const p of st.players) {
      const isMe = p.id === myId();
      const chips = [];
      if (st.phase === 'negotiate' && p.ready) chips.push(h('span', { class: 'chip ok', text: '✔ prêt' }));
      if (st.phase === 'decide' && p.locked) chips.push(h('span', { class: 'chip ok', text: '🔒 choisi' }));
      if (st.phase === 'accuse' && p.voted) chips.push(h('span', { class: 'chip ok', text: '🗳 voté' }));
      if (st.phase === 'reveal' && p.ready) chips.push(h('span', { class: 'chip ok', text: '✔' }));
      if (p.pact && ['negotiate', 'decide'].includes(st.phase)) chips.push(h('span', { class: 'chip', text: '🤝 lié(e)' }));
      if (p.expo) chips.push(h('span', { class: 'chip warn', text: '👁 démasqué ×' + p.expo }));
      const mini = h('div', { class: 'mini' });
      if (!isMe) {
        mini.append(h('button', { title: 'Chuchoter', onclick: () => { $('to').value = String(p.id); $('msg').focus(); }, text: '🤫' }));
        if (nego) mini.append(h('button', { title: 'Proposer un pacte', disabled: !!myPact || p.pact, onclick: () => send({ t: 'pact', to: p.id }), text: '🤝' }));
      }
      box.append(h('div', { class: 'pcard' + (isMe ? ' me' : '') + (p.on ? '' : ' off') },
        h('div', { class: 'top' },
          h('span', { class: 'nm', style: `color:${colorOf(p.id)}`, text: (st.host === p.id ? '👑 ' : '') + (p.ext ? '📡 ' : p.bot ? '🤖 ' : '') + p.name + (isMe ? ' (toi)' : '') }),
          h('span', { class: 'pc' }, String(p.pc), h('small', { text: ' PC' }))),
        h('div', { class: 'sub' }, chips, mini)));
    }
  }

  // ------------------------------------------------------------ scène
  const ACTS = [
    { a: 'coop', ic: '🤝', t: 'Coopérer', d: 'Tu mets 2 PC au pot commun. Le pot doublé est partagé entre tous.' },
    { a: 'betray', ic: '🗡', t: 'Trahir', d: 'Vole 3 PC à un élève qui coopère. Désigne un faux coupable si tu veux.' },
    { a: 'watch', ic: '👁', t: 'Observer', d: 'Tu vois ce qu\'une cible a fait en secret. Protégé(e) des vols ce tour.' },
  ];
  const others = () => st.players.filter(p => p.id !== myId());
  function targetPicker(cur, onPick, allowNone) {
    const box = h('div', { class: 'targets' });
    if (allowNone) box.append(h('button', { class: 'tg' + (!cur ? ' sel' : ''), onclick: () => onPick(0), text: 'Personne' }));
    for (const p of others()) box.append(h('button', { class: 'tg' + (cur === p.id ? ' sel' : ''), style: cur === p.id ? '' : `color:${colorOf(p.id)}`, onclick: () => onPick(p.id), text: p.name }));
    return box;
  }
  function intelBox() {
    if (!intel) return null;
    return h('div', { class: 'box' },
      h('div', { class: 'label', style: 'margin-top:0', text: `Tes informations (manche ${intel.round}) — personne d'autre ne les voit` }),
      intel.lines.map(l => h('p', { text: l })),
      h('p', { class: intel.delta >= 0 ? 'pos' : 'neg', text: `Variation : ${intel.delta >= 0 ? '+' : ''}${intel.delta} PC (total ${intel.pc})` }));
  }
  function describeAct(a) {
    if (a.a === 'coop') return 'Coopérer';
    if (a.a === 'watch') return 'Observer ' + nameOf(a.target);
    return 'Trahir ' + nameOf(a.target) + (a.scapegoat ? ` (faux coupable : ${nameOf(a.scapegoat)})` : '');
  }

  function renderStage() {
    if (!st || !visible) return;
    const s = $('stage'); s.textContent = '';
    const title = (a, b) => h('h2', { class: 'stage' }, a, ' ', h('b', { text: b }));
    const isHost = st.host === myId();
    switch (st.phase) {
      case 'lobby': {
        s.append(title('Table de', 'manipulation'));
        s.append(h('p', { class: 'hint', text: `${st.players.length} élève(s) à la table — il en faut au moins 3 (les pions 🤖 comptent).` }));
        if (isHost) {
          const sr = h('select', { class: 'sel-inline', onchange: () => send({ t: 'settings', rounds: Number(sr.value), nego: Number(sn.value) }) });
          for (const n of [3, 5, 6, 8, 10, 12]) sr.append(h('option', { value: n, text: n + ' manches' }));
          const sn = h('select', { class: 'sel-inline', onchange: () => send({ t: 'settings', rounds: Number(sr.value), nego: Number(sn.value) }) });
          for (const n of [45, 90, 150]) sn.append(h('option', { value: n, text: 'négociation ' + n + ' s' }));
          sr.value = st.rounds; sn.value = st.nego;
          s.append(h('div', { class: 'row' }, sr, sn,
            h('button', { class: 'ghost', onclick: () => send({ t: 'addbot' }), text: '+ Pion 🤖' }),
            h('button', { class: 'ghost', onclick: () => send({ t: 'delbot' }), text: '− Pion' })));
          s.append(h('button', { class: 'primary', disabled: st.players.length < 3, onclick: () => send({ t: 'start', rounds: Number(sr.value), nego: Number(sn.value) }), text: 'LANCER LA PARTIE' }));
        } else s.append(h('p', { class: 'hint', text: 'En attente de l\'hôte (👑)…' }));
        s.append(h('div', { class: 'box', style: 'margin-top:22px' }, h('p', { text: 'Tout le monde veut être le plus sombre. Mais la noirceur ne vaut que si on ne se fait pas prendre. Clique sur « ? » pour lire les règles.' })));
        break;
      }
      case 'negotiate': {
        s.append(title('Négociation', `${st.round}/${st.rounds}`));
        s.append(h('p', { class: 'hint', text: 'Parle, chuchote, promets. Propose un pacte de confiance (🤝 sur une carte) — ou fais semblant. À la fin, chacun choisit en secret.' }));
        s.append(myPact
          ? h('div', { class: 'box violet' }, h('p', { text: `🤝 Pacte avec ${myPact.name}. Si vous coopérez tous les deux : +2 PC chacun. Le trahir rapporte beaucoup de noirceur… et beaucoup de haine.` }))
          : h('div', { class: 'box violet' }, h('p', { text: 'Aucun pacte pour l\'instant. Un seul par tour.' })));
        for (const r of reqs) {
          if (myPact) break;
          s.append(h('div', { class: 'req' }, h('span', { text: `${r.name} te propose un pacte de confiance.` }),
            h('button', { class: 'yes', onclick: () => { send({ t: 'pactr', from: r.from, ok: true }); reqs = reqs.filter(x => x !== r); renderStage(); }, text: 'Accepter' }),
            h('button', { onclick: () => { send({ t: 'pactr', from: r.from, ok: false }); reqs = reqs.filter(x => x !== r); renderStage(); }, text: 'Refuser' })));
        }
        s.append(h('div', { class: 'row' },
          h('button', { class: 'primary', disabled: readySent, onclick: () => { readySent = true; send({ t: 'ready' }); renderStage(); }, text: readySent ? 'EN ATTENTE DES AUTRES…' : 'JE SUIS PRÊT' }),
          isHost ? h('button', { class: 'ghost', onclick: () => send({ t: 'skip' }), text: 'Passer (hôte)' }) : null));
        break;
      }
      case 'decide': {
        s.append(title('Choix', 'secret'));
        s.append(h('p', { class: 'hint', text: 'Personne ne verra ton choix. Tu peux le changer jusqu\'à la fin du compte à rebours.' }));
        if (myPact) s.append(h('div', { class: 'box violet' }, h('p', { text: `🤝 Pacte avec ${myPact.name} : trahir ${myPact.name} brise le pacte (grosse noirceur, mais il/elle le saura).` })));
        s.append(h('div', { class: 'cards' }, ACTS.map(a => h('button', { class: 'act' + (sel.a === a.a ? ' sel' : ''), onclick: () => { sel.a = a.a; if (a.a === 'coop') sel.target = 0; renderStage(); } },
          h('div', { class: 'ic', text: a.ic }), h('h3', { text: a.t }), h('p', { text: a.d })))));
        if (sel.a !== 'coop') s.append(h('div', { class: 'label', text: sel.a === 'betray' ? 'Qui trahir ?' : 'Qui observer ?' }), targetPicker(sel.target, id => { sel.target = id; if (sel.scapegoat === id) sel.scapegoat = 0; renderStage(); }));
        if (sel.a === 'betray') {
          s.append(h('div', { class: 'label', text: 'Faux coupable (optionnel) : la victime croira que c\'est lui/elle' }),
            h('div', { class: 'targets' },
              h('button', { class: 'tg' + (!sel.scapegoat ? ' sel' : ''), onclick: () => { sel.scapegoat = 0; renderStage(); }, text: 'Aucun' }),
              others().filter(p => p.id !== sel.target).map(p => h('button', { class: 'tg' + (sel.scapegoat === p.id ? ' sel' : ''), onclick: () => { sel.scapegoat = p.id; renderStage(); }, text: p.name }))));
        }
        const ok = sel.a === 'coop' || sel.target;
        s.append(h('div', { class: 'row' }, h('button', { class: 'primary', disabled: !ok, onclick: () => send({ t: 'act', a: sel.a, target: sel.target, scapegoat: sel.scapegoat }), text: lockedAct ? 'MODIFIER MON CHOIX' : 'VERROUILLER MON CHOIX' })));
        if (lockedAct) s.append(h('div', { class: 'status', text: '🔒 Choix enregistré : ' + describeAct(lockedAct) }));
        if (isHost) s.append(h('button', { class: 'ghost', onclick: () => send({ t: 'skip' }), text: 'Passer (hôte)' }));
        break;
      }
      case 'accuse': {
        s.append(title('Accusation', `${st.round}/${st.rounds}`));
        const ib = intelBox(); if (ib) s.append(ib);
        s.append(h('div', { class: 'label', text: 'Qui est le plus sombre ce tour ?' }));
        s.append(h('p', { class: 'hint', text: 'Accusation juste : +2 PC et la cible est démasquée. À tort : l\'accusé gagne 1 PC de sympathie.' }));
        s.append(targetPicker(accSel === undefined ? -1 : accSel, id => { accSel = id; send({ t: 'accuse', target: id }); renderStage(); }, true));
        if (accSel !== undefined) s.append(h('div', { class: 'status', text: accSel ? `🗳 Tu accuses ${nameOf(accSel)}.` : '🗳 Tu n\'accuses personne.' }));
        if (isHost) s.append(h('div', { class: 'row' }, h('button', { class: 'ghost', onclick: () => send({ t: 'skip' }), text: 'Passer (hôte)' })));
        break;
      }
      case 'reveal': {
        s.append(title('Révélation', `${st.round}/${st.rounds}`));
        const ib = intelBox(); if (ib) s.append(ib);
        if (reveal) {
          for (const l of reveal.lines) s.append(h('p', { class: 'hint', text: l }));
          const t = h('table', null, h('tr', null, h('th', { text: 'Élève' }), h('th', { text: 'PC' }), h('th', { text: 'Δ' }), h('th', { text: 'Accusations' }), h('th', { text: 'Démasqué' })));
          for (const p of [...reveal.players].sort((a, b) => b.pc - a.pc)) {
            t.append(h('tr', null, h('td', { style: `color:${colorOf(p.id)}`, text: p.name }), h('td', { text: String(p.pc) }),
              h('td', { class: p.delta >= 0 ? 'pos' : 'neg', text: (p.delta >= 0 ? '+' : '') + p.delta }), h('td', { text: String(p.votes) }), h('td', { text: p.expo ? '👁'.repeat(Math.min(5, p.expo)) : '—' })));
          }
          s.append(t);
        }
        s.append(h('div', { class: 'row' }, h('button', { class: 'primary', disabled: readySent, onclick: () => { readySent = true; send({ t: 'ready' }); renderStage(); }, text: readySent ? 'EN ATTENTE…' : 'MANCHE SUIVANTE' })));
        break;
      }
      case 'final': renderFinal(s); break;
    }
    // bouton retour au salon pour l'hôte hors partie
    if (isHost && ['lobby'].includes(st.phase)) s.append(h('div', { class: 'row' }, h('button', { class: 'ghost', onclick: () => send({ t: 'mode', mode: 'hub' }), text: '← Retour au salon' })));
  }

  function renderFinal(s) {
    if (!final) { s.append(h('p', { class: 'hint', text: 'Calcul des noirceurs…' })); return; }
    const P = final.players, max = Math.max(1, ...P.map(p => p.score));
    s.append(h('div', { class: 'crown', text: '👑' }));
    s.append(h('h2', { class: 'stage', style: 'text-align:center' }, 'Le plus sombre : ', h('b', { text: P[0].name })));
    s.append(h('p', { class: 'hint', style: 'text-align:center', text: 'La vérité sur chacun, enfin révélée.' }));
    const fills = [];
    P.forEach((p, i) => {
      const fill = h('i'); fills.push([fill, (p.score / max) * 100]);
      s.append(h('div', { class: 'rank' + (i === 0 ? ' first' : '') },
        h('span', { text: String(i + 1) }), h('span', { class: 'nm', style: `color:${colorOf(p.id)}`, text: p.name }),
        h('div', { class: 'bar' }, fill, h('u', { text: `noirceur ${p.noir} + discrétion ${p.discretion}` })), h('b', { text: p.score + ' pts' })));
    });
    setTimeout(() => fills.forEach(([f, w]) => { f.style.width = w + '%'; }), 80);
    if (final.titles.length) s.append(h('div', { class: 'label', text: 'Titres' }), h('div', { class: 'titles' }, final.titles.map(t => h('div', { class: 'title' }, h('b', { text: `${t.icon} ${t.title}` }), h('span', { style: `color:${colorOf(t.id)}`, text: t.name }), h('br'), h('small', { text: t.text })))));
    s.append(h('div', { class: 'label', text: 'Dossiers' }));
    for (const p of P) s.append(h('details', null, h('summary', { text: `${p.name} — PC ${p.pc} · démasqué ×${p.expo} · vols ${p.stats.steals} · faux coupables ${p.stats.frames} · pactes brisés ${p.stats.trust}` }),
      h('ul', null, p.deeds.length ? p.deeds.map(d => h('li', { text: d })) : h('li', { text: 'Mains propres… ou presque.' }))));
    if (final.rumors.length) s.append(h('div', { class: 'label', text: 'Rumeurs démasquées' }), h('div', { class: 'box' }, final.rumors.map(r => h('p', { text: `Manche ${r.round} — ${r.name} : « ${r.text} »` }))));
    if (st.host === myId()) s.append(h('div', { class: 'row' }, h('button', { class: 'primary', onclick: () => send({ t: 'lobby' }), text: 'REJOUER' }), h('button', { class: 'ghost', onclick: () => send({ t: 'mode', mode: 'hub' }), text: '← Salon' })));
  }

  // ------------------------------------------------------------ minuteur
  const PH = { lobby: 'Salon', negotiate: 'Négociation', decide: 'Choix secret', accuse: 'Accusation', reveal: 'Révélation', final: 'Verdict' };
  setInterval(() => {
    if (!st || !visible) return;
    const rem = Math.max(0, st.rem - (performance.now() - recvAt));
    const timed = ['negotiate', 'decide', 'accuse', 'reveal'].includes(st.phase);
    $('timerFill').style.width = timed ? Math.min(100, (rem / phaseTotal) * 100) + '%' : '0';
    const sec = Math.ceil(rem / 1000);
    $('phase').innerHTML = '';
    $('phase').append(st.round ? `Examen ${st.round}/${st.rounds} · ` : '', h('b', { text: PH[st.phase] }), timed ? ` · ${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, '0')}` : '');
    $('tping').textContent = Net.ping ? Net.ping + ' ms' : '';
  }, 250);

  return {
    show() { visible = true; $('tableUI').classList.remove('hidden'); st = null; phaseKey = ''; $('log').textContent = ''; if (pending) { const p = pending; pending = null; onState(p); } },
    hide() { visible = false; $('tableUI').classList.add('hidden'); },
    reset() { st = null; phaseKey = ''; intel = reveal = final = null; myPact = null; reqs = []; lockedAct = null; },
    feed(m) { if (visible) onState(m); },
  };
}
