"""Déroulement d'une partie : inscription, phases, abandons et annonce du résultat (MaitreDuJeu)."""
import json
import random

import maitre
import pytest
from aides import ID_PARTIE, ConditionInstantanee


@pytest.fixture
def espion_tire(monkeypatch):
    """Fixe le tirage de l'espion : espion_tire("rpi3")."""
    def tirer(id_joueur):
        monkeypatch.setattr(random, "choice", lambda sequence: id_joueur)
    return tirer


def phases(m):
    return [e["etat"] for e in m.client.publies("iot/partie/etat")]


# --- Partie complète ----------------------------------------------------------


def test_partie_complete_innocent_puis_espion_elimines(maitre_jeu, arrivee, espion_tire, joueurs_scriptes):
    arrivee("rpi1", "rpi2", "rpi3", "rpi4", "rpi5")
    espion_tire("rpi3")
    joueurs_scriptes({
        1: {"rpi1": "rpi2", "rpi2": "rpi1", "rpi3": "rpi1", "rpi4": "rpi1", "rpi5": "rpi1"},
        2: {"rpi2": "rpi3", "rpi3": "rpi2", "rpi4": "rpi3", "rpi5": "rpi3"},
    })

    maitre_jeu.jouer(["rpi1", "rpi2", "rpi3", "rpi4", "rpi5"])

    resultat = maitre_jeu.client.dernier("iot/partie/resultat")
    assert resultat["gagnant"] == "capteurs"
    assert resultat["espion"] == "rpi3"
    assert resultat["manches"] == 2
    assert resultat["elimines"] == [{"id": "rpi1", "manche": 1}, {"id": "rpi3", "manche": 2}]


def test_partie_complete_enchaine_les_phases_dans_l_ordre(maitre_jeu, arrivee, espion_tire, joueurs_scriptes):
    arrivee("rpi1", "rpi2", "rpi3")
    espion_tire("rpi3")
    joueurs_scriptes({1: {"rpi1": "rpi3", "rpi2": "rpi3", "rpi3": "rpi1"}})

    maitre_jeu.jouer(["rpi1", "rpi2", "rpi3"])

    assert phases(maitre_jeu) == ["mesures", "debat", "vote", "verdict", "fini"]


def test_debut_de_partie_un_role_par_joueur_et_un_seul_espion(maitre_jeu, arrivee, espion_tire, joueurs_scriptes):
    arrivee("rpi1", "rpi2", "rpi3")
    espion_tire("rpi2")
    joueurs_scriptes({1: {"rpi1": "rpi2", "rpi2": "rpi1", "rpi3": "rpi2"}})

    maitre_jeu.jouer(["rpi1", "rpi2", "rpi3"])

    roles = {p.topic: p.contenu["role"] for p in maitre_jeu.client.publications if p.topic.startswith("iot/role/")}
    assert roles == {"iot/role/rpi1": "normal", "iot/role/rpi2": "espion", "iot/role/rpi3": "normal"}


def test_role_n_est_pas_retenu(maitre_jeu, arrivee, espion_tire, joueurs_scriptes):
    # Retenu, le rôle resterait lisible par n'importe qui sur le broker
    arrivee("rpi1", "rpi2", "rpi3")
    espion_tire("rpi2")
    joueurs_scriptes({1: {"rpi1": "rpi2", "rpi3": "rpi2"}})

    maitre_jeu.jouer(["rpi1", "rpi2", "rpi3"])

    assert not any(p.retain for p in maitre_jeu.client.publications if p.topic.startswith("iot/role/"))


def test_manches_max_par_defaut_vaut_joueurs_moins_un(maitre_jeu, arrivee, espion_tire, joueurs_scriptes):
    arrivee("rpi1", "rpi2", "rpi3", "rpi4")
    espion_tire("rpi4")
    joueurs_scriptes({})   # personne ne vote : l'espion tient jusqu'à la dernière manche

    maitre_jeu.jouer(["rpi1", "rpi2", "rpi3", "rpi4"])

    resultat = maitre_jeu.client.dernier("iot/partie/resultat")
    assert resultat["manches"] == 3
    assert resultat["gagnant"] == "espion"


