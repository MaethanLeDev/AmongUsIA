"""Le joueur (joueur.py), vu de l'extérieur : ce qu'il publie sur MQTT et ce qu'il demande à Ollama.

Les tests ne lisent pas ses attributs internes. Ce qu'il a retenu des autres se voit dans le champ « calcul »
de son vote (la méthode sans LLM) ou dans le contexte qu'il envoie au LLM.
"""
import json
import random

import pytest
from aides import ID_PARTIE, FauxClientMQTT, FauxMessage

import joueur

AUTRE_PARTIE = ID_PARTIE - 500
STABLES = {"rpi2": [12.0] * 5, "rpi4": [12.1] * 5}
INSTABLE = [13.4, 11.0, 13.9, 10.8, 13.6]


def temperatures(j):
    return j.client.publies("iot/capteurs/rpi1/temperature")


def votes(j):
    return j.client.publies("iot/votes/rpi1")


def repliques(j):
    return j.client.publies("iot/chat/rpi1")


def mesure(id_joueur, temperature, echange=1, manche=1, partie=ID_PARTIE):
    return f"iot/capteurs/{id_joueur}/temperature", {"id": id_joueur, "temperature": temperature, "echange": echange,
                                                     "manche": manche, "partie": partie}


def publier_mesures(j, series, manche=1, partie=ID_PARTIE):
    """series = {"rpi2": [12.0, ...]} : ces joueurs publient leurs températures, un échange après l'autre."""
    for id_joueur, valeurs in series.items():
        for echange, valeur in enumerate(valeurs, start=1):
            j.client.injecter(*mesure(id_joueur, valeur, echange, manche, partie))


def parole(joueur="rpi1", tour=1, manche=1, partie=ID_PARTIE):
    return {"partie": partie, "manche": manche, "joueur": joueur, "tour": tour, "tours": 2, "rang": 1, "sur": 4,
            "delai": 90, "fin": ID_PARTIE + 90}


def donner_la_parole(j, **champs):
    j.client.injecter("iot/partie/parole", parole(**champs))


# --- Rôle et partie en cours --------------------------------------------------


def test_capteur_honnete_publie_la_meteo_de_sa_ville(en_partie, annoncer_phase):
    j = en_partie("normal")

    annoncer_phase("mesures")

    assert {m["temperature"] for m in temperatures(j)} == {12.3}


def test_sans_role_le_joueur_ne_mesure_pas(joueur_jeu, annoncer_phase):
    annoncer_phase("mesures")

    assert temperatures(joueur_jeu) == []


def test_role_inconnu_est_ignore(joueur_jeu, donner_role, annoncer_phase):
    donner_role("roi")

    annoncer_phase("mesures")

    assert temperatures(joueur_jeu) == []


def test_role_recu_deux_fois_garde_ce_qui_a_ete_entendu(en_partie, donner_role, annoncer_phase):
    j = en_partie()
    publier_mesures(j, {**STABLES, "rpi3": INSTABLE})

    donner_role("normal")   # renvoyé par le maître après une reconnexion
    annoncer_phase("vote")

    assert votes(j)[0]["calcul"] == "rpi3"


def test_etat_d_une_autre_partie_met_fin_a_la_partie_en_cours(en_partie, annoncer_phase):
    j = en_partie()

    annoncer_phase("debat", partie=AUTRE_PARTIE)
    annoncer_phase("mesures")

    assert temperatures(j) == []


@pytest.mark.parametrize("etat", ["inscription", "arret"])
def test_inscription_ou_arret_met_fin_a_la_partie_en_cours(en_partie, annoncer_phase, etat):
    j = en_partie()

    j.client.injecter("iot/partie/etat", {"etat": etat}, retain=True)
    annoncer_phase("mesures")

    assert temperatures(j) == []


def test_elimine_ne_mesure_ni_ne_vote(en_partie, annoncer_phase):
    j = en_partie()
    publier_mesures(j, {**STABLES, "rpi3": INSTABLE})

    annoncer_phase("mesures", manche=2, vivants=["rpi2", "rpi3", "rpi4"])
    annoncer_phase("vote", manche=2, vivants=["rpi2", "rpi3", "rpi4"])

    assert j.client.publications == []


