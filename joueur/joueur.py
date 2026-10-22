"""Joueur générique : un capteur de température sur Raspberry Pi.

Le même script tourne sur toutes les machines, seul config.json change.
Usage : uv run joueur/joueur.py [chemin/vers/config.json]
Protocole : docs/protocole.md
"""
import json
import random
import statistics
import sys
import threading
import time
from pathlib import Path

import paho.mqtt.client as mqtt
import requests

DUREE_MANCHE = 5         # secondes entre deux températures, fixé par le sujet
ECART_ESPION = (0.05, 0.10)  # l'espion décale la moyenne des autres de 5 à 10 %, vers le haut ou le bas


# --- Météo ---------------------------------------------------------------

class Meteo:
    """Température actuelle d'une ville via l'API Open-Meteo."""

    def __init__(self, ville):
        reponse = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                               params={"name": ville, "count": 1, "language": "fr"}, timeout=10)
        reponse.raise_for_status()
        resultats = reponse.json().get("results")
        if not resultats:
            raise ValueError(f"Ville introuvable : {ville}")
        self.latitude = resultats[0]["latitude"]
        self.longitude = resultats[0]["longitude"]
        self.derniere = None

    def temperature(self):
        try:
            reponse = requests.get("https://api.open-meteo.com/v1/forecast",
                                   params={"latitude": self.latitude, "longitude": self.longitude,
                                           "current": "temperature_2m"}, timeout=10)
            reponse.raise_for_status()
            self.derniere = reponse.json()["current"]["temperature_2m"]
        except (requests.RequestException, KeyError) as erreur:
            print(f"  Météo indisponible ({erreur}), on garde la dernière valeur")
        return self.derniere


# --- Stratégies de détection ---------------------------------------------
# Chaque stratégie reçoit l'historique {id: [températures]} des autres joueurs
# et renvoie (suspect, raison).

def strategie_ecart(historique):
    """Le suspect est celui qui s'écarte le plus des autres et dont les valeurs varient le plus.

    Les vraies températures bougent peu en 25 s, alors que l'espion tire une valeur différente à chaque manche.
    """
    scores = {}
    for id_joueur, valeurs in historique.items():
        ecarts = []
        for manche, valeur in enumerate(valeurs):
            autres = [v[manche] for i, v in historique.items() if i != id_joueur and manche < len(v)]
            if autres:
                ecarts.append(abs(valeur - statistics.median(autres)))
        ecart_moyen = statistics.mean(ecarts) if ecarts else 0
        instabilite = statistics.pstdev(valeurs) if len(valeurs) > 1 else 0
        scores[id_joueur] = ecart_moyen + instabilite

    suspect = max(scores, key=scores.get)
    return suspect, f"score {scores[suspect]:.2f} (écart à la médiane + instabilité)"


def strategie_llm(historique, config_ollama):
    """Demande l'avis du LLM local, et revient à strategie_ecart s'il ne donne pas un id valide."""
    tableau = "\n".join(f"- {i} : {', '.join(f'{v:.1f}' for v in valeurs)} °C"
                        for i, valeurs in historique.items())
    question = ("Plusieurs capteurs de villes voisines mesurent la température. L'un d'eux est un espion "
                "qui publie de fausses valeurs, différentes d'environ 10 % et qui changent à chaque mesure.\n"
                f"Mesures successives :\n{tableau}\n"
                "Quel capteur est l'espion ? Réponds uniquement par son identifiant.")
    try:
        reponse = requests.post(f"{config_ollama['url']}/api/chat", timeout=60, json={
            "model": config_ollama["modele"],
            "messages": [{"role": "user", "content": question}],
            "stream": False,
            "think": False,
        })
        reponse.raise_for_status()
        texte = reponse.json()["message"]["content"]
    except (requests.RequestException, KeyError) as erreur:
        print(f"  LLM indisponible ({erreur})")
        texte = ""

    # On garde l'id le plus long trouvé dans la réponse, pour ne pas confondre rpi1 et rpi10
    trouves = [i for i in historique if i in texte]
    if trouves:
        suspect = max(trouves, key=len)
        return suspect, f"avis du LLM : {texte.strip()[:100]}"
    suspect, raison = strategie_ecart(historique)
    return suspect, f"LLM sans réponse exploitable, {raison}"


# --- Joueur --------------------------------------------------------------

