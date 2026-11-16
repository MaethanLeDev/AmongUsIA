"""Gemini dans le joueur (ia.py, joueur.py) : requêtes, lecture des réponses, repli sur Ollama, vérification de la clé.

Le réseau est simulé : aucun test n'appelle Google, et aucune vraie clé n'est nécessaire.
"""
import json
from types import SimpleNamespace

import pytest
import requests
from aides import FausseReponseHTTP

import ia
import joueur

CLE = "cle-de-test-secrete"
GEMINI = {"cle_api": CLE, "modele": "gemini-test"}
MESSAGES = [{"role": "system", "content": "Règles du jeu"}, {"role": "user", "content": "Salut"}]
REPONSE_OLLAMA = "Salut (Ollama)."


def reponse_gemini(texte="Bonjour (Gemini)."):
    return FausseReponseHTTP({"candidates": [{"content": {"role": "model", "parts": [{"text": texte}]}, "finishReason": "STOP"}]})


@pytest.fixture
def cerveau_gemini(config_joueur):
    config_joueur["gemini"] = dict(GEMINI)
    return ia.IA(config_joueur)


@pytest.fixture
def reseau(monkeypatch):
    """Faux Gemini et faux Ollama (requests.post / requests.get). Chaque attribut est une réponse, ou une exception à lever :
    .gemini et .ollama pour générer, .verif_gemini et .verif_ollama pour la vérification au démarrage.
    .requetes garde chaque appel ; .services() dit lesquels ont été sollicités, dans l'ordre."""
    faux = SimpleNamespace(
        gemini=reponse_gemini(), ollama=FausseReponseHTTP({"message": {"role": "assistant", "content": REPONSE_OLLAMA}}),
        verif_gemini=FausseReponseHTTP({"name": "models/gemini-test"}),
        verif_ollama=FausseReponseHTTP({"models": [{"name": "qwen3:0.6b"}]}), requetes=[])

    def appeler(methode, url, json, headers, timeout):
        service = "gemini" if "generativelanguage" in url else "ollama"
        faux.requetes.append({"methode": methode, "service": service, "url": url, "json": json,
                              "headers": headers or {}, "timeout": timeout})
        reponse = getattr(faux, service if methode == "POST" else f"verif_{service}")
        if isinstance(reponse, Exception):
            raise reponse
        return reponse

    monkeypatch.setattr(ia.requests, "post", lambda url, json=None, headers=None, timeout=None:
                        appeler("POST", url, json, headers, timeout))
    monkeypatch.setattr(ia.requests, "get", lambda url, headers=None, timeout=None: appeler("GET", url, None, headers, timeout))
    faux.services = lambda: [r["service"] for r in faux.requetes]
    return faux


# --- La requête ---------------------------------------------------------------


def test_requete_gemini_url_entete_et_corps(cerveau_gemini, reseau):
    cerveau_gemini.discuter(MESSAGES, delai=60, max_tokens=120, temperature=0.5)

    requete = reseau.requetes[0]
    corps = requete["json"]
    assert requete["url"] == "https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent"
    assert requete["headers"] == {"x-goog-api-key": CLE}
    assert corps["systemInstruction"] == {"parts": [{"text": "Règles du jeu"}]}
    assert corps["contents"] == [{"role": "user", "parts": [{"text": "Salut"}]}]
    assert corps["generationConfig"]["temperature"] == 0.5


def test_la_cle_ne_voyage_que_dans_l_entete(cerveau_gemini, reseau):
    cerveau_gemini.discuter(MESSAGES, delai=60, max_tokens=120)

    requete = reseau.requetes[0]
    assert CLE not in requete["url"]
    assert CLE not in json.dumps(requete["json"])


def test_requete_gemini_ne_depasse_pas_son_delai(cerveau_gemini, reseau):
    cerveau_gemini.discuter(MESSAGES, delai=100, max_tokens=120)

    assert reseau.requetes[0]["timeout"] == ia.DELAI_GEMINI


def test_requete_gemini_respecte_un_delai_court(cerveau_gemini, reseau):
    cerveau_gemini.discuter(MESSAGES, delai=12, max_tokens=120)

    assert reseau.requetes[0]["timeout"] == 12


def test_historique_de_l_agent_traduit_assistant_en_model(cerveau_gemini, reseau):
    historique = [{"role": "user", "content": "Salut"}, {"role": "assistant", "content": "Bonjour"}]

    cerveau_gemini.repondre(historique, "Comment vas-tu ?")

    roles = [c["role"] for c in reseau.requetes[0]["json"]["contents"]]
    assert roles == ["user", "model", "user"]


