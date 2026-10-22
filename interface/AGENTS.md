# Relier les Raspberry Pi au salon

Le salon (`server.js`) est la partie « interface » du projet. Chaque Raspberry Pi qui rejoint la partie devient **un personnage** (📡) assis à la table ronde, et ses messages apparaissent dans le chat de la table. Le code du pont est dans [`agents.js`](agents.js) (logique) et [`mqtt.js`](mqtt.js) (client MQTT sans dépendance).

```
 Raspberry Pi (joueur.py / agent Ollama)                 Salon Classe Noire (ce dossier)
 ───────────────────────────────────────                 ───────────────────────────────
  iot/joueurs/<id>  {"en_ligne":true}  ───────MQTT────►  un personnage 📡 apparaît
  iot/capteurs/<id>/temperature        ───────MQTT────►  gardée dans /api/agents
  iot/chat/<id>     {"text":"…"}       ───────MQTT────►  message dans le chat de la table
  iot/votes/<id>                       ───────MQTT────►  ligne « 🗳 … soupçonne … » dans la table
  iot/table/chat    (chat de la table) ◄──────MQTT──────  tout ce qui se dit à la table
```

**Mode « Espion »** ([espion.js](espion.js), [public/espionui.js](public/espionui.js)) : l'hôte le choisit dans le salon ; il suit la partie du TP via MQTT (manche, températures, votes, résultat) et affiche l'espion à la fin.

Trois façons de brancher un Pi, au choix (elles se combinent) :

| Mode | Ce que le Pi doit faire | Quand l'utiliser |
|------|-------------------------|------------------|
| **MQTT** | publier/s'abonner aux topics ci-dessous | cas normal du TP, le serveur est client du broker |
| **API HTTP du salon** | appeler `/api/...` sur le serveur | pas de MQTT sur le Pi, ou test à la main |
| **API de l'agent** | exposer `POST /message` (Flask + Ollama, comme `~/agent/app.py`) | zéro code en plus : le salon appelle le Pi à chaque message |

## 1. Lancer le salon avec le broker

```bash
node server.js                     # utilise par défaut le broker de Niels : 10.109.150.215:1883 (broker/README.md)
```

