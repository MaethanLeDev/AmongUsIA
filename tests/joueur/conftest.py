"""Fixtures du joueur : un Joueur branché sur le faux client MQTT, avec Ollama et Open-Meteo simulés au niveau HTTP.

Les tests regardent ce qui sort du joueur (publications MQTT, requêtes à Ollama), pas comment il range ses données :
une réorganisation de joueur.py ne doit pas casser les tests tant que le comportement ne change pas.
"""
from types import SimpleNamespace

import joueur
import pytest
import requests
from aides import ID_PARTIE, FausseReponseHTTP

from ia import Partie

JOUEURS = ["rpi1", "rpi2", "rpi3", "rpi4"]
VOTE_LLM = '{"suspect": "rpi3", "raison": "Ses valeurs sautent."}'


@pytest.fixture
def temps(figer_temps):
    return figer_temps(joueur)


@pytest.fixture
def llm(monkeypatch):
    """Faux Ollama (requests.post) : .vote pour les réponses JSON, .parole sinon, .pendant(corps) appelé pendant
    la « réflexion ». .requetes garde chaque requête, .prompts() le dernier message de chacune."""
    faux = SimpleNamespace(vote=VOTE_LLM, parole="Kaito, explique-toi.", pendant=None, requetes=[])
    faux.prompts = lambda: [r["json"]["messages"][-1]["content"] for r in faux.requetes]

    def post(url, json=None, timeout=None):
        faux.requetes.append({"url": url, "json": json, "timeout": timeout})
        if faux.pendant:
            faux.pendant(json)
        contenu = faux.vote if json.get("format") == "json" else faux.parole
        return FausseReponseHTTP({"message": {"role": "assistant", "content": contenu}})

    monkeypatch.setattr(requests, "post", post)
    return faux


@pytest.fixture
def meteo_service(monkeypatch):
    """Faux Open-Meteo (requests.get) : .valeur est un nombre, None (réponse sans température) ou une fonction."""
    service = SimpleNamespace(valeur=12.34)

    def get(url, params=None, timeout=None):
        if "open-meteo" not in url:
            return FausseReponseHTTP({"models": []})   # /api/tags d'Ollama (GET /health)
        valeur = service.valeur() if callable(service.valeur) else service.valeur
        return FausseReponseHTTP({"current": {} if valeur is None else {"temperature_2m": valeur}})

    monkeypatch.setattr(requests, "get", get)
    return service


@pytest.fixture
def joueur_jeu(faux_mqtt, config_joueur, temps, llm, meteo_service):
    """Le joueur rpi1. Ses actions (mesurer, parler, voter…) s'exécutent tout de suite, sans thread."""
    j = joueur.Joueur(config_joueur)

    def executer(fonction, *args):
        fonction(*args)
    j.en_arriere_plan = executer
    return j


@pytest.fixture
def donner_role(joueur_jeu):
    """donner_role("espion") : le maître envoie son rôle à rpi1."""
    def donner(role="normal", partie=ID_PARTIE):
        joueur_jeu.client.injecter("iot/role/rpi1", {"role": role, "partie": partie})
    return donner


@pytest.fixture
def annoncer_phase(joueur_jeu):
    """annoncer_phase("vote", manche=2) : le maître publie iot/partie/etat (retenu). La phase finit à ID_PARTIE + 60."""
    def annoncer(etat, manche=1, partie=ID_PARTIE, vivants=JOUEURS, **champs):
        contenu = {"etat": etat, "partie": partie, "manche": manche, "manches_max": 3, "joueurs": JOUEURS,
                   "vivants": list(vivants), "elimines": [], "fin": ID_PARTIE + 60, "echanges": 5, **champs}
        joueur_jeu.client.injecter("iot/partie/etat", contenu, retain=True)
        return contenu
    return annoncer


@pytest.fixture
def en_partie(joueur_jeu, donner_role, annoncer_phase):
    """rpi1 a reçu son rôle et la manche 1 est annoncée (phase sans action : débat)."""
    def preparer(role="normal"):
        donner_role(role)
        annoncer_phase("debat")
        return joueur_jeu
    return preparer


@pytest.fixture
def partie_type():
    """Une Partie vue par rpi1 (normal), manche 1, avec les noms et les mesures de 4 joueurs. rpi3 est instable."""
    partie = Partie(ID_PARTIE, "rpi1", "normal")
    partie.participants, partie.vivants, partie.numero = list(JOUEURS), list(JOUEURS), 1
    partie.noms = {"rpi1": "Sherlock", "rpi2": "Mimi", "rpi3": "Kaito", "rpi4": "Yuki"}
    partie.villes = {"rpi1": "Annecy", "rpi2": "Seynod", "rpi3": "Poisy", "rpi4": "Sévrier"}
    partie.manche().mesures = {
        "rpi1": [12.0, 12.1, 12.0, 12.1, 12.0],
        "rpi2": [12.2, 12.2, 12.3, 12.2, 12.2],
        "rpi3": [13.4, 11.0, 13.9, 10.8, 13.6],
        "rpi4": [11.9, 12.0, 11.9, 12.0, 12.0],
    }
    return partie
