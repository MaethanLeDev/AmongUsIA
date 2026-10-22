# Broker MQTT — Niels

- **Adresse** : `10.109.150.215`
- **Port** : `1883`
- **Authentification** : aucune (`allow_anonymous true`, suffisant pour le TP)

C'est l'adresse que tous les autres modules doivent renseigner dans leur config.

## Installation sur un Raspberry Pi

```bash
sudo apt install mosquitto mosquitto-clients
sudo cp mosquitto.conf /etc/mosquitto/conf.d/jeu.conf
sudo systemctl restart mosquitto
```

Par défaut, Mosquitto 2 n'écoute qu'en local. `mosquitto.conf` l'ouvre au réseau sur le port 1883.

## Tester à la main

```bash
mosquitto_sub -h 10.109.150.215 -t 'iot/#' -v      # voir tout le trafic du jeu
mosquitto_pub -h 10.109.150.215 -t 'iot/test' -m 'hello'
```

Protocole : [../docs/protocole.md](../docs/protocole.md)
