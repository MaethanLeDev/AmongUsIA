"""Le cerveau du joueur (ia.py) : stratégie « ecart », lecture des réponses du LLM, requêtes Ollama ou Claude, mémoire."""
from types import SimpleNamespace

import anthropic
import httpx2
import pytest
import requests
from aides import ID_PARTIE, FausseReponseHTTP

import ia

CANDIDATS = {"rpi2": "Mimi", "rpi3": "Kaito", "rpi4": "Yuki"}


@pytest.fixture
def cerveau(config_joueur):
    return ia.IA(config_joueur)


@pytest.fixture
def llm_repond(cerveau, monkeypatch):
    """llm_repond("texte") : discuter() renvoie ce texte (ou lève l'exception donnée). Renvoie les appels reçus."""
    appels = []

    def repondre(reponse):
        def discuter(messages, delai, max_tokens, json_attendu=False, temperature=0.8):
            appels.append({"messages": messages, "delai": delai, "json_attendu": json_attendu})
            if isinstance(reponse, Exception):
                raise reponse
            return reponse
        monkeypatch.setattr(cerveau, "discuter", discuter)
        return appels
    return repondre


# --- Stratégie « ecart » ------------------------------------------------------


def test_analyser_ecart_signe_a_la_mediane_des_autres():
    analyse = ia.analyser({"a": [10.0, 10.0], "b": [10.0, 10.0], "d": [10.0, 10.0], "c": [12.0, 12.0]})

    assert analyse["c"]["ecart"] == pytest.approx(2.0)
    assert analyse["a"]["ecart"] == pytest.approx(0.0)


def test_analyser_amplitude_des_valeurs():
    assert ia.analyser({"a": [10.0, 13.5, 11.0]})["a"]["amplitude"] == pytest.approx(3.5)


def test_analyser_series_de_longueurs_differentes():
    # Un joueur arrivé en retard a moins de mesures : on ne compare que les échanges communs
    analyse = ia.analyser({"a": [10.0, 10.0, 10.0], "b": [11.0]})

    assert analyse["a"]["ecart"] == pytest.approx(-1.0)
    assert analyse["b"]["ecart"] == pytest.approx(1.0)


def test_analyser_joueur_seul_ecart_nul():
    assert ia.analyser({"a": [10.0, 11.0]})["a"]["ecart"] == 0.0


def test_calcul_designe_le_capteur_instable(partie_type):
    suspect, detail = ia.suspect_par_calcul(partie_type)

    assert suspect == "rpi3"
    assert "change de 3.2 °C" in detail


def test_calcul_un_ecart_constant_n_est_pas_suspect(partie_type):
    # rpi4 est 1.4 °C plus chaud, mais toujours autant : une autre ville. rpi3 varie un peu : c'est lui le suspect.
    partie_type.manche().mesures = {"rpi1": [12.0] * 3, "rpi2": [12.1] * 3, "rpi3": [12.0, 12.6, 11.8], "rpi4": [13.4] * 3}

    assert ia.suspect_par_calcul(partie_type)[0] == "rpi3"


def test_calcul_ne_se_designe_jamais_soi_meme(partie_type):
    partie_type.manche().mesures["rpi1"] = [20.0, 5.0, 20.0, 5.0, 20.0]

    assert ia.suspect_par_calcul(partie_type)[0] != "rpi1"


def test_calcul_ignore_un_elimine(partie_type):
    partie_type.vivants.remove("rpi3")

    assert ia.suspect_par_calcul(partie_type)[0] != "rpi3"


def test_calcul_sans_donnees_ne_designe_personne(partie_type):
    partie_type.manche().mesures = {}

    assert ia.suspect_par_calcul(partie_type) == (None, "aucune donnée")


def test_tableau_traduit_la_stabilite_en_mots(partie_type):
    tableau = ia.tableau_mesures(partie_type)

    assert "- Kaito, Poisy : 13.4, 11.0, 13.9, 10.8, 13.6 °C → INSTABLE : son écart avec les autres change de 3.2 °C" in tableau
    assert "- Sherlock (toi), Annecy" in tableau
    assert "Mimi, Seynod : 12.2, 12.2, 12.3, 12.2, 12.2 °C → STABLE" in tableau


