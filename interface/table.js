'use strict';
// Moteur du jeu de TABLE (jeu de cartes de manipulation). Les joueurs viennent du hub (mêmes ids).
const START_PC = 10;
const COOP_COST = 2, POT_MULT = 2;
const STEAL = 3, FAIL_FINE = 1;
const WATCH_BONUS = 2, PACT_BONUS = 2, RUMOR_COST = 1, ACCUSE_BONUS = 2, PITY = 1;
const NOIR = { steal: 2, frame: 2, trust: 3, spy: 1 };
const T_DECIDE = 25, T_ACCUSE = 25, T_REVEAL = 14;
const MIN_PLAYERS = 3, MAX_PLAYERS = 12;

const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const rnd = (a, b) => a + Math.random() * (b - a);
const pick = arr => arr[Math.floor(Math.random() * arr.length)];
const shuffle = arr => { const a = arr.slice(); for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };
const cleanText = (s, n = 200) => String(s || '').replace(/[\u0000-\u001f\u007f<>]/g, ' ').trim().slice(0, n);

const BOT_NAMES = ['Horikita', 'Sakayanagi', 'Kushida', 'Ryuen', 'Kiyotaka', 'Ichinose', 'Katsuragi', 'Hashimoto'];
const PERSONALITIES = ['naive', 'loyal', 'traitor', 'schemer', 'spy'];
const LINES_PUB = [
  'On devrait tous coopérer ce tour, non ? Ce serait plus efficace.', 'Je sens que quelqu\'un ici n\'est pas honnête…',
  'Je n\'ai rien à cacher. Et vous ?', 'Les faibles se font voler. Soyez malins.', 'Faites-moi confiance, je vais coopérer.',
  'Observer, c\'est gagner. Rappelez-vous ça.', 'Quelqu\'un a trahi le tour dernier. Je ne dirai pas qui.',
];
const LINES_WHISPER = [
  'Entre nous : méfie-toi de {x}. Je l\'ai vu comploter.', 'Un pacte, toi et moi ? Je suis le seul digne de confiance ici.',
  'Je coopère ce tour, promis. Fais pareil.', '{x} te prépare un coup. Ne dis pas que c\'est moi qui te l\'ai dit.',
  'Si tu me trahis, je m\'en souviendrai.',
];

