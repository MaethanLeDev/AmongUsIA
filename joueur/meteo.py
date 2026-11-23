"""Température d'une ville, via l'API Open-Meteo (gratuite, sans clé) : actuelle, ou tirée dans l'historique."""
import random
import statistics
import threading
import time

import requests

ARCHIVES = "https://archive-api.open-meteo.com/v1/archive"
PERIODE = ("2021-01-01", "2023-12-31")   # trois années entières : toutes les saisons, plusieurs fois
NOUVEL_ESSAI = 60                        # secondes avant de redemander les archives après un échec


class Meteo:
    def __init__(self, ville, coordonnees=None):
        self.ville = ville
        # [latitude, longitude] dans config.json : évite le géocodage (ville homonyme, réseau sans DNS…)
        self.coordonnees = tuple(coordonnees) if coordonnees else None
        self.derniere = None
        self.archives = None        # [(mois, °C), …] horaires sur PERIODE, chargées une seule fois (mode « historique »)
        self.moyennes = {}          # mois -> température moyenne de la ville, calculée avec les archives
        self.echec_archives = None  # instant du dernier échec de chargement des archives
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
            except (requests.RequestException, KeyError, TypeError, ValueError) as erreur:   # TypeError : "current": null
                print(f"  Météo indisponible ({erreur}), on garde la dernière valeur")
            return self.derniere

    # --- Mode « historique » : une mesure tirée au hasard dans les trois dernières années ---

    def historique(self):
        """Les températures horaires de la ville sur PERIODE, [(mois, °C), …], chargées en une seule requête.
        None si l'API d'archives ne répond pas (on ne réessaie qu'après NOUVEL_ESSAI s, pour ne pas bloquer les mesures)."""
        with self.verrou:
            if self.archives is None and (self.echec_archives is None or time.monotonic() - self.echec_archives > NOUVEL_ESSAI):
                try:
                    if self.coordonnees is None:
                        self._localiser()
                    latitude, longitude = self.coordonnees
                    reponse = requests.get(ARCHIVES, params={"latitude": latitude, "longitude": longitude, "hourly": "temperature_2m",
                                                             "start_date": PERIODE[0], "end_date": PERIODE[1]}, timeout=60)
                    reponse.raise_for_status()
                    horaire = reponse.json()["hourly"]
                    self.archives = [(int(heure[5:7]), valeur)   # « 2022-07-14T15:00 » : le mois est aux caractères 5 et 6
                                     for heure, valeur in zip(horaire["time"], horaire["temperature_2m"], strict=True)
                                     if valeur is not None]
                    mois = {m: [v for m2, v in self.archives if m2 == m] for m in range(1, 13)}
                    self.moyennes = {m: statistics.mean(valeurs) for m, valeurs in mois.items() if valeurs}
                    self.echec_archives = None
                except (requests.RequestException, KeyError, ValueError, TypeError) as erreur:
                    print(f"  Archives météo indisponibles ({erreur}), mesures actuelles en attendant")
                    self.echec_archives = time.monotonic()
            return self.archives or None

    def tirage(self):
        """Une mesure au hasard (n'importe quel jour, n'importe quelle heure) : (mois, °C), ou None sans archives."""
        archives = self.historique()
        return random.choice(archives) if archives else None

    def mois_pour(self, temperature):
        """Le mois dont la température moyenne ici est la plus proche : le mois que l'espion annonce pour sa fausse valeur.
        Au hasard sans archives."""
        if not self.historique() or not self.moyennes:
            return random.randint(1, 12)
        return min(self.moyennes, key=lambda mois: abs(self.moyennes[mois] - temperature))
