# Mode d'emploi

Tout ce qu'il faut pour lancer une partie, avec ou sans Raspberry Pi, et tout ce qui se personnalise.
Les commandes marchent telles quelles dans PowerShell (terminal de VS Code), cmd et bash : aucune variable d'environnement n'est nécessaire.

À faire une fois par machine qui lance du Python : installer [uv](https://docs.astral.sh/uv/) (`pip install uv`, ou `curl -LsSf https://astral.sh/uv/install.sh | sh` sur un Pi), puis c'est tout : `uv run` installe lui-même les dépendances au premier lancement.
La machine de l'interface a besoin de Node.js 18 ou plus, sans `npm install`.

## Les façons de jouer

### 1. Simulation sur un seul PC (aucun Pi, aucun LLM)

Le plus rapide pour tester le jeu ou l'interface. Il faut deux terminaux :

```bash
uv run outils/simulation.py --joueurs 6 --rapide        # terminal 1 : broker, faux Ollama, 6 IA, maître
node interface/server.js                                # terminal 2 : interface
```

Ouvrir ensuite http://localhost:5050. On arrête la simulation avec **Ctrl+C** dans son terminal.
Les IA sont branchées sur un **faux Ollama** : leurs phrases sont tirées d'une liste, et leurs votes visent surtout le capteur marqué « INSTABLE », un indice que le jeu a calculé. Leur modèle s'affiche « simulé ».

### 2. Simulation avec un vrai LLM sur le PC

Il faut d'abord un Ollama qui tourne sur le PC :

1. installer Ollama ([ollama.com/download](https://ollama.com/download)), qui se lance ensuite tout seul en arrière-plan ;
2. télécharger le modèle : `ollama pull qwen3:0.6b` ;
3. vérifier qu'il répond : `curl http://127.0.0.1:11434/api/tags` doit lister le modèle.

```bash
uv run outils/simulation.py --joueurs 4 --ollama http://127.0.0.1:11434 --modele qwen3:0.6b
node interface/server.js
```

La simulation vérifie Ollama et le modèle avant de démarrer, et dit quoi faire s'il manque quelque chose.
Toutes les IA partagent le même Ollama, qui répond à une seule à la fois : une partie à 4 joueurs prend quelques minutes.

### 3. Vraie partie avec les Raspberry Pi

| Où                       | Commande                    | Remarque                                         |
|--------------------------|-----------------------------|--------------------------------------------------|
| Serveur (Pi du broker)   | `uv run serveur.py`         | broker + interface + maître du jeu ; Ctrl+C arrête tout (le broker Docker reste) |
| Chaque joueur            | `uv run joueur/joueur.py`   | crée `joueur/config.json` au premier lancement, démarre Ollama, télécharge le modèle |

**Côté serveur**, `serveur.py` prend le premier broker qui répond (`localhost`, `amongus.local`, `10.109.150.215`).
S'il n'y en a aucun, il démarre Mosquitto avec Docker (`broker/`), ou à défaut le broker de test `outils/broker_dev.py`.
Il lance ensuite l'interface si Node.js est installé, puis le maître du jeu au premier plan (Entrée lance la partie).
Ses options inconnues vont au maître : `uv run serveur.py --tp`, `uv run serveur.py --tours 3`. Autres options : `--broker <ip>` (ne cherche pas, n'en démarre pas), `--sans-interface`.
Un seul serveur par broker : deux maîtres du jeu se déconnectent l'un l'autre.

**Côté joueur**, seul [Ollama](https://ollama.com/download) s'installe à la main, une fois (`curl -fsSL https://ollama.com/install.sh | sh` sur un Pi).
Au premier lancement, le joueur demande le nom de son IA, sa ville et son caractère (Entrée garde la proposition), et écrit `joueur/config.json`.
Si Ollama est installé mais arrêté, il le démarre ; si le modèle manque, il le télécharge (une seule fois, quelques minutes).
Sans Ollama, il démarre quand même et vote par calcul. Pour changer de réglages : modifier `joueur/config.json`, ou le supprimer et relancer.

Les morceaux se lancent aussi séparément : `cd broker && docker compose up -d`, `uv run maitre_du_jeu/maitre.py`, `node interface/server.js`.

Le maître et l'interface trouvent le broker tout seuls : `localhost`, puis `amongus.local`, puis `10.109.150.215`.
La partie démarre 30 s après la dernière IA arrivée, dès qu'il y en a 3. Les parties s'enchaînent ensuite.

### 4. Le jeu de base du sujet (pour la démonstration au prof)

```bash
uv run maitre_du_jeu/maitre.py --tp
```

Une seule manche, pas de débat, et la majorité stricte des votes désigne l'espion : exactement les règles du TP.
Pour comparer avec la méthode de calcul, mettez `"strategie": "ecart"` dans la config de certains Pi.

## Personnaliser son IA : `joueur/config.json`

Le premier lancement l'écrit tout seul ; on peut ensuite l'adapter (ou partir de `joueur/config.example.json`). Seuls `id` et `ville` sont obligatoires.

```json
{
  "id": "maethan",
  "ville": "Seynod",
  "ollama": { "url": "http://127.0.0.1:11434", "modele": "qwen3:0.6b" },
  "personnalite": "Tu es paranoïaque et théâtral : tu soupçonnes tout le monde, surtout ceux qui sont calmes.",
  "strategie": "llm",
  "memoire": "resume",
  "interface": { "nom": "Kuro", "arch": "ombre", "couleurs": { "cheveux": "#1c7ed6", "yeux": "#e0162b", "accent": "#7048e8" } }
}
```

| Champ           | Valeurs                                                                         | Effet                                             |
|-----------------|---------------------------------------------------------------------------------|---------------------------------------------------|
| `id`            | texte sans espace, `/`, `+`, `#`                                                | identifiant MQTT, unique                          |
| `ville`         | une ville **voisine** des autres (Annecy, Seynod, Sévrier…)                     | la température publiée                            |
| `coordonnees`   | `[45.886, 6.089]`                                                               | remplace le géocodage de la ville                 |
| `ollama.modele` | tout modèle installé (`ollama list`)                                            | le cerveau de l'IA                                |
| `fournisseur`   | `ollama` (défaut) ou `anthropic`                                                | `anthropic` : Claude à la place d'Ollama (clé dans `ANTHROPIC_API_KEY`, réglages dans `anthropic`, voir [joueur/README.md](../joueur/README.md)) |
| `personnalite`  | une ou deux phrases « Tu es… »                                                  | sa façon de débattre                              |
| `strategie`     | `llm` (défaut) ou `ecart`                                                       | vote par le LLM, ou par le calcul seul            |
| `meteo`         | `reelle` (défaut) ou `historique`                                               | `historique` : chaque mesure est un jour et une heure au hasard des 3 dernières années, mois annoncé. **À régler pareil sur tous les Pi** |
| `vote_honnete`  | `llm` (défaut) ou `calcul`                                                      | `calcul` : honnête, on vote par le calcul ; le LLM ne sert qu'à l'espion (sauf en mode `historique`) |
| `memoire`       | `faits` (défaut) ou `resume`                                                    | `resume` : le LLM écrit en plus ses notes à chaque manche |
| `interface.nom` | 16 caractères max                                                               | nom affiché à la table                            |
| `interface.arch`| `stratege`, `vengeur`, `sourire`, `reine`, `ombre`, `prodige`                   | apparence du personnage                           |
| `interface.couleurs` | `cheveux`, `yeux`, `accent` en `#rrggbb`                                   | couleurs du personnage (l'accent colore aussi son nom et sa bulle) |
| `broker`        | `{"hote": "amongus.local,10.109.150.215", "port": 1883}`                        | où trouver le broker (hôtes essayés dans l'ordre)  |
| `api.port`      | `5000` (défaut), `0` pour couper                                                | l'API de l'agent du TP Ollama                     |

Détails : [joueur/README.md](../joueur/README.md).

## Régler la partie : options du maître du jeu

On ajoute les options après la commande, par exemple `uv run maitre_du_jeu/maitre.py --tours 3 --auto 60`.

| Option                       | Défaut | Effet                                                         |
|------------------------------|--------|---------------------------------------------------------------|
| `--tp`                       |        | jeu de base du sujet (voir plus haut)                          |
| `--auto N`                   | 30     | lancement N s après la dernière arrivée (`0` : touche Entrée)  |
| `--min-joueurs`, `--max-joueurs` | 3, 12 |                                                            |
| `--tours N`                  | 2      | tours de parole par manche (`0` : pas de débat)                |
| `--delai-parole`, `--delai-vote` | 90, 120 | secondes laissées au LLM                                  |
| `--pause`, `--pause-verdict`, `--pause-fin` | 2, 12, 20 | rythme du spectacle                              |
| `--manches-max N`            | joueurs − 1 |                                                          |
| `--majorite`                 |        | éliminer seulement à la majorité stricte                       |
| `--broker`                   | `localhost,amongus.local,10.109.150.215` |                              |

Détails : [maitre_du_jeu/README.md](../maitre_du_jeu/README.md).

## Options de la simulation, et le `--`

| Option                       | Effet                                                                        |
|------------------------------|------------------------------------------------------------------------------|
| `--joueurs N`                | nombre d'IA (2 à 12)                                                         |
| `--rapide`                   | un seul tour de débat, pauses courtes                                         |
| `--ollama URL --modele M`    | un vrai LLM au lieu du faux Ollama                                            |
| `--resume`                   | toutes les IA en mémoire `resume`                                            |
| `--broker IP`                | utiliser un broker existant au lieu du broker de test (attention : visible par tous) |

Tout ce qui suit `--` est transmis **au maître du jeu**. Par exemple, pour simuler le jeu de base du TP :

```bash
uv run outils/simulation.py --joueurs 4 -- --tp
uv run outils/simulation.py -- --tours 3 --auto 15
```

## Options de l'interface

```bash
node interface/server.js --broker 10.109.150.215    # forcer un broker
node interface/server.js --port 8080                # autre port que 5050
```

À l'écran, en haut à droite : qualité graphique (baisser sur un PC lent), caméra automatique, son (il s'active au premier clic), règles.
Sur chaque carte d'IA, on lit 📍 sa ville, 🧠 son modèle Ollama, et sa façon de voter (💬 par LLM, 🧮 par calcul).
« ⚠ LLM injoignable », « ⚠ modèle absent » ou « ⚠ LLM trop lent » : son LLM ne répond pas. Elle dit alors une phrase de secours et vote par calcul ; son terminal explique quoi faire.

## Lire les statistiques « Votes justes »

En bas à droite : `Votes justes · LLM : 7/8 (88 %) · calcul sans LLM : 6/12 (50 %)`.

- **LLM** : parmi les votes des IA en stratégie `llm`, combien ont désigné le vrai espion.
- **Calcul sans LLM** : pour **chaque** vote, ce qu'aurait désigné la méthode de calcul, et combien de fois elle avait raison.
- Seuls les votes des innocents comptent : l'espion ne vote jamais contre lui-même.

C'est la réponse à la question de l'extension du TP (« l'agent est-il plus ou moins efficace que la méthode de départ ? »). La ligne LLM ne veut dire quelque chose qu'avec de **vrais** LLM : en simulation, le faux Ollama ne raisonne pas, il suit l'indice « INSTABLE ».
Les statistiques sont cumulées dans `maitre_du_jeu/stats.json` ; chaque simulation repart de zéro dans son propre dossier.
