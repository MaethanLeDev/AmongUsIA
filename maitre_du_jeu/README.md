# Maître du jeu : l'arbitre

```bash
uv sync                               # une fois, à la racine du dépôt
uv run maitre_du_jeu/maitre.py        # broker amongus.local, puis 10.109.150.215
uv run maitre_du_jeu/maitre.py --tp   # le jeu de base du sujet : une manche, sans débat, majorité stricte
```

Il tourne sur n'importe quelle machine qui joint le broker (le Pi du broker convient très bien). Il enchaîne les parties tout seul : Ctrl+C pour l'arrêter.
**Un seul maître à la fois** par broker : deux maîtres ont le même identifiant MQTT et se déconnectent l'un l'autre en boucle (« Connecté au broker » qui se répète).

## Options

| Option             | Défaut                           | Rôle                                                                     |
|--------------------|----------------------------------|--------------------------------------------------------------------------|
| `--broker`         | `amongus.local,10.109.150.215`   | broker(s), essayés dans l'ordre                                          |
| `--port`           | `1883`                           |                                                                          |
| `--min-joueurs`    | `3`                              |                                                                          |
| `--max-joueurs`    | `12`                             | le nombre de sièges de l'interface ; les suivants attendent              |
| `--auto`           | `30`                             | lance la partie N s après la dernière arrivée, dès qu'il y a assez de joueurs (`0` : Entrée seulement) |
| `--echanges`       | `5`                              | températures par manche (sujet : 5)                                       |
| `--tours`          | `2`                              | tours de parole par manche (`0` : pas de débat)                          |
| `--delai-parole`   | `90`                             | secondes max pour une prise de parole (un LLM est lent sur un Pi)        |
| `--pause`          | `2`                              | secondes entre deux prises de parole, plus le temps de lecture           |
| `--delai-vote`     | `120`                            |                                                                          |
| `--pause-verdict`  | `12`                             | après un verdict : animation d'élimination, notes des IA                 |
| `--pause-fin`      | `20`                             | affichage du résultat avant la partie suivante                           |
| `--manches-max`    | nombre de joueurs − 1            |                                                                          |
| `--majorite`       |                                  | éliminer seulement à la majorité stricte des vivants (règle du sujet)    |
| `--stats`          | `maitre_du_jeu/stats.json`       | fichier où cumuler les statistiques                                      |

## Ce que fait le maître

1. Il publie `iot/partie/etat = inscription` et suit les présences (`iot/joueurs/+`). Si le maître plante, son *Last Will* publie `{"etat": "arret"}`.
2. Il tire l'espion et envoie à chacun son rôle (`iot/role/<id>`). Un joueur qui redémarre en pleine partie reçoit à nouveau le sien.
3. À chaque manche, il publie la phase (`mesures`, `debat`, `vote`, `verdict`), donne la parole à chacun son tour (`iot/partie/parole`) et passe au suivant dès qu'il a répondu, ou au bout du délai.
4. Il ignore les votes invalides : en double, contre soi-même, contre un éliminé, ou d'une manche précédente. Il publie le verdict (`iot/partie/verdict`) : le plus désigné est éliminé, personne en cas d'égalité.
5. En fin de partie, il publie le résultat (`iot/partie/resultat`) et les statistiques (`iot/partie/stats`).

Une partie s'arrête aussi si l'espion se déconnecte (les capteurs gagnent par abandon), ou s'il reste moins de deux joueurs en ligne (partie annulée).

## Statistiques : le LLM contre le calcul

Chaque vote contient le suspect choisi (`suspect`) et celui de la méthode de calcul (`calcul`). Le maître compte, partie après partie, combien de votes désignent vraiment l'espion :
- `llm` : les votes des joueurs en stratégie `llm` ;
- `calcul` : ce qu'aurait voté la méthode sans LLM, pour **tous** les votes.

C'est la réponse chiffrée à la question de l'extension du TP. Elle s'affiche dans la console, dans `stats.json` et dans l'interface.
