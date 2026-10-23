"""Température actuelle d'une ville, via l'API Open-Meteo (gratuite, sans clé)."""
import threading

import requests


class Meteo:
    def __init__(self, ville, coordonnees=None):
        self.ville = ville
        # [latitude, longitude] dans config.json : évite le géocodage (ville homonyme, réseau sans DNS…)
        self.coordonnees = tuple(coordonnees) if coordonnees else None
        self.derniere = None
        self.verrou = threading.Lock()

    def _localiser(self):
        reponse = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                               params={"name": self.ville, "count": 1, "language": "fr"}, timeout=10)
        reponse.raise_for_status()
        resultats = reponse.json().get("results")
        if not resultats:
            raise ValueError(f"ville introuvable : {self.ville} (mettre \"coordonnees\": [lat, lon] dans config.json)")
        self.coordonnees = (resultats[0]["latitude"], resultats[0]["longitude"])

    def temperature(self):
        """La température actuelle, ou la dernière connue si l'API ne répond pas (None si jamais obtenue)."""
        with self.verrou:  # le géocodage n'est fait qu'une fois, même si deux threads demandent en même temps
            try:
                if self.coordonnees is None:
                    self._localiser()
                latitude, longitude = self.coordonnees
                reponse = requests.get("https://api.open-meteo.com/v1/forecast",
                                       params={"latitude": latitude, "longitude": longitude,
                                               "current": "temperature_2m"}, timeout=10)
                reponse.raise_for_status()
                self.derniere = reponse.json()["current"]["temperature_2m"]
            except (requests.RequestException, KeyError, ValueError) as erreur:
                print(f"  Météo indisponible ({erreur}), on garde la dernière valeur")
            return self.derniere
