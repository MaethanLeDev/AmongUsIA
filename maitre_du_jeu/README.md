# Maître du jeu

```bash
uv sync    # une fois, à la racine du dépôt
uv run maitre_du_jeu/maitre.py --broker 10.109.150.215
```

| Option          | Défaut      | Rôle                                                  |
|-----------------|-------------|-------------------------------------------------------|
| `--broker`      | `localhost` | adresse du broker                                     |
| `--port`        | `1883`      |                                                       |
| `--min-joueurs` | `3`         | nombre minimum de joueurs pour lancer                 |
| `--manches`     | `5`         | nombre de manches annoncé aux joueurs                 |
| `--delai-vote`  | `60`        | secondes laissées pour voter après la dernière manche (le LLM est lent sur un Pi) |

## Ce que fait le maître du jeu

1. Il publie `iot/partie/etat = inscription` et écoute `iot/joueurs/+`. Les joueurs apparaissent au fur et à mesure.
2. Quand on appuie sur Entrée, il tire un espion au hasard parmi les joueurs en ligne.
3. Il envoie à chaque joueur son rôle (`iot/role/<id>`).
4. Il collecte les votes (`iot/votes/+`). Il ignore les votes en double, ceux contre soi-même et ceux qui désignent un joueur inconnu.
5. Il publie le résultat (`iot/partie/resultat`) : les capteurs gagnent si plus de la moitié des joueurs désigne l'espion. Il propose ensuite de rejouer.
