"""Le joueur (joueur.py) : filtres partie/manche, une action par phase, mesures de l'espion, vote, config.json."""
import json
import random

import joueur
import pytest
from aides import ID_PARTIE, FauxClientMQTT, FauxMessage

from ia import Partie

AUTRE_PARTIE = ID_PARTIE - 500


def mesure(id_joueur, temperature, echange=1, manche=1, partie=ID_PARTIE):
    return f"iot/capteurs/{id_joueur}/temperature", {"id": id_joueur, "temperature": temperature, "echange": echange,
                                                     "manche": manche, "partie": partie}


# --- Rôle et partie en cours --------------------------------------------------


def test_role_cree_la_partie(joueur_jeu, donner_role):
    donner_role("espion")

    assert (joueur_jeu.partie.id, joueur_jeu.partie.role) == (ID_PARTIE, "espion")


def test_role_recu_deux_fois_garde_la_partie_en_cours(en_partie, donner_role):
    j = en_partie()
    j.client.injecter(*mesure("rpi2", 12.0))

    donner_role("normal")

    assert j.partie.manche(1).mesures == {"rpi2": [12.0]}


def test_role_inconnu_est_ignore(joueur_jeu, donner_role):
    donner_role("roi")

    assert joueur_jeu.partie is None


def test_etat_d_une_autre_partie_oublie_la_partie_en_cours(en_partie, annoncer_phase):
    j = en_partie()

    annoncer_phase("mesures", partie=AUTRE_PARTIE)

    assert j.partie is None


@pytest.mark.parametrize("etat", ["inscription", "arret"])
def test_inscription_ou_arret_oublie_la_partie_en_cours(en_partie, joueur_jeu, etat):
    j = en_partie()

    j.client.injecter("iot/partie/etat", {"etat": etat}, retain=True)

    assert j.partie is None


def test_etat_recopie_les_vivants_et_la_manche(en_partie, annoncer_phase):
    j = en_partie()

    annoncer_phase("debat", manche=2, vivants=["rpi1", "rpi3"])

    assert (j.partie.vivants, j.partie.numero) == (["rpi1", "rpi3"], 2)


# --- Une seule action par phase -----------------------------------------------


@pytest.mark.parametrize(("phase", "action"), [("mesures", "mesurer"), ("vote", "voter"), ("verdict", "memoriser")])
def test_phase_lance_son_action(en_partie, annoncer_phase, lances, phase, action):
    en_partie()

    annoncer_phase(phase)

    assert lances() == [action]


def test_etat_retenu_recu_deux_fois_ne_lance_qu_une_mesure(en_partie, annoncer_phase, lances):
    en_partie()

    annoncer_phase("mesures")
    annoncer_phase("mesures")   # reconnexion : le broker renvoie le message retenu

    assert lances() == ["mesurer"]


def test_nouvelle_manche_relance_la_mesure(en_partie, annoncer_phase, lances):
    en_partie()

    annoncer_phase("mesures", manche=1)
    annoncer_phase("mesures", manche=2)

    assert lances() == ["mesurer", "mesurer"]


def test_etat_retenu_recu_avant_le_role_lance_la_phase_a_l_arrivee_du_role(annoncer_phase, donner_role, lances):
    annoncer_phase("mesures")   # le joueur démarre en pleine phase : l'état retenu arrive avant le rôle
    assert lances() == []

    donner_role()

    assert lances() == ["mesurer"]


def test_phase_de_debat_ne_lance_rien(en_partie, annoncer_phase, lances):
    en_partie()

    annoncer_phase("debat", manche=1, tours=2)

    assert lances() == []


def test_elimine_ne_mesure_ni_ne_vote(en_partie, annoncer_phase, lances):
    en_partie()

    annoncer_phase("mesures", manche=2, vivants=["rpi2", "rpi3", "rpi4"])
    annoncer_phase("vote", manche=2, vivants=["rpi2", "rpi3", "rpi4"])

    assert lances() == []


def test_phase_d_une_partie_sans_role_ne_lance_rien(joueur_jeu, annoncer_phase, lances):
    annoncer_phase("mesures")

    assert lances() == []


