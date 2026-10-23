# Interface graphique — Valérian

Mettez ici l'interface dérivée de votre jeu de l'espace.

Elle s'abonne au broker en **lecture seule** (`iot/#`) et affiche :

- les joueurs connectés (`iot/joueurs/+`)
- les températures publiées à chaque manche (`iot/capteurs/+/temperature`)
- l'état de la partie (`iot/partie/etat`)
- les votes et le résultat (`iot/votes/+`, `iot/partie/resultat`)

Elle ne doit **pas** s'abonner à `iot/role/+` pendant la partie, sinon elle révèle l'espion, sauf en mode « spectateur omniscient ».

Protocole : [../docs/protocole.md](../docs/protocole.md)

---

## Base de code : Classe Noire

Le dossier contient le jeu **Classe Noire** réduit à son salon 3D et à sa **table ronde**, comme base de l'interface (Node.js sans dépendance, rendu Three.js). Le mode « Mission 3D » du jeu d'origine a été retiré.

```bash
cd interface
node server.js                   # puis http://localhost:3939 — broker de Niels (10.109.150.215) par défaut
# autre broker : set MQTT_HOST=<ip>    |    sans MQTT : set MQTT_HOST=off
```

- Mode **Espion** : suit la partie du TP (températures, votes, résultat) via MQTT.
- Chaque Raspberry Pi qui s'annonce sur `iot/joueurs/<id>` devient un **personnage** 📡 à la table ronde.
- Les agents IA discutent dans le chat de la table (MQTT `iot/chat/<id>` / `iot/table/chat`, ou API HTTP, ou appel de leur API Flask/Ollama).
- Températures, votes et résultat du TP sont relayés dans le salon.

Fonctionnement détaillé, topics, API et exemple de code pour le Pi : [AGENTS.md](AGENTS.md). Jeu d'origine : [README_classe-noire.md](README_classe-noire.md).
