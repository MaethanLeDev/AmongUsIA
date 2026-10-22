# Joueur (script générique pour chaque Raspberry Pi)

Le même code tourne sur tous les RPi. Seul `config.json` change.

```bash
cp config.example.json config.json   # puis régler id, ville, broker
pip install paho-mqtt requests
python3 joueur.py
```

## Ce que fait le joueur

1. Il se connecte au broker et annonce sa présence (`iot/joueurs/<id>`).
2. Il attend son rôle (`iot/role/<id>`).
3. Toutes les 5 s, il publie une température (`iot/capteurs/<id>/temperature`) :
   - si son rôle est `normal`, il convertit sa ville en coordonnées avec l'API de géocodage d'Open-Meteo, puis récupère la température actuelle ;
   - si son rôle est `espion`, il publie la moyenne des autres valeurs, modifiée de ±10 %.
4. Il écoute les températures des autres joueurs et garde l'historique.
5. Après 5 manches, il applique sa stratégie de détection et publie son vote (`iot/votes/<id>`).

La `strategie` est configurable (ex : `ecart_mediane`, ou `llm` pour l'extension Ollama).
