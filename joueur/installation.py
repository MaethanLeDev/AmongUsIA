"""Préparation du joueur au lancement, pour que « uv run joueur/joueur.py » suffise.

- Pas encore de config.json : trois questions (nom, ville, caractère), et il est écrit tout seul.
  Le choix du LLM et les autres réglages suivent dans le menu de reglages.py.
- Ollama installé mais arrêté : on le démarre.
- Modèle pas encore téléchargé : on le télécharge (équivalent de « ollama pull »), avec la progression.

Ce qui ne peut pas se faire tout seul (installer Ollama) est expliqué, et le joueur démarre quand même :
il votera par calcul en attendant. Appelé par joueur.py ; options : docs/mode-emploi.md
"""
import json
import random
import shutil
import subprocess
import sys
import time
import unicodedata
from urllib.parse import urlsplit

import requests

# Des villes voisines d'Annecy (le sujet demande des villes adjacentes) : leurs coordonnées évitent le géocodage
VILLES = {"Annecy": [45.899, 6.129], "Seynod": [45.886, 6.089], "Cran-Gevrier": [45.900, 6.104],
          "Annecy-le-Vieux": [45.919, 6.143], "Sévrier": [45.864, 6.141], "Épagny": [45.936, 6.084],
          "Argonay": [45.944, 6.138], "Poisy": [45.921, 6.064], "Talloires": [45.841, 6.214],
          "Rumilly": [45.867, 5.942], "Faverges": [45.750, 6.295], "Thônes": [45.881, 6.325]}
CARACTERES = [
    ("stratege", "Tu es un détective froid et méthodique. Tu cites toujours les chiffres."),
    ("sourire", "Tu es très gentille, un peu naïve, et tu fais confiance trop vite."),
    ("vengeur", "Tu es soupçonneux et agressif : tu accuses vite et fort."),
    ("reine", "Tu es hautaine et précise. Tu méprises les arguments faibles."),
    ("ombre", "Tu parles peu, par phrases mystérieuses, mais tu observes tout."),
    ("prodige", "Tu es brillante et taquine, tu aimes piéger les autres avec des questions."),
]
COULEURS = ["#c1121f", "#1c7ed6", "#2f9e44", "#f08c00", "#7048e8", "#e64980", "#0c8599", "#5c940d"]
NOM_MAX = 16                  # longueur affichée par l'interface
PORT_OLLAMA = 11434           # là où « ollama serve » écoute : une autre adresse locale est une passerelle
DEMARRAGE_OLLAMA = 15         # secondes laissées à « ollama serve » pour répondre
TELECHARGEMENT_MAX = 3600     # secondes : un modèle de 500 Mo sur le Wi-Fi de l'IUT peut être long


# --- La config ------------------------------------------------------------

def identifiant(nom):
    """« Kuro-chan 2 » -> « kuro-chan2 » : un id MQTT sans accent, espace, /, + ni #."""
    sans_accent = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode()
    return "".join(c for c in sans_accent.lower() if c.isalnum() or c in "-_") or f"joueur{random.randint(100, 999)}"


def demander(question, defaut):
    reponse = input(f"{question} [{defaut}] : ").strip()
    return reponse or defaut


def choisir_ville(defaut=None):
    villes = list(VILLES)
    print("Villes voisines : " + ", ".join(f"{i}. {v}" for i, v in enumerate(villes, 1)))
    reponse = demander("Ta ville (numéro ou nom)", defaut or random.choice(villes))
    if reponse.isdigit() and 1 <= int(reponse) <= len(villes):
        return villes[int(reponse) - 1]
    return reponse


def nouvelle_config(nom, ville, caractere=None):
    """Une config complète : seuls le nom et la ville viennent du joueur, le reste a une valeur par défaut."""
    arch, personnalite = random.choice(CARACTERES)
    config = {
        "id": identifiant(nom), "ville": ville,
        "broker": {"hote": "amongus.local,10.109.150.215", "port": 1883},
        "ollama": {"url": "http://127.0.0.1:11434", "modele": "qwen3:0.6b"},
        "personnalite": caractere or personnalite, "strategie": "llm", "memoire": "faits",
        "interface": {"nom": nom[:NOM_MAX], "arch": arch, "couleurs": {"accent": random.choice(COULEURS)}},
        "api": {"port": 5000},
    }
    if ville in VILLES:
        config["coordonnees"] = VILLES[ville]
    return config