def parole(joueur="rpi1", tour=1, partie=ID_PARTIE):
    return {"partie": partie, "manche": 1, "joueur": joueur, "tour": tour, "tours": 2, "rang": 1, "sur": 4,
            "delai": 90, "fin": ID_PARTIE + 90}


def test_parole_pour_moi_lance_une_seule_prise_de_parole(en_partie, lances):
    j = en_partie()

    j.client.injecter("iot/partie/parole", parole())
    j.client.injecter("iot/partie/parole", parole())

    assert lances() == ["parler"]


def test_parole_au_tour_suivant_relance_une_prise_de_parole(en_partie, lances):
    j = en_partie()

    j.client.injecter("iot/partie/parole", parole(tour=1))
    j.client.injecter("iot/partie/parole", parole(tour=2))

    assert lances() == ["parler", "parler"]


def test_parole_pour_un_autre_est_ignoree(en_partie, lances):
    j = en_partie()

    j.client.injecter("iot/partie/parole", parole(joueur="rpi2"))

    assert lances() == []


def test_parole_d_une_autre_partie_est_ignoree(en_partie, lances):
    j = en_partie()

    j.client.injecter("iot/partie/parole", parole(partie=AUTRE_PARTIE))

    assert lances() == []


# --- Ce que le joueur retient des autres --------------------------------------


def test_temperature_des_autres_est_retenue_par_manche(en_partie):
    j = en_partie()

    j.client.injecter(*mesure("rpi2", 12.4, manche=1))
    j.client.injecter(*mesure("rpi2", 13.0, manche=2))

    assert (j.partie.manche(1).mesures, j.partie.manche(2).mesures) == ({"rpi2": [12.4]}, {"rpi2": [13.0]})


def test_temperature_d_une_autre_partie_est_ignoree(en_partie):
    j = en_partie()

    j.client.injecter(*mesure("rpi2", 12.4, partie=AUTRE_PARTIE))

    assert j.partie.manche(1).mesures == {}


def test_temperature_qui_n_est_pas_un_nombre_est_ignoree(en_partie):
    j = en_partie()
    topic, contenu = mesure("rpi2", "12.4")

    j.client.injecter(topic, contenu)

    assert j.partie.manche(1).mesures == {}


@pytest.mark.xfail(reason="bug : une mesure reçue deux fois (QoS 1) est ajoutée deux fois, "
                          "ce qui décale les échanges comparés par analyser()")
def test_temperature_recue_deux_fois_n_est_retenue_qu_une_fois(en_partie):
    j = en_partie()

    j.client.injecter(*mesure("rpi2", 12.4, echange=1))
    j.client.injecter(*mesure("rpi2", 12.4, echange=1))

    assert j.partie.manche(1).mesures == {"rpi2": [12.4]}


def test_chat_des_autres_est_retenu(en_partie):
    j = en_partie()

    j.client.injecter("iot/chat/rpi2", {"text": "Kaito ment.", "partie": ID_PARTIE, "manche": 1, "tour": 1})

    assert j.partie.manche(1).debat == [("rpi2", "Kaito ment.")]


def test_chat_d_une_autre_partie_est_ignore(en_partie):
    j = en_partie()

    j.client.injecter("iot/chat/rpi2", {"text": "Vieux message.", "partie": AUTRE_PARTIE, "manche": 1})

    assert j.partie.manche(1).debat == []


@pytest.mark.xfail(reason="bug : une réplique reçue deux fois (QoS 1) apparaît deux fois dans le débat du LLM")
def test_chat_recu_deux_fois_n_est_retenu_qu_une_fois(en_partie):
    j = en_partie()
    message = {"text": "Kaito ment.", "partie": ID_PARTIE, "manche": 1, "tour": 1}

    j.client.injecter("iot/chat/rpi2", message)
    j.client.injecter("iot/chat/rpi2", message)

    assert j.partie.manche(1).debat == [("rpi2", "Kaito ment.")]


def test_vote_des_autres_est_retenu_une_fois(en_partie):
    j = en_partie()
    vote = {"votant": "rpi2", "suspect": "rpi3", "partie": ID_PARTIE, "manche": 1}

    j.client.injecter("iot/votes/rpi2", vote)
    j.client.injecter("iot/votes/rpi2", vote)

    assert j.partie.manche(1).votes == {"rpi2": "rpi3"}


