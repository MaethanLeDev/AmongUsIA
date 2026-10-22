# Interface graphique — Valérian

Mettez ici l'interface dérivée de votre jeu de l'espace.

Elle s'abonne au broker en **lecture seule** (`iot/#`) et affiche :

- les joueurs connectés (`iot/joueurs/+`)
- les températures publiées à chaque manche (`iot/capteurs/+/temperature`)
- l'état de la partie (`iot/partie/etat`)
- les votes et le résultat (`iot/votes/+`, `iot/partie/resultat`)

Elle ne doit **pas** s'abonner à `iot/role/+` pendant la partie, sinon elle révèle l'espion, sauf en mode « spectateur omniscient ».

Protocole : [../docs/protocole.md](../docs/protocole.md)
