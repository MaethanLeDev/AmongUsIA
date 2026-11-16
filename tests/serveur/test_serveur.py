"""serveur.py : le côté serveur en une commande. On vérifie le choix du broker, sans Docker ni réseau."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))   # serveur.py est à la racine du dépôt
import serveur  # noqa: E402 (après le sys.path)


class FauxProcessus:
    def __init__(self, commande, **kwargs):
        self.commande = commande


@pytest.fixture
def lances(monkeypatch):
    """Les commandes lancées par subprocess.Popen, sans rien lancer."""
    commandes = []

    def popen(commande, **kwargs):
        commandes.append(commande)
        return FauxProcessus(commande)

    monkeypatch.setattr(serveur.subprocess, "Popen", popen)
    monkeypatch.setattr(serveur, "attendre_broker", lambda delai=0: True)
    return commandes


def test_sans_docker_le_broker_de_test_est_lance(lances, monkeypatch):
    monkeypatch.setattr(serveur.shutil, "which", lambda programme: None)
    processus = []

    serveur.demarrer_broker(processus)

    assert len(processus) == 1
    assert lances[0][-1].endswith("broker_dev.py")


def test_avec_docker_mosquitto_est_demarre(lances, monkeypatch):
    monkeypatch.setattr(serveur.shutil, "which", lambda programme: "/usr/bin/docker")
    lancements = []
    monkeypatch.setattr(serveur.subprocess, "run", lambda commande, cwd: lancements.append(commande) or SimpleNamespace(returncode=0))
    processus = []

    serveur.demarrer_broker(processus)

    assert lancements == [["docker", "compose", "up", "-d"]]
    assert processus == []   # le broker Docker n'est pas un enfant : il reste après Ctrl+C
