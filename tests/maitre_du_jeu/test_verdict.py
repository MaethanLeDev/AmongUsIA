"""Verdict d'une manche, conditions de victoire et statistiques LLM contre calcul (MaitreDuJeu)."""
from aides import ID_PARTIE

# --- Élimination -------------------------------------------------------------


def test_le_plus_designe_est_elimine(en_partie, voter):
    m = en_partie()
    for votant, suspect in [("rpi1", "rpi3"), ("rpi2", "rpi3"), ("rpi3", "rpi1"), ("rpi4", "rpi3"), ("rpi5", "rpi2")]:
        voter(votant, suspect)

    verdict = m.phase_verdict()

    assert verdict["elimine"] == "rpi3"
    assert verdict["compte"] == {"rpi3": 3, "rpi1": 1, "rpi2": 1}
    assert verdict["egalite"] is False


def test_verdict_publie_les_votes_de_chacun(en_partie, voter):
    m = en_partie()
    voter("rpi1", "rpi2")
    voter("rpi2", "rpi1")
    voter("rpi3", "rpi2")

    m.phase_verdict()

    publie = m.client.dernier("iot/partie/verdict")
    assert publie["partie"] == ID_PARTIE
    assert publie["manche"] == 1
    assert publie["votes"] == {"rpi1": "rpi2", "rpi2": "rpi1", "rpi3": "rpi2"}


def test_elimine_quitte_les_vivants(en_partie, voter):
    m = en_partie()
    voter("rpi1", "rpi2")
    voter("rpi3", "rpi2")

    m.phase_verdict()

    assert "rpi2" not in m.vivants
    assert m.elimines == [{"id": "rpi2", "manche": 1}]
    assert "rpi2" in m.participants   # les participants gardent les éliminés


def test_egalite_personne_n_est_elimine(en_partie, voter):
    m = en_partie()
    for votant, suspect in [("rpi1", "rpi3"), ("rpi2", "rpi3"), ("rpi3", "rpi1"), ("rpi4", "rpi1"), ("rpi5", "rpi2")]:
        voter(votant, suspect)

    verdict = m.phase_verdict()

    assert verdict["elimine"] is None
    assert verdict["egalite"] is True
    assert verdict["etait_espion"] is None
    assert m.vivants == ["rpi1", "rpi2", "rpi3", "rpi4", "rpi5"]


def test_sans_vote_personne_n_est_elimine(en_partie):
    m = en_partie()

    verdict = m.phase_verdict()

    assert verdict["elimine"] is None
    assert verdict["egalite"] is False
    assert verdict["compte"] == {}
    assert verdict["etait_espion"] is None


def test_espion_elimine_etait_espion_vrai(en_partie, voter):
    m = en_partie(espion="rpi3")
    voter("rpi1", "rpi3")

    assert m.phase_verdict()["etait_espion"] is True


def test_innocent_elimine_etait_espion_faux(en_partie, voter):
    m = en_partie(espion="rpi3")
    voter("rpi1", "rpi2")

    assert m.phase_verdict()["etait_espion"] is False


def test_sans_option_majorite_la_majorite_relative_suffit(en_partie, voter):
    m = en_partie()
    for votant, suspect in [("rpi1", "rpi3"), ("rpi2", "rpi3"), ("rpi3", "rpi1"), ("rpi4", "rpi2"), ("rpi5", "rpi4")]:
        voter(votant, suspect)

    assert m.phase_verdict()["elimine"] == "rpi3"


def test_option_majorite_deux_voix_sur_cinq_n_eliminent_personne(en_partie, voter):
    m = en_partie()
    m.reglages.majorite = True
    for votant, suspect in [("rpi1", "rpi3"), ("rpi2", "rpi3"), ("rpi3", "rpi1"), ("rpi4", "rpi2"), ("rpi5", "rpi4")]:
        voter(votant, suspect)

    verdict = m.phase_verdict()

    assert verdict["elimine"] is None
    assert verdict["egalite"] is False


def test_option_majorite_trois_voix_sur_cinq_eliminent(en_partie, voter):
    m = en_partie()
    m.reglages.majorite = True
    for votant, suspect in [("rpi1", "rpi3"), ("rpi2", "rpi3"), ("rpi3", "rpi1"), ("rpi4", "rpi3"), ("rpi5", "rpi4")]:
        voter(votant, suspect)

    assert m.phase_verdict()["elimine"] == "rpi3"


def test_option_majorite_compte_les_vivants_et_pas_les_votants(en_partie, voter):
    # 2 votes sur 2 votants, mais 5 vivants : ce n'est pas la majorité des vivants
    m = en_partie()
    m.reglages.majorite = True
    voter("rpi1", "rpi3")
    voter("rpi2", "rpi3")

    assert m.phase_verdict()["elimine"] is None


# --- Fin de partie (issue) ------------------------------------------------------


def test_capteurs_gagnent_quand_l_espion_est_elimine(en_partie):
    m = en_partie()

    assert m.issue({"etait_espion": True}) == ("capteurs", "l'espion a été éliminé")


def test_espion_gagne_quand_il_ne_reste_que_deux_joueurs(en_partie):
    m = en_partie(joueurs=("rpi1", "rpi2", "rpi3"))
    m.vivants.remove("rpi1")

    assert m.issue({"etait_espion": False}) == ("espion", "il ne reste que deux joueurs")


def test_espion_gagne_a_la_derniere_manche(en_partie):
    m = en_partie()
    m.manche = m.manches_max

    gagnant, raison = m.issue({"etait_espion": None})

    assert gagnant == "espion"
    assert raison == "l'espion a tenu jusqu'à la dernière manche"


def test_partie_continue_sinon(en_partie):
    m = en_partie()

    assert m.issue({"etait_espion": False}) == (None, "")


def test_espion_elimine_a_la_derniere_manche_les_capteurs_gagnent(en_partie):
    m = en_partie()
    m.manche = m.manches_max

    assert m.issue({"etait_espion": True})[0] == "capteurs"


# --- Statistiques : le LLM vote-t-il mieux que le calcul ? ------------------------


def test_vote_llm_juste_compte_pour_le_llm(en_partie, voter):
    m = en_partie(espion="rpi3")
    voter("rpi1", "rpi3", strategie="llm", calcul="rpi2")

    m.phase_verdict()

    assert m.stats["votes"]["llm"] == {"total": 1, "justes": 1}
    assert m.stats["votes"]["calcul"] == {"total": 1, "justes": 0}


def test_vote_en_strategie_ecart_ne_compte_pas_pour_le_llm(en_partie, voter):
    m = en_partie(espion="rpi3")
    voter("rpi1", "rpi3", strategie="ecart", calcul="rpi3")

    m.phase_verdict()

    assert m.stats["votes"]["llm"] == {"total": 0, "justes": 0}
    assert m.stats["votes"]["calcul"] == {"total": 1, "justes": 1}


def test_vote_sans_champ_calcul_ne_compte_pas_pour_le_calcul(en_partie, voter):
    m = en_partie(espion="rpi3")
    voter("rpi1", "rpi2", calcul=None)

    m.phase_verdict()

    assert m.stats["votes"]["calcul"] == {"total": 0, "justes": 0}
    assert m.stats["votes"]["llm"] == {"total": 1, "justes": 0}
