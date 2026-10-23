# AmongUsIA : qui est l'espion ?

TP R5.A.05 de l'IUT d'Annecy, étendu. Des **Raspberry Pi** sont des capteurs de température, chacun piloté par sa propre **IA Ollama**.
L'un d'eux est un **espion** qui publie de fausses valeurs. Les IA débattent, votent et éliminent un suspect, manche après manche, comme au Loup-Garou.
Les spectateurs regardent la partie dans une **salle 3D**, depuis n'importe quel PC du réseau.

```
                          ┌──────────────────────────────┐
                          │   Broker Mosquitto (MQTT)    │  broker/        amongus.local:1883
                          └──────────────┬───────────────┘
        ┌───────────────────┬────────────┴──────┬────────────────────────┐
┌───────┴──────┐     ┌──────┴───────┐    ┌──────┴───────┐        ┌───────┴────────┐
│ Joueur rpi1  │ ... │ Joueur rpiN  │    │ Maître du jeu│        │   Interface    │  interface/
│ + Ollama     │     │ + Ollama     │    │   (arbitre)  │        │ (Node, lecture │──── http://<ip>:5050
│ + API HTTP   │     │ + API HTTP   │    │              │        │     seule)     │     navigateurs des
└──────────────┘     └──────────────┘    └──────────────┘        └────────────────┘     spectateurs (3D)
   joueur/                                maitre_du_jeu/
```

| Dossier          | Contenu                                                                                         |
|------------------|-------------------------------------------------------------------------------------------------|
| `broker/`        | Mosquitto en Docker (Niels)                                                                     |
| `joueur/`        | le programme de chaque Raspberry Pi : capteur, IA qui débat et vote, API de l'agent (Maethan)   |
| `maitre_du_jeu/` | l'arbitre : inscription, tirage de l'espion, manches, verdicts, statistiques (Maethan)           |
| `interface/`     | la salle 3D des spectateurs, d'après le jeu « Classe Noire » (Valérian)                          |
| `outils/`        | broker, faux Ollama et simulation pour tester une partie sur un seul PC                          |
| `docs/`          | **[le protocole MQTT](docs/protocole.md)** : le contrat entre tous les modules                    |

