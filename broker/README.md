# Broker MQTT — Niels

- **Adresse** : `amongus.local` (sinon l'IP fixe `10.109.150.215`)
- **Port** : `1883`
- **Authentification** : aucune (`allow_anonymous true`, suffisant pour le TP)

C'est l'adresse que les joueurs doivent renseigner dans leur config.
Le nom `amongus.local` est publié en mDNS par Avahi sur le Pi serveur. Il fonctionne directement sous Raspberry Pi OS,
macOS et Windows 10+. Si le réseau bloque le mDNS, utiliser l'IP.
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

## Nom mDNS (déjà fait sur le Pi serveur)

```bash
sudo hostnamectl set-hostname amongus                          # et remplacer l'ancien nom dans /etc/hosts
sudo sed -i 's/^#allow-interfaces=.*/allow-interfaces=wlan0/' /etc/avahi/avahi-daemon.conf
sudo systemctl restart avahi-daemon
```

`allow-interfaces` est nécessaire avec Docker : sans cette ligne, Avahi publie aussi l'adresse du bridge `docker0`
(`172.17.0.1`), qui est injoignable depuis les autres machines.

## Tester à la main

```bash
mosquitto_sub -h amongus.local -t 'iot/#' -v      # voir tout le trafic du jeu
mosquitto_pub -h amongus.local -t 'iot/test' -m 'hello'
```

## Sans Docker, pour tester sur un PC

`python outils/broker_dev.py` lance un petit broker de test (MQTT 3.1.1, messages retenus, Last Will) sur le port 1883.
`outils/simulation.py` s'en sert pour jouer une partie complète sans Raspberry Pi. Pour les vraies parties, gardez Mosquitto.

Protocole : [../docs/protocole.md](../docs/protocole.md)
