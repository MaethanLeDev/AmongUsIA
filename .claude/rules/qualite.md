# Qualité de code (tous les fichiers)

- Changements **petits et ciblés** : ne pas reformater ni renommer du code voisin sans rapport avec la demande (5 personnes travaillent sur le dépôt, les gros diffs créent des conflits).
- Avant d'écrire, lire le code existant du module et réutiliser ses fonctions (`publier`, `log`, `lire_json`, `connecter`…) plutôt que d'en recréer.
- Une fonction = une responsabilité ; des noms français explicites ; constantes nommées et commentées plutôt que des nombres magiques.
- Commentaires : le *pourquoi*, pas le *quoi*. Garder les docstrings de tête de fichier à jour (usage, rôle).
- Pas de code mort, de `print` de débogage ni de TODO laissés dans un commit.
- Aucun secret, mot de passe ou IP personnelle en dur ; les réglages propres à une machine vont dans `config.json` (ignoré par git) ou en option de ligne de commande.
- Toute nouvelle option : valeur par défaut sensée, documentée dans le README du module.
- Bibliothèques externes (paho-mqtt, requests, Ollama, Three.js, Open-Meteo, Mosquitto, Docker Compose) : ne pas se fier à sa mémoire pour une API récente, utiliser Context7 pour la doc à jour.