> **[Mode d'emploi](docs/mode-emploi.md)** : lancer une partie avec ou sans Raspberry Pi, personnaliser son IA, toutes les options.
>
> Tous les modules ne communiquent **que** par MQTT, avec les topics définis dans [docs/protocole.md](docs/protocole.md).
> Pour changer un topic ou un champ, modifiez d'abord ce fichier et prévenez les autres.

## Une partie

1. **Inscription** : chaque IA qui se connecte apparaît à la table, dans une colonne de lumière.
2. Le maître tire un **espion** au hasard et envoie à chacun son rôle secret.
3. **Manche** :
   - **mesures** : 5 températures, une toutes les 5 s ;
   - **débat** : chaque IA parle à son tour, et la caméra la suit ;
   - **vote** : les arcs rouges montrent qui accuse qui ;
   - **verdict** : l'IA la plus désignée est aspirée par la lampe.
4. Si c'était l'espion, les innocents gagnent. Sinon, la manche suivante commence, et les IA **se souviennent** des manches précédentes. Quand il ne reste que deux joueurs, l'espion gagne.

Les règles complètes sont dans [docs/protocole.md](docs/protocole.md#règles).

## Ce que demande le sujet, et où c'est fait

| Consigne                                                                   | Où                                                                                       |
|----------------------------------------------------------------------------|------------------------------------------------------------------------------------------|
| Chaque RPi publie la température d'une ville voisine (Open-Meteo), toutes les 5 s | `joueur/meteo.py`, `joueur/joueur.py` → `iot/capteurs/<id>/temperature`              |
| Le serveur tire un espion et l'informe par `iot/role/<id>`                 | `maitre_du_jeu/maitre.py`                                                                 |
| L'espion publie des valeurs ±10 % différentes de celles des autres         | `Joueur.fausse_temperature`                                                              |
| Après 5 échanges, chaque RPi vote sur `iot/votes/<id>`                     | `Joueur.voter`                                                                           |
| Le serveur compte les votes ; majorité → les capteurs gagnent              | `MaitreDuJeu.phase_verdict` (mode exact du sujet : `maitre.py --tp`)                      |
| Chaque étudiant choisit sa méthode de détection                            | `"strategie": "ecart"` (calcul) ou `"llm"` dans `config.json`                             |
| **Extension** : chaque RPi est un agent Ollama qui vote avec l'avis du LLM | `joueur/ia.py`                                                                            |
| **Extension** : l'agent est-il plus efficace que la méthode de départ ?    | chaque vote contient aussi le choix du calcul ; le maître cumule les deux taux de réussite (`iot/partie/stats`, affichés dans l'interface) |
| **TP Ollama** : API `POST /message`, `GET /health`, `GET /agent`          | `joueur/api.py`, lancée avec le joueur (port 5000)                                       |
| **TP Ollama** : deux agents discutent en se souvenant de la conversation   | `joueur/discuter.py`, route `POST /discuter`                                             |

## Lancer une vraie partie

Une seule fois sur chaque machine Python : installer [uv](https://docs.astral.sh/uv/), puis `uv sync` à la racine du dépôt.

1. **Broker** (Pi de Niels) : `cd broker && docker compose up -d`.
2. **Chaque Raspberry Pi** :
   ```bash
   ollama pull qwen3:0.6b
   cp joueur/config.example.json joueur/config.json   # régler id, ville, personnalité, nom, apparence
   uv run joueur/joueur.py
   ```
3. **Maître du jeu** (n'importe quelle machine, par exemple le Pi du broker) : `uv run maitre_du_jeu/maitre.py`.
   La partie démarre toute seule 30 s après la dernière arrivée, dès qu'il y a 3 IA (ou plus tôt avec Entrée).
4. **Interface** (une machine avec Node.js ≥ 18) : `node interface/server.js`.
   Les spectateurs ouvrent l'adresse affichée, par exemple `http://10.109.150.140:5050`.

Le nombre d'IA n'est pas fixé : de 3 à 12, autant qu'il y a de sièges. Une IA qui arrive en cours de partie attend la suivante.

## Tester sans Raspberry Pi

Tout tient sur un seul PC, sans Docker ni Ollama :

```bash
uv run outils/simulation.py --joueurs 6 --rapide     # terminal 1
node interface/server.js                             # terminal 2
```

puis ouvrir http://localhost:5050. `outils/simulation.py` lance un broker de test (`outils/broker_dev.py`), un faux Ollama (`outils/faux_ollama.py`), N joueurs et le maître.
Arrêtez-la avec **Ctrl+C** dans son terminal : sous Windows, fermer la fenêtre autrement laisse tourner les joueurs en arrière-plan.
Avec un vrai Ollama installé sur le PC : `--ollama http://127.0.0.1:11434 --modele qwen3:0.6b`. Les options sont détaillées en tête de `outils/simulation.py`.

## Dépannage

| Problème                                               | Piste                                                                                          |
|--------------------------------------------------------|------------------------------------------------------------------------------------------------|
| « Aucun broker joignable »                             | Le réseau bloque peut-être le mDNS (`amongus.local`) : mettre l'IP `10.109.150.215` dans la config ou `--broker`. |
| « Météo indisponible »                                 | Pas d'accès Internet depuis le Pi (proxy de l'IUT ?) : `export HTTPS_PROXY=...`, ou `"coordonnees": [lat, lon]` si le géocodage échoue. |
| Une IA reste muette (« Je préfère écouter… »)          | Ollama ne répond pas : `curl http://127.0.0.1:11434/api/tags`, puis `GET http://<pi>:5000/health`. |
| L'interface reste sur « En attente du maître du jeu »  | Le maître n'est pas lancé, ou l'interface n'écoute pas le bon broker (`node interface/server.js --broker <ip>`). |
| Voir tout le trafic MQTT                               | `mosquitto_sub -h amongus.local -t 'iot/#' -v`, ou l'état reconstruit par l'interface : `http://<ip>:5050/api/etat`. |
