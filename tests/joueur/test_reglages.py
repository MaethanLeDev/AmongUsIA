"""Le menu de réglages (reglages.py) : choix du LLM et des réglages. Clavier et Ollama simulés, aucun réseau."""
import json
import sys
from types import SimpleNamespace

import pytest

import ia
import installation
import joueur
import reglages

INSTALLES = ["llama3.2:1b", "gemma3:1b"]   # dans le menu : 1, 2, puis 3 Gemini, 4 télécharger, 5 autre adresse
PASSERELLE = "http://127.0.0.1:11500"


@pytest.fixture
def serveurs(monkeypatch):
    """Les modèles de chaque adresse Ollama ; une adresse absente ne répond pas."""
    connus = {reglages.OLLAMA_LOCAL: list(INSTALLES)}
    monkeypatch.setattr(reglages, "modeles_installes", lambda url: connus.get(url))
    monkeypatch.setattr(reglages, "demarrer_ollama", lambda url: None)
    return connus


@pytest.fixture
def clavier(monkeypatch):
    """clavier("1", "") : ce que tape le joueur, dans l'ordre. La clé de getpass vient de la même liste."""
    def taper(*reponses):
        suite = iter(reponses)

        def lire(question=""):
            reponse = next(suite, EOFError)
            if reponse in (EOFError, KeyboardInterrupt):
                raise reponse
            return reponse

        monkeypatch.setattr("builtins.input", lire)
        monkeypatch.setattr(reglages.getpass, "getpass", lire)
        monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: True))
    return taper


@pytest.fixture
def avec_gemini(config_joueur):
    config_joueur.update(gemini={"cle_api": "cle-de-test", "modele": "gemini-test"}, fournisseur="gemini")
    return config_joueur


def test_choisir_un_modele_installe(serveurs, clavier, config_joueur):
    clavier("2")

    reglages.regler_llm(config_joueur)

    assert (config_joueur["fournisseur"], config_joueur["ollama"]["modele"]) == ("ollama", "gemma3:1b")


def test_entree_prend_un_modele_deja_installe(serveurs, clavier, config_joueur):
    clavier("")   # qwen3:0.6b, le modèle par défaut, n'est pas installé : pas question de le télécharger

    reglages.regler_llm(config_joueur)

    assert config_joueur["ollama"]["modele"] == "llama3.2:1b"


def test_entree_garde_le_modele_actuel(serveurs, clavier, config_joueur):
    config_joueur["ollama"]["modele"] = "gemma3:1b"
    clavier("")

    reglages.regler_llm(config_joueur)

    assert config_joueur["ollama"]["modele"] == "gemma3:1b"


def test_choisir_gemini(serveurs, clavier, config_joueur):
    clavier("3", "cle-de-test", "gemini-test")

    reglages.regler_llm(config_joueur)

    cerveau = ia.IA(config_joueur)
    assert (cerveau.fournisseur, cerveau.modele_actif) == ("Gemini", "gemini-test")


def test_gemini_garde_un_modele_installe_en_secours(serveurs, clavier, config_joueur):
    clavier("3", "cle-de-test", "")

    reglages.regler_llm(config_joueur)

    assert config_joueur["ollama"]["modele"] == "llama3.2:1b"


def test_revenir_au_modele_local_garde_la_cle(serveurs, clavier, avec_gemini):
    clavier("1")

    reglages.regler_llm(avec_gemini)

    assert ia.IA(avec_gemini).fournisseur == "Ollama"
    assert avec_gemini["gemini"]["cle_api"] == "cle-de-test"


def test_revenir_a_gemini_sans_retaper_la_cle(serveurs, clavier, avec_gemini):
    avec_gemini["fournisseur"] = "ollama"
    clavier("3", "", "")

    reglages.regler_llm(avec_gemini)

    assert ia.IA(avec_gemini).fournisseur == "Gemini"


def test_entree_garde_gemini(serveurs, clavier, avec_gemini):
    clavier("", "", "")

    reglages.regler_llm(avec_gemini)

    assert ia.IA(avec_gemini).fournisseur == "Gemini"


def test_gemini_sans_cle_revient_au_choix(serveurs, clavier, config_joueur):
    clavier("3", "", "2")

    reglages.regler_llm(config_joueur)

    assert config_joueur["ollama"]["modele"] == "gemma3:1b"


def test_config_d_avant_avec_une_cle_reste_sur_gemini(config_joueur):
    config_joueur["gemini"] = {"cle_api": "cle-de-test"}   # pas de champ "fournisseur"

    assert ia.IA(config_joueur).fournisseur == "Gemini"


def test_telecharger_un_autre_modele(serveurs, clavier, config_joueur):
    clavier("4", "tinyllama")

    reglages.regler_llm(config_joueur)

    assert config_joueur["ollama"]["modele"] == "tinyllama"


def test_passerelle_vers_une_api(serveurs, clavier, config_joueur):
    serveurs[PASSERELLE] = ["openai/gpt-oss-20b"]
    clavier("5", "127.0.0.1:11500", "1")

    reglages.regler_llm(config_joueur)

    assert config_joueur["ollama"] == {"url": PASSERELLE, "modele": "openai/gpt-oss-20b"}


def test_numero_invalide_redemande(serveurs, clavier, config_joueur):
    clavier("9", "deux", "2")

    reglages.regler_llm(config_joueur)

    assert config_joueur["ollama"]["modele"] == "gemma3:1b"