def test_vote_ne_suit_pas_le_llm_vers_un_elimine(en_partie, annoncer_phase, llm):
    j = en_partie()
    publier_mesures(j, {**STABLES, "rpi3": INSTABLE})
    llm.vote = '{"suspect": "rpi2", "raison": "Mimi ment."}'

    annoncer_phase("vote", vivants=["rpi1", "rpi3", "rpi4"])   # rpi2 a été éliminé

    assert votes(j)[0]["suspect"] == "rpi3"


# --- Une seule action par phase -----------------------------------------------


def test_etat_retenu_recu_deux_fois_ne_mesure_qu_une_fois(en_partie, annoncer_phase):
    j = en_partie()

    annoncer_phase("mesures")
    annoncer_phase("mesures")   # reconnexion : le broker renvoie le message retenu

    assert len(temperatures(j)) == 5


def test_nouvelle_manche_relance_la_mesure(en_partie, annoncer_phase):
    j = en_partie()

    annoncer_phase("mesures", manche=1)
    annoncer_phase("mesures", manche=2)

    assert [m["manche"] for m in temperatures(j)] == [1] * 5 + [2] * 5


def test_etat_recu_avant_le_role_la_phase_demarre_a_l_arrivee_du_role(joueur_jeu, annoncer_phase, donner_role):
    annoncer_phase("mesures")   # le joueur démarre en pleine phase : l'état retenu arrive avant le rôle

    donner_role()

    assert len(temperatures(joueur_jeu)) == 5


def test_debat_ne_publie_rien_sans_avoir_la_parole(en_partie, annoncer_phase):
    j = en_partie()

    annoncer_phase("debat", tours=2)

    assert j.client.publications == []


def test_etat_de_vote_recu_deux_fois_ne_vote_qu_une_fois(en_partie, annoncer_phase):
    j = en_partie()
    publier_mesures(j, {**STABLES, "rpi3": INSTABLE})

    annoncer_phase("vote")
    annoncer_phase("vote")

    assert len(votes(j)) == 1


def test_parole_recue_deux_fois_ne_parle_qu_une_fois(en_partie):
    j = en_partie()

    donner_la_parole(j)
    donner_la_parole(j)

    assert len(repliques(j)) == 1


def test_parole_au_tour_suivant_parle_de_nouveau(en_partie):
    j = en_partie()

    donner_la_parole(j, tour=1)
    donner_la_parole(j, tour=2)

    assert [r["tour"] for r in repliques(j)] == [1, 2]


def test_parole_donnee_a_un_autre_le_joueur_se_tait(en_partie):
    j = en_partie()

    donner_la_parole(j, joueur="rpi2")

    assert repliques(j) == []


def test_parole_d_une_autre_partie_ignoree(en_partie):
    j = en_partie()

    donner_la_parole(j, partie=AUTRE_PARTIE)

    assert repliques(j) == []


# --- Ce que le joueur retient des autres --------------------------------------


def test_mesures_des_autres_designent_le_suspect_du_calcul(en_partie, annoncer_phase):
    j = en_partie()
    publier_mesures(j, {**STABLES, "rpi3": INSTABLE})

    annoncer_phase("vote")

    assert votes(j)[0]["calcul"] == "rpi3"


def test_mesures_de_chaque_manche_comptent_separement(en_partie, annoncer_phase):
    j = en_partie()
    publier_mesures(j, {"rpi2": [12.0] * 5, "rpi3": INSTABLE, "rpi4": [12.1] * 5}, manche=1)
    publier_mesures(j, {"rpi2": [12.0] * 5, "rpi3": [12.1] * 5, "rpi4": INSTABLE}, manche=2)

    annoncer_phase("vote", manche=2)

    assert votes(j)[0]["calcul"] == "rpi4"


