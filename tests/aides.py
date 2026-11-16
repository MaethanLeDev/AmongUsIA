"""Outils des tests : faux client MQTT, fausse réponse HTTP, temps figé, condition instantanée (importés par les tests)."""
import json
import threading
from collections import namedtuple

import requests

ID_PARTIE = 1761200000   # horodatage de la partie type, et heure du temps figé
Publication = namedtuple("Publication", "topic contenu retain")


def correspond(filtre, topic):
    """Un filtre MQTT (+ et #) correspond-il au topic ?"""
    f, t = filtre.split("/"), topic.split("/")
    for i, morceau in enumerate(f):
        if morceau == "#":
            return True
        if i >= len(t) or morceau not in ("+", t[i]):
            return False
    return len(f) == len(t)


class FauxMessage:
    def __init__(self, topic, payload, retain=False):
        self.topic, self.payload, self.retain, self.qos = topic, payload, retain, 1


class FausseInfo:
    """Ce que renvoie client.publish() : le maître appelle wait_for_publish() en s'arrêtant."""

    rc = 0

    def wait_for_publish(self, timeout=None):
        return None


class FauxClientMQTT:
    """Remplace paho.mqtt.client.Client : enregistre ce qui est publié, et permet d'injecter des messages."""

    def __init__(self, *args, client_id="", **kwargs):
        self.client_id = client_id
        self.publications = []    # Publication(topic, contenu JSON décodé, retain), dans l'ordre
        self.will = None          # (topic, contenu, retain)
        self.callbacks = {}       # filtre -> fonction(client, userdata, msg)
        self.abonnements = []
        self.reactions = []       # fonction(topic, contenu) appelée à chaque publication : des joueurs scriptés
        self.hotes_injoignables = set()
        self.hote = None
        self.connecte = False
        self.deconnecte = False
        self.on_connect = None
        self.suppress_exceptions = False

    # --- L'API de paho utilisée par les scripts ---

    def will_set(self, topic, payload=None, qos=0, retain=False):
        self.will = (topic, json.loads(payload), retain)

    def enable_logger(self, logger=None):
        pass

    def message_callback_add(self, filtre, fonction):
        self.callbacks[filtre] = fonction

    def connect(self, hote, port=1883, *args, **kwargs):
        if hote in self.hotes_injoignables:
            raise OSError(f"{hote} injoignable")
        self.hote, self.connecte = hote, True

    def is_connected(self):
        return self.connecte

    def subscribe(self, topics, qos=0):
        self.abonnements.append(topics)

    def publish(self, topic, payload=None, qos=0, retain=False):
        contenu = json.loads(payload) if payload else None
        self.publications.append(Publication(topic, contenu, retain))
        for reaction in list(self.reactions):
            reaction(topic, contenu)
        return FausseInfo()

    def loop_start(self):
        pass

    def loop_stop(self):
        pass

    def loop_forever(self):
        pass

    def disconnect(self):
        self.connecte, self.deconnecte = False, True

    # --- Pour les tests ---

    def injecter(self, topic, contenu, retain=False):
        """Livre un message comme le ferait le broker (contenu : dict encodé en JSON, ou octets bruts)."""
        payload = contenu if isinstance(contenu, bytes) else json.dumps(contenu, ensure_ascii=False).encode("utf-8")
        message = FauxMessage(topic, payload, retain)
        for filtre, fonction in list(self.callbacks.items()):
            if correspond(filtre, topic):
                fonction(self, None, message)

    def publies(self, topic):
        """Les contenus publiés sur ce topic (jokers acceptés), dans l'ordre."""
        return [p.contenu for p in self.publications if correspond(topic, p.topic)]

    def dernier(self, topic):
        publies = self.publies(topic)
        return publies[-1] if publies else None

    def retenu(self, topic):
        """La dernière publication exacte sur ce topic (pour vérifier son drapeau retain)."""
        return next((p for p in reversed(self.publications) if p.topic == topic), None)


class FausseReponseHTTP:
    """Ce que renvoie requests.get/post simulé : contenu JSON et code HTTP."""

    def __init__(self, contenu, code=200):
        self.contenu, self.status_code = contenu, code
        self.ok = code < 400

    def json(self):
        return self.contenu

    def raise_for_status(self):
        if not self.ok:
            raise requests.HTTPError(f"{self.status_code}")


class FauxTemps:
    """Remplace le module time d'un script : l'heure est figée et sleep() la fait avancer sans attendre."""

    def __init__(self, maintenant=ID_PARTIE):
        self.maintenant = float(maintenant)
        self.sommeils = []

    def time(self):
        return self.maintenant

    def monotonic(self):
        return self.maintenant

    def sleep(self, secondes):
        self.sommeils.append(secondes)
        self.maintenant += max(0, secondes)


class ConditionInstantanee(threading.Condition):
    """Condition dont wait(n) fait avancer le temps figé de n secondes au lieu d'attendre (boucles d'attente).

    au_reveil(temps) est appelé après chaque attente : un test y fait arriver des joueurs ou presse Entrée.
    """

    def __init__(self, temps, au_reveil=None):
        super().__init__()
        self.temps, self.au_reveil = temps, au_reveil

    def wait(self, timeout=None):
        self.temps.maintenant += timeout or 0
        if self.au_reveil:
            self.au_reveil(self.temps)
        return False