def creer_config(chemin):
    """Pose trois questions (Entrée garde la proposition) et écrit config.json. Sans clavier (service), tout est tiré au sort."""
    interactif = sys.stdin is not None and sys.stdin.isatty()
    prenom = random.choice(["Sherlock", "Mimi", "Kaito", "Yuki", "Nyx", "Hana", "Ren", "Aiko", "Jin", "Saki"])
    nom_propose = f"{prenom}{random.randint(100, 999)}"   # l'id en vient : deux id égaux se déconnectent l'un l'autre
    nom, ville, caractere = nom_propose, random.choice(list(VILLES)), ""
    if interactif:
        print(f"Première partie sur cette machine : création de {chemin.name} (Entrée pour garder la proposition).")
        try:
            nom = demander("Nom de ton IA à la table", nom_propose)
            ville = choisir_ville()
            caractere = input("Son caractère, en une phrase « Tu es… » [au hasard] : ").strip()
        except EOFError:   # pas de clavier finalement : sous Windows, NUL se fait passer pour un terminal
            print("\nPas de réponse possible : le reste est tiré au sort.")
    config = nouvelle_config(nom, ville, caractere)
    chemin.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{chemin} écrit (id « {config['id']} »). Pour le changer plus tard : même commande avec --reglages.\n")


def corriger_coordonnees(config):
    """Ville changée à la main : les coordonnées écrites pour l'ancienne donneraient la température de celle-ci."""
    coordonnees, voulues = config.get("coordonnees"), VILLES.get(config["ville"])
    if coordonnees in VILLES.values() and coordonnees != voulues:   # d'autres coordonnées ont été mises exprès
        if voulues:
            config["coordonnees"] = voulues
        else:
            del config["coordonnees"]


# --- Ollama ---------------------------------------------------------------

def modeles_installes(url):
    """La liste des modèles d'Ollama, ou None s'il ne répond pas."""
    try:
        reponse = requests.get(f"{url}/api/tags", timeout=3)
        reponse.raise_for_status()
        return [m.get("name", "") for m in reponse.json().get("models", [])]
    except (requests.RequestException, ValueError):
        return None


def ollama_de_cette_machine(url):
    adresse = urlsplit(url)
    return adresse.hostname in ("127.0.0.1", "localhost") and adresse.port == PORT_OLLAMA


def demarrer_ollama(url):
    """Ollama installé mais arrêté (souvent sous Linux sans service) : on lance « ollama serve » en arrière-plan."""
    if not ollama_de_cette_machine(url) or not shutil.which("ollama"):
        return None
    print("Ollama ne répond pas : démarrage de « ollama serve »…")
    subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)  # survit au joueur : le relancer ne recharge pas le modèle
    fin = time.monotonic() + DEMARRAGE_OLLAMA
    while time.monotonic() < fin:
        installes = modeles_installes(url)
        if installes is not None:
            return installes
        time.sleep(0.5)
    return None


def telecharger(url, modele):
    """Équivalent de « ollama pull », avec la progression sur une ligne. Renvoie True si le modèle est prêt."""
    print(f"Téléchargement du modèle {modele} (une seule fois)…")
    try:
        with requests.post(f"{url}/api/pull", json={"model": modele}, stream=True, timeout=TELECHARGEMENT_MAX) as reponse:
            reponse.raise_for_status()
            for ligne in reponse.iter_lines():
                etape = json.loads(ligne) if ligne else {}
                if etape.get("error"):
                    print(f"\nOllama refuse : {etape['error']}")
                    return False
                if etape.get("total"):
                    print(f"\r  {etape.get('completed', 0) * 100 // etape['total']:3d} %", end="", flush=True)
                if etape.get("status") == "success":
                    print(f"\rModèle {modele} prêt.     ")
                    return True
    except (requests.RequestException, ValueError) as erreur:
        print(f"\nTéléchargement interrompu ({erreur.__class__.__name__}) : relance le joueur pour reprendre.")
    return False


def preparer_ollama(config, principal="Ollama"):
    """Ollama tourne-t-il, avec le modèle ? Sinon on le démarre et on télécharge le modèle, quand c'est possible."""
    url, modele = config["ollama"]["url"].rstrip("/"), config["ollama"]["modele"]
    installes = modeles_installes(url)
    if installes is None:
        installes = demarrer_ollama(url)
    if installes is None:
        if principal != "Ollama":
            print(f"Pas d'Ollama sur {url} : {principal} parlera, sans LLM de secours (le calcul prendra le relais).\n")
            return
        if not ollama_de_cette_machine(url):
            print(f"Rien ne répond sur {url} : lance d'abord ta passerelle ou ton Ollama distant, ou change de LLM "
                  "avec --reglages. Le joueur démarre quand même : en attendant, il votera par calcul.\n")
            return
        print("Ollama n'est pas installé ou ne démarre pas. Pour l'installer :\n"
              "  Raspberry Pi / Linux : curl -fsSL https://ollama.com/install.sh | sh\n"
              "  Windows / macOS      : https://ollama.com/download\n"
              "Le joueur démarre quand même : en attendant, il votera par calcul.\n")
        return
    if modele not in installes and f"{modele}:latest" not in installes:
        telecharger(url, modele)
