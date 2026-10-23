# Protocole MQTT

C'est le contrat commun entre les modules : joueurs (Raspberry Pi), maître du jeu et interface.
Tous les messages sont en **JSON UTF-8**. `<id>` est l'identifiant d'un joueur (ex : `rpi1`) : il est unique et ne contient ni espace, ni `/`, ni `+`, ni `#`.

Le broker est `amongus.local:1883` (IP de secours : `10.109.150.215`, voir `broker/`).
Une partie accepte de 3 à **12 joueurs** : c'est le nombre de sièges autour de la table de l'interface.

> Pour changer un topic ou un champ, modifiez d'abord ce fichier et prévenez les autres.

## Vocabulaire

| Terme       | Sens                                                                                     |
|-------------|------------------------------------------------------------------------------------------|
| **partie**  | une partie complète, du tirage de l'espion jusqu'au résultat. Identifiée par `partie` (horodatage Unix du début). |
| **manche**  | un tour de jeu : mesures → débat → vote → verdict. Une partie enchaîne plusieurs manches. |
| **échange** | une publication de température. Une manche compte 5 échanges, un toutes les 5 s (sujet du TP). |
| **vivants** | les joueurs encore en jeu. Un joueur éliminé ne mesure plus, ne parle plus et ne vote plus. |

## Déroulement d'une partie

Le maître du jeu est l'**arbitre** : lui seul fait avancer les phases. Un joueur qui arrive en cours de partie attend la suivante.

```
INSCRIPTION   joueurs → iot/joueurs/<id>                présence (retain)
              maître  → iot/partie/etat                  {"etat": "inscription", ...}

DÉBUT         maître  → iot/role/<id>                    rôle secret, un message par joueur, une seule fois par partie

┌─ MANCHE n ──────────────────────────────────────────────────────────────────────────────┐
│ MESURES     maître  → iot/partie/etat                  {"etat": "mesures", "manche": n, ...}
│             vivants → iot/capteurs/<id>/temperature    5 échanges, un toutes les 5 s
│ DÉBAT       maître  → iot/partie/etat                  {"etat": "debat", ...}
│             pour chaque tour, chaque vivant à son tour :
│               maître → iot/partie/parole               {"joueur": "rpi2", ...}
│               rpi2   → iot/chat/rpi2                   sa prise de parole
│ VOTE        maître  → iot/partie/etat                  {"etat": "vote", ...}
│             vivants → iot/votes/<id>
│ VERDICT     maître  → iot/partie/verdict               qui est éliminé (ou personne)
│             maître  → iot/partie/etat                  {"etat": "verdict", ...}   pause : animation, mémoire des IA
└──────────────────────────────────────────────────────────────────────────────────────────┘
              … manche suivante, jusqu'à la fin …

FIN           maître  → iot/partie/resultat              (retain)
              maître  → iot/partie/stats                 (retain) bilan LLM contre calcul
              maître  → iot/partie/etat                  {"etat": "fini", ...}
```

### Règles

- **Élimination** : à chaque manche, le joueur qui reçoit le plus de votes est éliminé. En cas d'égalité, ou si personne n'a voté, personne n'est éliminé.
  Option `--majorite` du maître : il faut en plus la majorité stricte des vivants (règle du TP).
- **Les capteurs gagnent** dès que l'espion est éliminé.
- **L'espion gagne** s'il ne reste que 2 vivants (lui et un capteur), ou si la dernière manche autorisée se termine sans qu'il soit éliminé.
  Par défaut, le nombre maximum de manches est `nombre de joueurs − 1`. Avec 3 joueurs, une seule élimination est donc possible.
- **Mode TP** (`maitre.py --tp`) : une seule manche, sans débat, majorité stricte. C'est exactement le jeu de base du sujet.
- Si l'espion se déconnecte pendant la partie, les capteurs gagnent par abandon. S'il reste moins de 2 vivants en ligne, la partie est annulée.

## Topics

### `iot/joueurs/<id>` : présence (joueur → tous, retain)

Le joueur la publie à sa connexion. Il configure aussi un *Last Will* `{"id": "<id>", "en_ligne": false}`, que le broker publie à sa place s'il disparaît.

```json
{"id": "rpi1", "ville": "Annecy", "en_ligne": true, "nom": "Sherlock", "arch": "stratege",
 "couleurs": {"cheveux": "#17151c", "yeux": "#9aa0b8", "accent": "#c1121f"},
 "modele": "qwen3:0.6b", "strategie": "llm", "api": "http://10.109.150.60:5000"}
```

Seuls `id` et `en_ligne` sont obligatoires. Les autres champs servent à l'interface :
- `nom` : nom affiché (16 caractères max). Par défaut, l'id.
- `arch` : apparence du personnage (`stratege`, `vengeur`, `sourire`, `reine`, `ombre`, `prodige`). Par défaut, elle est choisie d'après l'id.
- `couleurs` : couleurs du personnage (`#rrggbb`). Chacune est facultative.
- `modele`, `strategie` : informatifs. `api` : URL de l'API HTTP de l'agent (TP Ollama, voir `joueur/README.md`).

### `iot/partie/etat` : phase de la partie (maître → tous, retain)

Le maître configure le *Last Will* `{"etat": "arret"}` : si le maître s'arrête, tout le monde le sait.

