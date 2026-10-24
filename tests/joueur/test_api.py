"""API HTTP de l'agent (api.py) : un vrai serveur sur un port libre de cette machine, le LLM et l'autre agent simulés."""
import json
import threading
import urllib.error
import urllib.request

import pytest
import requests
from aides import ID_PARTIE, FausseReponseHTTP

import api


@pytest.fixture
def serveur(joueur_jeu, monkeypatch):
    """L'API de rpi1 sur un port libre. Le LLM répond « réponse n » en écho, en notant l'historique reçu."""
    historiques = []

    def repondre(historique, message, delai=120):
        historiques.append(list(historique))
        return f"réponse {len(historiques)} à « {message} »"
    monkeypatch.setattr(joueur_jeu.ia, "repondre", repondre)
    monkeypatch.setattr(joueur_jeu.ia, "disponible", lambda: True)
    serveur = api.demarrer_api(joueur_jeu, 0)
    serveur.historiques = historiques
    serveur.url = f"http://127.0.0.1:{serveur.server_address[1]}"
    yield serveur

    # shutdown() attend la fin d'un tour de serve_forever (0,5 s) : on l'attend en arrière-plan
    def arreter():
        serveur.shutdown()
        serveur.server_close()
    threading.Thread(target=arreter, daemon=True).start()


