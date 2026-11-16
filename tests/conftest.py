"""Fixtures communes aux tests Python : faux client MQTT, temps figé, réglages et messages types.

Les tests tournent sans broker, sans Ollama et sans Internet : paho est remplacé par FauxClientMQTT (aides.py),
requests est simulé dans chaque test, et le module time des scripts est remplacé par FauxTemps.
"""
import argparse
import copy
import sys
from pathlib import Path

import paho.mqtt.client as mqtt
import pytest

# Les scripts ne sont pas un paquet (uv run joueur/joueur.py) : on rend leurs dossiers importables, et tests/ pour aides.py
RACINE = Path(__file__).resolve().parent.parent
for dossier in ("joueur", "maitre_du_jeu", "outils", "tests"):
    if str(RACINE / dossier) not in sys.path:
        sys.path.insert(0, str(RACINE / dossier))

from aides import ID_PARTIE, FauxClientMQTT, FauxTemps  # noqa: E402 (après le sys.path)


@pytest.fixture
def faux_mqtt(monkeypatch):
    """Remplace paho.mqtt.client.Client. Renvoie la liste des faux clients créés."""
    clients = []

    def fabrique(*args, **kwargs):
        client = FauxClientMQTT(*args, **kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(mqtt, "Client", fabrique)
    return clients


@pytest.fixture
def figer_temps(monkeypatch):
    """figer_temps(module, ...) remplace le module time de ces scripts par un même FauxTemps, et le renvoie."""
    def figer(*modules):
        temps = FauxTemps()
        for module in modules:
            monkeypatch.setattr(module, "time", temps)
        return temps
    return figer


@pytest.fixture
def reglages_maitre(tmp_path):
    """Les options de maitre.py, avec des délais très courts : une attente qui expire ne coûte que 50 ms."""
    return argparse.Namespace(
        broker="localhost", port=1883, min_joueurs=3, max_joueurs=12, auto=30, echanges=5, tours=2,
        delai_parole=0.05, pause=0, delai_vote=0.05, pause_verdict=0, pause_fin=0, manches_max=0,
        majorite=False, stats=tmp_path / "stats.json", tp=False,
    )


# Une config.json type, telle que la renvoie lire_config (valeurs par défaut d'Ollama remplies)
CONFIG_TYPE = {
    "id": "rpi1", "ville": "Annecy", "coordonnees": [45.899, 6.129],
    "broker": {"hote": "localhost", "port": 1883},
    "ollama": {"url": "http://127.0.0.1:11434", "modele": "qwen3:0.6b"},
    "personnalite": "Tu es un détective froid et méthodique.",
    "strategie": "llm", "memoire": "faits",
    "interface": {"nom": "Sherlock", "arch": "stratege", "couleurs": {"accent": "#c1121f"}},
    "api": {"port": 0},
}


@pytest.fixture
def config_joueur(request):
    """Une copie de CONFIG_TYPE. Un test change des réglages avec
    @pytest.mark.parametrize("config_joueur", [{"memoire": "resume"}], indirect=True)."""
    return {**copy.deepcopy(CONFIG_TYPE), **getattr(request, "param", {})}


@pytest.fixture
def etat_partie():
    """Un message iot/partie/etat type (docs/protocole.md) : manche 2, rpi2 éliminé à la manche 1."""
    return {"etat": "debat", "partie": ID_PARTIE, "manche": 2, "manches_max": 4,
            "joueurs": ["rpi1", "rpi2", "rpi3", "rpi4", "rpi5"], "vivants": ["rpi1", "rpi3", "rpi4", "rpi5"],
            "elimines": [{"id": "rpi2", "manche": 1}], "tours": 2, "fin": None}
