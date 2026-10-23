"""Maître du jeu : l'arbitre de la partie.

Il inscrit les joueurs, tire l'espion, puis fait avancer les phases :
mesures -> débat (chacun son tour) -> vote -> résultat.

Usage : uv run maitre_du_jeu/maitre.py
Protocole : docs/protocole.md
"""
import argparse
import json
import random
import threading
import time
from collections import Counter

import paho.mqtt.client as mqtt

DUREE_MANCHE = 5  # secondes entre deux températures, fixé par le sujet
MAX_JOUEURS = 8   # nombre de sièges de l'interface


class MaitreDuJeu:
    def __init__(self, reglages):
        self.reglages = reglages
        self.cond = threading.Condition()  # protège l'état ci-dessous et réveille les phases en attente
        self.joueurs = {}          # id -> message de présence, joueurs en ligne
        self.participants = []     # joueurs de la partie en cours
        self.mesures = Counter()   # id -> nombre de températures reçues
        self.parole = None         # id du joueur qui a la parole
        self.reponse = None        # ce qu'il a dit
        self.vote_ouvert = False
        self.votes = {}            # votant -> suspect

        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="maitre-du-jeu")
        self.client.on_connect = self._on_connect
        self.client.message_callback_add("iot/joueurs/+", self._on_presence)
        self.client.message_callback_add("iot/capteurs/+/temperature", self._on_temperature)
        self.client.message_callback_add("iot/chat/+", self._on_chat)
        self.client.message_callback_add("iot/votes/+", self._on_vote)
        self.client.connect(reglages.broker, reglages.port)
        self.client.loop_start()

    # --- Réception MQTT -------------------------------------------------

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        print(f"Connecté au broker {self.reglages.broker} ({reason_code})")
        client.subscribe([("iot/joueurs/+", 1), ("iot/capteurs/+/temperature", 0),
                          ("iot/chat/+", 1), ("iot/votes/+", 1)])

    def _on_presence(self, client, userdata, msg):
        id_joueur = expediteur(msg)
        presence = lire_json(msg.payload)
        with self.cond:
            if presence.get("en_ligne"):
                if id_joueur not in self.joueurs:
                    print(f"  + {decrire(id_joueur, presence)}")
                self.joueurs[id_joueur] = presence
            elif id_joueur in self.joueurs:
                print(f"  - {self.nom(id_joueur)} est parti")
                del self.joueurs[id_joueur]
            self.cond.notify_all()

    def _on_temperature(self, client, userdata, msg):
        with self.cond:
            id_joueur = msg.topic.split("/")[2]
            if id_joueur in self.participants:
                self.mesures[id_joueur] += 1
                self.cond.notify_all()

    def _on_chat(self, client, userdata, msg):
        texte = lire_json(msg.payload).get("text")
        with self.cond:
            # On n'écoute que le joueur qui a la parole : les autres attendent leur tour
            if expediteur(msg) == self.parole and isinstance(texte, str):
                self.reponse = texte
                self.cond.notify_all()

    def _on_vote(self, client, userdata, msg):
        votant = expediteur(msg)
        suspect = lire_json(msg.payload).get("suspect")
        with self.cond:
            if not self.vote_ouvert or votant not in self.participants or votant in self.votes:
                return
            if suspect not in self.participants or suspect == votant:
                print(f"  Vote invalide de {self.nom(votant)} : {suspect!r}")
                return
            self.votes[votant] = suspect
            print(f"  🗳  {self.nom(votant)} vote contre {self.nom(suspect)}")
            self.cond.notify_all()

    # --- Outils ---------------------------------------------------------

    def publier(self, topic, contenu, retain=False):
        self.client.publish(topic, json.dumps(contenu, ensure_ascii=False), qos=1, retain=retain)

    def nom(self, id_joueur):
        return self.joueurs.get(id_joueur, {}).get("nom") or id_joueur

    def en_ligne(self):
        return [i for i in self.participants if i in self.joueurs]

    def attendre(self, condition, delai):
        """Attend que condition() soit vraie, au plus delai secondes. Renvoie False si le délai expire."""
        with self.cond:
            return self.cond.wait_for(condition, delai)

    # --- Phases ---------------------------------------------------------

    def inscription(self):
        self.publier("iot/partie/etat", {"etat": "inscription"}, retain=True)
        print(f"\n=== INSCRIPTION === (au moins {self.reglages.min_joueurs} joueurs, {MAX_JOUEURS} au plus)")
        while True:
            input("Appuie sur Entrée pour lancer la partie.\n")
            with self.cond:
                inscrits = sorted(self.joueurs)
            if len(inscrits) > MAX_JOUEURS:
                print(f"{len(inscrits)} joueurs, on garde les {MAX_JOUEURS} premiers.")
                inscrits = inscrits[:MAX_JOUEURS]
            if len(inscrits) >= self.reglages.min_joueurs:
                return inscrits
            print(f"Seulement {len(inscrits)} joueur(s) : {', '.join(inscrits) or 'personne'}")

    def jouer(self, inscrits):
        espion = random.choice(inscrits)
        with self.cond:
            self.participants = inscrits
            self.mesures.clear()
            self.votes = {}
        print(f"\nPartie : {', '.join(self.nom(i) for i in inscrits)}. Espion : {self.nom(espion)} (chut)")

        self.phase_mesures(espion)
        self.phase_debat()
        self.phase_vote()
        self.annoncer(espion)

    def phase_mesures(self, espion):
        manches = self.reglages.manches
        print(f"\n=== MESURES === ({manches} manches de {DUREE_MANCHE} s)")
        self.publier("iot/partie/etat", {"etat": "en_cours", "joueurs": self.participants, "manches": manches},
                     retain=True)
        for id_joueur in self.participants:
            self.publier(f"iot/role/{id_joueur}", {"role": "espion" if id_joueur == espion else "normal"})

        tous_mesures = lambda: all(self.mesures[i] >= manches for i in self.en_ligne())
        if not self.attendre(tous_mesures, manches * DUREE_MANCHE + 15):
            print("  Certains capteurs n'ont pas fini leurs mesures, on continue.")

    def phase_debat(self):
        tours, delai = self.reglages.tours, self.reglages.delai_parole
        ordre = random.sample(self.participants, len(self.participants))
        print(f"\n=== DÉBAT === ({tours} tours, {delai} s max par prise de parole)")
        self.publier("iot/partie/etat", {"etat": "debat", "joueurs": self.participants, "tours": tours},
                     retain=True)

        for tour in range(1, tours + 1):
            print(f"\n--- Tour {tour}/{tours} ---")
            for rang, id_joueur in enumerate(ordre, start=1):
                if id_joueur not in self.joueurs:
                    continue
                with self.cond:
                    self.parole, self.reponse = id_joueur, None
                self.publier("iot/partie/parole", {"joueur": id_joueur, "tour": tour, "tours": tours,
                                                   "rang": rang, "sur": len(ordre), "delai": delai})
                a_parle = self.attendre(lambda: self.reponse is not None or self.parole not in self.joueurs, delai)
                print(f"  {self.nom(id_joueur)} : {self.reponse if a_parle and self.reponse else '(silence)'}")
                time.sleep(self.reglages.pause)  # laisse les spectateurs lire la bulle avant le suivant
        with self.cond:
            self.parole = None

    def phase_vote(self):
        delai = self.reglages.delai_vote
        print(f"\n=== VOTE === ({delai} s max)")
        with self.cond:
            self.votes, self.vote_ouvert = {}, True
        self.publier("iot/partie/etat", {"etat": "vote", "joueurs": self.participants, "delai": delai}, retain=True)

        if not self.attendre(lambda: all(i in self.votes for i in self.en_ligne()), delai):
            print("  Temps écoulé : certains joueurs n'ont pas voté.")
        with self.cond:
            self.vote_ouvert = False

    def annoncer(self, espion):
        with self.cond:
            votes = dict(self.votes)
        compte = Counter(votes.values())
        designe = compte.most_common(1)[0][0] if compte else None
        gagnant = "capteurs" if compte[espion] > len(self.participants) / 2 else "espion"

        self.publier("iot/partie/resultat", {"espion": espion, "designe": designe, "votes": votes, "gagnant": gagnant})
        self.publier("iot/partie/etat", {"etat": "fini"}, retain=True)

        print("\n=== RÉSULTAT ===")
        for suspect, nb in compte.most_common():
            print(f"  {self.nom(suspect)} : {nb} vote(s)")
        print(f"  L'espion était {self.nom(espion)}. Victoire : {gagnant.upper()}")

    def fermer(self):
        self.client.loop_stop()
        self.client.disconnect()


