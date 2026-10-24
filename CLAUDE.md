# AmongUsIA : qui est l'espion ?

Jeu distribué (TP R5.A.05, IUT d'Annecy, groupe de 5) : des Raspberry Pi capteurs de température, chacun piloté par une IA Ollama, débattent et votent pour démasquer un espion qui publie de fausses valeurs. Tout passe par MQTT. Une salle 3D montre la partie aux spectateurs.

Vue d'ensemble, règles et dépannage : @README.md

## Le contrat : `docs/protocole.md`

Les modules ne communiquent **que** par MQTT, avec les topics et champs de `docs/protocole.md`. Ce fichier fait foi.
- Toute modification d'un topic, d'un champ, d'un `retain` ou d'un Last Will : **d'abord** `docs/protocole.md`, puis tous les modules concernés (skill `/changer-protocole`). Ne jamais changer le format d'un message d'un seul côté.
- Le topic `iot/capteurs/<id>/temperature` et les champs du TP (`espion`, `designe`, `votes`, `gagnant` dans `iot/partie/resultat`) sont imposés par le sujet : ne pas les renommer.
- **L'interface ne lit jamais `iot/role/+`** et ne publie rien : elle révélerait l'espion. Même chose pour `GET /agent` de l'API joueur (jamais le rôle).

## Modules

| Dossier | Langage | Responsable | Point d'entrée |
|---|---|---|---|
| `broker/` | Mosquitto (Docker) | Niels | `docker compose up -d` |
| `joueur/` | Python | Maethan | `joueur.py` (+ `ia.py` LLM, `meteo.py` Open-Meteo, `api.py` HTTP port 5000, `discuter.py`) |
| `maitre_du_jeu/` | Python | Maethan | `maitre.py` : l'arbitre, seul à faire avancer les phases |
| `interface/` | Node.js ≥ 18, Three.js | Valérian | `server.js` (HTTP + WebSocket maison), `spectacle.js` (état reconstruit), `public/` (3D) |
| `outils/` | Python | | `simulation.py`, `broker_dev.py`, `faux_ollama.py` : tester sur un seul PC |

Chaque dossier a un README détaillé : le lire avant de modifier le module.

## Commandes

```bash
uv sync                                               # une fois, à la racine
uv run outils/simulation.py --joueurs 3 --rapide      # partie complète sans Pi ni Ollama (skill /simulation)
uv run maitre_du_jeu/maitre.py --tp                   # mode exact du sujet : 1 manche, pas de débat, majorité
uv run joueur/joueur.py [config.json]
cd interface && node server.js                        # MQTT_HOST=localhost pour la simulation ; http://localhost:5050, /api/etat
uv run python -m py_compile joueur/*.py maitre_du_jeu/*.py outils/*.py   # vérif syntaxe
node --check interface/server.js                      # idem côté Node
```

Il n'y a pas de tests automatisés : la vérification, c'est la compilation + une simulation rapide dont on lit les journaux (skill `/verifier`).

## Bonnes pratiques

Détaillées dans `.claude/rules/` : `qualite.md` (toujours chargé), `python.md` et `interface.md` (chargés quand Claude travaille sur ces fichiers).
- **Doc à jour** : pour toute API de paho-mqtt, requests, Ollama, Three.js, Open-Meteo, Mosquitto ou Docker Compose, consulter Context7 (serveur MCP dans `.mcp.json`) au lieu de se fier à sa mémoire.
- **Lint** : fait par la pipeline CI (règles ruff dans `pyproject.toml`). Ne pas lancer de lint ni de reformatage en local.

## Conventions de code

- **Tout est en français** : noms de variables, fonctions, classes (`Joueur.voter`, `MaitreDuJeu.phase_verdict`), commentaires, docstrings, messages de log, README. Garder ce style, sans accents dans les identifiants.
- Python 3.14 (fixé par `.python-version`, installé par uv sur chaque machine, y compris les Pi, sans toucher au Python du système). Dépendances limitées à `paho-mqtt` (API v2 : callbacks avec `reason_code, properties`) et `requests`. N'en ajouter une qu'avec `uv add`, et seulement si c'est indispensable : elle doit s'installer sur un Pi.
- Les scripts sont lancés avec `uv run <dossier>/<script>.py` (pas un paquet : `package = false`) ; les imports entre fichiers d'un même dossier sont directs (`from ia import IA`).
- Interface : **zéro dépendance npm**, Node seul (client MQTT 3.1.1 et WebSocket écrits à la main). `public/` est en modules ES servis tels quels, sans build. Ne jamais modifier `interface/public/vendor/` (Three.js fourni).
- Messages MQTT : JSON UTF-8, `ensure_ascii=False`. Les `id` ne contiennent ni espace, ni `/`, `+`, `#`.
- Code court et lisible, commentaires qui expliquent le *pourquoi* (voir les constantes en tête de `joueur.py`). Pas de sur-ingénierie : c'est un TP.
- Un README de module qui décrit un comportement modifié doit être mis à jour dans le même commit.

## Pièges connus

- **Robustesse MQTT** : les messages retenus arrivent deux fois après une reconnexion. Le joueur n'agit qu'une fois par phase et ignore les messages d'une autre `partie`/`manche` : préserver ces gardes (`de_la_partie`, `de_cette_manche`) dans toute nouvelle logique.
- **Un seul maître du jeu par broker** (même client id → déconnexions en boucle).
- **Petits modèles** (`qwen3:0.6b`) : ils lisent mal les chiffres et peuvent répondre hors JSON. Toujours garder un repli sur le calcul (`strategie: ecart`), retirer les balises `<think>`, passer `think: false`. Un prompt modifié dans `ia.py` doit aussi rester compris par `outils/faux_ollama.py` (il lit les noms et les mentions « INSTABLE » du contexte).
- **Windows** : une simulation arrêtée autrement que par Ctrl+C laisse tourner broker, faux Ollama et joueurs (ports 1883, 11435, 5100+). Les scripts forcent `stdout` en UTF-8 pour les consoles Windows.
- **Ne pas lancer de simulation sur le vrai broker** (`--broker amongus.local` / `10.109.150.215`) sans le demander : tout le monde la voit.
- Broker réel : `amongus.local:1883`, IP de secours `10.109.150.215`, anonyme. `joueur/config.json` et `maitre_du_jeu/stats.json` sont ignorés par git.

## Git

- Branches par personne/module (`server-niels`, `scripts-maethan`, `interface/classe-noire`), fusion via `integration` puis PR vers `main`.
- Messages de commit en français, préfixés par le module : `Broker : accès par le nom amongus.local`, `Joueur : mémoire entre les manches`, `Protocole : …`, `Interface : …`, `Outils : …`, `Documentation : …`. Corps optionnel qui explique le pourquoi.
- Ne jamais pousser ni réécrire l'historique sans qu'on le demande.
