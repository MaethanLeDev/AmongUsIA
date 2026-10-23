"""Broker MQTT minimal pour tester sur un seul PC, sans Docker ni Mosquitto.

Il gère ce dont le jeu a besoin : MQTT 3.1.1, publications QoS 0 et 1 (livrées en QoS 0),
messages retenus, Last Will, keep-alive, jokers + et #. Pour jouer pour de vrai, utilisez Mosquitto (broker/).

Usage : python outils/broker_dev.py [--port 1883]
"""
import argparse
import asyncio
import struct


def chaine(donnees, pos):
    taille = struct.unpack_from("!H", donnees, pos)[0]
    return donnees[pos + 2:pos + 2 + taille], pos + 2 + taille


def taille_restante(n):
    octets = bytearray()
    while True:
        n, octet = divmod(n, 128)
        octets.append(octet | (128 if n else 0))
        if not n:
            return bytes(octets)


def paquet_publish(topic, message, retenu):
    t = topic.encode()
    corps = struct.pack("!H", len(t)) + t + message
    return bytes([0x30 | (1 if retenu else 0)]) + taille_restante(len(corps)) + corps


def correspond(filtre, topic):
    f, t = filtre.split("/"), topic.split("/")
    if topic.startswith("$") and f[0] in ("+", "#"):
        return False
    for i, morceau in enumerate(f):
        if morceau == "#":
            return True
        if i >= len(t) or (morceau != "+" and morceau != t[i]):
            return False
    return len(f) == len(t)


class Client:
    def __init__(self, writer):
        self.writer = writer
        self.id = ""
        self.filtres = set()
        self.will = None  # (topic, message, retenu)
        self.keepalive = 60

    def envoyer(self, donnees):
        if not self.writer.is_closing():
            self.writer.write(donnees)


class Broker:
    def __init__(self):
        self.clients = {}   # id -> Client
        self.retenus = {}   # topic -> message

    async def gerer(self, reader, writer):
        client, propre = Client(writer), False
        try:
            while True:
                # Keep-alive : sans nouvelles pendant 1,5 x keepalive, le client est considéré comme mort (Last Will)
                entete = await asyncio.wait_for(reader.readexactly(1), client.keepalive * 1.5 or None)
                taille, mult = 0, 1
                while True:
                    octet = (await reader.readexactly(1))[0]
                    taille += (octet & 127) * mult
                    mult *= 128
                    if not octet & 128:
                        break
                corps = await reader.readexactly(taille) if taille else b""
                genre = entete[0] >> 4
                if genre == 1:
                    self.connect(client, corps)
                elif genre == 3:
                    self.publish(client, entete[0] & 15, corps)
                elif genre == 8:
                    self.subscribe(client, corps)
                elif genre == 10:
                    self.unsubscribe(client, corps)
                elif genre == 12:
                    client.envoyer(b"\xd0\x00")  # PINGRESP
                elif genre == 14:
                    propre = True
                    break
        except (asyncio.IncompleteReadError, asyncio.TimeoutError, ConnectionError, struct.error):
            pass
        finally:
            if self.clients.get(client.id) is client:
                del self.clients[client.id]
                print(f"- {client.id}{'' if propre else ' (sans prévenir)'}")
                if not propre and client.will:
                    self.diffuser(*client.will)
            writer.close()

    def connect(self, client, corps):
        _, pos = chaine(corps, 0)               # "MQTT"
        drapeaux = corps[pos + 1]
        client.keepalive = struct.unpack_from("!H", corps, pos + 2)[0]
        identifiant, pos = chaine(corps, pos + 4)
        client.id = identifiant.decode() or f"anonyme-{id(client)}"
        if drapeaux & 0x04:
            topic, pos = chaine(corps, pos)
            message, pos = chaine(corps, pos)
            client.will = (topic.decode(), message, bool(drapeaux & 0x20))
        ancien = self.clients.get(client.id)
        if ancien:
            ancien.writer.close()                # même identifiant : le nouveau remplace l'ancien
        self.clients[client.id] = client
        client.envoyer(b"\x20\x02\x00\x00")      # CONNACK accepté
        print(f"+ {client.id}")

    def publish(self, client, drapeaux, corps):
        topic, pos = chaine(corps, 0)
        if (drapeaux >> 1) & 3:
            client.envoyer(b"\x40\x02" + corps[pos:pos + 2])  # PUBACK
            pos += 2
        self.diffuser(topic.decode(), corps[pos:], bool(drapeaux & 1))

    def diffuser(self, topic, message, retenu):
        if retenu:
            if message:
                self.retenus[topic] = message
            else:
                self.retenus.pop(topic, None)
        paquet = paquet_publish(topic, message, False)
        for autre in list(self.clients.values()):
            if any(correspond(f, topic) for f in autre.filtres):
                autre.envoyer(paquet)

    def subscribe(self, client, corps):
        identifiant, pos, filtres = corps[:2], 2, []
        while pos < len(corps):
            filtre, pos = chaine(corps, pos)
            filtres.append(filtre.decode())
            pos += 1                             # QoS demandée : on accorde 0
        client.filtres.update(filtres)
        client.envoyer(bytes([0x90, 2 + len(filtres)]) + identifiant + bytes(len(filtres)))
        for topic, message in list(self.retenus.items()):
            if any(correspond(f, topic) for f in filtres):
                client.envoyer(paquet_publish(topic, message, True))

    def unsubscribe(self, client, corps):
        pos = 2
        while pos < len(corps):
            filtre, pos = chaine(corps, pos)
            client.filtres.discard(filtre.decode())
        client.envoyer(b"\xb0\x02" + corps[:2])


async def principal(port):
    broker = Broker()
    serveur = await asyncio.start_server(broker.gerer, "0.0.0.0", port)
    print(f"Broker de test sur le port {port} (Ctrl+C pour arrêter)")
    async with serveur:
        await serveur.serve_forever()


def main():
    parser = argparse.ArgumentParser(description="Broker MQTT minimal pour les tests")
    parser.add_argument("--port", type=int, default=1883)
    try:
        asyncio.run(principal(parser.parse_args().port))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
