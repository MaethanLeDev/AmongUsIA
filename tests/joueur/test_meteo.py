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
