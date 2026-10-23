---
name: verifier
description: Vérifie les changements en cours d'AmongUsIA avant un commit : syntaxe Python et Node, cohérence avec docs/protocole.md, règles du projet, puis simulation rapide si le comportement du jeu a changé.
---

# Vérifier avant de commiter

1. **Ce qui a changé** : `git status` et `git diff` (plus `git diff --cached`). Lister les modules touchés.
2. **Syntaxe** :
   - `uv run python -m py_compile joueur/*.py maitre_du_jeu/*.py outils/*.py`
   - `node --check` sur chaque `.js` modifié de `interface/` (hors `public/vendor/`)
   - `config.example.json` et tout JSON modifié doivent rester valides.
3. **Contrat** : si un message MQTT publié ou lu a changé, confier la relecture à l'agent `gardien-protocole` (il compare le code à `docs/protocole.md`).
4. **Règles du projet** (CLAUDE.md et `.claude/rules/`) : identifiants et commentaires en français ; aucune dépendance ajoutée sans raison (`pyproject.toml`, aucun `package.json` dans `interface/`) ; `public/vendor/` intact ; l'interface ne lit pas `iot/role/+` ; gardes contre les messages en double ou d'une autre partie conservées ; README du module à jour ; aucun `innerHTML` avec une donnée reçue ; tout appel `requests` a un `timeout` ; rien de bloquant dans un callback paho.
5. **Comportement** : si joueur, maître ou outils ont changé, lancer `/simulation` (3 joueurs, `--rapide`) et vérifier qu'une partie va jusqu'au résultat sans `Traceback`.
6. **Bilan** court : OK / problèmes trouvés (fichier:ligne), puis un message de commit proposé au format `Module : description` en français. Ne pas commiter sans accord.