def appeler(serveur, route, corps=None, brut=None):
    """(code HTTP, contenu JSON) d'une requête GET (sans corps) ou POST."""
    donnees = brut if brut is not None else (json.dumps(corps).encode() if corps is not None else None)
    requete = urllib.request.Request(serveur.url + route, data=donnees, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(requete, timeout=5) as reponse:
            return reponse.status, json.loads(reponse.read())
    except urllib.error.HTTPError as erreur:
        return erreur.code, json.loads(erreur.read())


# --- GET ----------------------------------------------------------------------


def test_health_repond_ok(serveur):
    code, contenu = appeler(serveur, "/health")

    assert code == 200
    assert contenu == {"status": "ok", "id": "rpi1", "broker": False, "ollama": True}


def test_agent_decrit_l_agent_et_ses_routes(serveur):
    code, contenu = appeler(serveur, "/agent")

    assert code == 200
    assert contenu["nom"] == "Sherlock"
    assert "POST /message" in contenu["routes"]


def test_agent_ne_revele_jamais_le_role_de_l_espion(serveur, joueur_jeu):
    joueur_jeu.client.injecter("iot/role/rpi1", {"role": "espion", "partie": ID_PARTIE})

    _, contenu = appeler(serveur, "/agent")

    assert "role" not in contenu
    assert contenu["jeu"] == {"phase": None, "en_partie": True, "vivant": False}


def test_route_inconnue(serveur):
    code, contenu = appeler(serveur, "/secret")

    assert code == 404
    assert "routes" in contenu["erreur"]


# --- POST /message ------------------------------------------------------------


def test_message_renvoie_la_reponse_du_llm(serveur):
    code, contenu = appeler(serveur, "/message", {"message": "Salut", "de": "rpi2"})

    assert (code, contenu) == (200, {"reponse": "réponse 1 à « Salut »"})


def test_message_se_souvient_de_la_conversation(serveur):
    appeler(serveur, "/message", {"message": "Salut", "de": "rpi2"})

    appeler(serveur, "/message", {"message": "Ça va ?", "de": "rpi2"})

    assert serveur.historiques[1] == [{"role": "user", "content": "Salut"},
                                      {"role": "assistant", "content": "réponse 1 à « Salut »"}]


def test_message_une_conversation_par_interlocuteur(serveur):
    appeler(serveur, "/message", {"message": "Salut", "de": "rpi2"})

    appeler(serveur, "/message", {"message": "Bonjour", "de": "rpi3"})

    assert serveur.historiques[1] == []


def test_message_sans_texte(serveur):
    code, contenu = appeler(serveur, "/message", {"de": "rpi2", "message": "   "})

    assert code == 400
    assert "message" in contenu["erreur"]


@pytest.mark.parametrize("brut", [b"{pas du json", b"[1, 2]"])
def test_corps_invalide(serveur, brut):
    assert appeler(serveur, "/message", brut=brut)[0] == 400


def test_message_llm_injoignable(serveur, joueur_jeu, monkeypatch):
    def repondre(historique, message, delai=120):
        raise requests.ConnectionError("Ollama absent")
    monkeypatch.setattr(joueur_jeu.ia, "repondre", repondre)

    code, contenu = appeler(serveur, "/message", {"message": "Salut"})

    assert code == 502
    assert "injoignable" in contenu["erreur"]


def test_post_route_inconnue(serveur):
    assert appeler(serveur, "/vote", {"suspect": "rpi2"})[0] == 404


# --- Historique ---------------------------------------------------------------


def test_historique_limite_aux_derniers_messages():
    conversations = api.Conversations()

    for i in range(30):
        conversations.ajouter("rpi2", f"question {i}", f"réponse {i}")

    historique = conversations.lire("rpi2")
    assert len(historique) == api.MAX_HISTORIQUE
    assert historique[-1] == {"role": "assistant", "content": "réponse 29"}


def test_historique_lu_est_une_copie():
    conversations = api.Conversations()
    conversations.ajouter("rpi2", "q", "r")

    conversations.lire("rpi2").clear()

    assert len(conversations.lire("rpi2")) == 2


# --- POST /discuter -----------------------------------------------------------


@pytest.fixture
def autre_agent(monkeypatch):
    """Simule le /message de l'autre agent. Renvoie les requêtes qu'il a reçues."""
    recues = []

    def post(url, json=None, timeout=None):
        recues.append({"url": url, "json": json, "timeout": timeout})
        return FausseReponseHTTP({"reponse": f"réplique {len(recues)} de l'autre"})
    monkeypatch.setattr(api.requests, "post", post)
    return recues


def test_discuter_alterne_les_repliques(serveur, autre_agent):
    code, contenu = appeler(serveur, "/discuter", {"avec": "http://10.0.0.7:5000/", "sujet": "la pluie", "tours": 2})

    assert code == 200
    assert [e["de"] for e in contenu["echanges"]] == ["rpi1", "http://10.0.0.7:5000", "rpi1", "http://10.0.0.7:5000", "rpi1"]
    assert autre_agent[0]["url"] == "http://10.0.0.7:5000/message"
    assert autre_agent[0]["timeout"]


def test_discuter_transmet_notre_replique_a_l_autre(serveur, autre_agent):
    _, contenu = appeler(serveur, "/discuter", {"avec": "http://10.0.0.7:5000", "tours": 1})

    assert autre_agent[0]["json"] == {"message": contenu["echanges"][0]["texte"], "de": "rpi1"}


def test_discuter_nombre_de_tours_borne(serveur, autre_agent):
    appeler(serveur, "/discuter", {"avec": "http://10.0.0.7:5000", "tours": 50})

    assert len(autre_agent) == api.MAX_TOURS


def test_discuter_sans_url(serveur):
    code, contenu = appeler(serveur, "/discuter", {"avec": "rpi2"})

    assert code == 400
    assert "avec" in contenu["erreur"]


def test_discuter_autre_agent_injoignable(serveur, monkeypatch):
    def post(url, json=None, timeout=None):
        raise requests.ConnectTimeout("pas de réponse")
    monkeypatch.setattr(api.requests, "post", post)

    assert appeler(serveur, "/discuter", {"avec": "http://10.0.0.7:5000"})[0] == 502


def test_discuter_tours_invalide(serveur, autre_agent):
    assert appeler(serveur, "/discuter", {"avec": "http://10.0.0.7:5000", "tours": "beaucoup"})[0] == 502


@pytest.mark.xfail(reason="bug : \"tours\": null lève une TypeError non attrapée, le client n'a aucune réponse",
                   raises=(urllib.error.URLError, ConnectionError))
def test_discuter_tours_nul_renvoie_une_erreur(serveur, autre_agent):
    assert appeler(serveur, "/discuter", {"avec": "http://10.0.0.7:5000", "tours": None})[0] in (400, 502)