@pytest.mark.parametrize(("max_tokens", "attendu"), [(120, 1200), (200, 2000), (10, 1024)])
def test_limite_de_tokens_large_car_la_reflexion_compte(cerveau_gemini, reseau, max_tokens, attendu):
    cerveau_gemini.discuter(MESSAGES, delai=30, max_tokens=max_tokens)

    assert reseau.requetes[0]["json"]["generationConfig"]["maxOutputTokens"] == attendu


def test_vote_demande_du_json(cerveau_gemini, reseau):
    cerveau_gemini.discuter(MESSAGES, delai=30, max_tokens=200, json_attendu=True)

    assert reseau.requetes[0]["json"]["generationConfig"]["responseMimeType"] == "application/json"


def test_parole_sans_format_json(cerveau_gemini, reseau):
    cerveau_gemini.discuter(MESSAGES, delai=30, max_tokens=120)

    assert "responseMimeType" not in reseau.requetes[0]["json"]["generationConfig"]


# --- La réponse ---------------------------------------------------------------


def test_gemini_repond_sans_appeler_ollama(cerveau_gemini, reseau):
    assert cerveau_gemini.discuter(MESSAGES, delai=30, max_tokens=120) == "Bonjour (Gemini)."
    assert reseau.services() == ["gemini"]
    assert cerveau_gemini.etat_llm == "ok"


def test_gemini_assemble_les_parties_et_ignore_les_pensees(cerveau_gemini, reseau):
    reseau.gemini = FausseReponseHTTP({"candidates": [{"content": {"parts": [
        {"text": "Je réfléchis…", "thought": True}, {"text": "Kaito "}, {"text": "ment."}]}}]})

    assert cerveau_gemini.discuter(MESSAGES, delai=30, max_tokens=120) == "Kaito ment."


# --- Le repli sur Ollama ------------------------------------------------------

PANNES = {
    "injoignable": requests.ConnectionError("pas de réseau"),
    "trop lent": requests.Timeout("trop lent"),
    "quota dépassé": FausseReponseHTTP({"error": {"message": "Quota exceeded"}}, code=429),
    "réponse bloquée": FausseReponseHTTP({"promptFeedback": {"blockReason": "SAFETY"}}),
    "réponse coupée": FausseReponseHTTP({"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": []}}]}),
    "réponse illisible": FausseReponseHTTP(["pas", "un", "objet"]),
}


@pytest.mark.parametrize("panne", PANNES.values(), ids=PANNES.keys())
def test_ollama_prend_le_relais_quand_gemini_echoue(cerveau_gemini, reseau, panne):
    reseau.gemini = panne

    assert cerveau_gemini.discuter(MESSAGES, delai=60, max_tokens=120) == REPONSE_OLLAMA
    assert reseau.services() == ["gemini", "ollama"]


def test_le_repli_dit_pourquoi_sans_montrer_la_cle(cerveau_gemini, reseau, capsys):
    reseau.gemini = FausseReponseHTTP({"error": {"message": "API key not valid. Please pass a valid API key."}}, code=400)

    cerveau_gemini.discuter(MESSAGES, delai=60, max_tokens=120)

    sortie = capsys.readouterr().out
    assert "HTTP 400 : API key not valid" in sortie
    assert CLE not in sortie


def test_ollama_n_a_que_le_temps_qui_reste(cerveau_gemini, reseau):
    reseau.gemini = requests.Timeout("trop lent")

    cerveau_gemini.discuter(MESSAGES, delai=40, max_tokens=120)

    assert 5 <= reseau.requetes[1]["timeout"] <= 40


def test_sans_gemini_ni_ollama_la_panne_remonte(cerveau_gemini, reseau):
    reseau.gemini = requests.ConnectionError("pas de réseau")
    reseau.ollama = requests.ConnectionError("Ollama arrêté")

    with pytest.raises(requests.RequestException, match="Ollama arrêté"):
        cerveau_gemini.discuter(MESSAGES, delai=30, max_tokens=120)


def test_sans_cle_ollama_seul(config_joueur, reseau):
    config_joueur["gemini"] = {"cle_api": "", "modele": "gemini-test"}
    cerveau = ia.IA(config_joueur)

    assert cerveau.discuter(MESSAGES, delai=30, max_tokens=120) == REPONSE_OLLAMA
    assert reseau.services() == ["ollama"]
    assert (cerveau.fournisseur, cerveau.modele_actif) == ("Ollama", "qwen3:0.6b")


