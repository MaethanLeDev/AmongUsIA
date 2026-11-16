"""Ce que le maître du jeu accepte ou refuse des messages MQTT reçus (votes, mesures, chat, présence)."""
import pytest
from aides import ID_PARTIE

# --- Validation des votes -----------------------------------------------------


def test_vote_valide_est_enregistre(en_partie, voter):
    m = en_partie()

    voter("rpi1", "rpi3")

    assert m.votes["rpi1"]["suspect"] == "rpi3"


def test_vote_en_double_seul_le_premier_compte(en_partie, voter):
    # Un message QoS 1 peut arriver deux fois, et un joueur ne change pas d'avis
    m = en_partie()

    voter("rpi1", "rpi3")
    voter("rpi1", "rpi2")

    assert m.votes["rpi1"]["suspect"] == "rpi3"


def test_vote_contre_soi_est_refuse(en_partie, voter):
    m = en_partie()

    voter("rpi1", "rpi1")

    assert "rpi1" not in m.votes


def test_vote_contre_un_elimine_est_refuse(en_partie, voter):
    m = en_partie()
    m.vivants.remove("rpi2")

    voter("rpi1", "rpi2")

    assert "rpi1" not in m.votes


def test_vote_contre_un_inconnu_est_refuse(en_partie, voter):
    m = en_partie()

    voter("rpi1", "rpi99")

    assert "rpi1" not in m.votes


def test_vote_d_une_autre_manche_est_refuse(en_partie, voter):
    m = en_partie()
    m.manche = 2

    voter("rpi1", "rpi3", manche=1)

    assert "rpi1" not in m.votes


def test_vote_d_une_autre_partie_est_refuse(en_partie, voter):
    m = en_partie()

    voter("rpi1", "rpi3", partie=ID_PARTIE - 100)

    assert "rpi1" not in m.votes


def test_vote_hors_de_la_phase_de_vote_est_ignore(en_partie, voter):
    m = en_partie(vote_ouvert=False)

    voter("rpi1", "rpi3")

    assert m.votes == {}


def test_vote_d_un_elimine_est_ignore(en_partie, voter):
    m = en_partie()
    m.vivants.remove("rpi2")

    voter("rpi2", "rpi3")

    assert "rpi2" not in m.votes


def test_vote_refuse_puis_vote_valide_est_accepte(en_partie, voter):
    m = en_partie()

    voter("rpi1", "rpi1")
    voter("rpi1", "rpi3")

    assert m.votes["rpi1"]["suspect"] == "rpi3"


def test_vote_en_json_invalide_est_ignore_sans_planter(en_partie):
    m = en_partie()

    m.client.injecter("iot/votes/rpi1", b"{pas du json")
    m.client.injecter("iot/votes/rpi2", b"[1, 2]")

    assert m.votes == {}


def test_vote_avec_suspect_qui_n_est_pas_un_texte_est_refuse(en_partie, voter):
    m = en_partie()

    voter("rpi1", ["rpi3"])

    assert m.votes == {}


def test_vote_sans_partie_ni_manche_est_accepte(en_partie):
    # Comportement actuel : de_cette_manche tolère un message sans ces champs (client minimal d'un autre étudiant)
    m = en_partie()

    m.client.injecter("iot/votes/rpi1", {"votant": "rpi1", "suspect": "rpi3"})

    assert m.votes["rpi1"]["suspect"] == "rpi3"


# --- Mesures ------------------------------------------------------------------


def test_mesure_d_un_vivant_est_comptee(en_partie):
    m = en_partie()

    m.client.injecter("iot/capteurs/rpi1/temperature", {"temperature": 12.4, "echange": 1, "manche": 1, "partie": ID_PARTIE})

    assert m.mesures["rpi1"] == 1


def test_mesure_d_une_autre_manche_est_ignoree(en_partie):
    m = en_partie()

    m.client.injecter("iot/capteurs/rpi1/temperature", {"temperature": 12.4, "echange": 1, "manche": 3, "partie": ID_PARTIE})

    assert m.mesures["rpi1"] == 0


def test_mesure_d_un_elimine_est_ignoree(en_partie):
    m = en_partie()
    m.vivants.remove("rpi2")

    m.client.injecter("iot/capteurs/rpi2/temperature", {"temperature": 12.4, "echange": 1, "manche": 1, "partie": ID_PARTIE})

    assert m.mesures["rpi2"] == 0