| `etat`        | Champs en plus                                             | Signification                                   |
|---------------|------------------------------------------------------------|-------------------------------------------------|
| `inscription` | `min`, `max`, `debut` (horodatage ou `null`)               | les joueurs peuvent rejoindre ; `debut` = lancement automatique prévu |
| `mesures`     | commun + `echanges`                                        | les vivants publient leurs températures         |
| `debat`       | commun + `tours`                                           | les vivants débattent, chacun son tour          |
| `vote`        | commun                                                     | chaque vivant vote                              |
| `verdict`     | commun + `elimine` (id ou `null`)                          | pause après le verdict                          |
| `fini`        | `partie`, `gagnant`                                        | résultat publié                                 |
| `arret`       |                                                            | le maître du jeu n'est pas lancé                |

Les champs communs aux phases de jeu sont `partie`, `manche`, `manches_max`, `joueurs` (tous les participants, éliminés compris), `vivants`, `elimines` (`[{"id": "rpi2", "manche": 1}]`) et `fin`. `fin` est l'horodatage Unix (secondes) auquel la phase se termine au plus tard, ou `null`.

```json
{"etat": "debat", "partie": 1761200000, "manche": 2, "manches_max": 4, "joueurs": ["rpi1", "rpi2", "rpi3", "rpi4", "rpi5"],
 "vivants": ["rpi1", "rpi3", "rpi4", "rpi5"], "elimines": [{"id": "rpi2", "manche": 1}], "tours": 2, "fin": null}
```

### `iot/role/<id>` : rôle secret (maître → un joueur)

Il est envoyé une seule fois, au début de la partie.

```json
{"role": "normal" | "espion", "partie": 1761200000}
```

Personne d'autre ne s'y abonne. **L'interface ne le lit jamais** : l'espion n'est révélé que par le résultat.

### `iot/capteurs/<id>/temperature` : mesure (vivant → tous)

Ce topic est imposé par le sujet.

```json
{"id": "rpi1", "ville": "Annecy", "temperature": 12.4, "echange": 3, "manche": 1, "partie": 1761200000, "ts": 1761200015}
```

- **Joueur normal** : la température réelle de sa ville (API Open-Meteo). Les villes sont voisines les unes des autres (sujet : « une ville adjacente aux machines du système »).
- **Espion** : la moyenne des dernières valeurs des autres, décalée aléatoirement de 5 à 10 % vers le haut ou le bas (au moins 0,3 °C, pour rester détectable près de 0 °C).

### `iot/partie/parole` : tour de parole (maître → tous)

```json
{"partie": 1761200000, "manche": 2, "joueur": "rpi3", "tour": 1, "tours": 2, "rang": 2, "sur": 4, "delai": 90, "fin": 1761200190}
```

Seul `joueur` doit parler. Il a `delai` secondes ; ensuite, la parole passe au suivant. L'interface affiche « … » au-dessus de lui tant qu'il réfléchit.

### `iot/chat/<id>` : prise de parole (joueur → tous)

```json
{"text": "Mimi, ta température saute de deux degrés à chaque mesure, explique-toi.", "partie": 1761200000, "manche": 2, "tour": 1}
```

Pendant le débat, un joueur ne publie ici que lorsqu'il a la parole. Chaque joueur s'abonne à `iot/chat/+` pour entendre les autres.

### `iot/votes/<id>` : vote (vivant → tous)

```json
{"votant": "rpi1", "suspect": "rpi3", "raison": "Ses valeurs changent à chaque mesure.", "calcul": "rpi3",
 "strategie": "llm", "partie": 1761200000, "manche": 2}
```

- `suspect` : l'id d'un autre joueur vivant. C'est le vote qui compte.
- `calcul` : le suspect désigné par la méthode sans LLM (écart à la médiane + instabilité), même quand le joueur a voté avec son LLM.
  Le maître peut ainsi répondre à la question de l'extension du TP : *l'agent est-il plus ou moins efficace que la méthode de départ ?*

### `iot/partie/verdict` : verdict de la manche (maître → tous)

```json
{"partie": 1761200000, "manche": 1, "votes": {"rpi1": "rpi2", "rpi3": "rpi2", "rpi2": "rpi1", "rpi4": "rpi2"},
 "compte": {"rpi2": 3, "rpi1": 1}, "elimine": "rpi2", "egalite": false, "etait_espion": false}
```

`elimine` vaut `null` en cas d'égalité ou sans vote (`etait_espion` vaut alors `null`). Les joueurs s'en servent pour leur mémoire, et l'interface pour l'animation d'élimination.

### `iot/partie/resultat` : fin de partie (maître → tous, retain)

Les champs du TP (`espion`, `designe`, `votes`, `gagnant`) sont conservés. `votes` et `designe` sont ceux de la dernière manche.

```json
{"partie": 1761200000, "espion": "rpi3", "designe": "rpi3", "votes": {"rpi1": "rpi3", "rpi4": "rpi3", "rpi3": "rpi1"},
 "gagnant": "capteurs" | "espion" | null, "raison": "l'espion a été éliminé", "manches": 2,
 "elimines": [{"id": "rpi2", "manche": 1}, {"id": "rpi3", "manche": 2}]}
```

### `iot/partie/stats` : bilan cumulé (maître → tous, retain)

Le maître garde ces chiffres d'une partie à l'autre dans `maitre_du_jeu/stats.json`.

```json
{"parties": 7, "victoires": {"capteurs": 4, "espion": 3},
 "votes": {"llm":    {"total": 40, "justes": 22},
           "calcul": {"total": 52, "justes": 35}}}
```

- `votes.llm` : les votes des joueurs en stratégie `llm` (le choix du LLM).
- `votes.calcul` : le champ `calcul` de **tous** les votes, c'est-à-dire ce qu'aurait voté la méthode sans LLM.
- Un vote est **juste** s'il désigne l'espion.
