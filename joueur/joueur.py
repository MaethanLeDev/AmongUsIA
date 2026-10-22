"""Joueur générique : un capteur de température piloté par une IA Ollama.

Le même script tourne sur toutes les machines. Tout ce qui se personnalise est dans config.json :
ville, modèle Ollama, personnalité, nom et apparence dans l'interface.

Usage : uv run joueur/joueur.py [chemin/vers/config.json]
Protocole : docs/protocole.md
"""
import copy
import json
import random
import statistics
import sys
import threading
import time
from pathlib import Path

import paho.mqtt.client as mqtt

from ia import IA, Partie
from meteo import Meteo

DUREE_MANCHE = 5              # secondes entre deux températures, fixé par le sujet
ECART_ESPION = (0.05, 0.10)   # l'espion décale la moyenne des autres de 5 à 10 %, vers le haut ou le bas


class Joueur:
    def __init__(self, config):
        self.config = config
        self.id = config["id"]
        self.meteo = Meteo(config["ville"])
        self.ia = IA(config)
        self.verrou = threading.Lock()
        self.annuaire = {}       # id -> message de présence de chaque joueur en ligne
        self.participants = []   # annoncés par le maître au début de la partie
        self.partie = None       # partie en cours, None entre deux parties

        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"joueur-{self.id}")
        # Si le joueur disparaît sans prévenir, le broker annonce son départ à sa place
        self.client.will_set(f"iot/joueurs/{self.id}", json.dumps({"id": self.id, "en_ligne": False}),
                             qos=1, retain=True)
        self.client.on_connect = self._on_connect
        abonnements = {
            "iot/joueurs/+": self._on_presence,
            "iot/partie/etat": self._on_etat,
            f"iot/role/{self.id}": self._on_role,
            "iot/capteurs/+/temperature": self._on_temperature,
            "iot/partie/parole": self._on_parole,
            "iot/chat/+": self._on_chat,
        }
        for topic, fonction in abonnements.items():
            self.client.message_callback_add(topic, fonction)
        self.abonnements = [(topic, 1) for topic in abonnements]

    def lancer(self):
        broker = self.config["broker"]
        self.client.connect(broker["hote"], broker["port"])
        try:
            self.client.loop_forever()
        except KeyboardInterrupt:
            self.publier(f"iot/joueurs/{self.id}", {"id": self.id, "en_ligne": False}, retain=True)
            self.client.disconnect()

    def publier(self, topic, contenu, retain=False):
        self.client.publish(topic, json.dumps(contenu, ensure_ascii=False), qos=1, retain=retain)

    def log(self, texte):
        print(f"[{self.ia.nom}] {texte}")

    # --- Réception MQTT -------------------------------------------------

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        self.log(f"connecté au broker ({reason_code}), modèle {self.ia.modele}")
        client.subscribe(self.abonnements)
        self.annoncer_presence()

    def annoncer_presence(self):
        presence = {"id": self.id, "ville": self.config["ville"], "en_ligne": True, "modele": self.ia.modele}
        presence.update(self.config.get("interface", {}))  # nom, arch
        self.publier(f"iot/joueurs/{self.id}", presence, retain=True)

    def _on_presence(self, client, userdata, msg):
        presence = lire_json(msg.payload)
        with self.verrou:
            if presence.get("en_ligne"):
                self.annuaire[expediteur(msg)] = presence
            else:
                self.annuaire.pop(expediteur(msg), None)

    def _on_etat(self, client, userdata, msg):
        etat = lire_json(msg.payload)
        if etat.get("etat") == "inscription":
            with self.verrou:
                self.partie = None  # une éventuelle partie en cours s'arrête
            self.log("inscription ouverte, en attente du rôle")
            self.annoncer_presence()
        elif etat.get("etat") == "en_cours":
            with self.verrou:
                self.participants = etat.get("joueurs", [])
        elif etat.get("etat") == "vote" and self.partie and self.id in etat.get("joueurs", []):
            self.en_arriere_plan(self.voter, etat.get("delai", 60))

    def _on_role(self, client, userdata, msg):
        role = lire_json(msg.payload).get("role")
        if role not in ("normal", "espion"):
            return
        with self.verrou:
            self.partie = Partie(self.id, role)
            partie = self.partie
        self.log(f"rôle reçu : {role.upper()}")
        self.en_arriere_plan(self.mesurer, partie)

    def _on_temperature(self, client, userdata, msg):
        temperature = lire_json(msg.payload).get("temperature")
        with self.verrou:
            if self.partie and isinstance(temperature, (int, float)):
                self.partie.mesures.setdefault(msg.topic.split("/")[2], []).append(temperature)

    def _on_chat(self, client, userdata, msg):
        texte = lire_json(msg.payload).get("text")
        with self.verrou:
            if self.partie and isinstance(texte, str):
                self.partie.debat.append((expediteur(msg), texte))

    def _on_parole(self, client, userdata, msg):
        parole = lire_json(msg.payload)
        if self.partie and parole.get("joueur") == self.id:
            self.en_arriere_plan(self.parler, parole)

    # --- Actions (dans un thread, pour ne pas bloquer le réseau pendant que le LLM réfléchit) ---

    def en_arriere_plan(self, fonction, *args):
        threading.Thread(target=fonction, args=args, daemon=True).start()

    def instantane(self):
        """Copie de la partie, avec les noms et villes à jour, que le LLM peut lire tranquillement."""
        with self.verrou:
            if self.partie is None:
                return None
            partie = copy.deepcopy(self.partie)
            partie.participants = list(self.participants)
            partie.noms = {i: p.get("nom") or i for i, p in self.annuaire.items()}
            partie.villes = {i: p.get("ville", "?") for i, p in self.annuaire.items()}
        return partie

    def mesurer(self, partie):
        for manche in range(1, 6):
            if self.partie is not partie:
                return
            temperature = self.meteo.temperature() if partie.role == "normal" else self.fausse_temperature(partie)
            if temperature is not None:
                self.publier(f"iot/capteurs/{self.id}/temperature", {
                    "id": self.id, "ville": self.config["ville"], "temperature": round(temperature, 1),
                    "manche": manche, "ts": int(time.time()),
                })
                self.log(f"manche {manche} : {temperature:.1f} °C")
            time.sleep(DUREE_MANCHE)

    def fausse_temperature(self, partie):
        # L'espion part de la moyenne des dernières valeurs des autres (ou de la vraie au début)
        with self.verrou:
            dernieres = [v[-1] for i, v in partie.mesures.items() if i != self.id and v]
        base = statistics.mean(dernieres) if dernieres else self.meteo.temperature()
        if base is None:
            return None
        return base * (1 + random.choice((-1, 1)) * random.uniform(*ECART_ESPION))

    def parler(self, parole):
        partie = self.instantane()
        if partie is None:
            return
        self.log(f"a la parole (tour {parole.get('tour')}), réfléchit…")
        debut = time.monotonic()
        texte = self.ia.parler(partie, parole.get("tour", 1), parole.get("tours", 1),
                               delai=max(10, parole.get("delai", 90) - 5))
        self.publier(f"iot/chat/{self.id}", {"text": texte, "tour": parole.get("tour")})
        self.log(f"({time.monotonic() - debut:.0f} s) {texte}")

    def voter(self, delai):
        partie = self.instantane()
        if partie is None or not partie.autres():
            return
        suspect, raison = self.ia.voter(partie, delai=max(10, delai - 10))
        if suspect is None:
            self.log("aucune donnée, pas de vote")
            return
        self.publier(f"iot/votes/{self.id}", {"votant": self.id, "suspect": suspect, "raison": raison})
        self.log(f"vote contre {partie.nom(suspect)} : {raison}")


def expediteur(msg):
    return msg.topic.split("/")[-1]


def lire_json(payload):
    try:
        contenu = json.loads(payload)
        return contenu if isinstance(contenu, dict) else {}
    except ValueError:
        return {}


def main():
    sys.stdout.reconfigure(line_buffering=True)  # journaux visibles tout de suite, même redirigés
    chemin = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("config.json")
    if not chemin.exists():
        sys.exit(f"Config introuvable : {chemin} (copie config.example.json en config.json)")
    Joueur(json.loads(chemin.read_text(encoding="utf-8"))).lancer()


if __name__ == "__main__":
    main()