def test_mesures_d_une_autre_partie_ignorees(en_partie, annoncer_phase):
    j = en_partie()
    publier_mesures(j, STABLES)
    publier_mesures(j, {"rpi3": INSTABLE}, partie=AUTRE_PARTIE)

    annoncer_phase("vote")

    assert votes(j)[0]["calcul"] != "rpi3"


def test_temperature_qui_n_est_pas_un_nombre_ignoree(en_partie, annoncer_phase):
    j = en_partie()
    publier_mesures(j, {**STABLES, "rpi3": [str(v) for v in INSTABLE]})

    annoncer_phase("vote")

    assert votes(j)[0]["calcul"] != "rpi3"


@pytest.mark.xfail(reason="bug : une mesure reçue deux fois (QoS 1) est ajoutée deux fois ; les échanges suivants "
                          "sont décalés et le calcul accuse un capteur honnête")
def test_mesure_recue_deux_fois_ne_fausse_pas_le_calcul(en_partie, annoncer_phase):
    # Les températures montent pour tout le monde ; rpi4 est décalé de 0,6 °C (l'espion)
    j = en_partie()
    honnete = [11.0, 12.0, 13.0, 14.0, 15.0]
    publier_mesures(j, {"rpi2": honnete, "rpi4": [v + 0.6 for v in honnete]})
    j.client.injecter(*mesure("rpi3", honnete[0], echange=1))   # premier échange de rpi3 reçu en double
    publier_mesures(j, {"rpi3": honnete})

    annoncer_phase("vote")

    assert votes(j)[0]["calcul"] == "rpi4"


def test_repliques_des_autres_transmises_au_llm(en_partie, llm):
    j = en_partie()
    j.client.injecter("iot/chat/rpi2", {"text": "Kaito ment.", "partie": ID_PARTIE, "manche": 1, "tour": 1})

    donner_la_parole(j)

    assert "« Kaito ment. »" in llm.prompts()[-1]


def test_replique_d_une_autre_partie_pas_transmise_au_llm(en_partie, llm):
    j = en_partie()
    j.client.injecter("iot/chat/rpi2", {"text": "Vieux message.", "partie": AUTRE_PARTIE, "manche": 1})

    donner_la_parole(j)

    assert "Vieux message." not in llm.prompts()[-1]


@pytest.mark.xfail(reason="bug : une réplique reçue deux fois (QoS 1) apparaît deux fois dans le débat montré au LLM")
def test_replique_recue_deux_fois_transmise_une_fois(en_partie, llm):
    j = en_partie()
    message = {"text": "Kaito ment.", "partie": ID_PARTIE, "manche": 1, "tour": 1}
    j.client.injecter("iot/chat/rpi2", message)
    j.client.injecter("iot/chat/rpi2", message)

    donner_la_parole(j)

    assert llm.prompts()[-1].count("Kaito ment.") == 1


def test_verdict_rappele_au_llm_a_la_manche_suivante(en_partie, annoncer_phase, llm):
    j = en_partie()
    j.client.injecter("iot/partie/verdict", {"partie": ID_PARTIE, "manche": 1, "votes": {"rpi1": "rpi2"},
                                             "compte": {"rpi2": 3}, "elimine": "rpi2", "etait_espion": False})
    annoncer_phase("debat", manche=2, vivants=["rpi1", "rpi3", "rpi4"])

    donner_la_parole(j, manche=2)

    assert "rpi2 a été éliminé avec 3 vote(s) : il n'était PAS l'espion." in llm.prompts()[-1]


def test_votes_des_autres_rappeles_au_llm_a_la_manche_suivante(en_partie, annoncer_phase, llm):
    j = en_partie()
    j.client.injecter("iot/votes/rpi2", {"votant": "rpi2", "suspect": "rpi3", "partie": ID_PARTIE, "manche": 1})
    j.client.injecter("iot/partie/verdict", {"partie": ID_PARTIE, "manche": 1, "elimine": None, "egalite": True})
    annoncer_phase("debat", manche=2)

    donner_la_parole(j, manche=2)

    assert "- Votes : rpi2 contre rpi3." in llm.prompts()[-1]