Autres réglages (variables d'environnement) : `MQTT_HOST=<ip>` pour changer de broker, `MQTT_PORT=1883`, `MQTT_HOST=off` pour ne garder que l'API HTTP.

Console attendue : `[agents] connecté au broker 10.109.150.215:1883`, puis `[agents] + rpi1 (mqtt)` à chaque Pi. Reconnexion automatique si le broker tombe (un message d'erreur toutes les 30 s au plus).

Le salon est **en lecture seule** sur les topics du TP : il ne publie que sur `iot/table/chat`. Les présences retenues (`retain`) des Pi déjà en ligne sont reçues dès l'abonnement, et le Last Will `{"en_ligne": false}` fait partir le personnage.

## 2. MQTT

Le salon s'abonne à `iot/joueurs/+`, `iot/chat/+`, `iot/capteurs/+/temperature`, `iot/votes/+`, `iot/partie/etat`, `iot/partie/resultat`. Il **n'écoute jamais** `iot/role/+` : l'interface ne doit pas révéler l'espion.

| Topic | Sens | Contenu | Effet dans le salon |
|-------|------|---------|---------------------|
| `iot/joueurs/<id>` | Pi → salon | `{"id":"rpi1","ville":"Annecy","en_ligne":true}` + champs facultatifs `"nom"` (nom affiché), `"arch"` (`stratege`, `vengeur`, `sourire`, `reine`, `ombre`, `prodige`), `"api"` (URL de l'agent, voir §4) | le personnage apparaît (`en_ligne:false` : il part). Sans `arch`, l'archétype est choisi d'après l'id |
| `iot/chat/<id>` | Pi → salon | `{"text":"je trouve rpi2 louche"}` ; ajouter `"to":"rpi2"` pour chuchoter (seulement pendant une partie de table) | message dans le chat de la table (lobby/négociation), ou dans le chat du salon si aucune table n'est ouverte |
| `iot/table/chat` | salon → Pi | `{"seq":7,"kind":"pub"\|"whisper"\|"rumor","from":2,"name":"rpi1","text":"…","to":0,"fromAgent":"rpi1"}` | publié à chaque message de la table : le Pi s'abonne pour **entendre** les autres (humains, pions, autres Pi) |
| `iot/capteurs/<id>/temperature` | Pi → tous | message du protocole | mémorisée, visible dans `GET /api/agents` |
| `iot/votes/<id>` | Pi → maître | message du protocole | affichée dans le chat de la table |
| `iot/partie/etat`, `iot/partie/resultat` | maître → tous | messages du protocole | annoncés dans le salon et la table |

Les champs `nom`, `arch`, `api` et les topics `iot/chat/<id>` et `iot/table/chat` sont des **ajouts au protocole commun** : ils sont décrits dans [../docs/protocole.md](../docs/protocole.md) pour que Niels et Maethan les voient.

Exemple minimal côté Pi (`pip install paho-mqtt`) :

```python
import json, paho.mqtt.client as mqtt

c = mqtt.Client()
c.on_message = lambda cl, u, m: print("la table dit :", json.loads(m.payload)["text"])
c.connect("10.109.150.xx", 1883)
c.publish("iot/joueurs/rpi1", json.dumps({"id": "rpi1", "ville": "Annecy", "en_ligne": True}), retain=True)
c.subscribe("iot/table/chat")
c.publish("iot/chat/rpi1", json.dumps({"text": "Bonjour la table"}))
c.loop_forever()
```

Pour tester sans Pi : `mosquitto_pub -h <broker> -t iot/joueurs/rpi9 -m '{"id":"rpi9","en_ligne":true}'` fait apparaître un personnage.

## 3. API HTTP du salon

Utile sans MQTT et pour déboguer (`curl`). Corps en JSON.

| Requête | Rôle |
|---------|------|
| `POST /api/agents/<id>/join` `{"ville":"Annecy","nom":"…","arch":"…","api":"http://ip:5000"}` | faire entrer un agent |
| `POST /api/agents/<id>/leave` | le faire sortir |
| `POST /api/agents/<id>/chat` `{"text":"…","to":"rpi2"}` | parler à la table (`to` = chuchoter) |
| `GET /api/chat?since=<n>` | lire les messages de la table depuis le numéro `n` → `{"dernier":n,"messages":[…]}` |
| `GET /api/agents` | état : connexion au broker, agents, dernière température, vote |

Un agent complet utilisant seulement ces routes et son Ollama local : [exemples/agent_pi.py](exemples/agent_pi.py).

## 4. Faire parler un agent Flask existant (sans modifier le Pi)

Le Pi expose déjà `POST /message {"message": "…"}` → `{"reponse": "…"}` (`~/agent/app.py`, modèle `qwen3:0.6b`). Si le joueur annonce `"api":"http://<ip du Pi>:5000"` (message de présence ou `join`), le salon envoie à ce Pi chaque message de la table et publie sa réponse comme message du joueur.

Garde-fous : au plus une réponse toutes les 8 s par agent, une seule requête à la fois, uniquement dans le salon, le lobby et la négociation, pas de réponse à soi-même ni aux rumeurs. Les chuchotements reçoivent un chuchotement en retour. **Les agents se taisent après 6 messages d'agents d'affilée** : dès qu'un humain ou un pion reparle, la conversation repart (sinon deux LLM se répondraient sans fin).

## 5. Comment le jeu traite un Pi

- Dans `server.js`, un Pi est un utilisateur sans WebSocket (`ext: true`). Il ne peut pas être hôte : l'hôte 👑 reste un humain.
- À la table (`table.js`), il joue comme un pion 🤖 pour les actions (coopérer/trahir/observer, accusation) afin que la partie avance, mais **ses phrases viennent du Pi** : le chat automatique des pions est coupé pour lui.
- Arrivée ou départ pendant une partie : le Pi attend la manche/partie suivante, ou reste « hors ligne » jusqu'à la fin.
- Identifiants : `<id>` fait 1 à 32 caractères, sans espace ni `/` (comme le protocole) ; le nom affiché est tronqué à 16 caractères, sauf si le joueur envoie `"nom"`.
- Limite connue : les décisions de jeu d'un Pi ne sont pas encore pilotées par son LLM, seulement son chat.
