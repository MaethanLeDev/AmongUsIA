---
name: changer-protocole
description: Procédure pour ajouter ou modifier un topic, un champ, un retain ou un Last Will du protocole MQTT d'AmongUsIA, en gardant tous les modules cohérents. À utiliser dès qu'un changement touche le format d'un message échangé entre joueur, maître du jeu et interface.
argument-hint: "[description du changement]"
---

# Changer le protocole MQTT

Changement demandé : `$ARGUMENTS`

`docs/protocole.md` est le contrat entre 5 personnes : un message changé d'un seul côté casse la partie des autres.

1. **Évaluer l'impact** avant d'écrire : quel topic, qui publie, qui s'abonne. Chercher le topic et le champ partout (`joueur/`, `maitre_du_jeu/`, `interface/spectacle.js`, `interface/public/main.js`, `outils/`). Signaler tout de suite si le changement touche un élément imposé par le sujet (`iot/capteurs/<id>/temperature`, `iot/role/<id>`, `iot/votes/<id>`, champs TP de `iot/partie/resultat`) ou s'il casse la compatibilité avec un joueur qui n'a pas encore mis à jour son Pi : préférer un champ **facultatif** avec une valeur par défaut.
2. **Modifier `docs/protocole.md` en premier** : tableau, exemple JSON, règle. Garder le style (français, exemples réalistes).
3. **Répercuter** dans l'ordre : publieur, puis chaque abonné :
   - `maitre_du_jeu/maitre.py` (publication, validation des messages reçus, `de_cette_manche`)
   - `joueur/joueur.py` (et `ia.py` si le LLM doit le voir)
   - `interface/spectacle.js` (état reconstruit) et `interface/public/main.js` / `hub3d.js` s'il est affiché. L'interface ne lit toujours pas `iot/role/+`.
   - `outils/faux_ollama.py` et `outils/simulation.py` si le contexte LLM ou les configs changent.
4. **Mettre à jour les README** des modules touchés et le tableau « Ce que demande le sujet » du README racine si besoin.
5. **Vérifier** avec `/verifier`, puis lancer `/simulation` et contrôler que le nouveau champ circule (journaux, ou `curl -s http://localhost:5050/api/etat`).
6. Proposer un commit `Protocole : …` et rappeler à l'utilisateur de **prévenir le groupe** : les autres doivent mettre à jour leur Pi.
