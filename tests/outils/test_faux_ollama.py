"""Faux Ollama (faux_ollama.py), et son contrat avec joueur/ia.py : il doit comprendre les vrais prompts du joueur.

Si un prompt d'ia.py change (noms, « INSTABLE », « Identifiants possibles »), les tests de contrat le signalent.
"""
import json
import random

import faux_ollama
import pytest
from aides import ID_PARTIE, FausseReponseHTTP

import ia

CANDIDATS = {"rpi2", "rpi3", "rpi4"}


@pytest.fixture
def partie():
    """La partie vue par rpi1 (Sherlock) : Kaito (rpi3) est le seul capteur INSTABLE."""
    p = ia.Partie(ID_PARTIE, "rpi1", "normal")
    p.participants = p.vivants = ["rpi1", "rpi2", "rpi3", "rpi4"]
    p.numero = 1
    p.noms = {"rpi1": "Sherlock", "rpi2": "Mimi", "rpi3": "Kaito", "rpi4": "Yuki"}
    p.manche().mesures = {"rpi1": [12.0] * 5, "rpi2": [12.2] * 5, "rpi3": [13.4, 11.0, 13.9, 10.8, 13.6], "rpi4": [11.9] * 5}
    return p


@pytest.fixture
def cerveau(config_joueur, monkeypatch):
    """Un vrai IA dont les requêtes HTTP vers Ollama sont servies par faux_ollama.repondre."""
    def post(url, json=None, timeout=None):
        contenu = faux_ollama.repondre(json["messages"], json.get("format") == "json")
        return FausseReponseHTTP({"message": {"role": "assistant", "content": contenu}, "done": True})
    monkeypatch.setattr(ia.requests, "post", post)
    return ia.IA(config_joueur)


@pytest.fixture
def hasard_fixe(monkeypatch):
    """random.random() vaut 0 et random.choice prend le premier élément : le faux Ollama suit les INSTABLES."""
    monkeypatch.setattr(random, "random", lambda: 0.0)
    monkeypatch.setattr(random, "choice", lambda sequence: list(sequence)[0])


# --- Contrat avec ia.py -------------------------------------------------------


def test_contrat_vote_json_valide_pour_un_vrai_prompt(cerveau, partie):
    for _ in range(30):
        suspect, raison, _calcul = cerveau.voter(partie, delai=10)

        assert suspect in CANDIDATS
        assert not raison.startswith("(réponse du LLM inexploitable")


def test_contrat_vote_contre_le_capteur_instable(cerveau, partie, hasard_fixe):
    assert cerveau.voter(partie, delai=10)[0] == "rpi3"


def test_contrat_ne_vote_jamais_pour_soi(cerveau, partie):
    assert all(cerveau.voter(partie, delai=10)[0] != "rpi1" for _ in range(50))


def test_contrat_parole_cite_un_autre_joueur(cerveau, partie):
    for _ in range(30):
        texte = cerveau.parler(partie, 1, 2, delai=10)

        assert texte != ia.REPLI_PAROLE
        assert any(nom in texte for nom in ("Mimi", "Kaito", "Yuki"))
        assert "Sherlock" not in texte


def test_contrat_notes_de_fin_de_manche(cerveau, partie):
    assert cerveau.resumer(partie, delai=10).startswith("Je me méfie de")


def test_contrat_conversation_de_l_agent(cerveau):
    assert "faux agent de test" in cerveau.repondre([], "Bonjour, qui es-tu ?")


# --- Réponses du faux Ollama --------------------------------------------------


def test_vote_sans_liste_d_identifiants_renvoie_un_suspect_vide():
    reponse = json.loads(faux_ollama.repondre([{"role": "user", "content": "Vote !"}], format_json=True))

    assert reponse["suspect"] == ""


def test_vote_renvoie_un_json_avec_suspect_et_raison():
    messages = [{"role": "system", "content": "Tu es Sherlock (identifiant rpi1)."},
                {"role": "user", "content": "Joueurs encore en jeu : Sherlock (toi), Mimi.\n"
                                            "Identifiants possibles : rpi2 (Mimi).\nRéponds en JSON"}]

    assert json.loads(faux_ollama.repondre(messages, format_json=True)) == {"suspect": "rpi2",
                                                                          "raison": "Mimi a des températures suspectes."}


def test_sans_message_ne_plante_pas():
    assert "faux agent de test" in faux_ollama.repondre([], format_json=False)
