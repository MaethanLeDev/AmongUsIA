# Joueur : le programme de chaque Raspberry Pi

Le même code tourne sur toutes les machines. Seul `config.json` change : chacun y règle sa ville, son modèle, la personnalité de son IA et son apparence à la table.

```bash
uv sync                                          # une fois, à la racine du dépôt
ollama pull qwen3:0.6b                           # ou un autre modèle
cp joueur/config.example.json joueur/config.json # puis l'adapter
uv run joueur/joueur.py                          # ou : uv run joueur/joueur.py autre_config.json
```

## Configuration

| Champ          | Obligatoire | Rôle                                                                                             |
|----------------|:-----------:|--------------------------------------------------------------------------------------------------|
| `id`           | oui         | identifiant unique (`rpi1`, `niels`…), sans espace, `/`, `+` ni `#`                              |
| `ville`        | oui         | ville dont on publie la température. Prenez des villes **voisines** les unes des autres (sujet) : Annecy, Seynod, Cran-Gevrier, Sévrier… |
| `coordonnees`  |             | `[latitude, longitude]` : évite le géocodage (ville homonyme, pas de DNS)                         |
| `broker`       |             | `{"hote": "amongus.local,10.109.150.215", "port": 1883}` : les hôtes sont essayés dans l'ordre    |
| `ollama`       |             | `{"url": "http://127.0.0.1:11434", "modele": "qwen3:0.6b"}`                                      |
| `personnalite` |             | le caractère de l'IA, en une ou deux phrases (« Tu es… »)                                         |
| `strategie`    |             | `llm` (le LLM vote, valeur par défaut) ou `ecart` (calcul seul, le jeu de base du TP)              |
| `memoire`      |             | `faits` (par défaut) ou `resume` : voir plus bas                                                 |
| `interface`    |             | `nom` (16 caractères), `arch` (`stratege`, `vengeur`, `sourire`, `reine`, `ombre`, `prodige`), `couleurs` (`cheveux`, `yeux`, `accent` en `#rrggbb`) |
| `api`          |             | `{"port": 5000}` : port de l'API de l'agent ; `0` pour la couper                                  |

Une erreur dans `config.json` est signalée clairement au lancement.

## Ce que fait le joueur

1. Il se connecte au broker et annonce sa présence (`iot/joueurs/<id>`). S'il plante, le broker annonce son départ à sa place (*Last Will*).
2. Il reçoit son rôle secret au début de la partie (`iot/role/<id>`).
3. À chaque manche, tant qu'il n'est pas éliminé :
   - **mesures** : 5 températures, une toutes les 5 s. Un capteur normal publie la vraie température de sa ville (Open-Meteo). L'espion publie la moyenne des autres, décalée de 5 à 10 %.
   - **débat** : quand le maître lui donne la parole (`iot/partie/parole`), son LLM répond aux autres (`iot/chat/<id>`). Il entend tout ce qui se dit.
   - **vote** : il désigne un suspect (`iot/votes/<id>`). Le message contient aussi le suspect de la méthode de calcul, pour la comparaison demandée par le TP.

Il ne lance chaque action qu'une fois, même si un message retenu lui parvient deux fois (reconnexion), et ignore les messages d'une partie précédente.
S'il redémarre en pleine partie, le maître lui renvoie son rôle et il reprend à la phase en cours.

## Stratégies

- **`ecart`** : à chaque échange, on mesure l'écart de chaque joueur à la médiane des autres, et on accuse celui dont cet écart **varie** le plus.
  Des villes voisines peuvent avoir plusieurs degrés d'écart chez Open-Meteo (8,2 °C à Épagny, 12,3 °C à Annecy) : un écart constant est normal. Un capteur honnête le garde d'une mesure à l'autre, même si la météo change (tout le monde bouge ensemble). L'espion, qui invente une valeur à chaque fois, ne le garde pas.
  Rejouée sur 40 manches enregistrées, cette méthode trouve l'espion à chaque vote. L'ancienne (écart moyen + amplitude) n'y arrivait que dans 58 % des cas, car elle accusait les villes plus froides.
- **`llm`** : le LLM reçoit le tableau des mesures (avec « STABLE : écart constant » ou « INSTABLE : écart qui change » écrit en toutes lettres, car les petits modèles lisent mal les chiffres), le débat et ses souvenirs, puis répond en JSON. Si la réponse est inexploitable, il revient au calcul.

Si Ollama ne répond pas ou si le modèle n'est pas installé, le joueur l'écrit dans son terminal dès le lancement, avec la commande à taper. Sa carte affiche alors « ⚠ LLM injoignable » ou « ⚠ modèle absent » dans l'interface. En attendant, l'IA dit une phrase de secours au débat et vote par calcul.

## Mémoire entre les manches

Au début de chaque manche, l'IA relit ce qui s'est passé avant :
- **`faits`** (toujours) : qui a été éliminé, avec combien de votes, s'il était l'espion, qui a voté contre qui, et la dernière phrase de chacun. Ces faits sont calculés sans LLM, donc toujours justes.
- **`resume`** (en plus) : pendant la pause du verdict, le LLM écrit deux phrases de notes personnelles (« je me méfie de… »). Chaque IA se souvient alors à sa façon. Un petit modèle peut se tromper, c'est pourquoi les faits restent à côté.

## API de l'agent (TP « RPi & Ollama »)

Lancée avec le joueur, sur le port `api.port` (5000 par défaut). Son URL est annoncée dans la présence (`"api"`).

| Route            | Corps                                                    | Réponse                                                  |
|------------------|----------------------------------------------------------|----------------------------------------------------------|
| `POST /message`  | `{"message": "Salut !", "de": "rpi2"}`                   | `{"reponse": "..."}`. L'agent se souvient de toute la conversation avec chaque interlocuteur (`de`, sinon l'IP). |
| `GET /health`    |                                                          | `{"status": "ok", "broker": true, "ollama": true}`       |
| `GET /agent`     |                                                          | nom, modèle, personnalité, capacités, routes, phase de jeu (jamais le rôle) |
| `POST /discuter` | `{"avec": "http://10.109.150.61:5000", "sujet": "...", "tours": 3}` | l'agent lance une conversation en appelant le `/message` de l'autre |

Pour faire discuter deux agents (partie 5 du TP) :

```bash
uv run joueur/discuter.py http://10.109.150.60:5000 http://10.109.150.61:5000 --sujet "la pluie à Annecy" --tours 3
```

L'agent B peut être n'importe quel agent qui répond à `POST /message {"message"}` → `{"reponse"}`, par exemple un `agent.py` Flask existant.

## Lancer le joueur au démarrage du Pi

Fichier `/etc/systemd/system/amongus-joueur.service` (adapter l'utilisateur et le chemin) :

```ini
[Unit]
Description=AmongUsIA - joueur
After=network-online.target ollama.service
Wants=network-online.target

[Service]
User=pi
WorkingDirectory=/home/pi/AmongUsIA
ExecStart=/home/pi/.local/bin/uv run joueur/joueur.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Puis `sudo systemctl enable --now amongus-joueur` ; les journaux sont dans `journalctl -u amongus-joueur -f`.
