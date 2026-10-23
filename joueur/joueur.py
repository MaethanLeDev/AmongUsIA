"""Joueur générique : un capteur de température piloté par une IA Ollama.

Le même script tourne sur toutes les machines. Tout ce qui se personnalise est dans config.json :
ville, modèle Ollama, personnalité, mémoire, nom et apparence dans l'interface.
Il expose aussi l'API HTTP de l'agent du TP « RPi & Ollama » (voir api.py).

Usage : uv run joueur/joueur.py [chemin/vers/config.json]
Protocole : docs/protocole.md
"""
import copy
import json
import random
import socket
import statistics
import sys
import threading
import time
from pathlib import Path

import paho.mqtt.client as mqtt

from api import demarrer_api
from ia import IA, Partie
from meteo import Meteo

DUREE_ECHANGE = 5             # secondes entre deux températures, fixé par le sujet
ECART_ESPION = (0.05, 0.10)   # l'espion décale la moyenne des autres de 5 à 10 %, vers le haut ou le bas
ECART_MIN = 0.3               # °C : près de 0 °C, 10 % ne se verrait pas
BROKER_PAR_DEFAUT = "amongus.local,10.109.150.215"


class Joueur:
    def __init__(self, config):
        self.config = config
        self.id = config["id"]
        self.meteo = Meteo(config["ville"], config.get("coordonnees"))
        self.ia = IA(config)
        self.ia.quand_etat_change = self._llm_change
        self.verrou = threading.Lock()
        self.noms, self.villes = {}, {}   # de chaque joueur vu, gardés même s'il se déconnecte
        self.etat = {}                    # dernier message iot/partie/etat
        self.partie = None                # partie en cours, créée à la réception du rôle
        self.faits = set()                # actions déjà lancées : un message retenu reçu deux fois ne relance rien
        self.url_api = None

        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"joueur-{self.id}")
        # Si le joueur disparaît sans prévenir, le broker annonce son départ à sa place
        self.client.will_set(f"iot/joueurs/{self.id}", json.dumps({"id": self.id, "en_ligne": False}),
                             qos=1, retain=True)
        # Une erreur dans un callback est affichée, sans arrêter le thread réseau (sinon on n'entend plus rien)
        self.client.suppress_exceptions = True
        self.client.enable_logger()
        self.client.on_connect = self._on_connect
        abonnements = {
            "iot/joueurs/+": self._on_presence,
            "iot/partie/etat": self._on_etat,
            f"iot/role/{self.id}": self._on_role,
            "iot/capteurs/+/temperature": self._on_temperature,
            "iot/partie/parole": self._on_parole,
            "iot/chat/+": self._on_chat,
            "iot/votes/+": self._on_vote,
            "iot/partie/verdict": self._on_verdict,
        }
        for topic, fonction in abonnements.items():
            self.client.message_callback_add(topic, fonction)
        self.abonnements = [(topic, 1) for topic in abonnements]

    def lancer(self):
        broker = self.config.get("broker", {})
        hote = connecter(self.client, broker.get("hote", BROKER_PAR_DEFAUT), broker.get("port", 1883))
        port = self.config.get("api", {}).get("port", 5000)
        if port:
            try:
                demarrer_api(self, port)
                self.url_api = f"http://{adresse_locale(hote, broker.get('port', 1883))}:{port}"
                self.log(f"API de l'agent : {self.url_api} (/message, /health, /agent)")
            except OSError as erreur:
                self.log(f"API non démarrée, port {port} occupé ? ({erreur})")
        self.en_arriere_plan(self.meteo.temperature)  # géocode tout de suite : une ville introuvable se voit au lancement
        self.en_arriere_plan(self.verifier_llm)       # de même pour un Ollama arrêté ou un modèle pas installé
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
        self.log(f"connecté au broker ({reason_code}), modèle {self.ia.modele}, stratégie {self.ia.strategie}")
        client.subscribe(self.abonnements)
        self.annoncer_presence()

    def annoncer_presence(self):
        presence = {"id": self.id, "ville": self.config["ville"], "en_ligne": True,
                    "modele": self.ia.modele, "strategie": self.ia.strategie}
        presence.update(self.config.get("interface", {}))  # nom, arch, couleurs
        if self.url_api:
            presence["api"] = self.url_api
        if self.ia.etat_llm:
            presence["llm"] = self.ia.etat_llm  # l'interface affiche « ⚠ LLM injoignable » sur la carte de l'IA
        self.publier(f"iot/joueurs/{self.id}", presence, retain=True)

    def verifier_llm(self):
        alerte = self.ia.verifier()
        if alerte:
            self.log(f"⚠ {alerte}. En attendant, cette IA passera son tour au débat et votera par calcul.")
        else:
            self.log(f"Ollama prêt, modèle {self.ia.modele}")

    def _llm_change(self, etat):
        """Le LLM répond de nouveau, ou plus : on le dit à tout le monde (l'interface l'affiche)."""
        if self.client.is_connected():
            self.annoncer_presence()

    def _on_presence(self, client, userdata, msg):
        presence = lire_json(msg.payload)
        if presence.get("en_ligne"):
            with self.verrou:
                self.noms[expediteur(msg)] = presence.get("nom") or expediteur(msg)
                self.villes[expediteur(msg)] = presence.get("ville", "?")

    def _on_etat(self, client, userdata, msg):
        etat = lire_json(msg.payload)
        with self.verrou:
            precedent, self.etat = self.etat.get("etat"), etat
            if etat.get("etat") in ("inscription", "arret") or \
                    (self.partie and etat.get("partie") not in (None, self.partie.id)):
                self.partie = None
            elif self.partie and etat.get("partie") == self.partie.id:
                self.appliquer(etat)
        if etat.get("etat") != precedent:
            self.log({"inscription": "inscription ouverte, en attente de la partie", "arret": "maître du jeu arrêté",
                      "fini": "partie terminée"}.get(etat.get("etat"), f"phase : {etat.get('etat')}, manche {etat.get('manche')}"))
        self.synchroniser()

    def appliquer(self, etat):
        """Recopie dans la partie ce que le maître annonce (à appeler avec le verrou)."""
        self.partie.participants = etat.get("joueurs") or self.partie.participants
        self.partie.vivants = etat.get("vivants") or self.partie.vivants
        self.partie.numero = etat.get("manche") or self.partie.numero

    def _on_role(self, client, userdata, msg):
        message = lire_json(msg.payload)
        role, id_partie = message.get("role"), message.get("partie")
        if role not in ("normal", "espion"):
            return
        with self.verrou:
            if self.partie and self.partie.id == id_partie:
                return  # rôle renvoyé en double
            self.partie = Partie(id_partie, self.id, role)
            if self.etat.get("partie") == id_partie:
                self.appliquer(self.etat)
        self.log(f"nouvelle partie, rôle secret : {role.upper()}")
        self.synchroniser()

    def _on_temperature(self, client, userdata, msg):
        mesure = lire_json(msg.payload)
        temperature = mesure.get("temperature")
        with self.verrou:
            if self.de_la_partie(mesure) and isinstance(temperature, (int, float)):
                manche = self.partie.manche(mesure.get("manche"))
                manche.mesures.setdefault(msg.topic.split("/")[2], []).append(temperature)

    def _on_chat(self, client, userdata, msg):
        message = lire_json(msg.payload)
        texte = message.get("text")
        with self.verrou:
            if self.de_la_partie(message) and isinstance(texte, str):
                self.partie.manche(message.get("manche")).debat.append((expediteur(msg), texte))

    def _on_vote(self, client, userdata, msg):
        vote = lire_json(msg.payload)
        with self.verrou:
            if self.de_la_partie(vote) and isinstance(vote.get("suspect"), str):
                self.partie.manche(vote.get("manche")).votes[expediteur(msg)] = vote["suspect"]

    def _on_verdict(self, client, userdata, msg):
        verdict = lire_json(msg.payload)
        with self.verrou:
            if not self.de_la_partie(verdict):
                return
            self.partie.manche(verdict.get("manche")).verdict = verdict
            elimine = verdict.get("elimine")
        if elimine == self.id:
            self.log("je suis éliminé·e…")
        elif elimine:
            self.log(f"{self.noms.get(elimine, elimine)} est éliminé·e ({'espion' if verdict.get('etait_espion') else 'innocent·e'})")

    def _on_parole(self, client, userdata, msg):
        parole = lire_json(msg.payload)
        with self.verrou:
            if parole.get("joueur") != self.id or not self.de_la_partie(parole) or self.id not in self.partie.vivants:
                return
            cle = (self.partie.id, parole.get("manche"), "parole", parole.get("tour"))
            if cle in self.faits:
                return
            self.faits.add(cle)
        self.en_arriere_plan(self.parler, parole)

    def de_la_partie(self, message):
        """Le message concerne-t-il la partie en cours ? (à appeler avec le verrou)"""
        return self.partie is not None and message.get("partie", self.partie.id) == self.partie.id

    # --- Ce que la phase attend de nous --------------------------------

    def synchroniser(self):
        """Lance l'action de la phase en cours, une seule fois par manche."""
        actions = {"mesures": self.mesurer, "vote": self.voter, "verdict": self.memoriser}
        with self.verrou:
            p, etat = self.partie, self.etat
            action = actions.get(etat.get("etat"))
            if action is None or p is None or etat.get("partie") != p.id or self.id not in p.vivants:
                return
            cle = (p.id, etat.get("manche"), etat["etat"])
            if cle in self.faits:
                return
            self.faits.add(cle)
        self.en_arriere_plan(action, dict(etat))

    def encore(self, etat):
        """Vrai tant que la phase annoncée par etat est toujours en cours."""
        with self.verrou:
            return (self.partie is not None and self.partie.id == etat.get("partie")
                    and (self.etat.get("etat"), self.etat.get("manche")) == (etat.get("etat"), etat.get("manche")))

    # --- Actions (dans un thread, pour ne pas bloquer le réseau pendant que le LLM réfléchit) ---

    def en_arriere_plan(self, fonction, *args):
        threading.Thread(target=fonction, args=args, daemon=True).start()

    def instantane(self):
        """Copie de la partie, avec les noms et villes à jour, que le LLM peut lire tranquillement."""
        with self.verrou:
            if self.partie is None:
                return None
            partie = copy.deepcopy(self.partie)
            partie.noms, partie.villes = dict(self.noms), dict(self.villes)
        return partie

    def mesurer(self, etat):
        with self.verrou:
            role = self.partie.role if self.partie else None
        debut = time.monotonic()
        for echange in range(1, etat.get("echanges", 5) + 1):
            if not self.encore(etat):
                return
            temperature = self.meteo.temperature() if role == "normal" else self.fausse_temperature(etat["manche"])
            if temperature is not None:
                self.publier(f"iot/capteurs/{self.id}/temperature", {
                    "id": self.id, "ville": self.config["ville"], "temperature": round(temperature, 1),
                    "echange": echange, "manche": etat["manche"], "partie": etat["partie"], "ts": int(time.time()),
                })
                self.log(f"manche {etat['manche']}, échange {echange} : {temperature:.1f} °C")
            # Toutes les 5 s pile, même si l'API météo a mis du temps à répondre
            time.sleep(max(0, debut + echange * DUREE_ECHANGE - time.monotonic()))

    def fausse_temperature(self, manche):
        # L'espion part de la moyenne des dernières valeurs des autres (ou de sa vraie température au début)
        with self.verrou:
            mesures = self.partie.manche(manche).mesures if self.partie else {}
            dernieres = [v[-1] for i, v in mesures.items() if i != self.id and v]
        base = statistics.mean(dernieres) if dernieres else self.meteo.temperature()
        if base is None:
            return None
        ecart = max(abs(base) * random.uniform(*ECART_ESPION), ECART_MIN)
        return base + random.choice((-1, 1)) * ecart

    def parler(self, parole):
        partie = self.instantane()
        if partie is None:
            return
        delai = parole.get("delai", 90)
        self.log(f"a la parole (tour {parole.get('tour')}), réfléchit…")
        debut = time.monotonic()
        texte = self.ia.parler(partie, parole.get("tour", 1), parole.get("tours", 1), delai=max(10, delai - 5))
        duree = time.monotonic() - debut
        if duree > delai:
            self.log(f"({duree:.0f} s) trop tard, la parole est passée : {texte}")
            return
        self.publier(f"iot/chat/{self.id}", {"text": texte, "partie": parole.get("partie"),
                                             "manche": parole.get("manche"), "tour": parole.get("tour")})
        self.log(f"({duree:.0f} s) {texte}")

    def voter(self, etat):
        partie = self.instantane()
        if partie is None or not partie.autres():
            return
        delai = (etat.get("fin") or time.time() + 60) - time.time()
        suspect, raison, calcul = self.ia.voter(partie, delai=max(10, min(delai - 10, 120)))
        if suspect is None:
            self.log("aucune donnée, pas de vote")
            return
        if not self.encore(etat):
            self.log("vote trop tard, ignoré")
            return
        self.publier(f"iot/votes/{self.id}", {"votant": self.id, "suspect": suspect, "raison": raison,
                                              "calcul": calcul, "strategie": self.ia.strategie,
                                              "partie": etat["partie"], "manche": etat["manche"]})
        self.log(f"vote contre {partie.nom(suspect)} : {raison}")

    def memoriser(self, etat):
        """Pendant la pause du verdict, le LLM écrit ses notes sur la manche (option "memoire": "resume")."""
        if self.ia.memoire != "resume":
            return  # les faits (votes, éliminés, répliques) sont déjà gardés, sans LLM
        partie = self.instantane()
        if partie is None:
            return
        delai = (etat.get("fin") or time.time() + 15) - time.time()
        notes = self.ia.resumer(partie, delai=max(5, delai))
        with self.verrou:
            if notes and self.partie and self.partie.id == partie.id:
                self.partie.souvenirs[partie.numero] = notes
        if notes:
            self.log(f"notes de la manche {partie.numero} : {notes}")

    # --- Pour l'API HTTP --------------------------------------------------

    def fiche(self):
        with self.verrou:
            etat, partie = self.etat.get("etat"), self.partie
            vivant = partie is not None and self.id in partie.vivants
        return {
            "id": self.id, "nom": self.ia.nom, "modele": self.ia.modele, "personnalite": self.ia.personnalite,
            "ville": self.config["ville"], "strategie": self.ia.strategie,
            "capacites": ["discuter en se souvenant de la conversation (POST /message)",
                          "lancer une conversation avec un autre agent (POST /discuter)",
                          "jouer au jeu de l'espion par MQTT : mesurer, débattre, voter"],
            "routes": ["POST /message", "GET /health", "GET /agent", "POST /discuter"],
            "jeu": {"phase": etat, "en_partie": partie is not None, "vivant": vivant},
        }

    def sante(self):
        return {"status": "ok", "id": self.id, "broker": self.client.is_connected(), "ollama": self.ia.disponible(),
                "llm": self.ia.etat_llm}


