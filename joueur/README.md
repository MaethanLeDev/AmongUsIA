# Joueur (script générique pour chaque Raspberry Pi)

Le même code tourne sur tous les RPi. Seul `config.json` change.

```bash
uv sync                                         # une fois, à la racine du dépôt
cp joueur/config.example.json joueur/config.json # puis régler id, ville, broker
uv run joueur/joueur.py                          # ou : uv run joueur/joueur.py autre_config.json
```

## Configuration

| Champ        | Rôle                                                                         |
|--------------|------------------------------------------------------------------------------|
| `id`         | identifiant unique du joueur (`rpi1`, `rpi2`…)                               |
| `ville`      | ville dont on publie la température (n'importe quel nom connu d'Open-Meteo) |
| `broker`     | adresse et port du broker MQTT                                              |
| `strategie`  | `ecart` (calcul) ou `llm` (avis du LLM Ollama, extension du TP)             |
| `ollama`     | URL et modèle Ollama, utilisés seulement avec `"strategie": "llm"`           |
| `interface`  | facultatif : `nom`, `arch`, `api` affichés par l'interface de Valérian      |

## Ce que fait le joueur

1. Il se connecte au broker et annonce sa présence (`iot/joueurs/<id>`). Si le Pi plante, le broker annonce son départ à sa place (*Last Will*).
2. Il attend son rôle (`iot/role/<id>`).
3. Toutes les 5 s, pendant 5 manches, il publie une température (`iot/capteurs/<id>/temperature`) :
   - s'il est `normal` : la température réelle de sa ville (Open-Meteo) ;
   - s'il est `espion` : la moyenne des dernières valeurs des autres, décalée de 5 à 10 % vers le haut ou le bas.
4. Il enregistre les températures des autres joueurs.
5. Il vote (`iot/votes/<id>`) et annonce son soupçon à la table (`iot/chat/<id>`).

## Stratégies

- **`ecart`** : pour chaque joueur, il additionne son écart moyen à la médiane des autres et l'instabilité de ses valeurs. Une vraie température ne bouge presque pas en 25 s, alors que celle de l'espion change à chaque manche. Le score le plus haut désigne le suspect.
- **`llm`** : il envoie le tableau des mesures au LLM local et lui demande quel capteur est l'espion. Si la réponse ne contient aucun id valide, il revient à `ecart`.
