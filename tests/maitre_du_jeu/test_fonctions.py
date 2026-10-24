"""Fonctions utilitaires de maitre.py (statistiques, JSON, connexion) et options de la ligne de commande."""
import json
import sys

import maitre
import pytest
from aides import FauxClientMQTT, FauxMessage

STATS_VIDES = {"parties": 0, "victoires": {"capteurs": 0, "espion": 0},
               "votes": {"llm": {"total": 0, "justes": 0}, "calcul": {"total": 0, "justes": 0}}}


# --- Statistiques -------------------------------------------------------------


def test_stats_fichier_absent_donne_des_stats_vides(tmp_path):
    assert maitre.charger_stats(tmp_path / "absent.json") == STATS_VIDES


def test_stats_json_corrompu_donne_des_stats_vides(tmp_path):
    fichier = tmp_path / "stats.json"
    fichier.write_text("{pas du json", encoding="utf-8")

    assert maitre.charger_stats(fichier) == STATS_VIDES


def test_stats_avec_d_autres_cles_donne_des_stats_vides(tmp_path):
    fichier = tmp_path / "stats.json"
    fichier.write_text(json.dumps({"parties": 3}), encoding="utf-8")

    assert maitre.charger_stats(fichier) == STATS_VIDES


@pytest.mark.xfail(reason="bug : seules les clés de premier niveau sont vérifiées ; "
                          "\"votes\": {} est accepté et le maître plante (KeyError) à la fin de la partie")
def test_stats_incompletes_donnent_des_stats_vides(tmp_path):
    fichier = tmp_path / "stats.json"
    fichier.write_text(json.dumps({"parties": 2, "victoires": {}, "votes": {}}), encoding="utf-8")

    assert maitre.charger_stats(fichier) == STATS_VIDES


def test_stats_sauvees_puis_rechargees_sont_identiques(tmp_path):
    stats = json.loads(json.dumps(STATS_VIDES))
    stats["parties"], stats["votes"]["llm"] = 4, {"total": 10, "justes": 7}
    fichier = tmp_path / "stats.json"

    maitre.sauver_stats(stats, fichier)

    assert maitre.charger_stats(fichier) == stats


def test_stats_non_sauvegardables_ne_plantent_pas(tmp_path, capsys):
    maitre.sauver_stats(STATS_VIDES, tmp_path / "dossier_absent" / "stats.json")

    assert "Statistiques non sauvegardées" in capsys.readouterr().out


def test_pourcentage_sans_vote():
    assert maitre.pourcentage({"total": 0, "justes": 0}) == "aucun vote"


def test_pourcentage_arrondi():
    assert maitre.pourcentage({"total": 3, "justes": 2}) == "2/3 (67 %)"


# --- Lecture des messages -----------------------------------------------------


@pytest.mark.parametrize("payload", [b"{pas du json", b"", b"[1, 2]", b"\"texte\"", b"42", b"\xff\xfe"])
def test_lire_json_invalide_ou_pas_un_objet_donne_un_dict_vide(payload):
    assert maitre.lire_json(payload) == {}


def test_lire_json_objet_valide():
    assert maitre.lire_json('{"suspect": "rpi3", "raison": "écart"}'.encode()) == {"suspect": "rpi3", "raison": "écart"}


def test_expediteur_est_le_dernier_niveau_du_topic():
    assert maitre.expediteur(FauxMessage("iot/votes/rpi2", b"{}")) == "rpi2"


def test_decrire_un_joueur_avec_nom_ville_et_modele():
    presence = {"nom": "Sherlock", "ville": "Annecy", "modele": "qwen3:0.6b"}

    assert maitre.decrire("rpi1", presence) == "Sherlock [rpi1] (Annecy, qwen3:0.6b)"


def test_decrire_un_joueur_sans_details():
    assert maitre.decrire("rpi1", {}) == "rpi1 [rpi1]"


# --- Connexion au broker ------------------------------------------------------


def test_connecter_essaie_le_broker_suivant_si_le_premier_est_injoignable():
    client = FauxClientMQTT()
    client.hotes_injoignables = {"amongus.local"}

    assert maitre.connecter(client, "amongus.local, 10.109.150.215", 1883) == "10.109.150.215"


def test_connecter_sans_broker_joignable_arrete_le_programme():
    client = FauxClientMQTT()
    client.hotes_injoignables = {"a", "b"}

    with pytest.raises(SystemExit, match="Aucun broker joignable"):
        maitre.connecter(client, "a,b", 1883)


# --- Ligne de commande --------------------------------------------------------


@pytest.fixture
def lancer_main(monkeypatch):
    """lancer_main("--tp") : lance main() avec un faux MaitreDuJeu, et renvoie les réglages qu'il a reçus."""
    recus = []

    class FauxMaitre:
        def __init__(self, reglages):
            recus.append(reglages)
            self.ferme = False

        def ecouter_clavier(self):
            pass

        def inscription(self):
            raise KeyboardInterrupt   # comme un Ctrl+C dès l'inscription

        def jouer(self, inscrits):
            pass

        def fermer(self):
            self.ferme = True

    def lancer(*options):
        monkeypatch.setattr(maitre, "MaitreDuJeu", FauxMaitre)
        monkeypatch.setattr(sys, "argv", ["maitre.py", *options])
        maitre.main()
        return recus[-1]
    return lancer


def test_option_tp_impose_le_jeu_de_base_du_sujet(lancer_main):
    reglages = lancer_main("--tp")

    assert (reglages.manches_max, reglages.tours, reglages.majorite) == (1, 0, True)


def test_sans_option_tp_debat_et_majorite_relative(lancer_main):
    reglages = lancer_main()

    assert (reglages.manches_max, reglages.tours, reglages.majorite) == (0, 2, False)


@pytest.mark.parametrize(("demande", "obtenu"), [("50", 12), ("1", 2), ("8", 8)])
def test_max_joueurs_borne_entre_deux_et_douze_sieges(lancer_main, demande, obtenu):
    assert lancer_main("--max-joueurs", demande).max_joueurs == obtenu
