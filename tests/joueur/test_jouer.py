"""jouer.py : jouer sans cloner le dépôt. GitHub est simulé, et rien n'est écrit hors du dossier temporaire."""
import io
import re
import sys
import tomllib
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

RACINE = Path(__file__).resolve().parents[2]
sys.path.append(str(RACINE))   # jouer.py est à la racine du dépôt
import jouer  # noqa: E402 (après le sys.path)


@pytest.fixture
def github(monkeypatch):
    """github({chemin: contenu}) sert cette archive ; github(erreur) simule une panne."""
    def servir(reponse):
        def get(url, timeout=None):
            if isinstance(reponse, Exception):
                raise reponse
            tampon = io.BytesIO()
            with zipfile.ZipFile(tampon, "w") as archive:
                for chemin, contenu in reponse.items():
                    archive.writestr(f"AmongUsIA-main/{chemin}", contenu)
            return SimpleNamespace(content=tampon.getvalue(), raise_for_status=lambda: None)

        monkeypatch.setattr(requests, "get", get)
    return servir


def test_ne_garde_que_les_scripts_du_joueur(github, tmp_path):
    github({"joueur/joueur.py": "", "joueur/ia.py": "", "joueur/README.md": "", "serveur.py": "", "tests/joueur/test_ia.py": ""})

    jouer.recuperer_code(tmp_path)

    assert sorted(p.name for p in tmp_path.iterdir()) == ["ia.py", "joueur.py"]


def test_remplace_l_ancienne_version(github, tmp_path):
    (tmp_path / "joueur.py").write_text("ancien", encoding="utf-8")
    github({"joueur/joueur.py": "nouveau"})

    jouer.recuperer_code(tmp_path)

    assert (tmp_path / "joueur.py").read_text(encoding="utf-8") == "nouveau"


def test_sans_internet_garde_la_version_deja_recuperee(github, tmp_path):
    (tmp_path / "joueur.py").write_text("ancien", encoding="utf-8")
    github(requests.ConnectionError())

    jouer.recuperer_code(tmp_path)

    assert (tmp_path / "joueur.py").read_text(encoding="utf-8") == "ancien"


def test_reponse_illisible_garde_la_version_deja_recuperee(monkeypatch, tmp_path):
    (tmp_path / "joueur.py").write_text("ancien", encoding="utf-8")
    portail_wifi = SimpleNamespace(content=b"<html>Connectez-vous</html>", raise_for_status=lambda: None)
    monkeypatch.setattr(requests, "get", lambda url, timeout=None: portail_wifi)

    jouer.recuperer_code(tmp_path)

    assert (tmp_path / "joueur.py").read_text(encoding="utf-8") == "ancien"


def test_sans_internet_au_premier_lancement_explique(github, tmp_path):
    github(requests.ConnectionError())

    with pytest.raises(SystemExit, match="Internet au premier lancement"):
        jouer.recuperer_code(tmp_path)


def test_archive_sans_joueur_est_refusee(github, tmp_path):
    github({"serveur.py": ""})

    with pytest.raises(SystemExit, match=re.escape("joueur.py absent")):
        jouer.recuperer_code(tmp_path)


@pytest.fixture
def lancement(github, monkeypatch, tmp_path):
    """Les arguments avec lesquels joueur.py est lancé."""
    github({"joueur/joueur.py": ""})
    monkeypatch.setattr(jouer, "DOSSIER", tmp_path)
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(sys, "stdout", SimpleNamespace(reconfigure=lambda **k: None, write=lambda t: None, flush=lambda: None))
    monkeypatch.setattr(sys, "stderr", SimpleNamespace(reconfigure=lambda **k: None, write=lambda t: None, flush=lambda: None))
    recus = []
    monkeypatch.setattr(jouer.runpy, "run_path", lambda script, run_name: recus.extend(sys.argv))

    def lancer(*arguments):
        monkeypatch.setattr(sys, "argv", ["jouer.py", *arguments])
        jouer.main()
        return recus
    return lancer


def test_config_rangee_hors_du_code_remplace(lancement, tmp_path):
    assert lancement()[1] == str(tmp_path / "config.json")


def test_config_en_argument_est_transmise(lancement):
    assert lancement("autre.json")[1] == "autre.json"


def test_option_reglages_est_transmise_avec_la_config_par_defaut(lancement, tmp_path):
    assert lancement("--reglages")[1:] == [str(tmp_path / "config.json"), "--reglages"]


def test_memes_dependances_que_le_projet():
    entete = re.search(r"^# /// script\n(.*?)^# ///$", (RACINE / "jouer.py").read_text(encoding="utf-8"), re.S | re.M)
    script = tomllib.loads("".join(ligne[2:] for ligne in entete[1].splitlines(keepends=True)))
    projet = tomllib.loads((RACINE / "pyproject.toml").read_text(encoding="utf-8"))["project"]

    assert script["dependencies"] == projet["dependencies"]
    assert script["requires-python"] == projet["requires-python"]
