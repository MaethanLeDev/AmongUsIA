"""Température d'une ville (meteo.py), avec l'API Open-Meteo simulée."""
import pytest
import requests
from aides import FausseReponseHTTP

import meteo

GEOCODAGE = "https://geocoding-api.open-meteo.com/v1/search"
PREVISION = "https://api.open-meteo.com/v1/forecast"


@pytest.fixture
def open_meteo(monkeypatch):
    """Simule Open-Meteo. Régler .villes et .temperature (ou une exception) ; .appels liste les requêtes."""
    class Service:
        villes = [{"latitude": 45.9, "longitude": 6.13}]
        temperature = 12.4
        appels = []

    def get(url, params=None, timeout=None):
        Service.appels.append({"url": url, "params": params, "timeout": timeout})
        if url == GEOCODAGE:
            return FausseReponseHTTP({"results": Service.villes} if Service.villes else {})
        if isinstance(Service.temperature, Exception):
            raise Service.temperature
        return FausseReponseHTTP({"current": {"temperature_2m": Service.temperature}})

    Service.appels = []
    monkeypatch.setattr(meteo.requests, "get", get)
    return Service


def urls(service):
    return [appel["url"] for appel in service.appels]


def test_temperature_actuelle_de_la_ville(open_meteo):
    assert meteo.Meteo("Annecy").temperature() == 12.4


def test_geocode_puis_demande_la_temperature_actuelle(open_meteo):
    meteo.Meteo("Annecy").temperature()

    assert urls(open_meteo) == [GEOCODAGE, PREVISION]
    assert open_meteo.appels[1]["params"] == {"latitude": 45.9, "longitude": 6.13, "current": "temperature_2m"}


def test_geocodage_fait_une_seule_fois(open_meteo):
    ville = meteo.Meteo("Annecy")

    ville.temperature()
    ville.temperature()

    assert urls(open_meteo).count(GEOCODAGE) == 1


def test_coordonnees_fournies_pas_de_geocodage(open_meteo):
    meteo.Meteo("Annecy", [45.899, 6.129]).temperature()

    assert urls(open_meteo) == [PREVISION]


def test_toutes_les_requetes_ont_un_delai_maximum(open_meteo):
    meteo.Meteo("Annecy").temperature()

    assert all(appel["timeout"] for appel in open_meteo.appels)


def test_ville_introuvable_ne_donne_rien(open_meteo, capsys):
    open_meteo.villes = []

    assert meteo.Meteo("Atlantide").temperature() is None
    assert "ville introuvable" in capsys.readouterr().out


def test_ville_introuvable_reessaie_le_geocodage(open_meteo):
    open_meteo.villes = []
    ville = meteo.Meteo("Atlantide")

    ville.temperature()
    ville.temperature()

    assert urls(open_meteo) == [GEOCODAGE, GEOCODAGE]


def test_panne_reseau_garde_la_derniere_valeur(open_meteo):
    ville = meteo.Meteo("Annecy", [45.9, 6.1])
    ville.temperature()
    open_meteo.temperature = requests.ConnectionError("pas d'Internet")

    assert ville.temperature() == 12.4


def test_panne_reseau_sans_valeur_connue_ne_donne_rien(open_meteo):
    open_meteo.temperature = requests.Timeout("proxy de l'IUT")

    assert meteo.Meteo("Annecy", [45.9, 6.1]).temperature() is None


def test_reponse_sans_temperature_garde_la_derniere_valeur(open_meteo, monkeypatch):
    ville = meteo.Meteo("Annecy", [45.9, 6.1])
    ville.temperature()
    monkeypatch.setattr(meteo.requests, "get", lambda url, params=None, timeout=None: FausseReponseHTTP({"current": {}}))

    assert ville.temperature() == 12.4


def test_erreur_http_garde_la_derniere_valeur(open_meteo, monkeypatch):
    ville = meteo.Meteo("Annecy", [45.9, 6.1])
    ville.temperature()
    monkeypatch.setattr(meteo.requests, "get", lambda url, params=None, timeout=None: FausseReponseHTTP({}, code=503))

    assert ville.temperature() == 12.4


@pytest.mark.xfail(reason="bug : \"current\": null lève une TypeError non attrapée, qui arrête le thread de mesure",
                   raises=TypeError)
def test_reponse_current_nulle_ne_plante_pas(monkeypatch):
    monkeypatch.setattr(meteo.requests, "get", lambda url, params=None, timeout=None: FausseReponseHTTP({"current": None}))

    assert meteo.Meteo("Annecy", [45.9, 6.1]).temperature() is None


def test_coordonnees_mal_formees_ne_plantent_pas(open_meteo):
    assert meteo.Meteo("Annecy", [45.9]).temperature() is None


# --- Archives : le mode météo « historique » ------------------------------------