def connecter(client, hotes, port):
    """Se connecte au premier broker joignable de la liste "amongus.local,10.109.150.215"."""
    for hote in (h.strip() for h in hotes.split(",") if h.strip()):
        try:
            client.connect(hote, port)
            return hote
        except OSError as erreur:
            print(f"Broker {hote}:{port} injoignable ({erreur})")
    sys.exit("Aucun broker joignable : vérifie \"broker\" dans config.json et que le broker est lancé.")


def adresse_locale(hote, port):
    """L'adresse IP de cette machine sur le réseau du broker (pour annoncer l'URL de l'API)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect((hote, port))
            return s.getsockname()[0]
    except OSError:
        return socket.gethostname()


def expediteur(msg):
    return msg.topic.split("/")[-1]


def lire_json(payload):
    try:
        contenu = json.loads(payload)
        return contenu if isinstance(contenu, dict) else {}
    except ValueError:
        return {}


def lire_config(chemin):
    """Lit config.json et explique clairement ce qui ne va pas : chacun écrit la sienne à la main."""
    if not chemin.exists():
        sys.exit(f"Config introuvable : {chemin} (copie joueur/config.example.json en joueur/config.json)")
    try:
        config = json.loads(chemin.read_text(encoding="utf-8"))
    except ValueError as erreur:
        sys.exit(f"{chemin} n'est pas du JSON valide : {erreur}")
    erreurs = []
    id_joueur = config.get("id")
    if not isinstance(id_joueur, str) or not id_joueur or any(c in id_joueur for c in " /+#"):
        erreurs.append('"id" : un texte sans espace, ni /, ni +, ni # (ex : "rpi1")')
    if not config.get("ville"):
        erreurs.append('"ville" : la ville dont on publie la température (ex : "Annecy")')
    if config.get("strategie", "llm") not in ("llm", "ecart"):
        erreurs.append('"strategie" : "llm" ou "ecart"')
    if config.get("memoire", "faits") not in ("faits", "resume"):
        erreurs.append('"memoire" : "faits" ou "resume"')
    if erreurs:
        sys.exit(f"{chemin} à corriger :\n  - " + "\n  - ".join(erreurs))
    config.setdefault("ollama", {})
    config["ollama"].setdefault("url", "http://127.0.0.1:11434")
    config["ollama"].setdefault("modele", "qwen3:0.6b")
    return config


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)  # visibles tout de suite, même redirigés
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    chemin = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("config.json")
    Joueur(lire_config(chemin)).lancer()


if __name__ == "__main__":
    main()