def test_verdict_d_une_autre_partie_pas_rappele(en_partie, annoncer_phase, llm):
    j = en_partie()
    j.client.injecter("iot/partie/verdict", {"partie": AUTRE_PARTIE, "manche": 1, "elimine": "rpi2", "etait_espion": True})
    annoncer_phase("debat", manche=2)

    donner_la_parole(j, manche=2)

    assert "éliminé" not in llm.prompts()[-1]


def test_noms_des_autres_transmis_au_llm(en_partie, llm):
    j = en_partie()
    j.client.injecter("iot/joueurs/rpi2", {"id": "rpi2", "en_ligne": True, "nom": "Mimi", "ville": "Seynod"})

    donner_la_parole(j)

    assert "Mimi" in llm.prompts()[-1]


def test_joueur_parti_garde_son_nom(en_partie, llm):
    j = en_partie()
    j.client.injecter("iot/joueurs/rpi2", {"id": "rpi2", "en_ligne": True, "nom": "Mimi"})
    j.client.injecter("iot/joueurs/rpi2", {"id": "rpi2", "en_ligne": False})

    donner_la_parole(j)

    assert "Mimi" in llm.prompts()[-1]


def test_messages_malformes_ne_l_empechent_pas_de_jouer(en_partie, annoncer_phase):
    j = en_partie()
    for topic in ("iot/partie/etat", "iot/role/rpi1", "iot/capteurs/rpi2/temperature", "iot/chat/rpi2",
                  "iot/votes/rpi2", "iot/partie/verdict", "iot/partie/parole", "iot/joueurs/rpi2"):
        j.client.injecter(topic, b"\xff{pas du json")
    publier_mesures(j, {**STABLES, "rpi3": INSTABLE})

    annoncer_phase("vote")

    assert len(votes(j)) == 1


# --- Mesures ------------------------------------------------------------------


def test_mesure_publie_cinq_temperatures_conformes_au_protocole(en_partie, annoncer_phase):
    j = en_partie()

    annoncer_phase("mesures")

    assert [m["echange"] for m in temperatures(j)] == [1, 2, 3, 4, 5]
    assert temperatures(j)[0] == {"id": "rpi1", "ville": "Annecy", "temperature": 12.3, "echange": 1, "manche": 1,
                                  "partie": ID_PARTIE, "ts": ID_PARTIE}


def test_mesure_toutes_les_cinq_secondes(en_partie, annoncer_phase):
    j = en_partie()

    annoncer_phase("mesures")

    assert [m["ts"] - ID_PARTIE for m in temperatures(j)] == [0, 5, 10, 15, 20]


def test_mesure_garde_le_rythme_si_la_meteo_est_lente(en_partie, annoncer_phase, meteo_service, temps):
    def meteo_lente():
        temps.maintenant += 2   # Open-Meteo met 2 s à répondre
        return 12.0
    meteo_service.valeur = meteo_lente
    j = en_partie()

    annoncer_phase("mesures")

    assert [m["ts"] - ID_PARTIE for m in temperatures(j)] == [2, 7, 12, 17, 22]


def test_mesure_s_arrete_quand_la_phase_change(en_partie, annoncer_phase, meteo_service):
    appels = []

    def meteo():
        appels.append(1)
        if len(appels) == 2:
            annoncer_phase("debat")   # le maître passe au débat avant la fin des 5 échanges
        return 12.0
    meteo_service.valeur = meteo
    j = en_partie()

    annoncer_phase("mesures")

    assert len(temperatures(j)) == 2


def test_mesure_sans_meteo_ne_publie_rien(en_partie, annoncer_phase, meteo_service):
    meteo_service.valeur = None
    j = en_partie()

    annoncer_phase("mesures")

    assert temperatures(j) == []


# --- Fausses températures de l'espion -----------------------------------------


@pytest.fixture
def tirages(monkeypatch):
    """tirages(ecart, sens) fixe le hasard de l'espion : décalage de ecart (0,05 à 0,10), vers le haut (+1) ou le bas (-1)."""
    def fixer(ecart=0.10, sens=1):
        monkeypatch.setattr(random, "uniform", lambda a, b: ecart)
        monkeypatch.setattr(random, "choice", lambda sequence: sens)
    return fixer


