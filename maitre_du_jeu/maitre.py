"""Maître du jeu : inscrit les joueurs, tire l'espion, collecte les votes et annonce le résultat.

Usage : uv run maitre_du_jeu/maitre.py --broker 10.109.150.215
Protocole : docs/protocole.md
"""
import argparse
import json
import random
import threading
from collections import Counter

import paho.mqtt.client as mqtt

TOPIC_JOUEURS = "iot/joueurs/+"
TOPIC_VOTES = "iot/votes/+"
TOPIC_ETAT = "iot/partie/etat"
TOPIC_RESULTAT = "iot/partie/resultat"
DUREE_MANCHE = 5  # secondes entre deux températures, fixé par le sujet


class MaitreDuJeu:
    def __init__(self, hote, port, manches, delai_vote):
        self.manches = manches
        self.delai_vote = delai_vote
        self.verrou = threading.Lock()
        self.joueurs = {}          # id -> ville, joueurs actuellement en ligne
        self.participants = []     # joueurs de la partie en cours
        self.votes = {}            # votant -> suspect
        self.tous_ont_vote = threading.Event()

        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="maitre-du-jeu")
        self.client.on_connect = self._on_connect
        self.client.message_callback_add(TOPIC_JOUEURS, self._on_presence)
        self.client.message_callback_add(TOPIC_VOTES, self._on_vote)
        self.client.connect(hote, port)
        self.client.loop_start()

    # --- Réception MQTT -------------------------------------------------

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        print(f"Connecté au broker ({reason_code})")
        client.subscribe([(TOPIC_JOUEURS, 1), (TOPIC_VOTES, 1)])

    def _on_presence(self, client, userdata, msg):
        id_joueur = msg.topic.split("/")[-1]
        presence = lire_json(msg.payload)
        with self.verrou:
            if presence.get("en_ligne"):
                arrive = id_joueur not in self.joueurs
                self.joueurs[id_joueur] = presence.get("ville", "?")
                if arrive:
                    print(f"  + {id_joueur} ({self.joueurs[id_joueur]})")
            elif self.joueurs.pop(id_joueur, None) is not None:
                print(f"  - {id_joueur} est parti")

    def _on_vote(self, client, userdata, msg):
        votant = msg.topic.split("/")[-1]
        suspect = lire_json(msg.payload).get("suspect")
        with self.verrou:
            if votant not in self.participants or votant in self.votes:
                return
            if suspect not in self.participants or suspect == votant:
                print(f"  Vote invalide de {votant} : {suspect!r}")
                return
            self.votes[votant] = suspect
            print(f"  {votant} vote contre {suspect} ({len(self.votes)}/{len(self.participants)})")
            if len(self.votes) == len(self.participants):
                self.tous_ont_vote.set()

    # --- Déroulement d'une partie --------------------------------------

    def publier(self, topic, contenu, retain=False):
        self.client.publish(topic, json.dumps(contenu, ensure_ascii=False), qos=1, retain=retain)

    def inscription(self, min_joueurs):
        self.publier(TOPIC_ETAT, {"etat": "inscription"}, retain=True)
        print(f"\nInscription ouverte, en attente d'au moins {min_joueurs} joueurs…")
        while True:
            input("Appuie sur Entrée pour lancer la partie.\n")
            with self.verrou:
                inscrits = sorted(self.joueurs)
            if len(inscrits) >= min_joueurs:
                return inscrits
            print(f"Seulement {len(inscrits)} joueur(s) : {inscrits}")

    def jouer(self, inscrits):
        espion = random.choice(inscrits)
        with self.verrou:
            self.participants = inscrits
            self.votes = {}
            self.tous_ont_vote.clear()

        print(f"\nPartie lancée avec {inscrits}. Espion : {espion} (chut)")
        self.publier(TOPIC_ETAT, {"etat": "en_cours", "joueurs": inscrits, "manches": self.manches}, retain=True)
        for id_joueur in inscrits:
            role = "espion" if id_joueur == espion else "normal"
            self.publier(f"iot/role/{id_joueur}", {"role": role})

        attente = self.manches * DUREE_MANCHE + self.delai_vote
        print(f"Attente des votes (au plus {attente} s)…")
        if not self.tous_ont_vote.wait(attente):
            print("Temps écoulé : certains joueurs n'ont pas voté.")

        with self.verrou:
            votes = dict(self.votes)
        self.annoncer(espion, inscrits, votes)

    def annoncer(self, espion, inscrits, votes):
        compte = Counter(votes.values())
        designe = compte.most_common(1)[0][0] if compte else None
        # Les capteurs gagnent si plus de la moitié des joueurs désigne l'espion
        gagnant = "capteurs" if compte[espion] > len(inscrits) / 2 else "espion"

        self.publier(TOPIC_RESULTAT, {"espion": espion, "designe": designe, "votes": votes, "gagnant": gagnant})
        self.publier(TOPIC_ETAT, {"etat": "fini"}, retain=True)

        print("\n===== Résultat =====")
        for suspect, nb in compte.most_common():
            print(f"  {suspect} : {nb} vote(s)")
        print(f"  L'espion était {espion}. Victoire : {gagnant.upper()}")

    def fermer(self):
        self.client.loop_stop()
        self.client.disconnect()


def lire_json(payload):
    try:
        contenu = json.loads(payload)
        return contenu if isinstance(contenu, dict) else {}
    except ValueError:
        return {}


def main():
    parser = argparse.ArgumentParser(description="Maître du jeu de l'espion")
    parser.add_argument("--broker", default="localhost", help="adresse du broker MQTT")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--min-joueurs", type=int, default=3)
    parser.add_argument("--manches", type=int, default=5)
    parser.add_argument("--delai-vote", type=int, default=60,
                        help="secondes laissées aux joueurs pour voter après la dernière manche")
    args = parser.parse_args()

    maitre = MaitreDuJeu(args.broker, args.port, args.manches, args.delai_vote)
    try:
        while True:
            maitre.jouer(maitre.inscription(args.min_joueurs))
            if input("\nRejouer ? (o/n) ").strip().lower() != "o":
                break
    except KeyboardInterrupt:
        pass
    finally:
        maitre.fermer()


if __name__ == "__main__":
    main()