def expediteur(msg):
    return msg.topic.split("/")[-1]


def decrire(id_joueur, presence):
    details = ", ".join(str(presence[c]) for c in ("ville", "modele") if presence.get(c))
    nom = presence.get("nom") or id_joueur
    return f"{nom} [{id_joueur}]" + (f" ({details})" if details else "")


def lire_json(payload):
    try:
        contenu = json.loads(payload)
        return contenu if isinstance(contenu, dict) else {}
    except ValueError:
        return {}


def main():
    parser = argparse.ArgumentParser(description="Maître du jeu de l'espion")
    parser.add_argument("--broker", default="amongus.local", help="adresse du broker MQTT")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--min-joueurs", type=int, default=3)
    parser.add_argument("--manches", type=int, default=5)
    parser.add_argument("--tours", type=int, default=2, help="tours de parole du débat")
    parser.add_argument("--delai-parole", type=int, default=90,
                        help="secondes max pour une prise de parole (un gros modèle est lent sur un Pi)")
    parser.add_argument("--pause", type=float, default=3, help="secondes entre deux prises de parole")
    parser.add_argument("--delai-vote", type=int, default=120)
    reglages = parser.parse_args()

    maitre = MaitreDuJeu(reglages)
    try:
        while True:
            maitre.jouer(maitre.inscription())
            if input("\nRejouer ? (o/n) ").strip().lower() != "o":
                break
    except KeyboardInterrupt:
        pass
    finally:
        maitre.fermer()


if __name__ == "__main__":
    main()
