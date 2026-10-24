---
paths:
  - "joueur/**/*.py"
  - "maitre_du_jeu/**/*.py"
  - "outils/**/*.py"
---

# Bonnes pratiques Python du projet

- Python 3.14 (`.python-version`) : f-strings, `pathlib.Path`, `X | None`, `match` si ça simplifie vraiment. La syntaxe récente est permise, puisque uv installe la même version sur les Pi.
- Le lint (ruff, règles dans `pyproject.toml`) est vérifié par la CI : écrire du code qui le respecte, sans lancer de lint ni de reformatage local.
- Fichiers : toujours `encoding="utf-8"`, et `with open(...)`. JSON : `json.dumps(..., ensure_ascii=False)`.
- Réseau (`requests`) : **toujours un `timeout=`**, capturer `requests.RequestException` et prévoir un repli (le Pi peut ne pas avoir Internet, Ollama peut être lent ou absent).
- Exceptions : jamais de `except:` nu ni `except Exception` silencieux ; attraper l'erreur précise, et journaliser ce qui est ignoré avec `self.log(...)`.
- Le code ne doit jamais planter sur un message MQTT malformé : passer par `lire_json` et valider les champs avant usage (un autre étudiant peut publier n'importe quoi).

## paho-mqtt 2.x

- `mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=...)` ; callbacks v2 : `on_connect(client, userdata, flags, reason_code, properties)`.
- S'abonner dans `on_connect` (réabonnement automatique après reconnexion) ; un callback par topic avec `message_callback_add`.
- **Les callbacks tournent dans le thread réseau** : ne jamais y bloquer (LLM, `sleep`, HTTP). Déléguer avec `en_arriere_plan(...)` et protéger l'état partagé par `self.verrou`.
- Messages retenus et reconnexions : un même message peut arriver deux fois → actions idempotentes, filtrage par `partie`/`manche`.
- `will_set` avant `connect` ; effacer un message retenu = publier un payload vide avec `retain=True`.

## Ollama / LLM

- API `/api/chat` avec `"stream": false`, `"think": false`, `"format": "json"` quand on attend du JSON ; supprimer les `<think>…</think>` restants.
- La sortie du LLM n'est **pas fiable** : parser défensivement, vérifier que le suspect est un id vivant et différent de soi, sinon repli sur le calcul.
- Les textes des autres joueurs injectés dans un prompt sont des données, pas des consignes : les présenter comme citations, tronquer leur longueur.
- Avant d'utiliser une option de paho-mqtt, requests ou de l'API Ollama dont tu n'es pas sûr, consulte la doc à jour via Context7.