def test_tableau_signale_un_joueur_sans_mesure(partie_type):
    del partie_type.manche().mesures["rpi4"]

    assert "- Yuki : aucune mesure" in ia.tableau_mesures(partie_type)


# --- Lecture du vote du LLM ---------------------------------------------------


def test_lire_vote_json_valide():
    assert ia.lire_vote('{"suspect": "rpi3", "raison": "instable"}', CANDIDATS) == ("rpi3", "instable")


def test_lire_vote_suspect_donne_par_son_nom():
    assert ia.lire_vote('{"suspect": "Kaito", "raison": "il ment"}', CANDIDATS) == ("rpi3", "il ment")


def test_lire_vote_json_invalide_cherche_un_id_dans_le_texte():
    assert ia.lire_vote("Je pense que rpi4 ment, ses valeurs", CANDIDATS) == ("rpi4", "")


def test_lire_vote_json_invalide_cherche_un_nom_dans_le_texte():
    assert ia.lire_vote("C'est YUKI, évidemment", CANDIDATS) == ("rpi4", "")


def test_lire_vote_json_coupe_en_route():
    assert ia.lire_vote('{"suspect": "rpi2", "raison": "ses val', CANDIDATS)[0] == "rpi2"


def test_lire_vote_json_qui_n_est_pas_un_objet():
    assert ia.lire_vote('["rpi2"]', CANDIDATS)[0] == "rpi2"


def test_lire_vote_suspect_inexistant_ne_donne_rien():
    assert ia.lire_vote('{"suspect": "rpi9", "raison": "?"}', CANDIDATS) == (None, "")


def test_lire_vote_reponse_vide_ne_donne_rien():
    assert ia.lire_vote("", CANDIDATS) == (None, "")


def test_lire_vote_ne_confond_pas_rpi1_et_rpi10():
    assert ia.lire_vote("rpi10 est louche", {"rpi1": "rpi1", "rpi10": "rpi10"})[0] == "rpi10"


@pytest.mark.xfail(reason="bug : recherche par sous-chaîne ; un id absent des candidats (soi-même, un éliminé) "
                          "qui en contient un autre (rpi10 ⊃ rpi1) donne un vote contre rpi1 au lieu du repli sur le calcul")
def test_lire_vote_id_non_candidat_qui_en_contient_un_autre_ne_donne_rien():
    # rpi10 vote pour lui-même : il n'est pas candidat, la réponse est inexploitable
    assert ia.lire_vote('{"suspect": "rpi10", "raison": "moi"}', {"rpi1": "rpi1", "rpi2": "rpi2"}) == (None, "")


def test_lire_vote_raison_tronquee():
    suspect, raison = ia.lire_vote('{"suspect": "rpi3", "raison": "' + "x" * 500 + '"}', CANDIDATS)

    assert len(raison) == 200


# --- Nettoyage des réponses ---------------------------------------------------


def test_nettoyer_retire_la_reflexion():
    assert ia.nettoyer("<think>Qui ment ?\nMimi.</think>Mimi ment.") == "Mimi ment."


def test_nettoyer_retire_une_reflexion_jamais_refermee():
    assert ia.nettoyer("<think>je réfléchis encore et le texte est coupé") == ""


def test_nettoyer_retire_le_nom_en_tete():
    assert ia.nettoyer("Sherlock : Mimi ment.") == "Mimi ment."


def test_nettoyer_retire_le_markdown():
    assert ia.nettoyer("**Kaito** : tu **mens**") == "tu mens"


def test_nettoyer_retire_les_guillemets_et_les_espaces():
    assert ia.nettoyer('  « Mimi\n\n   ment »  ') == "Mimi ment"


def test_nettoyer_limite_la_longueur():
    assert len(ia.nettoyer("a " * 500)) == 400


# --- Requête à Ollama ---------------------------------------------------------


