# /// script
# requires-python = ">=3.14"
# dependencies = ["paho-mqtt>=2.1.0", "requests>=2.34.2"]
# ///
"""Jouer sans cloner le dépôt : ce seul fichier récupère le code du joueur, puis le lance.

À chaque lancement, il prend le dossier joueur/ de la branche main : tout le monde joue avec la même version.
Si GitHub ne répond pas, il relance la dernière version récupérée (pour jouer sans Internet, enregistrer ce fichier :
uv ne peut pas lancer une URL hors ligne). Rien d'autre du projet n'est gardé sur la machine :
    ~/.amongusia/code/         le code du joueur, remplacé à chaque lancement
    ~/.amongusia/config.json   les réglages du joueur, jamais remplacés

Usage : uv run https://raw.githubusercontent.com/MaethanLeDev/AmongUsIA/main/jouer.py [chemin/vers/config.json] [--reglages]
"""
import io
import runpy
import sys
import zipfile
from pathlib import Path, PurePosixPath

import requests

# L'archive entière (environ 400 Ko) plutôt que fichier par fichier : un nouveau module de joueur/ suit tout seul
ARCHIVE = "https://codeload.github.com/MaethanLeDev/AmongUsIA/zip/refs/heads/main"
DOSSIER = Path.home() / ".amongusia"
DELAI_GITHUB = 20   # secondes


def extraire_joueur(archive):
    """Les scripts de joueur/ contenus dans l'archive : {nom du fichier: contenu}."""
    fichiers = {}
    with zipfile.ZipFile(io.BytesIO(archive)) as contenu:
        for chemin in contenu.namelist():
            morceaux = PurePosixPath(chemin).parts   # AmongUsIA-main/joueur/ia.py
            if len(morceaux) == 3 and morceaux[1] == "joueur" and morceaux[2].endswith(".py"):
                fichiers[morceaux[2]] = contenu.read(chemin)
    return fichiers


def recuperer_code(code):
    """Met le code à jour. Si GitHub ne répond pas, on garde celui de la fois d'avant."""
    try:
        reponse = requests.get(ARCHIVE, timeout=DELAI_GITHUB)
        reponse.raise_for_status()
        fichiers = extraire_joueur(reponse.content)   # tout est lu avant d'écrire : pas de code à moitié à jour
    except (requests.RequestException, zipfile.BadZipFile) as erreur:
        probleme = f"GitHub injoignable ou réponse illisible ({erreur.__class__.__name__})"
    else:
        if "joueur.py" in fichiers:
            code.mkdir(parents=True, exist_ok=True)
            for nom, octets in fichiers.items():
                (code / nom).write_bytes(octets)
            return
        probleme = "joueur.py absent de l'archive"

    if not (code / "joueur.py").exists():
        sys.exit(f"Impossible de récupérer le joueur : {probleme}. Il faut Internet au premier lancement.")
    print(f"{probleme} : lancement de la version déjà récupérée.")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)  # console Windows : pas de plantage sur un emoji
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    code = DOSSIER / "code"
    recuperer_code(code)
    options = [a for a in sys.argv[1:] if a.startswith("-")]   # --reglages : transmises au joueur
    chemins = [a for a in sys.argv[1:] if not a.startswith("-")]
    config = chemins[0] if chemins else str(DOSSIER / "config.json")   # hors de code/, qui est remplacé
    script = str(code / "joueur.py")
    sys.argv = [script, config, *options]
    sys.path.insert(0, str(code))   # joueur.py importe ses voisins directement (from ia import IA)
    try:
        runpy.run_path(script, run_name="__main__")
    except KeyboardInterrupt:       # Ctrl+C pendant les questions ou le téléchargement du modèle
        print("\nArrêt du joueur.")


if __name__ == "__main__":
    main()
