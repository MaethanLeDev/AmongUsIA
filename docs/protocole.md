# Protocole MQTT

Tous les messages sont en **JSON UTF-8**. `<id>` est l'identifiant d'un joueur (ex : `rpi1`) : il est unique et ne contient ni espace ni `/`.

## Déroulement d'une partie

```
1. INSCRIPTION  joueurs  → iot/joueurs/<id>               (présence)
2. DÉBUT        maître   → iot/partie/etat                 {"etat": "en_cours"}
                maître   → iot/role/<id>                   (un message par joueur)
3. MANCHES      joueurs  → iot/capteurs/<id>/temperature   (toutes les 5 s, 5 fois)
4. VOTE         joueurs  → iot/votes/<id>
5. RÉSULTAT     maître   → iot/partie/resultat
                maître   → iot/partie/etat                 {"etat": "fini"}
```

## Topics

### `iot/joueurs/<id>` — présence (joueur → maître)

Le joueur publie ce message à sa connexion, avec `retain=true`. Il configure aussi un *Last Will* avec `{"en_ligne": false}`, envoyé automatiquement par le broker si le joueur se déconnecte.
Le maître découvre ainsi les joueurs sans liste codée en dur.

```json
{"id": "rpi1", "ville": "Annecy", "en_ligne": true}
```

### `iot/partie/etat` — état de la partie (maître → tous, retain)

```json
{"etat": "inscription" | "en_cours" | "vote" | "fini", "joueurs": ["rpi1", "rpi2", "rpi3", "rpi4"], "manches": 5}
```

### `iot/role/<id>` — rôle secret (maître → un joueur)

Chaque joueur reçoit son rôle, pas seulement l'espion.

```json
{"role": "normal" | "espion"}
```

### `iot/capteurs/<id>/temperature` — mesure (joueur → tous)

```json
{"id": "rpi1", "ville": "Annecy", "temperature": 12.4, "manche": 3, "ts": 1761141600}
```

- **Joueur normal** : température réelle de sa ville, via l'API Open-Meteo.
- **Espion** : moyenne des valeurs reçues des autres joueurs, modifiée aléatoirement de ±10 %.

### `iot/votes/<id>` — vote (joueur → maître)

Le joueur l'envoie après 5 manches. `suspect` doit être l'id d'un autre joueur.

```json
{"votant": "rpi1", "suspect": "rpi3", "raison": "écart de +2.1 °C par rapport à la médiane"}
```

### `iot/partie/resultat` — résultat (maître → tous)

```json
{"espion": "rpi3", "designe": "rpi3", "votes": {"rpi1": "rpi3", "rpi2": "rpi3", "rpi3": "rpi1", "rpi4": "rpi3"}, "gagnant": "capteurs" | "espion"}
```

Les capteurs gagnent si la **majorité stricte** des votes désigne l'espion.