def test_la_cle_ne_s_affiche_jamais(serveurs, clavier, avec_gemini, tmp_path, capsys):
    clavier("")

    reglages.regler(tmp_path / "config.json", avec_gemini)

    assert "cle-de-test" not in capsys.readouterr().out


def test_premier_lancement_demande_le_llm_puis_joue(serveurs, clavier, config_joueur, tmp_path):
    clavier("2", "")
    chemin = tmp_path / "config.json"

    reglages.regler(chemin, config_joueur, premiere=True)

    assert joueur.lire_config(chemin)["ollama"]["modele"] == "gemma3:1b"


@pytest.mark.parametrize("numero, reponses, champ, attendu", [
    (2, ["2"], "strategie", "ecart"),
    (2, ["3"], "vote_honnete", "calcul"),
    (5, ["Tu es jovial."], "personnalite", "Tu es jovial."),
    (7, ["2"], "memoire", "resume"),
    (8, ["2"], "meteo", "historique"),
    (9, ["rpi9"], "id", "rpi9"),
    (9, ["rpi 9"], "id", "rpi1"),
    (10, ["10.0.0.5"], "broker", {"hote": "10.0.0.5", "port": 1883}),
    (11, ["5001"], "api", {"port": 5001}),
    (11, ["99999"], "api", {"port": 0}),
])
def test_menu_enregistre_chaque_reglage(clavier, config_joueur, tmp_path, numero, reponses, champ, attendu):
    clavier(str(numero), *reponses, "")
    chemin = tmp_path / "config.json"

    reglages.regler(chemin, config_joueur)

    assert joueur.lire_config(chemin)[champ] == attendu


def test_menu_change_le_nom(clavier, config_joueur, tmp_path):
    clavier("3", "Kuro", "")

    reglages.regler(tmp_path / "config.json", config_joueur)

    assert config_joueur["interface"]["nom"] == "Kuro"


def test_menu_change_l_apparence(clavier, config_joueur, tmp_path):
    clavier("6", "5", "#1c7ed6", "rouge", "", "")

    reglages.regler(tmp_path / "config.json", config_joueur)

    assert config_joueur["interface"]["arch"] == "ombre"
    assert config_joueur["interface"]["couleurs"] == {"cheveux": "#1c7ed6", "accent": "#c1121f"}


def test_changer_de_ville_change_les_coordonnees(clavier, config_joueur, tmp_path):
    clavier("4", "Seynod", "")

    reglages.regler(tmp_path / "config.json", config_joueur)

    assert config_joueur["coordonnees"] == installation.VILLES["Seynod"]


def test_ville_hors_liste_retire_les_coordonnees(clavier, config_joueur, tmp_path):
    clavier("4", "Chambéry", "")

    reglages.regler(tmp_path / "config.json", config_joueur)

    assert "coordonnees" not in config_joueur


def test_menu_garde_les_champs_qu_il_ne_connait_pas(clavier, config_joueur, tmp_path):
    config_joueur["anthropic"] = {"effort": "low"}
    clavier("7", "2", "")
    chemin = tmp_path / "config.json"

    reglages.regler(chemin, config_joueur)

    assert json.loads(chemin.read_text(encoding="utf-8"))["anthropic"] == {"effort": "low"}


def test_reglage_abandonne_ne_change_rien(clavier, config_joueur, tmp_path):
    clavier("6", "5", KeyboardInterrupt)

    with pytest.raises(SystemExit):
        reglages.regler(tmp_path / "config.json", config_joueur)

    assert config_joueur["interface"]["arch"] == "stratege"


def test_sans_clavier_pas_de_menu(monkeypatch, config_joueur, tmp_path):
    monkeypatch.setattr(sys, "stdin", None)

    reglages.regler(tmp_path / "config.json", config_joueur, premiere=True)

    assert not (tmp_path / "config.json").exists()


def test_ville_modifiee_a_la_main_corrige_les_coordonnees(config_joueur):
    config_joueur["ville"] = "Seynod"   # les coordonnées sont restées celles d'Annecy

    installation.corriger_coordonnees(config_joueur)

    assert config_joueur["coordonnees"] == installation.VILLES["Seynod"]


def test_coordonnees_choisies_expres_sont_gardees(config_joueur):
    config_joueur["coordonnees"] = [45.5, 6.0]

    installation.corriger_coordonnees(config_joueur)

    assert config_joueur["coordonnees"] == [45.5, 6.0]


@pytest.fixture
def lancement(monkeypatch, config_joueur, tmp_path):
    """lancer(*options) : joueur.main() sans réseau. Renvoie les appels au menu."""
    chemin = tmp_path / "config.json"
    chemin.write_text(json.dumps(config_joueur), encoding="utf-8")
    appels = []
    for flux in ("stdout", "stderr"):
        monkeypatch.setattr(getattr(sys, flux), "reconfigure", lambda **k: None, raising=False)
    monkeypatch.setattr(joueur, "regler", lambda *a: appels.append(a))
    monkeypatch.setattr(joueur, "preparer_ollama", lambda *a: None)
    monkeypatch.setattr(joueur, "Joueur", lambda config: SimpleNamespace(lancer=lambda: None))

    def lancer(*options):
        monkeypatch.setattr(sys, "argv", ["joueur.py", str(chemin), *options])
        joueur.main()
        return appels
    return lancer


def test_lancement_habituel_sans_question(lancement):
    assert lancement() == []


def test_option_reglages_ouvre_le_menu(lancement):
    assert len(lancement("--reglages")) == 1