def fausse_temperature_publiee(j, annoncer_phase, manche=1):
    annoncer_phase("mesures", manche=manche)
    return temperatures(j)[-1]["temperature"]


def test_espion_part_de_la_moyenne_des_dernieres_valeurs_des_autres(en_partie, annoncer_phase, tirages):
    j = en_partie("espion")
    tirages(ecart=0.10, sens=1)
    publier_mesures(j, {"rpi2": [30.0, 12.0], "rpi3": [14.0]})   # dernières valeurs : 12 et 14, moyenne 13

    assert fausse_temperature_publiee(j, annoncer_phase) == 14.3


def test_espion_ignore_ses_propres_valeurs(en_partie, annoncer_phase, tirages):
    j = en_partie("espion")
    tirages(ecart=0.10, sens=-1)
    publier_mesures(j, {"rpi1": [50.0], "rpi2": [20.0]})

    assert fausse_temperature_publiee(j, annoncer_phase) == 18.0


def test_espion_ecart_minimum_pres_de_zero(en_partie, annoncer_phase, tirages):
    j = en_partie("espion")
    tirages(ecart=0.05, sens=1)
    publier_mesures(j, {"rpi2": [1.0]})   # 5 % de 1 °C ne se verrait pas : au moins 0,3 °C

    assert fausse_temperature_publiee(j, annoncer_phase) == 1.3


def test_espion_temperature_negative(en_partie, annoncer_phase, tirages):
    j = en_partie("espion")
    tirages(ecart=0.10, sens=1)
    publier_mesures(j, {"rpi2": [-10.0]})

    assert fausse_temperature_publiee(j, annoncer_phase) == -9.0


def test_espion_decale_de_cinq_a_dix_pour_cent_vers_le_haut_ou_le_bas(en_partie, annoncer_phase):
    j = en_partie("espion")
    for manche in range(1, 41):
        publier_mesures(j, {"rpi2": [100.0]}, manche=manche)
        annoncer_phase("mesures", manche=manche)

    publiees = [m["temperature"] for m in temperatures(j)]
    assert len(publiees) == 200
    assert all(0.0495 <= abs(t - 100.0) / 100.0 <= 0.1005 for t in publiees)   # arrondi au dixième
    assert {t > 100.0 for t in publiees} == {True, False}


def test_espion_sans_mesure_des_autres_part_de_sa_vraie_temperature(en_partie, annoncer_phase, tirages, meteo_service):
    meteo_service.valeur = 10.0
    j = en_partie("espion")
    tirages(ecart=0.10, sens=-1)

    assert fausse_temperature_publiee(j, annoncer_phase) == 9.0


def test_espion_sans_aucune_donnee_ne_publie_rien(en_partie, annoncer_phase, meteo_service):
    meteo_service.valeur = None
    j = en_partie("espion")

    annoncer_phase("mesures")

    assert temperatures(j) == []


# --- Vote, parole, mémoire ----------------------------------------------------


def test_vote_publie_suspect_raison_et_calcul(en_partie, annoncer_phase):
    j = en_partie()
    publier_mesures(j, {"rpi2": INSTABLE, "rpi3": [12.0] * 5, "rpi4": [12.1] * 5})   # le calcul accuse rpi2

    annoncer_phase("vote")

    assert votes(j) == [{"votant": "rpi1", "suspect": "rpi3", "raison": "Ses valeurs sautent.", "calcul": "rpi2",
                         "strategie": "llm", "partie": ID_PARTIE, "manche": 1}]


def test_vote_laisse_dix_secondes_de_marge_au_llm(en_partie, annoncer_phase, llm):
    j = en_partie()
    publier_mesures(j, STABLES)

    annoncer_phase("vote")   # la phase finit dans 60 s

    assert llm.requetes[-1]["timeout"] == 50


def test_vote_trop_tard_n_est_pas_publie(en_partie, annoncer_phase, llm):
    j = en_partie()
    publier_mesures(j, STABLES)
    llm.pendant = lambda corps: annoncer_phase("verdict")   # le maître clôt le vote pendant que le LLM réfléchit

    annoncer_phase("vote")

    assert votes(j) == []


