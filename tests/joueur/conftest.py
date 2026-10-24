"""Fixtures du joueur : un Joueur branché sur le faux client MQTT, le temps figé, et ses actions enregistrées."""
import joueur
import pytest
from aides import ID_PARTIE

from ia import Partie

JOUEURS = ["rpi1", "rpi2", "rpi3", "rpi4"]


@pytest.fixture
def temps(figer_temps):
    return figer_temps(joueur)


@pytest.fixture
def joueur_jeu(faux_mqtt, config_joueur, temps):
    """Le joueur rpi1. Les actions lancées en arrière-plan ne s'exécutent pas : elles sont notées dans j.lances."""
    j = joueur.Joueur(config_joueur)
    j.lances = []

    def noter(fonction, *args):
        j.lances.append((fonction.__name__, *args))
    j.en_arriere_plan = noter
    return j


@pytest.fixture
def lances(joueur_jeu):
    """Les noms des actions lancées, dans l'ordre : ["mesurer", "voter", ...]."""
    def noms():
        return [action[0] for action in joueur_jeu.lances]
    return noms


@pytest.fixture
def donner_role(joueur_jeu):
    """donner_role("espion") : le maître envoie son rôle à rpi1."""
    def donner(role="normal", partie=ID_PARTIE):
        joueur_jeu.client.injecter("iot/role/rpi1", {"role": role, "partie": partie})
    return donner


@pytest.fixture
def annoncer_phase(joueur_jeu):
    """annoncer_phase("vote", manche=2) : le maître publie iot/partie/etat (retenu)."""
    def annoncer(etat, manche=1, partie=ID_PARTIE, vivants=JOUEURS, **champs):
        contenu = {"etat": etat, "partie": partie, "manche": manche, "manches_max": 3, "joueurs": JOUEURS,
                   "vivants": list(vivants), "elimines": [], "fin": ID_PARTIE + 60, **champs}
        joueur_jeu.client.injecter("iot/partie/etat", contenu, retain=True)
        return contenu
    return annoncer


@pytest.fixture
def en_partie(joueur_jeu, donner_role, annoncer_phase):
    """rpi1 a reçu son rôle et la manche 1 est annoncée (phase sans action : débat)."""
    def preparer(role="normal"):
        donner_role(role)
        annoncer_phase("debat")
        joueur_jeu.lances.clear()
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