ARCHIVES = "https://archive-api.open-meteo.com/v1/archive"


@pytest.fixture
def archives(monkeypatch):
    """Simule l'API d'archives. Régler .heures [(« 2022-01-03T08:00 », °C ou None), …] ou .erreur ; .appels liste les requêtes."""
    class Service:
        heures = [("2022-01-03T08:00", -2.0), ("2022-01-03T09:00", -3.0), ("2022-07-14T15:00", 25.0), ("2023-07-02T03:00", 15.0)]
        erreur = None
        appels = []

    def get(url, params=None, timeout=None):
        Service.appels.append({"url": url, "params": params, "timeout": timeout})
        if Service.erreur:
            raise Service.erreur
        return FausseReponseHTTP({"hourly": {"time": [h for h, _ in Service.heures],
                                             "temperature_2m": [v for _, v in Service.heures]}})

    Service.appels = []
    Service.erreur = None
    monkeypatch.setattr(meteo.requests, "get", get)
    return Service


def test_historique_demande_trois_ans_horaires_en_une_requete(archives):
    ville = meteo.Meteo("Annecy", [45.9, 6.13])

    ville.historique()
    ville.historique()
    ville.tirage()

    assert len(archives.appels) == 1
    assert archives.appels[0]["url"] == ARCHIVES
    assert archives.appels[0]["params"] == {"latitude": 45.9, "longitude": 6.13, "hourly": "temperature_2m",
                                            "start_date": "2021-01-01", "end_date": "2023-12-31"}


def test_historique_garde_le_mois_de_chaque_heure(archives):
    assert meteo.Meteo("Annecy", [45.9, 6.13]).historique() == [(1, -2.0), (1, -3.0), (7, 25.0), (7, 15.0)]


def test_historique_ignore_les_heures_sans_valeur(archives):
    archives.heures = [("2022-01-03T08:00", None), ("2022-01-03T09:00", 4.0)]

    assert meteo.Meteo("Annecy", [45.9, 6.13]).historique() == [(1, 4.0)]


def test_tirage_est_une_mesure_de_l_historique(archives):
    ville = meteo.Meteo("Annecy", [45.9, 6.13])

    assert {ville.tirage() for _ in range(60)} <= {(1, -2.0), (1, -3.0), (7, 25.0), (7, 15.0)}


def test_tirage_varie_d_une_mesure_a_l_autre(archives):
    ville = meteo.Meteo("Annecy", [45.9, 6.13])

    assert len({ville.tirage() for _ in range(60)}) > 1


def test_mois_pour_donne_le_mois_au_climat_le_plus_proche(archives):
    ville = meteo.Meteo("Annecy", [45.9, 6.13])   # moyennes : janvier -2,5 °C, juillet 20 °C

    assert ville.mois_pour(-1.0) == 1
    assert ville.mois_pour(18.0) == 7


def test_historique_indisponible_ne_donne_rien(archives, capsys):
    archives.erreur = requests.ConnectionError("pas d'Internet")
    ville = meteo.Meteo("Annecy", [45.9, 6.13])

    assert ville.historique() is None
    assert ville.tirage() is None
    assert "Archives météo indisponibles" in capsys.readouterr().out


def test_historique_indisponible_ne_reessaie_pas_tout_de_suite(archives, monkeypatch):
    archives.erreur = requests.Timeout("lent")
    maintenant = [1000.0]
    monkeypatch.setattr(meteo.time, "monotonic", lambda: maintenant[0])
    ville = meteo.Meteo("Annecy", [45.9, 6.13])

    ville.tirage()
    ville.tirage()
    assert len(archives.appels) == 1   # pas de nouvelle requête de 60 s qui bloquerait chaque mesure

    maintenant[0] += meteo.NOUVEL_ESSAI + 1
    archives.erreur = None
    assert ville.tirage() is not None
    assert len(archives.appels) == 2


def test_mois_pour_sans_archives_est_un_mois_au_hasard(archives):
    archives.erreur = requests.ConnectionError("pas d'Internet")

    assert meteo.Meteo("Annecy", [45.9, 6.13]).mois_pour(12.0) in range(1, 13)


def test_historique_geocode_si_pas_de_coordonnees(archives, monkeypatch):
    appels = []

    def get(url, params=None, timeout=None):
        appels.append(url)
        if url == GEOCODAGE:
            return FausseReponseHTTP({"results": [{"latitude": 45.9, "longitude": 6.13}]})
        return FausseReponseHTTP({"hourly": {"time": ["2022-01-03T08:00"], "temperature_2m": [1.0]}})

    monkeypatch.setattr(meteo.requests, "get", get)

    assert meteo.Meteo("Annecy").historique() == [(1, 1.0)]
    assert appels == [GEOCODAGE, ARCHIVES]