@pytest.fixture
def ollama(monkeypatch):
    """Simule requests.post vers Ollama. Renvoie les requêtes envoyées (url, json, timeout)."""
    requetes = []

    def post(url, json=None, timeout=None):
        requetes.append({"url": url, "json": json, "timeout": timeout})
        return FausseReponseHTTP({"message": {"role": "assistant", "content": "Bonjour."}})
    monkeypatch.setattr(ia.requests, "post", post)
    return requetes


def test_requete_ollama_sans_flux_ni_reflexion(cerveau, ollama):
    cerveau.discuter([{"role": "user", "content": "Salut"}], delai=30, max_tokens=50)

    corps = ollama[0]["json"]
    assert ollama[0]["url"] == "http://127.0.0.1:11434/api/chat"
    assert (corps["stream"], corps["think"]) == (False, False)
    assert corps["options"]["num_predict"] == 50
    assert ollama[0]["timeout"] == 30


def test_requete_ollama_demande_du_json_pour_un_vote(cerveau, ollama):
    cerveau.discuter([{"role": "user", "content": "Vote"}], delai=30, max_tokens=50, json_attendu=True)

    assert ollama[0]["json"]["format"] == "json"


def test_requete_ollama_sans_format_json_pour_parler(cerveau, ollama):
    cerveau.discuter([{"role": "user", "content": "Parle"}], delai=30, max_tokens=50)

    assert "format" not in ollama[0]["json"]


def test_requete_qwen3_ajoute_no_think_sans_modifier_les_messages(cerveau, ollama):
    messages = [{"role": "user", "content": "Salut"}]

    cerveau.discuter(messages, delai=30, max_tokens=50)

    assert ollama[0]["json"]["messages"][-1]["content"] == "Salut /no_think"
    assert messages[0]["content"] == "Salut"


def test_requete_autre_modele_sans_no_think(config_joueur, ollama):
    config_joueur["ollama"]["modele"] = "llama3.2:1b"

    ia.IA(config_joueur).discuter([{"role": "user", "content": "Salut"}], delai=30, max_tokens=50)

    assert ollama[0]["json"]["messages"][-1]["content"] == "Salut"


def test_ollama_disponible(cerveau, monkeypatch):
    monkeypatch.setattr(ia.requests, "get", lambda url, timeout: FausseReponseHTTP({"models": []}))

    assert cerveau.disponible() is True


def test_ollama_injoignable(cerveau, monkeypatch):
    def get(url, timeout):
        raise requests.ConnectionError("refusé")
    monkeypatch.setattr(ia.requests, "get", get)

    assert cerveau.disponible() is False


# --- Requête à Claude (fournisseur « anthropic ») -----------------------------


class FauxClaude:
    """Remplace le client Anthropic : garde chaque appel à messages.create (avec le délai demandé) et rend .reponse."""

    def __init__(self):
        self.appels = []
        self.reponse = SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="Bonjour.")])
        self.erreur = None
        self.messages = self
        self._delai = None

    def with_options(self, timeout):
        self._delai = timeout
        return self

    def create(self, **corps):
        self.appels.append({**corps, "delai": self._delai})
        if self.erreur:
            raise self.erreur
        return self.reponse


def requete_anthropic():
    return httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


@pytest.fixture
def claude(config_joueur, monkeypatch):
    """Un joueur configuré pour Claude, avec une clé de test et un faux client : aucun appel réel, aucun frais."""
    config_joueur["fournisseur"] = "anthropic"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    cerveau = ia.IA(config_joueur)
    cerveau._client_claude = FauxClaude()
    return cerveau


def test_claude_modele_par_defaut_et_reglages_du_config(config_joueur):
    config_joueur.update({"fournisseur": "anthropic", "anthropic": {"modele": "claude-sonnet-5-5", "effort": "medium"}})

    cerveau = ia.IA(config_joueur)

    assert (cerveau.modele_claude, cerveau.effort_claude) == ("claude-sonnet-5-5", "medium")
    assert ia.IA({**config_joueur, "anthropic": {}}).modele_claude == ia.CLAUDE_MODELE