class Joueur:
    def __init__(self, config):
        self.config = config
        self.id = config["id"]
        self.meteo = Meteo(config["ville"])
        self.verrou = threading.Lock()
        self.role = None
        self.historique = {}  # id -> températures reçues des autres joueurs, dans l'ordre des manches
        self.partie = 0       # incrémenté à chaque partie, pour arrêter une partie devenue obsolète

        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"joueur-{self.id}")
        # Si le joueur disparaît sans prévenir, le broker annonce son départ à sa place
        self.client.will_set(f"iot/joueurs/{self.id}", json.dumps({"id": self.id, "en_ligne": False}),
                             qos=1, retain=True)
        self.client.on_connect = self._on_connect
        self.client.message_callback_add(f"iot/role/{self.id}", self._on_role)
        self.client.message_callback_add("iot/partie/etat", self._on_etat)
        self.client.message_callback_add("iot/capteurs/+/temperature", self._on_temperature)

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

    # --- Réception MQTT -------------------------------------------------

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        print(f"[{self.id}] connecté au broker ({reason_code})")
        client.subscribe([(f"iot/role/{self.id}", 1), ("iot/partie/etat", 1), ("iot/capteurs/+/temperature", 0)])
        self.annoncer_presence()

    def annoncer_presence(self):
        presence = {"id": self.id, "ville": self.config["ville"], "en_ligne": True}
        # Champs facultatifs utilisés par l'interface (nom, arch, api)
        presence.update(self.config.get("interface", {}))
        self.publier(f"iot/joueurs/{self.id}", presence, retain=True)

    def _on_etat(self, client, userdata, msg):
        if json.loads(msg.payload).get("etat") == "inscription":
            with self.verrou:
                self.partie += 1  # une éventuelle partie en cours s'arrête
                self.role = None
            print(f"[{self.id}] inscription ouverte, en attente du rôle")
            self.annoncer_presence()

    def _on_role(self, client, userdata, msg):
        with self.verrou:
            if self.role is not None:
                return
            self.role = json.loads(msg.payload)["role"]
            self.historique = {}
            self.partie += 1
            partie = self.partie
        print(f"[{self.id}] rôle reçu : {self.role.upper()}")
        threading.Thread(target=self.jouer, args=(partie,), daemon=True).start()

    def _on_temperature(self, client, userdata, msg):
        expediteur = msg.topic.split("/")[2]
        if expediteur == self.id:
            return
        temperature = json.loads(msg.payload).get("temperature")
        if isinstance(temperature, (int, float)):
            with self.verrou:
                if self.role is not None:
                    self.historique.setdefault(expediteur, []).append(temperature)

    # --- Déroulement d'une partie --------------------------------------

    def jouer(self, partie):
        for manche in range(1, 6):
            if self.partie != partie:
                return
            temperature = self.mesurer()
            if temperature is not None:
                self.publier(f"iot/capteurs/{self.id}/temperature", {
                    "id": self.id, "ville": self.config["ville"], "temperature": round(temperature, 1),
                    "manche": manche, "ts": int(time.time()),
                })
                print(f"[{self.id}] manche {manche} : {temperature:.1f} °C")
            time.sleep(DUREE_MANCHE)

        if self.partie == partie:
            self.voter()

    def mesurer(self):
        if self.role != "espion":
            return self.meteo.temperature()

        # L'espion part de la moyenne des dernières valeurs des autres (ou de la sienne au début)
        with self.verrou:
            dernieres = [valeurs[-1] for valeurs in self.historique.values()]
        base = statistics.mean(dernieres) if dernieres else self.meteo.temperature()
        if base is None:
            return None
        return base * (1 + random.choice((-1, 1)) * random.uniform(*ECART_ESPION))

    def voter(self):
        with self.verrou:
            historique = {i: list(v) for i, v in self.historique.items()}
        if not historique:
            print(f"[{self.id}] aucune température reçue, pas de vote")
            return

        if self.config.get("strategie") == "llm":
            suspect, raison = strategie_llm(historique, self.config["ollama"])
        else:
            suspect, raison = strategie_ecart(historique)

        self.publier(f"iot/votes/{self.id}", {"votant": self.id, "suspect": suspect, "raison": raison})
        self.publier(f"iot/chat/{self.id}", {"text": f"Je soupçonne {suspect}."})
        print(f"[{self.id}] vote contre {suspect} : {raison}")


def main():
    sys.stdout.reconfigure(line_buffering=True)  # journaux visibles tout de suite, même redirigés
    chemin = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("config.json")
    if not chemin.exists():
        sys.exit(f"Config introuvable : {chemin} (copie config.example.json en config.json)")
    Joueur(json.loads(chemin.read_text(encoding="utf-8"))).lancer()


if __name__ == "__main__":
    main()