def test_etat_de_phase_contient_les_champs_communs(maitre_jeu, arrivee, espion_tire, joueurs_scriptes):
    arrivee("rpi1", "rpi2", "rpi3")
    espion_tire("rpi3")
    joueurs_scriptes({1: {"rpi1": "rpi3", "rpi2": "rpi3"}})

    maitre_jeu.jouer(["rpi1", "rpi2", "rpi3"])

    mesures = maitre_jeu.client.publies("iot/partie/etat")[0]
    assert mesures == {"etat": "mesures", "partie": ID_PARTIE, "manche": 1, "manches_max": 2,
                       "joueurs": ["rpi1", "rpi2", "rpi3"], "vivants": ["rpi1", "rpi2", "rpi3"], "elimines": [],
                       "fin": ID_PARTIE + 5 * 5 + 15, "echanges": 5}


# --- Mode TP ------------------------------------------------------------------


def test_mode_tp_une_manche_sans_debat(maitre_jeu, arrivee, espion_tire, joueurs_scriptes):
    maitre_jeu.reglages.manches_max, maitre_jeu.reglages.tours, maitre_jeu.reglages.majorite = 1, 0, True
    arrivee("rpi1", "rpi2", "rpi3")
    espion_tire("rpi3")
    joueurs_scriptes({1: {"rpi1": "rpi3", "rpi2": "rpi3", "rpi3": "rpi1"}})

    maitre_jeu.jouer(["rpi1", "rpi2", "rpi3"])

    assert phases(maitre_jeu) == ["mesures", "vote", "verdict", "fini"]
    assert maitre_jeu.client.publies("iot/partie/parole") == []
    assert maitre_jeu.client.dernier("iot/partie/resultat")["gagnant"] == "capteurs"


def test_mode_tp_sans_majorite_l_espion_gagne(maitre_jeu, arrivee, espion_tire, joueurs_scriptes):
    maitre_jeu.reglages.manches_max, maitre_jeu.reglages.tours, maitre_jeu.reglages.majorite = 1, 0, True
    arrivee("rpi1", "rpi2", "rpi3")
    espion_tire("rpi3")
    joueurs_scriptes({1: {"rpi1": "rpi2", "rpi2": "rpi3", "rpi3": "rpi1"}})

    maitre_jeu.jouer(["rpi1", "rpi2", "rpi3"])

    resultat = maitre_jeu.client.dernier("iot/partie/resultat")
    assert resultat["gagnant"] == "espion"
    assert resultat["elimines"] == []


# --- Abandons -----------------------------------------------------------------


def test_espion_qui_se_deconnecte_fait_gagner_les_capteurs(maitre_jeu, arrivee, espion_tire):
    arrivee("rpi1", "rpi2", "rpi3")
    espion_tire("rpi3")

    def espion_part(topic, contenu):
        if topic == "iot/partie/etat" and contenu["etat"] == "mesures":
            maitre_jeu.client.injecter("iot/joueurs/rpi3", {"id": "rpi3", "en_ligne": False})
    maitre_jeu.client.reactions.append(espion_part)

    maitre_jeu.jouer(["rpi1", "rpi2", "rpi3"])

    resultat = maitre_jeu.client.dernier("iot/partie/resultat")
    assert resultat["gagnant"] == "capteurs"
    assert resultat["raison"] == "l'espion a quitté la partie"


def test_espion_qui_part_pendant_le_vote_ferme_le_vote(en_partie):
    m = en_partie(espion="rpi3")

    def espion_part(topic, contenu):
        if topic == "iot/partie/etat" and contenu["etat"] == "vote":
            m.client.injecter("iot/joueurs/rpi3", {"id": "rpi3", "en_ligne": False})
    m.client.reactions.append(espion_part)

    with pytest.raises(maitre.FinDePartie, match="l'espion a quitté la partie"):
        m.phase_vote()
    assert m.vote_ouvert is False


def test_moins_de_deux_vivants_en_ligne_annule_la_partie(maitre_jeu, arrivee, espion_tire):
    arrivee("rpi1", "rpi2", "rpi3")
    espion_tire("rpi3")

    def deux_partent(topic, contenu):
        if topic == "iot/partie/etat" and contenu["etat"] == "mesures":
            for id_joueur in ("rpi1", "rpi2"):
                maitre_jeu.client.injecter(f"iot/joueurs/{id_joueur}", {"id": id_joueur, "en_ligne": False})
    maitre_jeu.client.reactions.append(deux_partent)

    maitre_jeu.jouer(["rpi1", "rpi2", "rpi3"])

    resultat = maitre_jeu.client.dernier("iot/partie/resultat")
    assert resultat["gagnant"] is None
    assert resultat["raison"] == "plus assez de joueurs en ligne"