def test_claude_parle_en_premier_quand_la_cle_est_la(claude):
    assert claude.fournisseur == "Claude"
    assert claude.modele_actif == ia.CLAUDE_MODELE


def test_claude_sans_cle_ollama_reste_le_fournisseur(claude, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)

    assert (claude.fournisseur, claude.modele_actif) == ("Ollama", "qwen3:0.6b")


def test_sans_fournisseur_anthropic_la_cle_est_ignoree(config_joueur, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    assert ia.IA(config_joueur).fournisseur == "Ollama"


def test_requete_claude_separe_le_prompt_systeme_des_echanges(claude):
    messages = [{"role": "system", "content": "Tu es Léa."}, {"role": "user", "content": "Salut"}]

    claude.discuter(messages, delai=30, max_tokens=50)

    appel = claude._client_claude.appels[0]
    assert appel["system"] == "Tu es Léa."
    assert appel["messages"] == [{"role": "user", "content": "Salut"}]
    assert (appel["model"], appel["output_config"], appel["delai"]) == (ia.CLAUDE_MODELE, {"effort": "low"}, 30)


def test_requete_claude_plafonne_son_delai_pour_laisser_la_main_a_ollama(claude):
    claude.discuter([{"role": "user", "content": "Parle"}], delai=120, max_tokens=50)

    assert claude._client_claude.appels[0]["delai"] == ia.DELAI_CLAUDE


def test_requete_claude_sans_temperature_ni_format(claude):
    claude.discuter([{"role": "user", "content": "Vote"}], delai=30, max_tokens=50, json_attendu=True, temperature=1.1)

    appel = claude._client_claude.appels[0]
    assert "temperature" not in appel
    assert "output_format" not in appel


def test_requete_claude_laisse_de_la_place_a_sa_reflexion(claude):
    claude.discuter([{"role": "user", "content": "Parle"}], delai=30, max_tokens=120)

    assert claude._client_claude.appels[0]["max_tokens"] == ia.CLAUDE_MIN_TOKENS


def test_requete_claude_garde_une_grande_limite_demandee(claude):
    claude.discuter([{"role": "user", "content": "Parle"}], delai=30, max_tokens=5000)

    assert claude._client_claude.appels[0]["max_tokens"] == 5000


def test_claude_ne_renvoie_que_le_texte_pas_la_reflexion(claude):
    claude._client_claude.reponse = SimpleNamespace(stop_reason="end_turn", content=[
        SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text="Kaito, "),
        SimpleNamespace(type="text", text="explique-toi.")])

    assert claude.discuter([{"role": "user", "content": "Parle"}], delai=30, max_tokens=50) == "Kaito, explique-toi."


def test_claude_refus_leve_une_erreur_reseau(claude):
    claude._client_claude.reponse = SimpleNamespace(stop_reason="refusal", content=[])

    with pytest.raises(requests.RequestException):
        claude._discuter_claude([{"role": "user", "content": "Parle"}], delai=30, max_tokens=50)


def test_claude_trop_lent_donne_une_requests_timeout(claude):
    claude._client_claude.erreur = anthropic.APITimeoutError(request=requete_anthropic())

    with pytest.raises(requests.Timeout):
        claude._discuter_claude([{"role": "user", "content": "Parle"}], delai=30, max_tokens=50)
    assert claude.etat_llm == "trop_lent"


def test_claude_injoignable_donne_une_requests_connection_error(claude):
    claude._client_claude.erreur = anthropic.APIConnectionError(request=requete_anthropic())

    with pytest.raises(requests.ConnectionError):
        claude._discuter_claude([{"role": "user", "content": "Parle"}], delai=30, max_tokens=50)
    assert claude.etat_llm == "injoignable"


def test_claude_cle_refusee_le_desactive_pour_la_suite(claude):
    reponse = httpx2.Response(401, request=requete_anthropic())
    claude._client_claude.erreur = anthropic.AuthenticationError("invalid x-api-key", response=reponse, body=None)

    with pytest.raises(requests.RequestException):
        claude._discuter_claude([{"role": "user", "content": "Parle"}], delai=30, max_tokens=50)

    assert claude.fournisseur == "Ollama"