@pytest.mark.xfail(reason="bug : une mesure reçue deux fois (QoS 1) est comptée deux fois, la phase peut finir trop tôt")
def test_mesure_recue_deux_fois_n_est_comptee_qu_une_fois(en_partie):
    m = en_partie()
    mesure = {"temperature": 12.4, "echange": 1, "manche": 1, "partie": ID_PARTIE}

    m.client.injecter("iot/capteurs/rpi1/temperature", mesure)
    m.client.injecter("iot/capteurs/rpi1/temperature", mesure)

    assert m.mesures["rpi1"] == 1


# --- Chat ---------------------------------------------------------------------


def test_reponse_de_celui_qui_a_la_parole_est_retenue(en_partie):
    m = en_partie()
    m.parole = "rpi2"

    m.client.injecter("iot/chat/rpi2", {"text": "  Mimi ment.  ", "partie": ID_PARTIE, "manche": 1})

    assert m.reponse == "Mimi ment."


def test_chat_d_un_joueur_qui_n_a_pas_la_parole_est_ignore(en_partie):
    m = en_partie()
    m.parole = "rpi2"

    m.client.injecter("iot/chat/rpi4", {"text": "Je coupe la parole !"})

    assert m.reponse is None


def test_chat_vide_est_ignore(en_partie):
    m = en_partie()
    m.parole = "rpi2"

    m.client.injecter("iot/chat/rpi2", {"text": "   "})
    m.client.injecter("iot/chat/rpi2", {"text": 42})

    assert m.reponse is None


# --- Présence -----------------------------------------------------------------


def test_arrivee_d_un_joueur_l_inscrit(maitre_jeu, arrivee):
    arrivee("rpi1")

    assert list(maitre_jeu.joueurs) == ["rpi1"]
    assert maitre_jeu.arrivees == 1


def test_presence_retenue_recue_deux_fois_ne_compte_qu_une_arrivee(maitre_jeu, arrivee):
    arrivee("rpi1")
    arrivee("rpi1")

    assert maitre_jeu.arrivees == 1


def test_depart_d_un_joueur_le_retire(maitre_jeu, arrivee):
    arrivee("rpi1", "rpi2")

    maitre_jeu.client.injecter("iot/joueurs/rpi1", {"id": "rpi1", "en_ligne": False}, retain=True)

    assert list(maitre_jeu.joueurs) == ["rpi2"]


def test_vivant_qui_revient_recoit_de_nouveau_son_role(en_partie):
    m = en_partie(espion="rpi3")
    m.client.injecter("iot/joueurs/rpi3", {"id": "rpi3", "en_ligne": False})

    m.client.injecter("iot/joueurs/rpi3", {"id": "rpi3", "en_ligne": True})

    assert m.client.publies("iot/role/rpi3") == [{"role": "espion", "partie": ID_PARTIE}]


def test_inconnu_qui_arrive_en_pleine_partie_ne_recoit_pas_de_role(en_partie):
    m = en_partie()

    m.client.injecter("iot/joueurs/rpi9", {"id": "rpi9", "en_ligne": True})

    assert m.client.publies("iot/role/+") == []


# --- Connexion et arrêt -------------------------------------------------------


def test_last_will_annonce_l_arret_du_maitre(maitre_jeu):
    assert maitre_jeu.client.will == ("iot/partie/etat", {"etat": "arret"}, True)


def test_connexion_abonne_aux_messages_des_joueurs(maitre_jeu):
    maitre_jeu._on_connect(maitre_jeu.client, None, {}, 0, None)

    topics = [topic for topic, _ in maitre_jeu.client.abonnements[0]]
    assert sorted(topics) == ["iot/capteurs/+/temperature", "iot/chat/+", "iot/joueurs/+", "iot/votes/+"]


def test_connexion_publie_les_statistiques_retenues(maitre_jeu):
    maitre_jeu._on_connect(maitre_jeu.client, None, {}, 0, None)

    assert maitre_jeu.client.retenu("iot/partie/stats").retain is True


def test_fermer_publie_l_arret_et_se_deconnecte(maitre_jeu):
    maitre_jeu.fermer()

    publication = maitre_jeu.client.retenu("iot/partie/etat")
    assert publication.contenu == {"etat": "arret"}
    assert publication.retain is True
    assert maitre_jeu.client.deconnecte
