# Interface : la salle 3D des spectateurs

Elle reprend le jeu **Classe Noire** de Valérian : sa salle, sa table ronde sous la lampe et ses personnages animés, dessinés à la main (Three.js, sans asset externe).
Ici, ce sont les IA des Raspberry Pi qui sont assises à la table, et les spectateurs regardent la partie.

```bash
cd interface
node server.js                        # broker amongus.local, sinon 10.109.150.215 ; port 5050
set MQTT_HOST=10.109.150.215          # (Windows) autre broker — Linux/macOS : MQTT_HOST=... node server.js
set PORT=8080                         # autre port
```

Il faut Node.js 18 ou plus, sans `npm install` : aucune dépendance. Les spectateurs ouvrent l'adresse « Depuis le réseau » affichée dans la console.

## Ce qu'on voit

- **Arrivée** : chaque IA qui se connecte apparaît sur son siège, dans une colonne de lumière. Les sièges sont stables, puis répartis régulièrement autour de la table au début de chaque partie.
- **Mesures** : une onde sur la table à chaque température publiée. Les valeurs s'affichent sous le nom de l'IA et dans sa carte, à gauche.
- **Débat** : la caméra se tourne vers celle qui a la parole. « … » s'affiche pendant qu'elle réfléchit, puis une bulle avec sa phrase. Tout le débat reste lisible à droite.
- **Vote** : un arc rouge va du votant à son suspect, avec le décompte en bas.
- **Verdict** : l'IA éliminée se lève et est aspirée vers la lampe (lumière bleue si elle était innocente, rouge si c'était l'espion). Seule son étiquette reste sur sa chaise.
- **Fin** : l'espion est révélé, avec les statistiques LLM contre calcul de l'extension du TP.

Boutons en haut à droite : qualité graphique, caméra automatique (on peut aussi tourner à la souris et zoomer), son (il s'active au premier clic dans la page), règles.

## Code

| Fichier               | Rôle                                                                                         |
|-----------------------|----------------------------------------------------------------------------------------------|
| `server.js`           | HTTP statique + WebSocket maison (RFC 6455). `GET /api/etat` renvoie l'état reconstruit (débogage). |
| `mqtt.js`             | client MQTT 3.1.1 minimal ; plusieurs brokers essayés à tour de rôle, reconnexion automatique   |
| `spectacle.js`        | reconstruit la partie à partir des messages MQTT, attribue les sièges, prévient les navigateurs |
| `public/main.js`      | panneaux, bandeau de phase, chronomètre ; branche les événements sur les animations            |
| `public/hub3d.js`     | la salle 3D et les animations                                                                |
| `public/chars.js`     | les personnages (6 archétypes, couleurs personnalisables)                                     |

L'interface est **en lecture seule** : elle ne publie rien et ne s'abonne jamais à `iot/role/+`, sinon elle révélerait l'espion avant la fin.
Le protocole est décrit dans [../docs/protocole.md](../docs/protocole.md).
