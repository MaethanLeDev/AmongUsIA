# Mode d'emploi

Tout ce qu'il faut pour lancer une partie, avec ou sans Raspberry Pi, et tout ce qui se personnalise.
Les commandes marchent telles quelles dans PowerShell (terminal de VS Code), cmd et bash : aucune variable d'environnement n'est nécessaire.

À faire une fois par machine qui lance du Python : installer [uv](https://docs.astral.sh/uv/) (`pip install uv`, ou `curl -LsSf https://astral.sh/uv/install.sh | sh` sur un Pi), puis `uv sync` à la racine du dépôt.
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

| Où                       | Commande                                   | Remarque                                         |
|--------------------------|--------------------------------------------|--------------------------------------------------|
| Pi du broker (Niels)     | `cd broker && docker compose up -d`        | une fois ; il redémarre tout seul avec le Pi     |
| Chaque Pi joueur         | `uv run joueur/joueur.py`                  | après avoir écrit `joueur/config.json` (voir plus bas) ; Ollama doit tourner |
| Une machine, une seule fois | `uv run maitre_du_jeu/maitre.py`         | le Pi du broker convient très bien               |
| Une machine avec Node    | `node interface/server.js`                 | les spectateurs ouvrent l'adresse « Depuis le réseau » affichée |

Le maître et l'interface trouvent le broker tout seuls : `localhost`, puis `amongus.local`, puis `10.109.150.215`.
La partie démarre 30 s après la dernière IA arrivée, dès qu'il y en a 3. Les parties s'enchaînent ensuite.

### 4. Le jeu de base du sujet (pour la démonstration au prof)

```bash
uv run maitre_du_jeu/maitre.py --tp
```

Une seule manche, pas de débat, et la majorité stricte des votes désigne l'espion : exactement les règles du TP.
Pour comparer avec la méthode de calcul, mettez `"strategie": "ecart"` dans la config de certains Pi.

## Personnaliser son IA : `joueur/config.json`

On copie `joueur/config.example.json` en `joueur/config.json`, puis on l'adapte. Seuls `id` et `ville` sont obligatoires.

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
| `personnalite`  | une ou deux phrases « Tu es… »                                                  | sa façon de débattre                              |
| `strategie`     | `llm` (défaut) ou `ecart`                                                       | vote par le LLM, ou par le calcul seul            |
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