def test_verdict_est_retenu_pour_la_memoire(en_partie):
    j = en_partie()
    verdict = {"partie": ID_PARTIE, "manche": 1, "elimine": "rpi2", "etait_espion": False}

    j.client.injecter("iot/partie/verdict", verdict)

    assert j.partie.manche(1).verdict == verdict


def test_verdict_d_une_autre_partie_est_ignore(en_partie):
    j = en_partie()

    j.client.injecter("iot/partie/verdict", {"partie": AUTRE_PARTIE, "manche": 1, "elimine": "rpi2"})

    assert j.partie.manche(1).verdict is None


def test_presence_retient_le_nom_et_la_ville(joueur_jeu):
    joueur_jeu.client.injecter("iot/joueurs/rpi2", {"id": "rpi2", "en_ligne": True, "nom": "Mimi", "ville": "Seynod"})
    joueur_jeu.client.injecter("iot/joueurs/rpi3", {"id": "rpi3", "en_ligne": True})

    assert joueur_jeu.noms == {"rpi2": "Mimi", "rpi3": "rpi3"}
    assert joueur_jeu.villes == {"rpi2": "Seynod", "rpi3": "?"}


def test_depart_garde_le_nom(joueur_jeu):
    joueur_jeu.client.injecter("iot/joueurs/rpi2", {"id": "rpi2", "en_ligne": True, "nom": "Mimi"})

    joueur_jeu.client.injecter("iot/joueurs/rpi2", {"id": "rpi2", "en_ligne": False})

    assert joueur_jeu.noms["rpi2"] == "Mimi"


def test_message_malforme_ne_plante_pas(en_partie):
    j = en_partie()

    for topic in ("iot/partie/etat", "iot/role/rpi1", "iot/capteurs/rpi2/temperature", "iot/chat/rpi2",
                  "iot/votes/rpi2", "iot/partie/verdict", "iot/partie/parole", "iot/joueurs/rpi2"):
        j.client.injecter(topic, b"\xff{pas du json")

    assert j.partie is not None


# --- Mesures ------------------------------------------------------------------


@pytest.fixture
def phase_mesures(en_partie, annoncer_phase, monkeypatch):
    """La phase de mesures est ouverte. meteo(valeurs ou fonction) règle ce que renvoie l'API météo."""
    def ouvrir(role="normal", meteo=12.34):
        j = en_partie(role)
        etat = annoncer_phase("mesures", echanges=5)
        monkeypatch.setattr(j.meteo, "temperature", meteo if callable(meteo) else lambda: meteo)
        return j, etat
    return ouvrir


def test_mesure_publie_cinq_temperatures(phase_mesures):
    j, etat = phase_mesures()

    j.mesurer(etat)

    publiees = j.client.publies("iot/capteurs/rpi1/temperature")
    assert [m["echange"] for m in publiees] == [1, 2, 3, 4, 5]
    assert publiees[0] == {"id": "rpi1", "ville": "Annecy", "temperature": 12.3, "echange": 1, "manche": 1,
                           "partie": ID_PARTIE, "ts": ID_PARTIE}


def test_mesure_toutes_les_cinq_secondes(phase_mesures, temps):
    j, etat = phase_mesures()

    j.mesurer(etat)

    assert temps.sommeils == [5, 5, 5, 5, 5]


def test_mesure_garde_le_rythme_si_la_meteo_est_lente(phase_mesures, temps):
    def meteo_lente():
        temps.maintenant += 2
        return 12.0
    j, etat = phase_mesures(meteo=meteo_lente)

    j.mesurer(etat)

    assert temps.sommeils == [3, 3, 3, 3, 3]


def test_mesure_s_arrete_quand_la_phase_change(phase_mesures, annoncer_phase):
    appels = []

    def meteo():
        appels.append(1)
        if len(appels) == 2:
            annoncer_phase("debat")
        return 12.0
    j, etat = phase_mesures(meteo=meteo)

    j.mesurer(etat)

    assert len(j.client.publies("iot/capteurs/rpi1/temperature")) == 2


def test_mesure_sans_meteo_ne_publie_rien(phase_mesures):
    j, etat = phase_mesures(meteo=None)

    j.mesurer(etat)

    assert j.client.publies("iot/capteurs/rpi1/temperature") == []


