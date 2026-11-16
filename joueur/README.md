# Joueur : le programme de chaque Raspberry Pi

Le même code tourne sur toutes les machines. Seul `config.json` change : chacun y règle sa ville, son modèle, la personnalité de son IA et son apparence à la table.

```bash
uv run joueur/joueur.py                          # ou : uv run joueur/joueur.py autre_config.json
```

Au premier lancement (`installation.py`) :
- s'il n'y a pas de `config.json`, trois questions (nom de l'IA, ville, caractère ; Entrée garde la proposition) l'écrivent. L'`id` vient du nom, l'apparence est tirée au sort. Lancé sans terminal (service systemd), tout est tiré au sort ;
- si Ollama est installé mais ne répond pas, il lance `ollama serve` ;
- si le modèle n'est pas installé, il le télécharge (`/api/pull`, comme `ollama pull`), avec la progression.

Seul Ollama lui-même s'installe à la main (`curl -fsSL https://ollama.com/install.sh | sh` sur un Pi). Sans lui, le joueur démarre quand même et vote par calcul.

## Configuration

| Champ          | Obligatoire | Rôle                                                                                             |
|----------------|:-----------:|--------------------------------------------------------------------------------------------------|
| `id`           | oui         | identifiant unique (`rpi1`, `niels`…), sans espace, `/`, `+` ni `#`                              |
| `ville`        | oui         | ville dont on publie la température. Prenez des villes **voisines** les unes des autres (sujet) : Annecy, Seynod, Cran-Gevrier, Sévrier… |
| `coordonnees`  |             | `[latitude, longitude]` : évite le géocodage (ville homonyme, pas de DNS)                         |
| `broker`       |             | `{"hote": "amongus.local,10.109.150.215", "port": 1883}` : les hôtes sont essayés dans l'ordre    |
| `ollama`       |             | `{"url": "http://127.0.0.1:11434", "modele": "qwen3:0.6b"}`                                      |
| `gemini`       |             | `{"cle_api": "ta clé", "modele": "gemini-3.8-flash"}` : l'IA parle avec Gemini au lieu d'Ollama. Clé vide ou bloc absent : Ollama seul. Voir « Gemini » plus bas |
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

## Gemini (optionnel)

Avec une clé API Google, l'IA débat avec Gemini : ses répliques sont bien meilleures que celles d'un petit modèle local.

```json
"gemini": {"cle_api": "ta clé", "modele": "gemini-3.8-flash"}
```

- **Sans clé** (champ vide ou bloc absent) : Ollama seul, comme avant. Le nom du modèle change chez Google : vérifiez celui-ci dans leur documentation (les anciens `gemini-2.5-*` sont dépréciés).
- **La clé reste dans `config.json`**, qui est ignoré par git : ne la commitez ni ne la partagez. Elle part dans un en-tête HTTP vers Google, jamais dans une URL, un journal, la présence MQTT ni `GET /agent`.
- **Au lancement**, le joueur vérifie la clé et le modèle. Si Google les refuse, il l'écrit dans le terminal et continue avec Ollama.
- **Pendant la partie**, si Gemini ne répond pas (coupure, quota dépassé, réponse bloquée) ou met plus de 30 s, la même demande part à Ollama : l'IA ne perd pas son tour. Ollama doit donc rester installé.
- **Le vote** : `"strategie": "ecart"` garde le vote par calcul (le plus fiable) et laisse Gemini débattre. Avec `llm`, Gemini vote aussi, et le calcul reste le repli si sa réponse est inexploitable. `"memoire": "resume"` donne de bonnes notes entre les manches avec Gemini.
- L'interface et `GET /agent` annoncent le modèle Gemini ; `GET /health` garde son champ `ollama`, qui reste celui du repli.

## Mémoire entre les manches

Au début de chaque manche, l'IA relit ce qui s'est passé avant :
- **`faits`** (toujours) : qui a été éliminé, avec combien de votes, s'il était l'espion, qui a voté contre qui, et la dernière phrase de chacun. Ces faits sont calculés sans LLM, donc toujours justes.
- **`resume`** (en plus) : pendant la pause du verdict, le LLM écrit deux phrases de notes personnelles (« je me méfie de… »). Chaque IA se souvient alors à sa façon. Un petit modèle peut se tromper, c'est pourquoi les faits restent à côté.

## API de l'agent (TP « RPi & Ollama »)

Lancée avec le joueur, sur le port `api.port` (5000 par défaut). Son URL est annoncée dans la présence (`"api"`).

| Route            | Corps                                                    | Réponse                                                  |
|------------------|----------------------------------------------------------|----------------------------------------------------------|
| `POST /message`  | `{"message": "Salut !", "de": "rpi2"}`                   | `{"reponse": "..."}`. L'agent se souvient de toute la conversation avec chaque interlocuteur (`de`, sinon l'IP). |
| `GET /health`    |                                                          | `{"status": "ok", "broker": true, "ollama": true, "llm": "ok"}` (`llm` : état du LLM, `null` avant le premier essai) |
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