def test_partie_annulee_ne_compte_pas_de_victoire(maitre_jeu, arrivee, espion_tire):
    arrivee("rpi3")   # rpi1 et rpi2 sont déjà partis : un seul vivant en ligne
    espion_tire("rpi3")

    maitre_jeu.jouer(["rpi1", "rpi2", "rpi3"])

    assert maitre_jeu.stats["parties"] == 0
    assert maitre_jeu.stats["victoires"] == {"capteurs": 0, "espion": 0}


# --- Phases -------------------------------------------------------------------


def test_debat_donne_la_parole_a_chaque_vivant_a_chaque_tour(en_partie, joueurs_scriptes):
    m = en_partie(joueurs=("rpi1", "rpi2", "rpi3"))
    joueurs_scriptes({})

    m.phase_debat()

    paroles = m.client.publies("iot/partie/parole")
    assert sorted(p["joueur"] for p in paroles) == ["rpi1", "rpi1", "rpi2", "rpi2", "rpi3", "rpi3"]
    assert [p["tour"] for p in paroles] == [1, 1, 1, 2, 2, 2]
    assert [p["rang"] for p in paroles] == [1, 2, 3, 1, 2, 3]


def test_debat_garde_le_meme_ordre_a_chaque_tour(en_partie, joueurs_scriptes):
    m = en_partie(joueurs=("rpi1", "rpi2", "rpi3", "rpi4"))
    joueurs_scriptes({})

    m.phase_debat()

    ordre = [p["joueur"] for p in m.client.publies("iot/partie/parole")]
    assert ordre[:4] == ordre[4:]


def test_debat_saute_un_joueur_hors_ligne(en_partie, joueurs_scriptes):
    m = en_partie(joueurs=("rpi1", "rpi2", "rpi3", "rpi4"), espion="rpi3")
    m.client.injecter("iot/joueurs/rpi2", {"id": "rpi2", "en_ligne": False})
    joueurs_scriptes({})

    m.phase_debat()

    assert "rpi2" not in {p["joueur"] for p in m.client.publies("iot/partie/parole")}


def test_debat_rend_la_parole_a_personne_a_la_fin(en_partie, joueurs_scriptes):
    m = en_partie(joueurs=("rpi1", "rpi2", "rpi3"))
    joueurs_scriptes({})

    m.phase_debat()

    assert m.parole is None


def test_sans_tour_de_parole_pas_de_debat(en_partie):
    m = en_partie()
    m.reglages.tours = 0

    m.phase_debat()

    assert m.client.publications == []


def test_vote_temps_ecoule_le_verdict_compte_les_votes_recus(en_partie, joueurs_scriptes):
    m = en_partie(joueurs=("rpi1", "rpi2", "rpi3"))
    joueurs_scriptes({1: {"rpi1": "rpi3", "rpi2": "rpi3"}})   # rpi3 ne vote pas

    m.phase_vote()

    assert m.phase_verdict()["elimine"] == "rpi3"


def test_pause_du_verdict_annonce_l_elimine(en_partie):
    m = en_partie()

    m.pause_verdict({"elimine": "rpi2"})

    etat = m.client.dernier("iot/partie/etat")
    assert etat["etat"] == "verdict"
    assert etat["elimine"] == "rpi2"


# --- Résultat -----------------------------------------------------------------


def test_resultat_contient_les_champs_du_tp_et_est_retenu(en_partie):
    m = en_partie(espion="rpi3")
    verdict = {"votes": {"rpi1": "rpi3", "rpi2": "rpi3"}, "elimine": "rpi3"}

    m.annoncer("capteurs", "l'espion a été éliminé", verdict)

    publication = m.client.retenu("iot/partie/resultat")
    assert publication.retain is True
    assert publication.contenu["espion"] == "rpi3"
    assert publication.contenu["designe"] == "rpi3"
    assert publication.contenu["votes"] == {"rpi1": "rpi3", "rpi2": "rpi3"}
    assert publication.contenu["gagnant"] == "capteurs"


def test_resultat_sans_elimine_designe_le_plus_vote(en_partie):
    m = en_partie(espion="rpi3")
    verdict = {"votes": {"rpi1": "rpi2", "rpi3": "rpi2", "rpi2": "rpi1"}, "elimine": None}

    m.annoncer("espion", "l'espion a tenu jusqu'à la dernière manche", verdict)

    assert m.client.dernier("iot/partie/resultat")["designe"] == "rpi2"


def test_resultat_sans_aucun_verdict_ne_plante_pas(en_partie):
    # L'espion part pendant la première manche : aucun verdict n'a été rendu
    m = en_partie()

    m.annoncer("capteurs", "l'espion a quitté la partie", None)

    resultat = m.client.dernier("iot/partie/resultat")
    assert resultat["designe"] is None
    assert resultat["votes"] == {}