def test_cle_faite_d_espaces_ne_compte_pas(config_joueur, reseau):
    config_joueur["gemini"] = {"cle_api": "  \n", "modele": "gemini-test"}

    assert ia.IA(config_joueur).fournisseur == "Ollama"


def test_modele_gemini_par_defaut(config_joueur):
    config_joueur["gemini"] = {"cle_api": CLE}

    assert ia.IA(config_joueur).modele_actif == ia.GEMINI_MODELE


# --- Vérification au démarrage ------------------------------------------------


def test_verifier_gemini_pret_sans_toucher_ollama(cerveau_gemini, reseau):
    assert cerveau_gemini.verifier() is None
    assert reseau.services() == ["gemini"]
    assert reseau.requetes[0]["headers"] == {"x-goog-api-key": CLE}
    assert (cerveau_gemini.fournisseur, cerveau_gemini.modele_actif, cerveau_gemini.etat_llm) == ("Gemini", "gemini-test", "ok")


@pytest.mark.parametrize(("code", "message"), [(400, "refuse la clé"), (403, "refuse la clé"), (404, "n'existe pas")])
def test_verifier_cle_ou_modele_refuse_bascule_sur_ollama(cerveau_gemini, reseau, capsys, code, message):
    reseau.verif_gemini = FausseReponseHTTP({"error": {"message": "refusé par Google"}}, code=code)

    assert cerveau_gemini.verifier() is None   # Ollama est prêt : pas d'alerte, le joueur peut jouer
    assert message in capsys.readouterr().out
    assert (cerveau_gemini.fournisseur, cerveau_gemini.modele_actif) == ("Ollama", "qwen3:0.6b")

    reseau.requetes.clear()
    assert cerveau_gemini.discuter(MESSAGES, delai=30, max_tokens=120) == REPONSE_OLLAMA
    assert reseau.services() == ["ollama"]   # on n'insiste pas auprès de Google


def test_verifier_gemini_injoignable_reste_sur_gemini(cerveau_gemini, reseau, capsys):
    reseau.verif_gemini = requests.ConnectionError("pas de réseau")

    assert cerveau_gemini.verifier() is None
    assert "Ollama prendra le relais" in capsys.readouterr().out
    assert cerveau_gemini.fournisseur == "Gemini"   # une coupure passagère ne désactive pas Gemini


def test_verifier_alerte_quand_gemini_et_ollama_sont_hors_service(cerveau_gemini, reseau):
    reseau.verif_gemini = FausseReponseHTTP({}, code=403)
    reseau.verif_ollama = requests.ConnectionError("Ollama arrêté")

    assert "Ollama ne répond pas" in cerveau_gemini.verifier()
    assert cerveau_gemini.etat_llm == "injoignable"


# --- config.json et ce que le joueur annonce ----------------------------------


@pytest.fixture
def ecrire(tmp_path):
    def ecrire_config(contenu):
        chemin = tmp_path / "config.json"
        chemin.write_text(json.dumps(contenu), encoding="utf-8")
        return chemin
    return ecrire_config


@pytest.mark.parametrize("gemini", ["ma-cle", ["ma-cle"], {"cle_api": 12}, {"cle_api": "x", "modele": None}])
def test_config_gemini_invalide(ecrire, gemini):
    with pytest.raises(SystemExit, match='"gemini"'):
        joueur.lire_config(ecrire({"id": "rpi1", "ville": "Annecy", "gemini": gemini}))


@pytest.mark.parametrize("gemini", [{}, {"cle_api": ""}, GEMINI])
def test_config_gemini_valide(ecrire, gemini):
    config = joueur.lire_config(ecrire({"id": "rpi1", "ville": "Annecy", "gemini": gemini}))

    assert config["gemini"] == gemini


def test_config_sans_bloc_gemini(ecrire):
    assert "gemini" not in joueur.lire_config(ecrire({"id": "rpi1", "ville": "Annecy"}))


@pytest.mark.parametrize("config_joueur", [{"gemini": GEMINI}], indirect=True)
def test_la_fiche_annonce_le_modele_gemini_sans_la_cle(joueur_jeu):
    fiche = joueur_jeu.fiche()

    assert fiche["modele"] == "gemini-test"
    assert CLE not in json.dumps(fiche)