def test_l_espion_publie_une_fausse_temperature(phase_mesures, monkeypatch):
    j, etat = phase_mesures("espion")
    monkeypatch.setattr(j, "fausse_temperature", lambda manche: 99.0)

    j.mesurer(etat)

    assert {m["temperature"] for m in j.client.publies("iot/capteurs/rpi1/temperature")} == {99.0}


# --- Fausse température de l'espion -------------------------------------------


@pytest.fixture
def espion(en_partie, monkeypatch):
    """rpi1 est l'espion. tirages(ecart, sens) fixe le hasard : décalage de ecart (0,05 à 0,10), vers le haut (+1) ou le bas (-1)."""
    j = en_partie("espion")

    def tirages(ecart=0.10, sens=1):
        monkeypatch.setattr(random, "uniform", lambda a, b: ecart)
        monkeypatch.setattr(random, "choice", lambda sequence: sens)
    j.tirages = tirages
    return j


def test_espion_part_de_la_moyenne_des_dernieres_valeurs_des_autres(espion):
    espion.tirages(ecart=0.10, sens=1)
    for topic, contenu in (mesure("rpi2", 30.0), mesure("rpi2", 12.0, echange=2), mesure("rpi3", 14.0)):
        espion.client.injecter(topic, contenu)

    assert espion.fausse_temperature(1) == pytest.approx(13.0 * 1.10)


def test_espion_ignore_ses_propres_valeurs(espion):
    espion.tirages(ecart=0.10, sens=-1)
    espion.client.injecter(*mesure("rpi1", 50.0))
    espion.client.injecter(*mesure("rpi2", 20.0))

    assert espion.fausse_temperature(1) == pytest.approx(18.0)


def test_espion_ecart_minimum_pres_de_zero(espion):
    espion.tirages(ecart=0.05, sens=1)
    espion.client.injecter(*mesure("rpi2", 1.0))

    assert espion.fausse_temperature(1) == pytest.approx(1.3)


def test_espion_temperature_negative(espion):
    espion.tirages(ecart=0.10, sens=1)
    espion.client.injecter(*mesure("rpi2", -10.0))

    assert espion.fausse_temperature(1) == pytest.approx(-9.0)


def test_espion_decale_de_cinq_a_dix_pour_cent(espion):
    espion.client.injecter(*mesure("rpi2", 20.0))

    ecarts = [abs(espion.fausse_temperature(1) - 20.0) / 20.0 for _ in range(200)]

    assert all(0.05 <= e <= 0.10 for e in ecarts)


def test_espion_decale_vers_le_haut_et_vers_le_bas(espion):
    espion.client.injecter(*mesure("rpi2", 20.0))

    valeurs = {espion.fausse_temperature(1) > 20.0 for _ in range(200)}

    assert valeurs == {True, False}


def test_espion_sans_mesure_des_autres_part_de_sa_vraie_temperature(espion, monkeypatch):
    espion.tirages(ecart=0.10, sens=-1)
    monkeypatch.setattr(espion.meteo, "temperature", lambda: 10.0)

    assert espion.fausse_temperature(1) == pytest.approx(9.0)


def test_espion_sans_aucune_donnee_ne_publie_rien(espion, monkeypatch):
    monkeypatch.setattr(espion.meteo, "temperature", lambda: None)

    assert espion.fausse_temperature(1) is None


# --- Vote, parole, mémoire ----------------------------------------------------


@pytest.fixture
def phase_vote(en_partie, annoncer_phase, monkeypatch):
    """La phase de vote est ouverte ; le cerveau vote contre rpi3 (le calcul dit rpi2). Renvoie (joueur, etat, appels)."""
    j = en_partie()
    etat = annoncer_phase("vote")
    appels = []

    def voter(partie, delai):
        appels.append(delai)
        return "rpi3", "Ses valeurs sautent.", "rpi2"
    monkeypatch.setattr(j.ia, "voter", voter)
    return j, etat, appels


def test_vote_publie_suspect_raison_et_calcul(phase_vote):
    j, etat, _ = phase_vote

    j.voter(etat)

    assert j.client.dernier("iot/votes/rpi1") == {"votant": "rpi1", "suspect": "rpi3", "raison": "Ses valeurs sautent.",
                                                  "calcul": "rpi2", "strategie": "llm", "partie": ID_PARTIE, "manche": 1}