def test_claude_en_panne_ollama_prend_le_relais(claude, monkeypatch):
    claude._client_claude.erreur = anthropic.APIConnectionError(request=requete_anthropic())
    monkeypatch.setattr(claude, "_ollama", lambda messages, delai, max_tokens, json_attendu, temperature: "Repli Ollama.")

    assert claude.discuter([{"role": "user", "content": "Parle"}], delai=30, max_tokens=50) == "Repli Ollama."


def test_claude_parle_et_vote_comme_avec_ollama(claude, partie_type):
    claude._client_claude.reponse = SimpleNamespace(stop_reason="end_turn", content=[
        SimpleNamespace(type="text", text='{"suspect": "rpi2", "raison": "Mimi est trop calme."}')])

    assert claude.voter(partie_type, delai=30)[:2] == ("rpi2", "Mimi est trop calme.")


def test_claude_sans_cle_la_verification_le_signale_sans_appeler_l_api(claude, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)

    assert "ANTHROPIC_API_KEY" in claude._verifier_claude()
    assert claude._client_claude.appels == []


def test_claude_avec_cle_la_verification_passe_sans_appeler_l_api(claude):
    assert claude.verifier() is None
    assert claude.etat_llm == "ok"
    assert claude.disponible() is True
    assert claude._client_claude.appels == []


# --- Vote ---------------------------------------------------------------------


def test_vote_strategie_ecart_sans_appeler_le_llm(config_joueur, partie_type, monkeypatch):
    config_joueur["strategie"] = "ecart"
    cerveau = ia.IA(config_joueur)
    monkeypatch.setattr(cerveau, "discuter", lambda *a, **k: pytest.fail("le LLM ne doit pas être appelé"))

    suspect, raison, calcul = cerveau.voter(partie_type, delai=30)

    assert suspect == calcul == "rpi3"
    assert raison.startswith("son écart")


def test_vote_llm_suit_l_avis_du_llm(cerveau, partie_type, llm_repond):
    llm_repond('{"suspect": "rpi2", "raison": "Mimi est trop calme."}')

    assert cerveau.voter(partie_type, delai=30) == ("rpi2", "Mimi est trop calme.", "rpi3")


def test_vote_llm_demande_du_json(cerveau, partie_type, llm_repond):
    appels = llm_repond('{"suspect": "rpi2", "raison": "."}')

    cerveau.voter(partie_type, delai=30)

    assert appels[0]["json_attendu"] is True


def test_vote_llm_ne_propose_pas_de_voter_pour_soi(cerveau, partie_type, llm_repond):
    appels = llm_repond('{"suspect": "rpi2", "raison": "."}')

    cerveau.voter(partie_type, delai=30)

    consigne = appels[0]["messages"][-1]["content"]
    assert "Identifiants possibles : rpi2 (Mimi), rpi3 (Kaito), rpi4 (Yuki)." in consigne


def test_vote_llm_inexploitable_repli_sur_le_calcul(cerveau, partie_type, llm_repond):
    llm_repond("Je ne sais vraiment pas.")

    suspect, raison, calcul = cerveau.voter(partie_type, delai=30)

    assert suspect == calcul == "rpi3"
    assert raison.startswith("(réponse du LLM inexploitable")


def test_vote_llm_qui_vote_pour_lui_repli_sur_le_calcul(cerveau, partie_type, llm_repond):
    llm_repond('{"suspect": "Sherlock", "raison": "je me dénonce"}')

    assert cerveau.voter(partie_type, delai=30)[0] == "rpi3"


def test_vote_ollama_injoignable_repli_sur_le_calcul(cerveau, partie_type, llm_repond):
    llm_repond(requests.ConnectionError("Ollama absent"))

    assert cerveau.voter(partie_type, delai=30)[0] == "rpi3"


