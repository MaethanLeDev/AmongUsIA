# Maître du jeu

```bash
pip install paho-mqtt
python3 maitre.py --broker <ip_broker> --min-joueurs 3
```

## Ce que fait le maître du jeu

1. Il publie `iot/partie/etat = inscription` et écoute `iot/joueurs/+` pour connaître les joueurs présents.
2. Quand on lance la partie (touche Entrée ou délai écoulé), il tire un espion au hasard parmi les joueurs.
3. Il envoie à chaque joueur son rôle (`iot/role/<id>`).
4. Il attend les votes (`iot/votes/+`) de tous les joueurs, avec un délai maximum.
5. Il compte les votes, publie le résultat (`iot/partie/resultat`), puis publie `iot/partie/etat = fini`.
