# Broker MQTT — Niels

Mettez ici la configuration Mosquitto :

- `mosquitto.conf` (listener 1883, `allow_anonymous true` pour le TP, ou des comptes si vous en créez)
- éventuellement `docker-compose.yml`
- l'**adresse IP et le port** du broker, que tous les autres modules doivent renseigner dans leur config

Pour tester à la main :

```bash
mosquitto_sub -h <ip_broker> -t 'iot/#' -v      # voir tout le trafic du jeu
mosquitto_pub -h <ip_broker> -t 'iot/test' -m 'hello'
```

Protocole : [../docs/protocole.md](../docs/protocole.md)
