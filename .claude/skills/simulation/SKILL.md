---
name: simulation
description: Lance une partie complète d'AmongUsIA sur ce PC (broker de test, faux Ollama, joueurs, maître), lit les journaux et résume le déroulement. À utiliser pour tester un changement de comportement du jeu, reproduire un bug ou vérifier une partie de bout en bout.
argument-hint: "[nombre de joueurs] [options du maître après --, ex : -- --tp]"
---

# Simulation d'une partie

Arguments reçus : `$ARGUMENTS` (par défaut : 3 joueurs, `--rapide`).

1. **Nettoyer** d'abord les restes d'une simulation précédente (ports 1883, 11435, 5100-5111) :
   `uv run python .claude/skills/simulation/nettoyer.py`
2. **Lancer en arrière-plan** (outil Bash avec `run_in_background`) :
   `uv run outils/simulation.py --joueurs 3 --rapide` (adapter avec les arguments). Jamais `--broker` vers le vrai broker sans accord explicite.
   La sortie affiche le dossier temporaire des journaux (`amongusia-…`) : le noter.
3. **Attendre une partie** : avec 3 joueurs et `--rapide`, compter ~2 à 3 minutes (inscription 8 s, 5 mesures × 5 s, débat, vote, verdict, manche suivante). Surveiller la sortie du maître jusqu'au résultat (`gagnant`) ; ne pas dormir en boucle courte.
   Option : si l'interface tourne (`MQTT_HOST=localhost node server.js` dans `interface/`), `curl -s http://localhost:5050/api/etat` donne l'état reconstruit.
4. **Arrêter** la tâche de fond, puis relancer `nettoyer.py` (sous Windows, tuer le parent laisse les joueurs tourner).
5. **Analyser** : sortie du maître + `sim*.log` et `broker.log` / `ollama.log` du dossier temporaire. Chercher : `Traceback`, `Erreur`, votes ignorés, joueurs muets, phases qui expirent (délai atteint), messages d'une autre partie traités.
6. **Rendre compte** en quelques lignes : déroulement (manches, éliminés, gagnant), anomalies avec l'extrait de journal et le fichier/la fonction en cause. Ne rien corriger sans qu'on le demande, sauf si la simulation servait à vérifier un correctif en cours.