def test_resultat_incremente_et_sauvegarde_les_statistiques(en_partie, reglages_maitre):
    m = en_partie()

    m.annoncer("espion", "il ne reste que deux joueurs", {})

    assert m.stats["parties"] == 1
    assert m.stats["victoires"]["espion"] == 1
    assert json.loads(reglages_maitre.stats.read_text(encoding="utf-8")) == m.stats


def test_resultat_publie_les_statistiques_et_l_etat_fini(en_partie):
    m = en_partie()

    m.annoncer("capteurs", "l'espion a été éliminé", {})

    assert m.client.retenu("iot/partie/stats").retain is True
    assert m.client.retenu("iot/partie/etat").contenu == {"etat": "fini", "partie": ID_PARTIE, "gagnant": "capteurs"}


# --- Inscription --------------------------------------------------------------


def inscrire(m, temps, au_reveil=None):
    """Lance inscription() avec un temps qui avance à chaque attente (pas d'attente réelle)."""
    def reveil(t):
        assert t.maintenant < ID_PARTIE + 1000, "l'inscription ne se termine jamais"
        if au_reveil:
            au_reveil(t)
    m.cond = ConditionInstantanee(temps, reveil)
    return m.inscription()


def test_inscription_lance_la_partie_apres_le_delai_automatique(maitre_jeu, arrivee, temps):
    arrivee("rpi1", "rpi2", "rpi3")

    inscrits = inscrire(maitre_jeu, temps)

    assert inscrits == ["rpi1", "rpi2", "rpi3"]
    assert temps.maintenant >= ID_PARTIE + 30


def test_inscription_annonce_le_debut_prevu(maitre_jeu, arrivee, temps):
    arrivee("rpi1", "rpi2", "rpi3")

    inscrire(maitre_jeu, temps)

    etat = maitre_jeu.client.dernier("iot/partie/etat")
    assert etat == {"etat": "inscription", "min": 3, "max": 12, "debut": ID_PARTIE + 30}


def test_inscription_chaque_arrivee_relance_le_compte_a_rebours(maitre_jeu, arrivee, temps):
    arrivee("rpi1", "rpi2", "rpi3")

    def quatrieme_joueur(t):
        if t.maintenant == ID_PARTIE + 10:
            arrivee("rpi4")

    inscrits = inscrire(maitre_jeu, temps, quatrieme_joueur)

    assert inscrits == ["rpi1", "rpi2", "rpi3", "rpi4"]
    assert [e["debut"] for e in maitre_jeu.client.publies("iot/partie/etat")] == [ID_PARTIE + 30, ID_PARTIE + 40]


def test_inscription_entree_avec_trop_peu_de_joueurs_ne_lance_rien(maitre_jeu, arrivee, temps):
    maitre_jeu.reglages.auto = 0
    arrivee("rpi1", "rpi2")

    def entree(t):
        maitre_jeu.lancer = True
        if t.maintenant == ID_PARTIE + 3:
            arrivee("rpi3")

    inscrits = inscrire(maitre_jeu, temps, entree)

    assert inscrits == ["rpi1", "rpi2", "rpi3"]
    assert temps.maintenant == ID_PARTIE + 3


def test_inscription_sans_lancement_automatique_attend_entree(maitre_jeu, arrivee, temps):
    maitre_jeu.reglages.auto = 0
    arrivee("rpi1", "rpi2", "rpi3")

    def entree_tardive(t):
        if t.maintenant == ID_PARTIE + 100:
            maitre_jeu.lancer = True

    inscrire(maitre_jeu, temps, entree_tardive)

    assert temps.maintenant == ID_PARTIE + 100
    assert maitre_jeu.client.dernier("iot/partie/etat")["debut"] is None


def test_inscription_limitee_au_nombre_de_sieges(maitre_jeu, arrivee, temps):
    maitre_jeu.reglages.auto = 0
    arrivee(*(f"rpi{i}" for i in range(1, 14)))

    def entree(topic, contenu):
        maitre_jeu.lancer = True
    maitre_jeu.client.reactions.append(entree)

    inscrits = inscrire(maitre_jeu, temps)

    assert inscrits == [f"rpi{i}" for i in range(1, 13)]


def test_inscription_remet_a_zero_la_partie_precedente(en_partie, temps):
    m = en_partie()
    m.elimines = [{"id": "rpi2", "manche": 1}]

    inscrire(m, temps)

    assert (m.partie, m.espion, m.vivants, m.elimines, m.manche) == (None, None, [], [], 0)
