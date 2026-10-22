# Classe Noire (jeu d'origine)

Jeu de manipulation en 3D, dans le navigateur, sans dépendance (Node.js seul ; Three.js est fourni dans `public/vendor/`). Thème « Classroom of the Elite » : tout le monde est assis autour d'une **table ronde** sous une lampe et se manipule.

Dans ce projet, **seul le salon et la table** sont gardés. Le mode « Mission 3D » (cartes, PNJ) du jeu d'origine a été retiré.

## Lancer

`node server.js` (ou `start.bat`), puis ouvrir `http://localhost:3939`. Autre port : `set PORT=4141 && node server.js`. Les autres machines utilisent l'adresse « Tes amis » affichée dans la console. Pour relier les Raspberry Pi : [AGENTS.md](AGENTS.md).

## Le salon

On choisit un nom de code et un **personnage** (6 archétypes, couleurs personnalisables : Stratège, Vengeur, Sourire, Reine des Glaces, Ombre, Prodige), puis on rejoint la table. L'hôte (👑, premier humain arrivé) lance **La Table**. Les Raspberry Pi (📡) apparaissent comme des personnages.

## La Table (jeu de cartes)

1. **Négociation** : chat public, chuchotements, pacte de confiance 🤝 (un par tour), rumeur anonyme 📢.
2. **Choix secret** : 🤝 coopérer (−2 PC au pot doublé et partagé), 🗡 trahir (vole 3 PC à qui coopère, avec un faux coupable optionnel), 👁 observer.
3. **Accusation** puis **révélation**. Noirceur secrète : vol +2, faux coupable +2, pacte trahi +3, traître surpris +1 ; bonus de discrétion (8 − 2 × démasquages). Les pions 🤖 permettent de jouer à moins de 3.

## Code

- `server.js` : HTTP + WebSocket maison (RFC 6455), hub, routage vers la table et vers le pont Raspberry Pi.
- `table.js` : moteur du jeu de cartes. `agents.js` + `mqtt.js` : pont MQTT / API vers les Raspberry Pi.
- `public/` : client. `chars.js` (personnages 3D), `hub3d.js` (salon), `main.js`, `tableui.js`, `net.js`.