def test_vote_honnete_par_calcul_sans_appeler_le_llm(config_joueur, partie_type, monkeypatch):
    config_joueur["vote_honnete"] = "calcul"
    cerveau = ia.IA(config_joueur)
    monkeypatch.setattr(cerveau, "discuter", lambda *a, **k: pytest.fail("le LLM ne doit pas être appelé"))

    suspect, _, calcul = cerveau.voter(partie_type, delai=30)

    assert suspect == calcul == "rpi3"


def test_vote_espion_par_le_llm_meme_avec_vote_honnete_par_calcul(config_joueur, partie_type, monkeypatch):
    config_joueur["vote_honnete"] = "calcul"
    partie_type.role = "espion"
    cerveau = ia.IA(config_joueur)
    appels = []
    monkeypatch.setattr(cerveau, "discuter", lambda messages, *a, **k: appels.append(messages) or '{"suspect": "rpi2", "raison": "Mimi."}')

    suspect, _, calcul = cerveau.voter(partie_type, delai=30)

    assert (suspect, calcul) == ("rpi2", "rpi3")
    assert "Tu es l'espion : vote pour l'innocent" in appels[0][-1]["content"]
    assert "Identifiants possibles : rpi2 (Mimi), rpi3 (Kaito), rpi4 (Yuki)." in appels[0][-1]["content"]


# --- Mode météo historique ----------------------------------------------------


@pytest.fixture
def partie_climat(partie_type):
    """La partie_type, mais les capteurs annoncent le mois de chaque mesure (rpi3 : mesure sans mois, rpi4 : aucune)."""
    manche = partie_type.manche()
    manche.mesures = {"rpi1": [12.0, 3.0], "rpi2": [24.0, -3.0], "rpi3": [20.0], "rpi4": []}
    manche.mois = {"rpi1": [6, 11], "rpi2": [7, 1], "rpi3": [None]}
    return partie_type


def test_partie_sans_mois_n_est_pas_en_mode_climat(partie_type):
    assert partie_type.climat() is False


def test_partie_dont_les_capteurs_annoncent_un_mois_est_en_mode_climat(partie_climat):
    assert partie_climat.climat() is True


def test_tableau_climat_affiche_les_mois_sans_verdict_de_stabilite(partie_climat):
    tableau = ia.tableau_mesures(partie_climat)

    assert "- Mimi, Seynod : juil. 24.0 °C ; janv. -3.0 °C" in tableau
    assert "- Sherlock (toi), Annecy : juin 12.0 °C ; nov. 3.0 °C" in tableau
    assert "- Kaito, Poisy : ? 20.0 °C" in tableau
    assert "- Yuki : aucune mesure" in tableau
    assert "STABLE" not in tableau


def test_consigne_du_capteur_honnete_parle_de_climat_en_mode_climat(cerveau, partie_climat, llm_repond):
    appels = llm_repond("Ok.")

    cerveau.parler(partie_climat, 1, 2, delai=30)

    systeme = appels[0]["messages"][0]["content"]
    assert "VRAIE température de sa ville" in systeme
    assert "garde le même écart" not in systeme   # la règle du mode normal serait fausse ici


def test_consigne_de_l_espion_en_mode_climat(config_joueur, partie_climat, monkeypatch):
    partie_climat.role = "espion"
    cerveau = ia.IA(config_joueur)
    appels = []
    monkeypatch.setattr(cerveau, "discuter", lambda messages, *a, **k: appels.append(messages) or "Ok.")

    cerveau.parler(partie_climat, 1, 2, delai=30)

    assert "calculées d'après la moyenne des autres" in appels[0][0]["content"]


def test_vote_honnete_par_calcul_est_ignore_en_mode_climat(config_joueur, partie_climat, monkeypatch):
    config_joueur["vote_honnete"] = "calcul"
    cerveau = ia.IA(config_joueur)
    appels = []
    monkeypatch.setattr(cerveau, "discuter", lambda messages, *a, **k: appels.append(messages) or '{"suspect": "rpi2", "raison": "Mimi."}')

    assert cerveau.voter(partie_climat, delai=30)[0] == "rpi2"
    assert len(appels) == 1   # le calcul ne trouve plus rien quand tout le monde varie : le LLM juge le climat


