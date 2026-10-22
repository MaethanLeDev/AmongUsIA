# Protocole MQTT

Tous les messages sont en **JSON UTF-8**. `<id>` est l'identifiant d'un joueur (ex : `rpi1`) : il est unique et ne contient ni espace ni `/`.

Le broker est `amongus.local:1883` (voir `broker/`). Une partie accepte jusqu'à **8 joueurs** : c'est le nombre de sièges de l'interface.

## Déroulement d'une partie

Le maître du jeu est l'**arbitre** : c'est lui qui fait avancer les phases et distribue la parole.
Un joueur qui arrive en cours de partie attend la suivante.

```
1. INSCRIPTION  joueurs → iot/joueurs/<id>                 présence (retain)
                maître  → iot/partie/etat                   {"etat": "inscription"}

2. MESURES      maître  → iot/partie/etat                   {"etat": "en_cours", ...}
                maître  → iot/role/<id>                     un message secret par joueur
                joueurs → iot/capteurs/<id>/temperature     toutes les 5 s, 5 fois

3. DÉBAT        maître  → iot/partie/etat                   {"etat": "debat", ...}
                pour chaque tour, pour chaque joueur, chacun son tour :
                  maître → iot/partie/parole                {"joueur": "rpi2", ...}
                  rpi2   → iot/chat/rpi2                    sa prise de parole
                  (le maître passe au suivant dès qu'il reçoit le message, ou au bout du délai)

4. VOTE         maître  → iot/partie/etat                   {"etat": "vote", ...}
                joueurs → iot/votes/<id>

5. RÉSULTAT     maître  → iot/partie/resultat
                maître  → iot/partie/etat                   {"etat": "fini"}
```

## Topics

### `iot/joueurs/<id>` — présence (joueur → tous, retain)

Le joueur publie ce message à sa connexion. Il configure aussi un *Last Will* `{"en_ligne": false}`, que le broker publie à sa place s'il se déconnecte.

```json
{"id": "rpi1", "ville": "Annecy", "en_ligne": true, "nom": "Sherlock", "arch": "stratege", "modele": "qwen3:0.6b"}
```

Champs facultatifs, utilisés par l'interface :
- `nom` : nom affiché (16 caractères maximum) ;
- `arch` : apparence du personnage (`stratege`, `vengeur`, `sourire`, `reine`, `ombre`, `prodige`) ;
- `modele` : le modèle Ollama du joueur, affiché à titre informatif.

### `iot/partie/etat` — phase de la partie (maître → tous, retain)

| `etat`        | Champs en plus                                        | Signification                                |
|---------------|-------------------------------------------------------|----------------------------------------------|
| `inscription` |                                                       | les joueurs peuvent rejoindre                |
| `en_cours`    | `joueurs` (liste d'ids), `manches`                    | rôles distribués, échange des températures   |
| `debat`       | `joueurs`, `tours`                                    | les IA débattent, chacune son tour           |
| `vote`        | `joueurs`, `delai` (s)                                | chaque IA vote                               |
| `fini`        |                                                       | résultat publié                              |

```json
{"etat": "debat", "joueurs": ["rpi1", "rpi2", "rpi3", "rpi4"], "tours": 2}
```

### `iot/role/<id>` — rôle secret (maître → un joueur)

```json
{"role": "normal" | "espion"}
```

Personne d'autre ne s'y abonne. L'interface ne le lit jamais : l'espion n'est révélé que par le résultat.

### `iot/capteurs/<id>/temperature` — mesure (joueur → tous)

```json
{"id": "rpi1", "ville": "Annecy", "temperature": 12.4, "manche": 3, "ts": 1761141600}
```

- **Joueur normal** : température réelle de sa ville (API Open-Meteo).
- **Espion** : moyenne des dernières valeurs des autres, décalée de 5 à 10 % vers le haut ou le bas.

### `iot/partie/parole` — tour de parole (maître → tous)

```json
{"joueur": "rpi2", "tour": 1, "tours": 2, "rang": 3, "sur": 4, "delai": 90}
```

`rang`/`sur` donne la position dans le tour (3ᵉ à parler sur 4). Seul `joueur` doit parler. Il a `delai` secondes avant que la parole passe au suivant.
L'interface peut s'en servir pour montrer qui réfléchit (par exemple un indicateur « … » au-dessus du personnage).

### `iot/chat/<id>` — prise de parole (joueur → tous)

```json
{"text": "Rpi3, ta température saute de 2 degrés à chaque mesure, explique-toi.", "tour": 1}
```

Pendant le débat, un joueur ne publie ici que lorsqu'il a la parole. Chaque joueur s'abonne à `iot/chat/+` pour entendre les autres.
Le champ facultatif `to` (id d'un joueur) indique un chuchotement, dans le salon de l'interface uniquement.

### `iot/votes/<id>` — vote (joueur → tous)

`suspect` doit être l'id d'un autre joueur.

```json
{"votant": "rpi1", "suspect": "rpi3", "raison": "Ses valeurs changent à chaque manche alors que la météo est stable."}
```

### `iot/partie/resultat` — résultat (maître → tous)

```json
{"espion": "rpi3", "designe": "rpi3", "votes": {"rpi1": "rpi3", "rpi2": "rpi3", "rpi3": "rpi1", "rpi4": "rpi3"}, "gagnant": "capteurs" | "espion"}
```

Les capteurs gagnent si **plus de la moitié des joueurs** désigne l'espion.

---

## Topics propres à l'interface

### `iot/table/chat` — chat de la table (interface → tous)

```json
{"seq": 7, "kind": "pub", "from": 2, "name": "rpi1", "text": "…", "to": 0, "fromAgent": "rpi1"}
```

`kind` vaut `pub`, `whisper` ou `rumor`. Ce topic sert au mode « La table » de l'interface. Le jeu de l'espion n'en a pas besoin : les joueurs s'écoutent directement sur `iot/chat/+`.
