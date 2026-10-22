'use strict';
// Pont entre le salon Classe Noire et les Raspberry Pi (agents IA). Détails et exemples : AGENTS.md
//  - MQTT (protocole commun du TP, docs/protocole.md) : présence, températures, votes, chat entre agents
//  - API HTTP (/api/...) : pour un agent sans MQTT, ou pour interroger le salon à la main
//  - Appel d'une API d'agent (ex. Flask + Ollama, route POST /message) pour le faire parler à la table
const createMqtt = require('./mqtt.js');

const ID_RE = /^[^s/#+]{1,32}$/;            // le protocole interdit seulement espace et /  (# et + sont réservés à MQTT)
const DEFAULT_BROKER = '10.109.150.215';       // broker de Niels (broker/README.md) ; MQTT_HOST=off pour désactiver
const MAX_AGENT_STREAK = 6;                    // après 6 messages d'agents d'affilée, ils se taisent jusqu'à ce qu'un humain/pion reparle
const MAX_AGENTS = 8;
const REPLY_MIN_MS = 8000;           // un agent API ne répond pas plus d'une fois toutes les 8 s (évite le bavardage infini)
const REPLY_TIMEOUT_MS = 120000;     // un petit LLM sur Raspberry Pi peut être lent
const CHAT_KEEP = 100;

module.exports = function createAgents({ host, table, espion, users, newId, cleanText, cleanLook, ARCHS, isInGame, broadcastHub, hubChat, reassignHost }) {
  const agents = new Map();          // id (texte, ex. "rpi1") -> { id, user, ville, api, via, temp, lastSeen, busy, lastReply, vote }
  const chatLog = [];                // derniers messages de la table, relisibles par GET /api/chat?since=N
  let seq = 0, mqtt = null, brokerLabel = '', streak = 0;
  const log = s => console.log('  [agents] ' + s);

  const hashArch = id => ARCHS[[...id].reduce((a, c) => a + c.charCodeAt(0), 0) % ARCHS.length];
  const list = () => [...agents.values()].map(a => ({ id: a.id, userId: a.user.id, name: a.user.name, ville: a.ville, online: a.user.connected }));
  const agentOfUser = uid => [...agents.values()].find(a => a.user.id === uid);
  const resolveTarget = to => {                       // "rpi2" (id d'agent) ou numéro de joueur de la table
    if (to == null || to === '') return 0;
    const a = agents.get(String(to)); if (a) return a.user.id;
    return Number(to) || 0;
  };

  // ------------------------------------------------------------ présence : un Pi arrive = un personnage apparaît
  function join(id, info = {}, via = 'mqtt') {
    if (!ID_RE.test(id)) { log(`id refusé : « ${String(id).slice(0, 40)} »`); return null; }
    let a = agents.get(id);
    if (!a) {
      if (agents.size >= MAX_AGENTS) return null;
      const look = cleanLook({ arch: info.arch || hashArch(id) });
      const user = { id: newId(), name: cleanText(info.nom || id, 16) || id, token: 'ext-' + id, conn: null, connected: true, ext: true, look };
      a = { id, user, ville: '', api: '', via, temp: null, lastSeen: 0, busy: false, lastReply: 0, vote: null };
      agents.set(id, a); users.set(user.id, user);
      log(`+ ${id} (${via})`);
      hubChat('📡 Salon', `${user.name} a rejoint la classe${info.ville ? ' (' + cleanText(info.ville, 30) + ')' : ''}.`);
    }
    a.user.connected = true; a.via = via; a.lastSeen = Date.now();
    if (info.ville) a.ville = cleanText(info.ville, 30);
    if (info.api && /^https?:\/\/[\w.\-:]+(\/.*)?$/.test(info.api)) a.api = info.api.replace(/\/$/, '');
    if (info.nom) a.user.name = cleanText(info.nom, 16) || a.user.name;
    reassignHost(); broadcastHub(); espion.changed();
    if (table.isActive()) table.addUser(a.user);
    return a;
  }
  function leave(id) {
    const a = agents.get(id); if (!a) return false;
    a.user.connected = false; log(`- ${id}`);
    if (table.isActive()) table.onDisconnect(a.user);
    if (!isInGame()) { users.delete(a.user.id); agents.delete(id); }     // en pleine partie, il reste (hors ligne) jusqu'à la fin
    hubChat('📡 Salon', `${a.user.name} a quitté la classe.`);
    reassignHost(); broadcastHub(); espion.changed();
    return true;
  }
  function keepOnlyAgents() { for (const [id, u] of users) if (!u.ext) users.delete(id); }

  // ------------------------------------------------------------ chat de la table : sortie (vers MQTT / API) et entrée
  function onTableChat(msg) {
    if (msg.kind === 'sys') return;
    const entry = { seq: ++seq, ts: Date.now(), kind: msg.kind, from: msg.from || 0, name: msg.name || '', text: msg.text, to: msg.to || 0, toName: msg.toName || '' };
    const fa = agentOfUser(entry.from); if (fa) entry.fromAgent = fa.id;
    streak = fa ? streak + 1 : 0;
    chatLog.push(entry); if (chatLog.length > CHAT_KEEP) chatLog.shift();
    if (mqtt) mqtt.publish('iot/table/chat', entry);          // tous les agents abonnés entendent la table
    for (const a of agents.values()) if (a.api && a.user.connected) maybeReply(a, entry);
  }

  // Un agent parle : à la table si une partie de table est ouverte, sinon dans le chat du salon (autour de la table ronde)
  function say(a, text, toId) {
    if (table.isActive()) return table.chatAs(a.user.id, text, toId);
    if (toId) return false;                                    // pas de messages privés dans le salon : on ne le publie pas à tout le monde
    text = cleanText(text); if (!text) return false;
    hubChat(a.user.name, text, a.user.id);
    onTableChat({ kind: 'pub', from: a.user.id, name: a.user.name, text });
    return true;
  }

  // Un agent exposant une API (POST <api>/message {"message": "..."} -> {"reponse": "..."}) répond au chat sans code de plus côté Pi.
  async function maybeReply(a, e) {
    if (e.kind === 'rumor' || e.from === a.user.id || a.busy || streak > MAX_AGENT_STREAK) return;
    if (e.kind === 'whisper' && e.to !== a.user.id) return;
    if (!['off', 'lobby', 'negotiate'].includes(table.phase())) return;     // 'off' = on est dans le salon (hub)
    if (Date.now() - a.lastReply < REPLY_MIN_MS) return;
    a.busy = true;
    try {
      const r = await fetch(a.api + '/message', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: `${e.name}${e.kind === 'whisper' ? ' (en privé)' : ''} : ${e.text}` }), signal: AbortSignal.timeout(REPLY_TIMEOUT_MS),
      });
      const j = await r.json(); const txt = j.reponse || j.response;
      if (txt && agents.get(a.id) === a) say(a, txt, e.kind === 'whisper' ? e.from : 0);
    } catch (err) { log(`${a.id} : API injoignable (${err.message})`); }
    a.busy = false; a.lastReply = Date.now();
  }

  // ------------------------------------------------------------ MQTT entrant
  function onMqtt(topic, obj) {
    const t = topic.split('/');
    if (t[0] !== 'iot' || !obj || typeof obj !== 'object') return;
    if (t[1] === 'joueurs' && t[2]) {
      if (obj.en_ligne === false) leave(t[2]); else join(t[2], obj, 'mqtt');
    } else if (t[1] === 'chat' && t[2]) {                      // {"text": "...", "to": "rpi2"}  (to facultatif = chuchotement)
      const a = agents.get(t[2]); if (!a) return;
      a.lastSeen = Date.now();
      if (!say(a, obj.text, resolveTarget(obj.to))) log(`${t[2]} : message ignoré (la table n'est pas en phase de discussion)`);
    } else if (t[1] === 'capteurs' && t[3] === 'temperature') {
      const a = agents.get(t[2]); if (a && typeof obj.temperature === 'number') { a.temp = { value: obj.temperature, manche: obj.manche, ville: obj.ville, ts: Date.now() }; a.lastSeen = Date.now(); espion.onTemp(a.id, obj); }
    } else if (t[1] === 'votes' && t[2]) {
      const a = agents.get(t[2]); if (!a) return;
      a.vote = { suspect: obj.suspect, raison: obj.raison }; espion.onVote(a.id, obj);
      table.info(`🗳 ${a.user.name} soupçonne ${obj.suspect}${obj.raison ? ' : ' + cleanText(obj.raison, 120) : ''}`);
    } else if (t[1] === 'partie' && t[2] === 'resultat') {
      const txt = `Résultat du TP : l'espion était ${obj.espion}, désigné ${obj.designe} → victoire des ${obj.gagnant}.`;
      espion.onResultat(obj); table.info('🏁 ' + txt); hubChat('📡 MQTT', txt);
    } else if (t[1] === 'partie' && t[2] === 'etat') {
      espion.onEtat(obj);
    }
  }

  function start() {
    const h = process.env.MQTT_HOST || DEFAULT_BROKER;
    if (h === 'off') { log('MQTT désactivé (MQTT_HOST=off). L\'API /api/... reste disponible.'); return; }
    const port = Number(process.env.MQTT_PORT) || 1883; brokerLabel = `${h}:${port}`;
    mqtt = createMqtt({
      host: h, port, clientId: 'classe-noire-' + Math.random().toString(16).slice(2, 8), log,
      onMessage: onMqtt,
      onState: up => log(up ? `connecté au broker ${brokerLabel}` : `broker ${brokerLabel} perdu, nouvelle tentative…`),
    });
    for (const s of ['iot/joueurs/+', 'iot/chat/+', 'iot/capteurs/+/temperature', 'iot/votes/+', 'iot/partie/etat', 'iot/partie/resultat']) mqtt.subscribe(s);
  }

  // ------------------------------------------------------------ API HTTP
  function readBody(req) {
    return new Promise(res => {
      let b = ''; req.on('data', d => { b += d; if (b.length > 8192) req.destroy(); });
      req.on('end', () => { try { res(JSON.parse(b || '{}')); } catch { res(null); } });
      req.on('error', () => res(null));
    });
  }
  const json = (res, code, o) => { res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' }); res.end(JSON.stringify(o)); };
  const status = () => ({
    mqtt: { broker: brokerLabel || null, connecte: !!(mqtt && mqtt.connected) },
    table: { phase: table.phase() },
    agents: [...agents.values()].map(a => ({ id: a.id, nom: a.user.name, joueur: a.user.id, ville: a.ville, via: a.via, api: a.api || null, en_ligne: a.user.connected, temperature: a.temp, vote: a.vote })),
  });

  async function http(req, res, url) {
    const t = url.split('/').filter(Boolean);                  // ['api', 'agents', 'rpi1', 'chat']
    const q = new URL(req.url, 'http://x').searchParams;
    if (req.method === 'GET' && url === '/api/agents') return json(res, 200, status());
    if (req.method === 'GET' && url === '/api/chat') { const since = Number(q.get('since')) || 0; return json(res, 200, { dernier: seq, messages: chatLog.filter(m => m.seq > since) }); }
    if (req.method === 'POST' && t[1] === 'agents' && t[2] && t[3]) {
      const body = await readBody(req); if (!body) return json(res, 400, { erreur: 'JSON invalide' });
      if (t[3] === 'join') { const a = join(t[2], body, 'http'); return a ? json(res, 200, { ok: true, joueur: a.user.id }) : json(res, 400, { erreur: 'id invalide (1-16 caractères a-z 0-9 _ -) ou salon plein' }); }
      if (t[3] === 'leave') return json(res, 200, { ok: leave(t[2]) });
      if (t[3] === 'chat') {
        const a = agents.get(t[2]); if (!a) return json(res, 404, { erreur: 'agent inconnu : fais d\'abord /join' });
        a.lastSeen = Date.now();
        return json(res, 200, { ok: say(a, body.text, resolveTarget(body.to)) });
      }
    }
    json(res, 404, { erreur: 'route inconnue' });
  }

  return { list, start, http, onTableChat, say, keepOnlyAgents, join, leave, status };
};
