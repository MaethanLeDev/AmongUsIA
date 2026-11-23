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

Une seule fois sur chaque machine Python : installer [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh` sur un Pi). Pas besoin de `uv sync` : `uv run` installe ce qui manque.
uv télécharge lui-même Python 3.14 (version fixée par `.python-version`), sans toucher au Python du système : il faut juste un accès Internet la première fois.

**Pour seulement jouer, pas besoin de cloner le dépôt** : avec uv installé, cette commande suffit, la même à chaque partie.

```bash
uv run https://raw.githubusercontent.com/MaethanLeDev/AmongUsIA/main/jouer.py
```

Au premier lancement, on choisit son LLM (un modèle déjà installé sur la machine, Gemini, ou une autre adresse Ollama).
Pour en changer, ou changer n'importe quel réglage, la même commande avec `--reglages` :

```bash
uv run https://raw.githubusercontent.com/MaethanLeDev/AmongUsIA/main/jouer.py --reglages
```

Elle ne garde que le code du joueur, dans `~/.amongusia/code/`, à jour de `main`, et la config dans `~/.amongusia/config.json`.

Avec le dépôt cloné, une commande de chaque côté :

| Où | Commande | Ce qu'elle fait |
|----|----------|-----------------|
| **Serveur** (Pi du broker) | `uv run serveur.py` | trouve le broker (ou démarre celui de `broker/`), lance l'interface 3D et le maître du jeu |
| **Chaque joueur** | `uv run joueur/joueur.py` | au premier lancement : nom, ville, caractère et choix du LLM, écrits dans `joueur/config.json` ; `--reglages` pour les changer |

Seul Ollama s'installe à la main sur chaque joueur, une fois : `curl -fsSL https://ollama.com/install.sh | sh` sur un Pi, [ollama.com/download](https://ollama.com/download) ailleurs.
La partie démarre toute seule 30 s après la dernière arrivée, dès qu'il y a 3 IA (ou plus tôt avec Entrée dans le terminal du serveur).
Les spectateurs ouvrent l'adresse affichée par le serveur, par exemple `http://10.109.150.140:5050`.
On peut toujours lancer les morceaux séparément : `docker compose up -d` dans `broker/`, `uv run maitre_du_jeu/maitre.py`, `node interface/server.js`.

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

## Tests

Des tests unitaires, qui tournent sans broker, sans Ollama, sans Internet et sans Raspberry Pi, en quelques secondes :

```bash
uv run pytest -q                                          # joueur/, maitre_du_jeu/, outils/
uv run pytest -q --cov=joueur --cov-report=term-missing   # couverture d'un module
node --test "interface/tests/*.test.js"                   # interface (les tests demandent Node ≥ 20.4)
```

- **Où les mettre** : `tests/<module>/test_<fichier>.py` pour Python, `interface/tests/<fichier>.test.js` pour l'interface (`node:test`, sans dépendance npm).
- **Outils communs** : `tests/aides.py` (`FauxClientMQTT` qui remplace paho et permet d'injecter des messages, `FauxTemps`, `FausseReponseHTTP`), les fixtures de `tests/conftest.py` et de chaque `tests/<module>/conftest.py`, et le faux broker de `interface/tests/aides.js`.
- **Conventions** :
  - un comportement par test, nommé en français : `test_egalite_personne_n_est_elimine` ;
  - jamais de vrai réseau : paho est remplacé, `requests` est simulé avec `monkeypatch`, le temps est figé (aucun `sleep` réel) ;
  - un test qui révèle un bug n'est pas « corrigé » en douce : il est marqué `@pytest.mark.xfail(reason="bug : …")`. Comme `xfail_strict` est activé, le jour où le bug est corrigé, le test passe et pytest le signale : il faut alors retirer la marque.
- **Sur un Raspberry Pi**, `uv sync --no-dev` évite d'installer pytest.

## Intégration continue

À chaque push et chaque PR, GitHub Actions ([.github/workflows/ci.yml](.github/workflows/ci.yml)) vérifie :
- le lint Python (`uvx ruff check`, règles dans `pyproject.toml`) et la compilation de `joueur/`, `maitre_du_jeu/`, `outils/` ;
- les tests unitaires Python (`uv run pytest -q`) ;
- la syntaxe du code Node de `interface/` (hors `public/vendor/`) et ses tests (`node --test`) ;
- le fichier `broker/docker-compose.yml` ;
- une partie complète simulée (`outils/simulation.py --joueurs 3 --rapide -- --tp`), qui doit se finir par une victoire. En cas d'échec, les journaux des joueurs sont joints au run.

Pas de déploiement automatique : les Pi sont sur le réseau de l'IUT, injoignables depuis GitHub.

## Dépannage

| Problème                                               | Piste                                                                                          |
|--------------------------------------------------------|------------------------------------------------------------------------------------------------|
| « Aucun broker joignable »                             | Le réseau bloque peut-être le mDNS (`amongus.local`) : mettre l'IP `10.109.150.215` dans la config ou `--broker`. |
| « Météo indisponible »                                 | Pas d'accès Internet depuis le Pi (proxy de l'IUT ?) : `export HTTPS_PROXY=...`, ou `"coordonnees": [lat, lon]` si le géocodage échoue. |
| Une IA répète « Je préfère écouter… », sa carte affiche « ⚠ LLM injoignable » ou « ⚠ modèle absent » | Son Ollama ne répond pas, ou le modèle n'est pas installé : le terminal du joueur dit quoi faire (`ollama pull …`). Vérifier avec `curl http://127.0.0.1:11434/api/tags`. |
| L'interface reste sur « En attente du maître du jeu »  | Le maître n'est pas lancé, ou l'interface n'écoute pas le bon broker (`node interface/server.js --broker <ip>`). |
| Voir tout le trafic MQTT                               | `mosquitto_sub -h amongus.local -t 'iot/#' -v`, ou l'état reconstruit par l'interface : `http://<ip>:5050/api/etat`. |