def test_vote_sans_aucune_donnee_ni_avis_du_llm_n_est_pas_publie(en_partie, annoncer_phase, llm):
    j = en_partie()
    llm.vote = "Je ne sais pas."

    annoncer_phase("vote")

    assert votes(j) == []


def test_parole_publie_la_replique_dans_le_chat(en_partie):
    j = en_partie()

    donner_la_parole(j, tour=2)

    assert repliques(j) == [{"text": "Kaito, explique-toi.", "partie": ID_PARTIE, "manche": 1, "tour": 2}]


def test_parole_trop_tard_n_est_pas_publiee(en_partie, llm, temps):
    j = en_partie()

    def reflechir_longtemps(corps):
        temps.maintenant += 100   # la parole (90 s) est passée au suivant
    llm.pendant = reflechir_longtemps

    donner_la_parole(j)

    assert repliques(j) == []


def test_memoire_faits_n_interroge_pas_le_llm_au_verdict(en_partie, annoncer_phase, llm):
    en_partie()

    annoncer_phase("verdict")

    assert llm.requetes == []


@pytest.mark.parametrize("config_joueur", [{"memoire": "resume"}], indirect=True)
def test_memoire_resume_rappelle_ses_notes_a_la_manche_suivante(en_partie, annoncer_phase, llm):
    j = en_partie()
    publier_mesures(j, STABLES)
    llm.parole = "Kaito est louche."
    annoncer_phase("verdict")
    annoncer_phase("debat", manche=2)
    llm.parole = "Je maintiens."

    donner_la_parole(j, manche=2)

    assert "Tes notes : Kaito est louche." in llm.prompts()[-1]


@pytest.mark.parametrize("config_joueur", [{"memoire": "resume"}], indirect=True)
def test_memoire_resume_une_seule_fois_par_verdict(en_partie, annoncer_phase, llm):
    en_partie()

    annoncer_phase("verdict")
    annoncer_phase("verdict")

    assert len(llm.requetes) == 1


# --- Présence, connexion, fiche de l'agent ------------------------------------


def test_last_will_annonce_le_depart(joueur_jeu):
    assert joueur_jeu.client.will == ("iot/joueurs/rpi1", {"id": "rpi1", "en_ligne": False}, True)


def test_connexion_s_abonne_a_son_role_et_pas_a_celui_des_autres(joueur_jeu):
    joueur_jeu._on_connect(joueur_jeu.client, None, {}, 0, None)

    topics = [topic for topic, _ in joueur_jeu.client.abonnements[0]]
    assert "iot/role/rpi1" in topics
    assert not any(t.startswith("iot/role/") and t != "iot/role/rpi1" for t in topics)


def test_connexion_publie_la_presence_retenue(joueur_jeu):
    joueur_jeu.url_api = "http://10.0.0.5:5000"

    joueur_jeu._on_connect(joueur_jeu.client, None, {}, 0, None)

    publication = joueur_jeu.client.retenu("iot/joueurs/rpi1")
    assert publication.retain is True
    assert publication.contenu == {"id": "rpi1", "ville": "Annecy", "en_ligne": True, "modele": "qwen3:0.6b",
                                   "strategie": "llm", "nom": "Sherlock", "arch": "stratege",
                                   "couleurs": {"accent": "#c1121f"}, "api": "http://10.0.0.5:5000"}


def test_fiche_de_l_espion_identique_a_celle_d_un_capteur(joueur_jeu, donner_role):
    # GET /agent ne doit jamais révéler le rôle, même indirectement
    donner_role("espion")
    fiche_espion = joueur_jeu.fiche()
    donner_role("normal", partie=ID_PARTIE + 1)

    assert fiche_espion == joueur_jeu.fiche()
    assert "role" not in json.dumps(fiche_espion)


def test_sante_indique_broker_et_ollama(joueur_jeu):
    joueur_jeu.client.connect("localhost")

    assert joueur_jeu.sante() == {"status": "ok", "id": "rpi1", "broker": True, "ollama": True}


