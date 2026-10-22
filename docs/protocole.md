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

---

## Ajouts proposés par l'interface (à valider avec le groupe)

Ils ne changent aucun topic existant ; un joueur ou un maître qui les ignore continue de fonctionner.

### `iot/joueurs/<id>` : champs facultatifs

```json
{"id": "rpi1", "ville": "Annecy", "en_ligne": true, "nom": "Ayanokoji", "arch": "ombre", "api": "http://10.109.150.60:5000"}
```

- `nom` : nom affiché dans l'interface (16 caractères max) ; `arch` : apparence du personnage (`stratege`, `vengeur`, `sourire`, `reine`, `ombre`, `prodige`).
- `api` : URL d'un agent qui répond à `POST /message` ; l'interface l'appelle pour le faire parler (voir `interface/AGENTS.md`).

### `iot/chat/<id>` : un agent parle à la table (joueur → interface)

```json
{"text": "La température de rpi3 est bizarre", "to": "rpi2"}
```

`to` est facultatif : s'il est présent, le message est un chuchotement. Cela ne remplace pas le vote `iot/votes/<id>`.

### `iot/table/chat` : tout ce qui se dit à la table (interface → tous)

```json
{"seq": 7, "kind": "pub", "from": 2, "name": "rpi1", "text": "…", "to": 0, "fromAgent": "rpi1"}
```

`kind` vaut `pub`, `whisper` ou `rumor`. Les agents s'y abonnent pour entendre les autres joueurs.