# --- Prise de parole ----------------------------------------------------------


def test_parler_renvoie_la_reponse_nettoyee(cerveau, partie_type, llm_repond):
    llm_repond("<think>hmm</think>Sherlock : Kaito, tes valeurs sautent.")

    assert cerveau.parler(partie_type, 1, 2, delai=30) == "Kaito, tes valeurs sautent."


def test_parler_un_aveu_est_remplace(cerveau, partie_type, llm_repond):
    llm_repond("Bon, je suis l'espion, j'avoue.")

    assert "Kaito" in cerveau.parler(partie_type, 1, 2, delai=30)   # réplique de secours : accuse avec les chiffres


def test_parler_une_negation_n_est_pas_un_aveu(cerveau, partie_type, llm_repond):
    llm_repond("Je ne suis pas l'espion, regardez mes chiffres.")

    assert cerveau.parler(partie_type, 1, 2, delai=30) == "Je ne suis pas l'espion, regardez mes chiffres."


def test_parler_reponse_vide_est_remplacee(cerveau, partie_type, llm_repond):
    llm_repond("<think>rien</think>")

    assert "Kaito" in cerveau.parler(partie_type, 1, 2, delai=30)   # réplique de secours : accuse avec les chiffres


def test_parler_ollama_injoignable(cerveau, partie_type, llm_repond):
    llm_repond(requests.Timeout("trop lent"))

    assert "Kaito" in cerveau.parler(partie_type, 1, 2, delai=30)   # réplique de secours : accuse avec les chiffres


def test_parler_sans_mesures_ni_llm_phrase_neutre(cerveau, partie_type, llm_repond):
    partie_type.manche().mesures = {}
    llm_repond(requests.Timeout("trop lent"))

    assert cerveau.parler(partie_type, 1, 2, delai=30) == ia.REPLI_PAROLE


def test_parler_le_contexte_cite_les_repliques_des_autres(cerveau, partie_type, llm_repond):
    partie_type.manche().debat.append(("rpi2", "Kaito ment."))
    appels = llm_repond("D'accord.")

    cerveau.parler(partie_type, 1, 2, delai=30)

    assert "- Mimi a dit « Kaito ment. »" in appels[0]["messages"][-1]["content"]


def test_parler_l_espion_recoit_un_conseil_secret(config_joueur, partie_type, monkeypatch):
    partie_type.role = "espion"
    cerveau = ia.IA(config_joueur)
    appels = []
    monkeypatch.setattr(cerveau, "discuter", lambda messages, *a, **k: appels.append(messages) or "Ok.")

    cerveau.parler(partie_type, 1, 2, delai=30)

    assert "Ton rôle secret : ESPION" in appels[0][0]["content"]
    assert "oriente les soupçons vers Kaito" in appels[0][-1]["content"]


def test_parler_un_capteur_honnete_ne_recoit_pas_de_conseil(cerveau, partie_type, llm_repond):
    appels = llm_repond("Ok.")

    cerveau.parler(partie_type, 1, 2, delai=30)

    assert "Conseil secret" not in appels[0]["messages"][-1]["content"]


# --- Mémoire entre les manches ------------------------------------------------


@pytest.fixture
def manche_passee(partie_type):
    """La manche 1 est finie (rpi2 éliminé, innocent) et la manche 2 commence."""
    manche = partie_type.manche(1)
    manche.debat = [("rpi2", "Kaito ment."), ("rpi3", "Non."), ("rpi2", "Si, regardez ses valeurs.")]
    manche.verdict = {"partie": ID_PARTIE, "manche": 1, "votes": {"rpi1": "rpi2", "rpi3": "rpi2", "rpi2": "rpi3"},
                      "compte": {"rpi2": 2, "rpi3": 1}, "elimine": "rpi2", "egalite": False, "etait_espion": False}
    partie_type.numero, partie_type.vivants = 2, ["rpi1", "rpi3", "rpi4"]
    return partie_type


