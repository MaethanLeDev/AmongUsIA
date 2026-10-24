---
paths:
  - "interface/**"
---

# Bonnes pratiques de l'interface

- Côté serveur (`server.js`, `mqtt.js`, `spectacle.js`) : CommonJS (`require`), `'use strict'`, modules Node intégrés uniquement. **Aucune dépendance npm**, pas de `package.json`.
- Côté navigateur (`public/`) : modules ES servis tels quels, sans build ni bundler ; Three.js vient de `public/vendor/` via l'import map de `index.html` (ne jamais modifier `vendor/`).
- **Sécurité** : les textes viennent des LLM et des configs des joueurs, donc non fiables. Toujours `textContent` / le helper `h(...)`, **jamais `innerHTML`** avec une donnée reçue. Limiter les longueurs affichées.
- Le serveur reste en **lecture seule** sur MQTT : aucune publication, jamais d'abonnement à `iot/role/+`.
- Three.js : réutiliser géométries et matériaux, appeler `dispose()` sur ce qu'on retire de la scène (voir `jeter` dans `hub3d.js`), une seule boucle `requestAnimationFrame`, tenir compte du réglage de qualité graphique.
- Robustesse : un navigateur qui se connecte en cours de partie doit retrouver l'état complet (état reconstruit dans `spectacle.js`) ; tolérer les champs manquants ou inconnus d'un message.
- JavaScript moderne (`const`/`let`, fonctions fléchées, `?.`, `??`) en restant compatible Node 18 côté serveur.
- Pour une API Three.js dont tu n'es pas sûr (elle change souvent d'une version à l'autre), c'est la r170 (`public/vendor/three/`) : consulte la doc via Context7.