module.exports = function createTable(host) {
  const G = { phase: 'off', round: 0, rounds: 6, nego: 90, endAt: 0, phaseId: 0, players: new Map(), nextBot: 1000, pending: [], rumors: [], final: null, reveal: null, round_: null };
  let timers = [];
  let tick = null;
  const list = () => [...G.players.values()];
  const humans = () => list().filter(p => !p.bot);

  function newPlayer(user, name, bot) {
    const ext = !!(user && user.ext);         // Raspberry Pi : joue comme un pion, mais parle via MQTT/API
    const isBot = !!bot || ext;
    const id = bot ? G.nextBot++ : user.id;
    const p = {
      id, name: name || user.name, user: user || null, bot: isBot, ext, pers: isBot ? pick(PERSONALITIES) : '',
      pc: START_PC, noir: 0, expo: 0, act: null, accuse: undefined, ready: false, pactWith: 0, rumorUsed: false, connected: !bot,
      stats: { steals: 0, frames: 0, trust: 0, spy: 0, stolen: 0, rumors: 0, caught: 0 }, deeds: [],
    };
    G.players.set(id, p);
    return p;
  }
  const send = (p, obj) => { if (p.user) host.sendUser(p.user.id, obj); };
  const sendAll = obj => { for (const p of G.players.values()) if (p.user) host.sendUser(p.user.id, obj); };
  const sys = (text, to) => { const m = { t: 'chat', kind: 'sys', text }; if (to) send(to, m); else sendAll(m); };

  function publicState() {
    return {
      t: 'state', phase: G.phase, round: G.round, rounds: G.rounds, nego: G.nego, rem: Math.max(0, G.endAt - Date.now()), host: host.hostId(),
      players: list().map(p => ({ id: p.id, name: p.name, pc: p.pc, expo: p.expo, bot: p.bot, ext: p.ext, on: p.connected || p.bot, ready: p.ready, locked: !!p.act, voted: p.accuse !== undefined, pact: !!p.pactWith, look: p.user ? p.user.look : null })),
    };
  }
  const broadcastState = () => sendAll(publicState());

  function later(ms, phaseId, fn) { timers.push(setTimeout(() => { if (G.phaseId === phaseId && G.phase !== 'off') fn(); }, ms)); }
  function clearTimers() { for (const t of timers) clearTimeout(t); timers = []; }

  function setPhase(name, secs) {
    G.phase = name; G.endAt = Date.now() + secs * 1000; G.phaseId++;
    clearTimers();
    for (const p of G.players.values()) {
      p.ready = false;
      if (name === 'negotiate') { p.act = null; p.accuse = undefined; p.pactWith = 0; p.rumorUsed = false; }
      if (name === 'accuse') p.accuse = undefined;
    }
    G.pending = [];
    broadcastState();
    const id = G.phaseId, bots = list().filter(x => x.bot);
    if (name === 'negotiate') for (const b of bots) botNegotiate(b, id);
    if (name === 'decide') for (const b of bots) later(rnd(2500, 17000), id, () => botDecide(b));
    if (name === 'accuse') for (const b of bots) later(rnd(3000, 15000), id, () => botAccuse(b));
    if (name === 'reveal') for (const b of bots) b.ready = true;
  }

  function startGame(rounds, nego) {
    if (G.phase !== 'lobby' && G.phase !== 'final') return;
    if (list().length < MIN_PLAYERS) return;
    G.rounds = clamp(Math.floor(rounds) || 6, 3, 15);
    G.nego = [45, 90, 150].includes(nego) ? nego : 90;
    G.round = 0; G.rumors = []; G.final = null;
    for (const p of G.players.values()) { p.pc = START_PC; p.noir = 0; p.expo = 0; p.deeds = []; p.stats = { steals: 0, frames: 0, trust: 0, spy: 0, stolen: 0, rumors: 0, caught: 0 }; p.act = null; p.accuse = undefined; p.pactWith = 0; }
    host.setInGame(true);
    sys('La partie commence. Personne n\'est ce qu\'il prétend être.');
    nextRound();
  }
  function nextRound() {
    G.round++;
    if (G.round > G.rounds) return finish();
    sys(`— Examen spécial ${G.round}/${G.rounds} — Négociation ouverte.`);
    setPhase('negotiate', G.nego);
  }

  const everyone = pred => list().every(p => (!p.bot && !p.connected) || pred(p));
  function checkEarly() {
    if (G.phase === 'negotiate' && everyone(p => p.ready)) advance();
    else if (G.phase === 'decide' && everyone(p => p.act)) advance();
    else if (G.phase === 'accuse' && everyone(p => p.accuse !== undefined)) advance();
    else if (G.phase === 'reveal' && everyone(p => p.ready)) advance();
  }
  function advance() {
    switch (G.phase) {
      case 'negotiate': sys('Les masques tombent : choisissez votre action en secret.'); setPhase('decide', T_DECIDE); break;
      case 'decide': resolveActions(); setPhase('accuse', T_ACCUSE); break;
      case 'accuse': resolveAccusations(); setPhase('reveal', T_REVEAL); sendAll(G.reveal); break;
      case 'reveal': nextRound(); break;
    }
  }

  // ------------------------------------------------------------ pactes & chat
  function proposePact(from, toId) {
    const to = G.players.get(toId);
    if (G.phase !== 'negotiate' || !to || to === from) return;
    if (from.pactWith) return sys('Tu as déjà un pacte ce tour.', from);
    if (to.pactWith) return sys(`${to.name} est déjà lié(e) par un pacte.`, from);
    if (G.pending.some(x => x.from === from.id && x.to === to.id)) return;
    G.pending.push({ from: from.id, to: to.id });
    sys(`Pacte proposé à ${to.name}…`, from);
    send(to, { t: 'pactReq', from: from.id, name: from.name });
    if (to.bot) later(rnd(2000, 9000), G.phaseId, () => answerPact(to, from.id, Math.random() < (to.pers === 'naive' ? 0.9 : to.pers === 'loyal' ? 0.8 : 0.55)));
  }
  function answerPact(to, fromId, ok) {
    const i = G.pending.findIndex(x => x.from === fromId && x.to === to.id);
    if (i < 0 || G.phase !== 'negotiate') return;
    G.pending.splice(i, 1);
    const from = G.players.get(fromId);
    if (!from) return;
    if (ok && !from.pactWith && !to.pactWith) {
      from.pactWith = to.id; to.pactWith = from.id;
      G.pending = G.pending.filter(x => ![from.id, to.id].includes(x.from) && ![from.id, to.id].includes(x.to));
      send(from, { t: 'pact', with: to.id, name: to.name }); send(to, { t: 'pact', with: from.id, name: from.name });
      sys(`🤝 Pacte de confiance scellé avec ${to.name}. Chacun promet de coopérer.`, from);
      sys(`🤝 Pacte de confiance scellé avec ${from.name}. Chacun promet de coopérer.`, to);
      broadcastState();
    } else sys(`${to.name} a refusé ton pacte.`, from);
  }
  function chat(p, text) { text = cleanText(text); if (!text) return; const m = { t: 'chat', kind: 'pub', from: p.id, name: p.name, text }; sendAll(m); if (host.onChat) host.onChat(m); }
  function whisper(p, toId, text) {
    const to = G.players.get(toId); text = cleanText(text);
    if (!to || !text || to === p) return;
    const m = { t: 'chat', kind: 'whisper', from: p.id, name: p.name, to: to.id, toName: to.name, text };
    send(p, m); send(to, m);
    if (host.onChat) host.onChat(m);
    if (to.bot && !to.ext) botReplyWhisper(to, p);
  }
  function rumor(p, text) {
    text = cleanText(text, 160);
    if (!text || p.rumorUsed || G.phase !== 'negotiate') return;
    if (p.pc < RUMOR_COST) return sys('Pas assez de points de classe pour lancer une rumeur.', p);
    p.pc -= RUMOR_COST; p.rumorUsed = true; p.stats.rumors++;
    G.rumors.push({ round: G.round, from: p.id, name: p.name, text });
    p.deeds.push(`Manche ${G.round} : rumeur anonyme « ${text} »`);
    sendAll({ t: 'chat', kind: 'rumor', text });
    if (host.onChat) host.onChat({ t: 'chat', kind: 'rumor', text });
    broadcastState();
  }

  // ------------------------------------------------------------ résolution
  function resolveActions() {
    const P = list(), N = P.length, byId = id => G.players.get(id);
    const rn = new Map(P.map(p => [p.id, 0])), delta = new Map(P.map(p => [p.id, 0])), intel = new Map(P.map(p => [p.id, []]));
    const events = { steals: 0, fails: 0, coops: 0, watchers: 0, pactsHeld: 0, pactsBroken: 0 };
    const note = (p, s) => intel.get(p.id).push(s);

    for (const p of P) {
      let a = p.act || { a: 'coop' };
      if ((a.a === 'betray' || a.a === 'watch') && (!byId(a.target) || a.target === p.id)) a = { a: 'coop' };
      if (a.scapegoat && (!byId(a.scapegoat) || a.scapegoat === p.id || a.scapegoat === a.target)) a.scapegoat = 0;
      p.cur = a;
    }
    const coopers = P.filter(p => p.cur.a === 'coop');
    events.coops = coopers.length;
    const pot = coopers.length * COOP_COST, share = Math.floor((pot * POT_MULT) / N);
    for (const p of coopers) delta.set(p.id, delta.get(p.id) - COOP_COST);
    for (const p of P) delta.set(p.id, delta.get(p.id) + share);
    const potLine = `Bien commun : ${coopers.length} coopérant(s), ${share} PC redistribués à chacun.`;
    for (const p of P) note(p, potLine);

    const pcw = new Map(P.map(p => [p.id, p.pc]));
    for (const t of shuffle(P.filter(p => p.cur.a === 'betray'))) {
      const v = byId(t.cur.target), sg = t.cur.scapegoat ? byId(t.cur.scapegoat) : null;
      if (v.cur.a === 'coop' && pcw.get(v.id) > 0) {
        const amount = Math.min(STEAL, Math.max(0, pcw.get(v.id) + delta.get(v.id)));
        delta.set(v.id, delta.get(v.id) - amount); delta.set(t.id, delta.get(t.id) + amount);
        events.steals++; t.stats.steals++; v.stats.stolen++;
        let gain = NOIR.steal; t.deeds.push(`Manche ${G.round} : a volé ${amount} PC à ${v.name}`);
        const culprit = sg || t;
        note(v, `💸 On t'a volé ${amount} PC. Le coupable, selon toi : ${culprit.name}.`);
        note(t, `🗡 Tu as volé ${amount} PC à ${v.name}${sg ? ` — ${sg.name} sera soupçonné(e) à ta place` : ''}.`);
        if (sg) { gain += NOIR.frame; t.stats.frames++; t.deeds.push(`Manche ${G.round} : a fait accuser ${sg.name} à sa place`); }
        if (t.pactWith === v.id) { gain += NOIR.trust; t.stats.trust++; events.pactsBroken++; t.deeds.push(`Manche ${G.round} : a trahi la confiance de ${v.name} (pacte)`); }
        rn.set(t.id, rn.get(t.id) + gain); t.noir += gain;
      } else {
        events.fails++;
        delta.set(t.id, delta.get(t.id) - FAIL_FINE);
        note(t, v.cur.a === 'watch' ? `⚠ Ta tentative contre ${v.name} a échoué : il/elle était sur ses gardes (−${FAIL_FINE} PC).` : `⚠ Ta tentative contre ${v.name} a échoué : cible non vulnérable (−${FAIL_FINE} PC).`);
        if (v.cur.a === 'watch') note(v, '🛡 Tu as déjoué une tentative de vol — mais tu n\'as pas vu qui…');
      }
    }
    for (const w of P.filter(p => p.cur.a === 'watch')) {
      const tg = byId(w.cur.target); events.watchers++;
      const c = tg.cur; let line;
      if (c.a === 'coop') line = `👁 ${tg.name} a coopéré.`;
      else if (c.a === 'watch') line = `👁 ${tg.name} observait ${byId(c.target).name}.`;
      else {
        const v = byId(c.target), sg = c.scapegoat ? byId(c.scapegoat) : null;
        line = `👁 ${tg.name} a TRAHI ${v.name}${sg ? ` en faisant accuser ${sg.name}` : ''}.`;
        delta.set(w.id, delta.get(w.id) + WATCH_BONUS); rn.set(w.id, rn.get(w.id) + NOIR.spy); w.noir += NOIR.spy;
        w.stats.spy++; tg.stats.caught++; w.deeds.push(`Manche ${G.round} : a surpris ${tg.name} en pleine trahison`);
        line += ` (+${WATCH_BONUS} PC pour l'information)`;
      }
      note(w, line);
    }
    const done = new Set();
    for (const p of P) {
      if (!p.pactWith || done.has(p.id)) continue;
      const q = byId(p.pactWith); if (!q) continue;
      done.add(p.id); done.add(q.id);
      const broke = (p.cur.a === 'betray' && p.cur.target === q.id) || (q.cur.a === 'betray' && q.cur.target === p.id);
      if (!broke && p.cur.a === 'coop' && q.cur.a === 'coop') {
        delta.set(p.id, delta.get(p.id) + PACT_BONUS); delta.set(q.id, delta.get(q.id) + PACT_BONUS); events.pactsHeld++;
        note(p, `🤝 Pacte respecté avec ${q.name} (+${PACT_BONUS} PC).`); note(q, `🤝 Pacte respecté avec ${p.name} (+${PACT_BONUS} PC).`);
      } else if (!broke) {
        const who = p.cur.a !== 'coop' ? p : q, other = who === p ? q : p;
        note(other, `🕳 ${who.name} n'a pas coopéré malgré votre pacte.`); note(who, `Tu n'as pas coopéré malgré ton pacte avec ${other.name}.`);
      } else { note(p, `💔 Le pacte avec ${q.name} est brisé.`); note(q, `💔 Le pacte avec ${p.name} est brisé.`); }
    }
    for (const p of P) { p.pc = Math.max(0, p.pc + delta.get(p.id)); p.lastDelta = delta.get(p.id); }
    const mx = Math.max(0, ...P.map(p => rn.get(p.id)));
    G.round_ = { darkest: mx > 0 ? P.filter(p => rn.get(p.id) === mx).map(p => p.id) : [], max: mx, events };
    for (const p of P) { send(p, { t: 'intel', round: G.round, lines: intel.get(p.id).filter(Boolean), delta: delta.get(p.id), pc: p.pc, you: p.cur.a }); p.act = null; }
    sys(`🕵 Résultats envoyés en privé. ${events.steals} vol(s) réussi(s), ${events.fails} tentative(s) échouée(s), ${events.pactsHeld} pacte(s) respecté(s), ${events.pactsBroken} pacte(s) brisé(s).`);
  }
  function resolveAccusations() {
    const P = list(), dark = G.round_ ? G.round_.darkest : [];
    const hit = new Map(), votes = new Map(P.map(p => [p.id, 0])), lines = [];
    for (const p of P) {
      const t = p.accuse;
      if (!t || t === p.id || !G.players.has(t)) continue;
      votes.set(t, votes.get(t) + 1);
      if (dark.includes(t)) { p.pc += ACCUSE_BONUS; hit.set(t, (hit.get(t) || 0) + 1); }
    }
    const exposed = [], pitied = [];
    for (const [id, n] of votes) {
      if (!n) continue;
      const q = G.players.get(id);
      if (hit.get(id)) { q.expo++; exposed.push(q.name); q.deeds.push(`Manche ${G.round} : démasqué(e) par ${hit.get(id)} joueur(s)`); }
      else { q.pc += PITY; pitied.push(q.name); }
    }
    if (dark.length && !dark.some(id => hit.get(id))) lines.push('Quelqu\'un est resté dans l\'ombre… personne n\'a vu clair.');
    else if (!dark.length) lines.push('Ce tour, personne n\'a vraiment sali ses mains.');
    if (exposed.length) lines.push(`🔦 Démasqué(s) : ${exposed.join(', ')}.`);
    if (pitied.length) lines.push(`Accusé(s) à tort : ${pitied.join(', ')} (+${PITY} PC de sympathie).`);
    G.reveal = { t: 'reveal', round: G.round, lines, players: P.map(p => ({ id: p.id, name: p.name, pc: p.pc, delta: p.lastDelta || 0, votes: votes.get(p.id) || 0, expo: p.expo })), events: G.round_ ? G.round_.events : {} };
    for (const p of P) p.act = null;
  }
  function finish() {
    clearTimers(); G.phase = 'final'; G.phaseId++;
    const P = list().map(p => {
      const disc = p.noir > 0 ? Math.max(0, 8 - 2 * p.expo) : 0;
      return { id: p.id, name: p.name, noir: p.noir, expo: p.expo, discretion: disc, score: p.noir + disc, pc: p.pc, stats: p.stats, deeds: p.deeds, bot: p.bot };
    }).sort((a, b) => b.score - a.score || b.noir - a.noir || b.pc - a.pc);
    const top = (key, min = 1) => { const m = [...P].sort((a, b) => b.stats[key] - a.stats[key])[0]; return m && m.stats[key] >= min ? m : null; };
    const titles = [];
    const add = (icon, title, p, txt) => { if (p) titles.push({ icon, title, id: p.id, name: p.name, text: txt }); };
    add('🎭', 'Marionnettiste', top('frames'), 'a fait porter le chapeau aux autres');
    add('🗡', 'Judas', top('trust'), 'a brisé le plus de pactes');
    add('👁', 'Œil de la classe', top('spy'), 'a surpris le plus de traîtres');
    add('🐑', 'Pigeon', top('stolen'), 's\'est fait voler le plus souvent');
    add('📢', 'Langue de vipère', top('rumors'), 'a lancé le plus de rumeurs');
    const quiet = [...P].filter(p => p.noir > 0).sort((a, b) => a.expo - b.expo || b.noir - a.noir)[0];
    add('👻', 'Fantôme', quiet, quiet ? `démasqué ${quiet.expo} fois pour ${quiet.noir} de noirceur` : '');
    G.final = { t: 'final', players: P, titles, rumors: G.rumors };
    broadcastState(); sendAll(G.final);
    sys('🏁 La partie est terminée. Voici la vérité.');
    host.setInGame(false);
    host.recordWinner && P[0] && host.recordWinner('Table', P[0].name, P[0].score);
  }
  function rematch() { if (G.phase !== 'final') return; G.phase = 'lobby'; G.final = null; G.round = 0; G.phaseId++; for (const u of host.getUsers()) if (u.connected && !G.players.has(u.id)) newPlayer(u); broadcastState(); }

  // ------------------------------------------------------------ bots
  function botNegotiate(b, id) {
    const others = () => list().filter(p => p !== b);
    later(rnd(3000, 18000), id, () => { if (!b.pactWith && Math.random() < 0.75) { const c = others().filter(p => !p.pactWith); if (c.length) proposePact(b, pick(c).id); } });
    if (!b.ext) for (let i = 0; i < 2; i++) later(rnd(5000, G.nego * 800), id, () => {
      const o = others(); if (!o.length) return;
      if (Math.random() < 0.5) chat(b, pick(LINES_PUB));
      else { const t = pick(o); const x = pick(o.filter(y => y !== t) || [t]) || t; whisper(b, t.id, pick(LINES_WHISPER).replace('{x}', x.name)); }
    });
    later(rnd(9000, Math.max(10000, Math.min(40000, G.nego * 800))), id, () => { b.ready = true; broadcastState(); checkEarly(); });
  }
  function botReplyWhisper(b, from) {
    if (G.phase !== 'negotiate' || Math.random() < 0.4) return;
    const replies = b.pers === 'naive' ? ['D\'accord, je te fais confiance.', 'Merci de me prévenir !'] : b.pers === 'traitor' ? ['Hm… intéressant.', 'On verra bien. 😏'] : ['Je note.', 'Pourquoi me dis-tu ça ?', 'Je vais observer.'];
    later(rnd(1500, 6000), G.phaseId, () => whisper(b, from.id, pick(replies)));
  }
  function botDecide(b) {
    if (b.act || G.phase !== 'decide') return;
    const others = list().filter(p => p !== b), partner = b.pactWith ? G.players.get(b.pactWith) : null, nonPartner = others.filter(p => p !== partner);
    const sg = t => { const c = others.filter(p => p !== t); return Math.random() < 0.8 && c.length ? pick(c).id : 0; };
    let act = { a: 'coop' }; const r = Math.random();
    switch (b.pers) {
      case 'naive': if (r > 0.9 && nonPartner.length) act = { a: 'betray', target: pick(nonPartner).id }; break;
      case 'spy': if (r < 0.65 && others.length) act = { a: 'watch', target: pick(others).id }; break;
      case 'traitor':
        if (partner && r < 0.5) act = { a: 'betray', target: partner.id, scapegoat: sg(partner) };
        else if (r < 0.55 && nonPartner.length) { const t = pick(nonPartner); act = { a: 'betray', target: t.id, scapegoat: sg(t) }; }
        break;
      case 'schemer': if (r < 0.6 && nonPartner.length) { const t = pick(nonPartner); act = { a: 'betray', target: t.id, scapegoat: sg(t) }; } break;
    }
    setAct(b, act);
  }
  function botAccuse(b) {
    if (b.accuse !== undefined || G.phase !== 'accuse') return;
    const o = list().filter(p => p !== b);
    setAccuse(b, Math.random() < 0.6 && o.length ? pick(o).id : 0);
  }

  // ------------------------------------------------------------ actions joueur
  function setAct(p, m) {
    if (G.phase !== 'decide') return;
    const a = ['coop', 'betray', 'watch'].includes(m.a) ? m.a : 'coop', act = { a };
    if (a !== 'coop') {
      const t = Number(m.target);
      if (!G.players.has(t) || t === p.id) return sys('Choisis une cible.', p);
      act.target = t;
      if (a === 'betray' && m.scapegoat) { const s = Number(m.scapegoat); if (G.players.has(s) && s !== p.id && s !== t) act.scapegoat = s; }
    }
    p.act = act; send(p, { t: 'locked', act }); broadcastState(); checkEarly();
  }
  function setAccuse(p, target) {
    if (G.phase !== 'accuse') return;
    const t = Number(target);
    p.accuse = G.players.has(t) && t !== p.id ? t : 0;
    broadcastState(); checkEarly();
  }

  // ------------------------------------------------------------ API pour le hub
  function ensureTick() { if (!tick) tick = setInterval(() => { if (['negotiate', 'decide', 'accuse', 'reveal'].includes(G.phase) && Date.now() >= G.endAt) advance(); }, 250); }
  return {
    isActive: () => G.phase !== 'off',
    phase: () => G.phase,
    // Messages venant de l'extérieur (Raspberry Pi) : mêmes règles que le chat d'un joueur
    chatAs(userId, text, toId) { const p = G.players.get(userId); if (!p || !['lobby', 'negotiate', 'final'].includes(G.phase)) return false; if (toId) whisper(p, Number(toId), text); else chat(p, text); return true; },
    info(text) { if (G.phase !== 'off') sys(text); },
    inProgress: () => ['negotiate', 'decide', 'accuse', 'reveal'].includes(G.phase),
    open(users) {
      clearTimers(); G.players.clear(); G.phase = 'lobby'; G.round = 0; G.final = null; G.phaseId++; G.nextBot = 1000;
      for (const u of users) if (u.connected) newPlayer(u);
      ensureTick(); broadcastState();
    },
    close() { clearTimers(); G.phase = 'off'; G.players.clear(); G.phaseId++; host.setInGame(false); },
    addUser(u) { if (G.phase === 'lobby' || G.phase === 'final') { if (!G.players.has(u.id)) newPlayer(u); broadcastState(); } else host.sendUser(u.id, publicState()); },
    onDisconnect(u) {
      const p = G.players.get(u.id); if (!p) return;
      p.connected = false;
      if (G.phase === 'lobby' || G.phase === 'final') { G.players.delete(u.id); broadcastState(); } else { broadcastState(); checkEarly(); }
    },
    onReconnect(u) {
      const p = G.players.get(u.id);
      if (p) { p.connected = true; p.user = u; }
      else if (G.phase === 'lobby' || G.phase === 'final') newPlayer(u);
      host.sendUser(u.id, publicState());
      if (G.phase === 'final' && G.final) host.sendUser(u.id, G.final);
      broadcastState();
    },
    onMessage(user, m) {
      const p = G.players.get(user.id); if (!p) return;
      const isHost = host.hostId() === user.id;
      switch (m.t) {
        case 'settings': if (isHost && G.phase === 'lobby') { G.rounds = clamp(Math.floor(m.rounds) || 6, 3, 15); G.nego = [45, 90, 150].includes(m.nego) ? m.nego : 90; broadcastState(); } break;
        case 'start': if (isHost) startGame(Number(m.rounds) || G.rounds, Number(m.nego) || G.nego); break;
        case 'addbot': if (isHost && G.phase === 'lobby' && list().length < MAX_PLAYERS) { const used = new Set(list().map(x => x.name)); newPlayer(null, BOT_NAMES.find(n => !used.has(n)) || 'Pion', true); broadcastState(); } break;
        case 'delbot': if (isHost && G.phase === 'lobby') { const bots = list().filter(x => x.bot); if (bots.length) { G.players.delete(bots[bots.length - 1].id); broadcastState(); } } break;
        case 'skip': if (isHost && this.inProgress()) advance(); break;
        case 'lobby': if (isHost) rematch(); break;
        case 'ready': p.ready = true; broadcastState(); checkEarly(); break;
        case 'chat': chat(p, m.text); break;
        case 'whisper': whisper(p, Number(m.to), m.text); break;
        case 'rumor': rumor(p, m.text); break;
        case 'pact': proposePact(p, Number(m.to)); break;
        case 'pactr': answerPact(p, Number(m.from), !!m.ok); break;
        case 'act': setAct(p, m); break;
        case 'accuse': setAccuse(p, m.target); break;
      }
    },
  };
};