def test_memoire_cite_l_elimine_et_son_role(manche_passee):
    assert "- Mimi a été éliminé avec 2 vote(s) : il n'était PAS l'espion." in ia.memoire(manche_passee)


def test_memoire_espion_elimine(manche_passee):
    manche_passee.manche(1).verdict["etait_espion"] = True

    assert "C'ÉTAIT l'espion" in ia.memoire(manche_passee)


def test_memoire_egalite(manche_passee):
    manche_passee.manche(1).verdict.update(elimine=None, egalite=True, etait_espion=None)

    assert "- Égalité aux votes : personne n'a été éliminé." in ia.memoire(manche_passee)


def test_memoire_rappelle_qui_a_vote_contre_qui(manche_passee):
    assert "- Votes : Sherlock contre Mimi, Kaito contre Mimi, Mimi contre Kaito." in ia.memoire(manche_passee)


def test_memoire_garde_la_derniere_replique_de_chacun(manche_passee):
    memoire = ia.memoire(manche_passee)

    assert "- Mimi a dit : « Si, regardez ses valeurs. »" in memoire
    assert "Kaito ment." not in memoire


def test_memoire_tronque_les_longues_repliques(manche_passee):
    manche_passee.manche(1).debat = [("rpi3", "mot " * 60)]

    replique = next(ligne for ligne in ia.memoire(manche_passee).splitlines() if "Kaito a dit" in ligne)
    assert replique.endswith("… »")
    assert len(replique) < ia.CITATION + 30


def test_memoire_inclut_les_notes_du_llm(manche_passee):
    manche_passee.souvenirs[1] = "Kaito me paraît louche."

    assert "- Tes notes : Kaito me paraît louche." in ia.memoire(manche_passee)


def test_memoire_ne_reprend_pas_la_manche_en_cours(manche_passee):
    manche_passee.manche(2).debat.append(("rpi4", "Manche en cours."))

    assert "Manche 2" not in ia.memoire(manche_passee)


def test_memoire_vide_a_la_premiere_manche(partie_type):
    assert ia.memoire(partie_type) == ""


def test_situation_cite_les_elimines(manche_passee):
    manche_passee.participants = ["rpi1", "rpi2", "rpi3", "rpi4"]

    assert ia.situation(manche_passee) == ("Manche 2. Joueurs encore en jeu : Sherlock (toi), Kaito, Yuki. "
                                           "Éliminés : Mimi.")


def test_resumer_renvoie_les_notes(cerveau, manche_passee, llm_repond):
    llm_repond("Kaito est louche. Yuki est fiable.")

    assert cerveau.resumer(manche_passee, delai=10) == "Kaito est louche. Yuki est fiable."


def test_resumer_ollama_injoignable_ne_donne_rien(cerveau, manche_passee, llm_repond):
    llm_repond(requests.ConnectionError("absent"))

    assert cerveau.resumer(manche_passee, delai=10) is None


# --- Agent conversationnel ----------------------------------------------------


def test_repondre_transmet_l_historique(cerveau, llm_repond):
    appels = llm_repond("Il fait beau.")
    historique = [{"role": "user", "content": "Salut"}, {"role": "assistant", "content": "Bonjour !"}]

    assert cerveau.repondre(historique, "Quel temps ?") == "Il fait beau."
    assert appels[0]["messages"][1:] == [*historique, {"role": "user", "content": "Quel temps ?"}]


# --- Partie -------------------------------------------------------------------


def test_autres_exclut_soi_meme(partie_type):
    assert partie_type.autres() == ["rpi2", "rpi3", "rpi4"]


def test_autres_sans_vivants_connus_utilise_les_mesures():
    partie = ia.Partie(ID_PARTIE, "rpi1", "normal")
    partie.manche(1).mesures = {"rpi1": [1.0], "rpi5": [2.0]}
    partie.numero = 1

    assert partie.autres() == ["rpi5"]


def test_nom_par_defaut_est_l_id():
    assert ia.Partie(ID_PARTIE, "rpi1", "normal").nom("rpi7") == "rpi7"
