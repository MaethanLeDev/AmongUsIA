# AmongUsIA — Jeu distribué de l'espion (MQTT)

TP R5.A.05 — IUT d'Annecy. N Raspberry Pi publient des températures via MQTT.
L'un d'eux est un espion qui publie de fausses valeurs. Les joueurs votent pour le démasquer.

## Organisation du dépôt

| Dossier          | Responsable | Contenu                                                     |
|------------------|-------------|-------------------------------------------------------------|
| `broker/`        | Niels       | Configuration Mosquitto (broker MQTT)                       |
| `maitre_du_jeu/` | Maethan     | Serveur de jeu : inscription, tirage de l'espion, dépouillement des votes |
| `joueur/`        | Maethan     | Script générique lancé sur chaque Raspberry Pi              |
| `interface/`     | Valérian    | Interface graphique (abonnée au broker, en lecture seule)   |
| `docs/`          | tous        | **Protocole MQTT** : le contrat commun entre les modules    |

> Avant de coder, lisez [docs/protocole.md](docs/protocole.md).
> Tous les modules ne communiquent **que** par MQTT, avec les topics et les formats JSON définis là-bas.
> Si vous voulez changer un topic ou un champ, modifiez d'abord ce fichier et prévenez les autres.

## Architecture

```
            ┌──────────────────────┐
            │   Broker Mosquitto   │  (broker/)
            └──────────┬───────────┘
     ┌─────────────────┼──────────────────┬───────────────┐
     │                 │                  │               │
┌────┴─────┐     ┌─────┴────┐       ┌─────┴────┐    ┌─────┴─────┐
│ Joueur 1 │ ... │ Joueur N │       │ Maître   │    │ Interface │
│ (RPi)    │     │ (RPi)    │       │ du jeu   │    │ graphique │
└──────────┘     └──────────┘       └──────────┘    └───────────┘
```

## Lancer une partie

Les scripts Python utilisent [uv](https://docs.astral.sh/uv/) : `uv sync` à la racine installe les dépendances.

1. Démarrer le broker (`broker/`).
2. Sur chaque RPi : `cp joueur/config.example.json joueur/config.json`, régler `id`, `ville` et `broker`, puis `uv run joueur/joueur.py`.
3. Lancer `uv run maitre_du_jeu/maitre.py --broker <ip_broker>` et appuyer sur Entrée quand tous les joueurs sont là.
4. (Optionnel) Lancer l'interface (`interface/`).
