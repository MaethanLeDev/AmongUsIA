# Broker MQTT — Niels

- **Adresse** : `10.109.150.215` (attribuée par DHCP, à vérifier à chaque séance avec `hostname -I`)
- **Port** : `1883`
- **Authentification** : aucune (`allow_anonymous true`, suffisant pour le TP)

C'est l'adresse que les joueurs doivent renseigner dans leur config.
Le maître du jeu et l'interface, s'ils tournent sur la même machine que le broker, peuvent utiliser `localhost:1883`.

## Lancer

Depuis ce dossier :

```bash
docker compose up -d
docker compose logs -f      # voir les connexions
```

Le port 1883 doit être libre. Si Mosquitto est aussi installé sur la machine, il faut le couper :
`sudo systemctl disable --now mosquitto`.

`mosquitto.conf` ouvre le broker au réseau et active la persistance : les messages retained
(`iot/joueurs/<id>`, `iot/partie/etat`) sont conservés dans le volume `broker-data`.

## Tester à la main

```bash
mosquitto_sub -h 10.109.150.215 -t 'iot/#' -v      # voir tout le trafic du jeu
mosquitto_pub -h 10.109.150.215 -t 'iot/test' -m 'hello'
```

Protocole : [../docs/protocole.md](../docs/protocole.md)
