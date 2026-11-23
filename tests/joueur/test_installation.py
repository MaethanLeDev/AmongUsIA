"""Premier lancement du joueur (installation.py) : config créée toute seule, modèle Ollama téléchargé s'il manque."""
import json
from types import SimpleNamespace

import pytest
import requests
from aides import FausseReponseHTTP

import installation
import joueur

URL = "http://127.0.0.1:11434"


class FluxPull:
    """La réponse en flux de POST /api/pull : une ligne JSON par étape."""

    def __init__(self, etapes):
        self.lignes = [json.dumps(e).encode() for e in etapes]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        pass

    def iter_lines(self):
        return iter(self.lignes)


@pytest.fixture
def ollama(monkeypatch):
    """Faux Ollama : .installes (None : il ne répond pas), .pulls garde les modèles demandés à /api/pull."""
    class Etat:
        installes = []
        pulls = []
        etapes = [{"status": "pulling", "total": 100, "completed": 50}, {"status": "success"}]

    def get(url, timeout=None):
        if Etat.installes is None:
            raise requests.ConnectionError("refusé")
        return FausseReponseHTTP({"models": [{"name": m} for m in Etat.installes]})

    def post(url, json=None, stream=False, timeout=None):
        Etat.pulls.append(json["model"])
        return FluxPull(Etat.etapes)

    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(installation.shutil, "which", lambda programme: None)   # pas d'ollama à démarrer
    return Etat


def config_ollama(modele="qwen3:0.6b"):
    return {"ollama": {"url": URL, "modele": modele}}


def test_identifiant_sans_accent_ni_espace():
    assert installation.identifiant("Héloïse 2") == "heloise2"


def test_identifiant_jamais_vide():
    assert installation.identifiant("★★").startswith("joueur")


def test_config_creee_est_acceptee_par_le_joueur(tmp_path, monkeypatch):
    monkeypatch.setattr(installation.sys, "stdin", None)   # lancé sans clavier (service systemd)
    chemin = tmp_path / "config.json"

    installation.creer_config(chemin)

    config = joueur.lire_config(chemin)
    assert config["ville"] in installation.VILLES
    assert config["coordonnees"] == installation.VILLES[config["ville"]]


def test_config_reprend_les_reponses(tmp_path, monkeypatch):
    reponses = iter(["Kuro", "2", "Tu es paranoïaque."])
    monkeypatch.setattr("builtins.input", lambda question: next(reponses))
    monkeypatch.setattr(installation.sys, "stdin", SimpleNamespace(isatty=lambda: True))   # un vrai terminal
    chemin = tmp_path / "config.json"

    installation.creer_config(chemin)

    config = json.loads(chemin.read_text(encoding="utf-8"))
    assert (config["id"], config["interface"]["nom"], config["ville"]) == ("kuro", "Kuro", "Seynod")
    assert config["personnalite"] == "Tu es paranoïaque."


def test_entree_fermee_tire_la_config_au_sort(tmp_path, monkeypatch):
    def fermee(question):
        raise EOFError

    monkeypatch.setattr("builtins.input", fermee)
    monkeypatch.setattr(installation.sys, "stdin", SimpleNamespace(isatty=lambda: True))   # NUL, sous Windows
    chemin = tmp_path / "config.json"

    installation.creer_config(chemin)

    assert joueur.lire_config(chemin)["ville"] in installation.VILLES


def test_nom_propose_numerote_pour_un_id_unique(tmp_path, monkeypatch):
    monkeypatch.setattr(installation.sys, "stdin", None)
    monkeypatch.setattr(installation.random, "randint", lambda debut, fin: 427)
    chemin = tmp_path / "config.json"

    installation.creer_config(chemin)

    assert json.loads(chemin.read_text(encoding="utf-8"))["id"].endswith("427")


def test_ville_hors_liste_sans_coordonnees():
    config = installation.nouvelle_config("Kuro", "Chambéry")

    assert config["ville"] == "Chambéry"
    assert "coordonnees" not in config   # le joueur la géocodera


def test_modele_absent_est_telecharge(ollama):
    installation.preparer_ollama(config_ollama())

    assert ollama.pulls == ["qwen3:0.6b"]


def test_modele_present_pas_de_telechargement(ollama):
    ollama.installes = ["qwen3:0.6b"]

    installation.preparer_ollama(config_ollama())

    assert ollama.pulls == []


def test_modele_latest_compte_comme_present(ollama):
    ollama.installes = ["llama3.2:latest"]

    installation.preparer_ollama(config_ollama("llama3.2"))

    assert ollama.pulls == []


def test_ollama_absent_explique_comment_l_installer(ollama, capsys):
    ollama.installes = None

    installation.preparer_ollama(config_ollama())

    assert "ollama.com/install.sh" in capsys.readouterr().out
    assert ollama.pulls == []


def test_gemini_sans_ollama_n_annonce_pas_un_vote_par_calcul(ollama, capsys):
    ollama.installes = None

    installation.preparer_ollama(config_ollama(), "Gemini")

    assert "Gemini parlera" in capsys.readouterr().out


@pytest.mark.parametrize("url, attendu", [
    ("http://127.0.0.1:11434", True),
    ("http://localhost:11434", True),
    ("http://127.0.0.1:11500", False),   # une passerelle vers une API : « ollama serve » ne la remplacerait pas
    ("http://10.0.0.5:11434", False),
])
def test_seul_l_ollama_de_cette_machine_est_demarre(monkeypatch, url, attendu):
    lances = []
    monkeypatch.setattr(installation.shutil, "which", lambda programme: "/usr/bin/ollama")
    monkeypatch.setattr(installation.subprocess, "Popen", lambda commande, **k: lances.append(commande))
    monkeypatch.setattr(installation, "DEMARRAGE_OLLAMA", 0)

    installation.demarrer_ollama(url)

    assert bool(lances) is attendu


def test_passerelle_arretee_le_dit(ollama, capsys):
    ollama.installes = None

    installation.preparer_ollama({"ollama": {"url": "http://127.0.0.1:11500", "modele": "openai/gpt-oss-120b"}})

    assert "passerelle" in capsys.readouterr().out
    assert ollama.pulls == []


def test_telechargement_refuse_par_ollama(ollama, capsys):
    ollama.etapes = [{"error": "pull model manifest: file does not exist"}]

    assert installation.telecharger(URL, "inconnu:1b") is False
    assert "Ollama refuse" in capsys.readouterr().out