# --- config.json --------------------------------------------------------------


@pytest.fixture
def ecrire_config(tmp_path):
    def ecrire(contenu):
        chemin = tmp_path / "config.json"
        chemin.write_text(contenu if isinstance(contenu, str) else json.dumps(contenu), encoding="utf-8")
        return chemin
    return ecrire


def test_config_minimale_recoit_les_valeurs_par_defaut_d_ollama(ecrire_config):
    config = joueur.lire_config(ecrire_config({"id": "rpi1", "ville": "Annecy"}))

    assert config["ollama"] == {"url": "http://127.0.0.1:11434", "modele": "qwen3:0.6b"}


def test_config_garde_le_modele_choisi(ecrire_config):
    config = joueur.lire_config(ecrire_config({"id": "rpi1", "ville": "Annecy", "ollama": {"modele": "llama3.2:1b"}}))

    assert config["ollama"]["modele"] == "llama3.2:1b"


def test_config_absente(tmp_path):
    with pytest.raises(SystemExit, match="Config introuvable"):
        joueur.lire_config(tmp_path / "config.json")


def test_config_json_invalide(ecrire_config):
    with pytest.raises(SystemExit, match="pas du JSON valide"):
        joueur.lire_config(ecrire_config('{"id": "rpi1",'))


@pytest.mark.parametrize("id_joueur", ["", "rpi 1", "rpi/1", "rpi+", "rpi#", 7, None])
def test_config_id_invalide(ecrire_config, id_joueur):
    with pytest.raises(SystemExit, match='"id"'):
        joueur.lire_config(ecrire_config({"id": id_joueur, "ville": "Annecy"}))


def test_config_sans_ville(ecrire_config):
    with pytest.raises(SystemExit, match='"ville"'):
        joueur.lire_config(ecrire_config({"id": "rpi1"}))


def test_config_strategie_inconnue(ecrire_config):
    with pytest.raises(SystemExit, match='"strategie"'):
        joueur.lire_config(ecrire_config({"id": "rpi1", "ville": "Annecy", "strategie": "hasard"}))


def test_config_memoire_inconnue(ecrire_config):
    with pytest.raises(SystemExit, match='"memoire"'):
        joueur.lire_config(ecrire_config({"id": "rpi1", "ville": "Annecy", "memoire": "tout"}))


def test_config_liste_toutes_les_erreurs_d_un_coup(ecrire_config):
    with pytest.raises(SystemExit) as erreur:
        joueur.lire_config(ecrire_config({"id": "a b", "strategie": "?"}))

    assert all(champ in str(erreur.value) for champ in ('"id"', '"ville"', '"strategie"'))


@pytest.mark.xfail(reason="bug : un config.json qui n'est pas un objet JSON (ex : []) donne une trace "
                          "AttributeError au lieu d'un message clair")
def test_config_qui_n_est_pas_un_objet(ecrire_config):
    with pytest.raises(SystemExit):
        joueur.lire_config(ecrire_config("[]"))


def test_config_exemple_du_depot_est_valide():
    config = joueur.lire_config(joueur.Path(joueur.__file__).with_name("config.example.json"))

    assert config["id"] == "rpi1"


# --- Fonctions utilitaires ----------------------------------------------------


def test_connecter_essaie_le_broker_suivant():
    client = FauxClientMQTT()
    client.hotes_injoignables = {"amongus.local"}

    assert joueur.connecter(client, "amongus.local,10.109.150.215", 1883) == "10.109.150.215"


def test_connecter_sans_broker_joignable_arrete_le_programme():
    client = FauxClientMQTT()
    client.hotes_injoignables = {"amongus.local"}

    with pytest.raises(SystemExit, match="Aucun broker joignable"):
        joueur.connecter(client, "amongus.local", 1883)


def test_lire_json_qui_n_est_pas_un_objet():
    assert joueur.lire_json(b"[1]") == {}


def test_expediteur():
    assert joueur.expediteur(FauxMessage("iot/chat/rpi4", b"{}")) == "rpi4"
