"""Fixtures du maître du jeu : un MaitreDuJeu branché sur le faux client MQTT, avec le temps figé."""
import maitre
import pytest
from aides import ID_PARTIE

JOUEURS = ("rpi1", "rpi2", "rpi3", "rpi4", "rpi5")


@pytest.fixture
def temps(figer_temps):
    return figer_temps(maitre)


@pytest.fixture
def maitre_jeu(faux_mqtt, reglages_maitre, temps):
    return maitre.MaitreDuJeu(reglages_maitre)


@pytest.fixture
def arrivee(maitre_jeu):
    """arrivee("rpi1", "rpi2") : ces joueurs publient leur présence (en ligne)."""
    def arriver(*ids):
        for id_joueur in ids:
            maitre_jeu.client.injecter(f"iot/joueurs/{id_joueur}", {"id": id_joueur, "en_ligne": True}, retain=True)
    return arriver


@pytest.fixture
def en_partie(maitre_jeu, arrivee):
    """Met le maître en pleine manche 1 : les joueurs sont connectés, rpi3 est l'espion, le vote est ouvert."""
    def preparer(joueurs=JOUEURS, espion="rpi3", vote_ouvert=True):
        arrivee(*joueurs)
        maitre_jeu.partie, maitre_jeu.espion = ID_PARTIE, espion
        maitre_jeu.participants, maitre_jeu.vivants = list(joueurs), list(joueurs)
        maitre_jeu.manche, maitre_jeu.manches_max = 1, len(joueurs) - 1
        maitre_jeu.vote_ouvert = vote_ouvert
        return maitre_jeu
    return preparer


@pytest.fixture
def voter(maitre_jeu):
    """voter("rpi1", "rpi3") : rpi1 publie un vote valide de la manche en cours (champs modifiables)."""
    def vote(votant, suspect, **champs):
        contenu = {"votant": votant, "suspect": suspect, "raison": "test", "calcul": suspect, "strategie": "llm",
                   "partie": maitre_jeu.partie, "manche": maitre_jeu.manche, **champs}
        maitre_jeu.client.injecter(f"iot/votes/{votant}", contenu)
    return vote


@pytest.fixture
def joueurs_scriptes(maitre_jeu):
    """Des faux joueurs qui réagissent aux publications du maître : ils mesurent, répondent quand ils ont
    la parole et votent selon votes_par_manche[manche] = {votant: suspect}."""
    def scripter(votes_par_manche):
        client = maitre_jeu.client

        def reagir(topic, contenu):
            if topic == "iot/partie/etat" and contenu["etat"] == "mesures":
                for id_joueur in contenu["vivants"]:
                    for echange in range(1, contenu["echanges"] + 1):
                        client.injecter(f"iot/capteurs/{id_joueur}/temperature", {
                            "id": id_joueur, "temperature": 12.0, "echange": echange,
                            "manche": contenu["manche"], "partie": contenu["partie"]})
            elif topic == "iot/partie/etat" and contenu["etat"] == "vote":
                for votant, suspect in votes_par_manche.get(contenu["manche"], {}).items():
                    client.injecter(f"iot/votes/{votant}", {
                        "votant": votant, "suspect": suspect, "calcul": suspect, "strategie": "llm",
                        "partie": contenu["partie"], "manche": contenu["manche"]})
            elif topic == "iot/partie/parole":
                client.injecter(f"iot/chat/{contenu['joueur']}", {
                    "text": "Tes valeurs bougent trop.", "partie": contenu["partie"],
                    "manche": contenu["manche"], "tour": contenu["tour"]})

        client.reactions.append(reagir)
    return scripter
