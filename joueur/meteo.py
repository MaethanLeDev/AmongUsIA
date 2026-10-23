"""Température actuelle d'une ville, via l'API Open-Meteo (gratuite, sans clé)."""
import requests


class Meteo:
    def __init__(self, ville):
        reponse = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                               params={"name": ville, "count": 1, "language": "fr"}, timeout=10)
        reponse.raise_for_status()
        resultats = reponse.json().get("results")
        if not resultats:
            raise ValueError(f"Ville introuvable : {ville}")
        self.latitude = resultats[0]["latitude"]
        self.longitude = resultats[0]["longitude"]
        self.derniere = None

    def temperature(self):
        try:
            reponse = requests.get("https://api.open-meteo.com/v1/forecast",
                                   params={"latitude": self.latitude, "longitude": self.longitude,
                                           "current": "temperature_2m"}, timeout=10)
            reponse.raise_for_status()
            self.derniere = reponse.json()["current"]["temperature_2m"]
        except (requests.RequestException, KeyError) as erreur:
            print(f"  Météo indisponible ({erreur}), on garde la dernière valeur")
        return self.derniere