def test_vote_laisse_dix_secondes_de_marge_avant_la_fin(phase_vote):
    j, etat, appels = phase_vote

    j.voter(etat)

    assert appels == [50]   # la phase finit dans 60 s


def test_vote_trop_tard_n_est_pas_publie(phase_vote, annoncer_phase, monkeypatch):
    j, etat, _ = phase_vote

    def voter_lentement(partie, delai):
        annoncer_phase("verdict")   # le maître a clos le vote pendant que le LLM réfléchissait
        return "rpi3", "Trop tard.", "rpi3"
    monkeypatch.setattr(j.ia, "voter", voter_lentement)

    j.voter(etat)

    assert j.client.publies("iot/votes/rpi1") == []


def test_vote_sans_suspect_n_est_pas_publie(phase_vote, monkeypatch):
    j, etat, _ = phase_vote
    monkeypatch.setattr(j.ia, "voter", lambda partie, delai: (None, "aucune donnée", None))

    j.voter(etat)

    assert j.client.publies("iot/votes/rpi1") == []


def test_parler_publie_la_replique_dans_le_chat(en_partie, monkeypatch):
    j = en_partie()
    monkeypatch.setattr(j.ia, "parler", lambda partie, tour, tours, delai: "Kaito, explique-toi.")

    j.parler(parole(tour=2))

    assert j.client.dernier("iot/chat/rpi1") == {"text": "Kaito, explique-toi.", "partie": ID_PARTIE, "manche": 1, "tour": 2}


def test_parler_trop_tard_ne_publie_rien(en_partie, temps, monkeypatch):
    j = en_partie()

    def parler_lentement(partie, tour, tours, delai):
        temps.maintenant += 100   # la parole (90 s) est passée au suivant
        return "Désolé du retard."
    monkeypatch.setattr(j.ia, "parler", parler_lentement)

    j.parler(parole())

    assert j.client.publies("iot/chat/rpi1") == []


def test_parler_voit_les_noms_des_autres(en_partie, monkeypatch):
    j = en_partie()
    j.client.injecter("iot/joueurs/rpi2", {"id": "rpi2", "en_ligne": True, "nom": "Mimi"})
    vus = []
    monkeypatch.setattr(j.ia, "parler", lambda partie, *a, **k: vus.append(partie.nom("rpi2")) or "Ok.")

    j.parler(parole())

    assert vus == ["Mimi"]


def test_memoire_faits_n_appelle_pas_le_llm(en_partie, annoncer_phase, monkeypatch):
    j = en_partie()
    etat = annoncer_phase("verdict")
    monkeypatch.setattr(j.ia, "resumer", lambda partie, delai: pytest.fail("le LLM ne doit pas être appelé"))

    j.memoriser(etat)

    assert j.partie.souvenirs == {}


def test_memoire_resume_garde_les_notes_du_llm(en_partie, annoncer_phase, monkeypatch):
    j = en_partie()
    j.ia.memoire = "resume"
    etat = annoncer_phase("verdict")
    monkeypatch.setattr(j.ia, "resumer", lambda partie, delai: "Kaito est louche.")

    j.memoriser(etat)

    assert j.partie.souvenirs == {1: "Kaito est louche."}


def test_instantane_est_une_copie(en_partie):
    j = en_partie()

    copie = j.instantane()
    copie.vivants.append("intrus")

    assert "intrus" not in j.partie.vivants


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
    joueur_jeu.partie = Partie(ID_PARTIE, "rpi1", "normal")
    joueur_jeu.partie.vivants = []

    assert fiche_espion == joueur_jeu.fiche()
    assert "role" not in json.dumps(fiche_espion)


def test_sante_indique_broker_et_ollama(joueur_jeu, monkeypatch):
    monkeypatch.setattr(joueur_jeu.ia, "disponible", lambda: False)
    joueur_jeu.client.connect("localhost")

    assert joueur_jeu.sante() == {"status": "ok", "id": "rpi1", "broker": True, "ollama": False}


def test_encore_vrai_pendant_la_phase_faux_apres(en_partie, annoncer_phase):
    j = en_partie()
    etat = annoncer_phase("vote")
    assert j.encore(etat)

    annoncer_phase("verdict")

    assert not j.encore(etat)


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
