'use strict';
// Partie du TP suivie via MQTT : températures, votes, résultat. Lecture seule, ne lit jamais iot/role.
module.exports = function createEspion({ list, sendAll, sendUser }) {
  const G = { phase: 'attente', manches: 5, manche: 0, temps: {}, votes: {}, resultat: null };
  let active = false, timer = null;
  const reset = () => Object.assign(G, { manche: 0, temps: {}, votes: {}, resultat: null });

  function state() {
    const ag = list(), nameOf = id => (ag.find(a => a.id === id) || {}).name || String(id);
    const players = ag.map(a => {
      const t = G.temps[a.id] || {}, ms = Object.keys(t).map(Number).sort((x, y) => x - y), v = G.votes[a.id];
      return { id: a.id, user: a.userId, name: a.name, ville: a.ville, on: a.online, temps: ms.map(m => t[m]), last: ms.length ? t[ms[ms.length - 1]] : null,
        vote: v ? { suspect: v.suspect, name: nameOf(v.suspect), raison: v.raison } : null };
    });
    const count = {};
    for (const v of Object.values(G.votes)) count[v.suspect] = (count[v.suspect] || 0) + 1;
    const r = G.resultat;
    return { t: 'e_state', phase: G.phase, manche: G.manche, manches: G.manches, players,
      tally: Object.entries(count).map(([id, n]) => ({ id, name: nameOf(id), n })).sort((a, b) => b.n - a.n),
      resultat: r ? { espion: r.espion, espionName: nameOf(r.espion), designe: r.designe, gagnant: r.gagnant } : null };
  }
  function push() { if (!active || timer) return; timer = setTimeout(() => { timer = null; sendAll(state()); }, 80); }
  function check() {
    if (G.phase === 'en_cours') { const ag = list().filter(a => a.online); if (ag.length && ag.every(a => Object.keys(G.temps[a.id] || {}).length >= G.manches)) G.phase = 'vote'; }
  }

  return {
    open() { active = true; push(); },
    close() { active = false; },
    sendTo(id) { if (active) sendUser(id, state()); },
    changed: push,
    onEtat(o) {
      if (o.manches) G.manches = Number(o.manches) || G.manches;
      if (o.etat === 'inscription') { reset(); G.phase = 'attente'; }
      else if (o.etat === 'en_cours') { if (G.phase === 'attente' || G.phase === 'fini') reset(); G.phase = 'en_cours'; }
      else if (o.etat === 'vote' || o.etat === 'fini') G.phase = o.etat;
      push();
    },
    onTemp(id, o) {
      if (G.phase === 'fini' && o.manche === 1) reset();
      if (G.phase === 'attente' || G.phase === 'fini') G.phase = 'en_cours';
      (G.temps[id] = G.temps[id] || {})[o.manche] = o.temperature;
      G.manche = Math.max(G.manche, Number(o.manche) || 0);
      check(); push();
    },
    onVote(id, o) {
      if (typeof o.suspect !== 'string') return;
      G.votes[id] = { suspect: o.suspect, raison: String(o.raison || '').slice(0, 160) };
      if (G.phase !== 'fini') G.phase = 'vote';
      push();
    },
    onResultat(o) { G.resultat = o; G.phase = 'fini'; push(); },
  };
};
