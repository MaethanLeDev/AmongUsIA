"""Lance une partie complète sur un seul PC, sans Raspberry Pi : broker de test, faux Ollama, N joueurs et le maître.

Pour regarder la partie dans l'interface, dans un autre terminal : node interface/server.js
puis ouvrir http://localhost:5050. Mode d'emploi complet : docs/mode-emploi.md

Usage :
    uv run outils/simulation.py                          5 joueurs, tout est simulé
    uv run outils/simulation.py --joueurs 8 --rapide     débat court, pour tester vite
    uv run outils/simulation.py --ollama http://127.0.0.1:11434 --modele qwen3:0.6b   avec un vrai LLM
    uv run outils/simulation.py --broker 10.109.150.215  sur le vrai broker (attention : visible par tous)
Les arguments après -- vont au maître du jeu : uv run outils/simulation.py -- --tp
"""
import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

RACINE = Path(__file__).resolve().parent.parent

# Des villes voisines d'Annecy (le sujet demande des villes adjacentes), avec leurs coordonnées
VILLES = [("Annecy", 45.899, 6.129), ("Seynod", 45.886, 6.089), ("Cran-Gevrier", 45.900, 6.104),
          ("Annecy-le-Vieux", 45.919, 6.143), ("Sévrier", 45.864, 6.141), ("Épagny", 45.936, 6.084),
          ("Argonay", 45.944, 6.138), ("Poisy", 45.921, 6.064), ("Talloires", 45.841, 6.214),
          ("Rumilly", 45.867, 5.942), ("Faverges", 45.750, 6.295), ("Thônes", 45.881, 6.325)]
PERSONNAGES = [
    ("Sherlock", "stratege", "Tu es un détective froid et méthodique. Tu cites toujours les chiffres."),
    ("Mimi", "sourire", "Tu es très gentille, un peu naïve, et tu fais confiance trop vite."),
    ("Kaito", "vengeur", "Tu es soupçonneux et agressif : tu accuses vite et fort."),
    ("Yuki", "reine", "Tu es hautaine et précise. Tu méprises les arguments faibles."),
    ("Nyx", "ombre", "Tu parles peu, par phrases mystérieuses, mais tu observes tout."),
    ("Hana", "prodige", "Tu es brillante et taquine, tu aimes piéger les autres avec des questions."),
    ("Ren", "stratege", "Tu es diplomate : tu cherches le consensus avant d'accuser."),
    ("Aiko", "prodige", "Tu es impulsive et drôle, tu changes souvent d'avis."),
    ("Jin", "vengeur", "Tu es loyal envers ceux qui te soutiennent, impitoyable avec les autres."),
    ("Saki", "reine", "Tu es une scientifique : seules les données comptent pour toi."),
    ("Kuro", "ombre", "Tu es paranoïaque : tout le monde te paraît suspect."),
    ("Momo", "sourire", "Tu es joyeuse et bavarde, tu fais des blagues sur la météo."),
]


def lancer(commande, journal=None):
    sortie = open(journal, "w", encoding="utf-8") if journal else None
    return subprocess.Popen([sys.executable, "-u", *map(str, commande)], cwd=RACINE,
                            stdout=sortie, stderr=subprocess.STDOUT if sortie else None)


def verifier_ollama(url, modele):
    """Sans Ollama, toutes les IA diraient leur phrase de secours : mieux vaut s'arrêter tout de suite et expliquer."""
    try:
        reponse = requests.get(f"{url}/api/tags", timeout=5)
        reponse.raise_for_status()
        installes = [m.get("name", "") for m in reponse.json().get("models", [])]
    except (requests.RequestException, ValueError) as erreur:
        sys.exit(f"Ollama ne répond pas sur {url} ({erreur.__class__.__name__}).\n"
                 "Installez-le (https://ollama.com/download), lancez-le, puis vérifiez : curl " + url + "/api/tags")
    if modele not in installes and f"{modele}:latest" not in installes:
        sys.exit(f"Le modèle {modele} n'est pas installé dans Ollama : ollama pull {modele}\n"
                 f"Modèles installés : {', '.join(installes) or 'aucun'}")
    print(f"Ollama prêt sur {url}, modèle {modele}.")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)  # console Windows : pas de plantage sur un emoji
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Simulation d'une partie sur un seul PC",
                                     epilog="Les arguments après -- sont passés au maître du jeu.")
    parser.add_argument("--joueurs", type=int, default=5)
    parser.add_argument("--broker", help="broker existant (par défaut : un broker de test sur le port 1883)")
    parser.add_argument("--ollama", help="URL d'un vrai Ollama (par défaut : le faux Ollama)")
    parser.add_argument("--modele", default="qwen3:0.6b")
    parser.add_argument("--rapide", action="store_true", help="un tour de débat, pauses courtes")
    parser.add_argument("--resume", action="store_true", help="mémoire \"resume\" : le LLM écrit ses notes à chaque manche")
    args, pour_le_maitre = parser.parse_known_args()
    pour_le_maitre = [a for a in pour_le_maitre if a != "--"]
    n = max(2, min(args.joueurs, len(PERSONNAGES)))
    if args.ollama:
        verifier_ollama(args.ollama.rstrip("/"), args.modele)

    dossier = Path(tempfile.mkdtemp(prefix="amongusia-"))
    processus = []
    try:
        if not args.broker:
            processus.append(lancer(["outils/broker_dev.py"], dossier / "broker.log"))
        if not args.ollama:
            processus.append(lancer(["outils/faux_ollama.py", "--port", 11435], dossier / "ollama.log"))
        time.sleep(1.5)
        if any(p.poll() is not None for p in processus):
            # Port déjà pris : souvent une simulation précédente fermée sans Ctrl+C, dont les processus tournent encore
            sys.exit("Le broker (port 1883) ou le faux Ollama (port 11435) n'a pas démarré : port déjà utilisé ?\n"
                     f"Voir {dossier}. Arrêtez l'ancienne simulation (ou les python.exe restants) et relancez.")

        for i in range(n):
            nom, arch, personnalite = PERSONNAGES[i]
            ville, lat, lon = VILLES[i]
            config = {
                "id": f"sim{i + 1}", "ville": ville, "coordonnees": [lat, lon],
                "broker": {"hote": args.broker or "localhost", "port": 1883},
                "ollama": {"url": args.ollama or "http://127.0.0.1:11435", "modele": args.modele if args.ollama else "simulé"},
                "personnalite": personnalite, "strategie": "llm" if i % 4 else "ecart",
                "memoire": "resume" if args.resume else "faits",
                "interface": {"nom": nom, "arch": arch}, "api": {"port": 5100 + i},
            }
            chemin = dossier / f"sim{i + 1}.json"
            chemin.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
            processus.append(lancer(["joueur/joueur.py", chemin], dossier / f"sim{i + 1}.log"))
            time.sleep(0.3)

        reglages = ["--broker", args.broker or "localhost", "--auto", "8", "--stats", dossier / "stats.json"]
        if args.rapide:
            reglages += ["--tours", "1", "--pause", "0.5", "--pause-verdict", "8", "--pause-fin", "10"]
        print(f"{n} joueurs lancés (journaux et configs : {dossier})")
        print(f"API des agents : http://localhost:5100 … http://localhost:{5100 + n - 1}  (/agent, /health, /message)\n")
        maitre = lancer(["maitre_du_jeu/maitre.py", *reglages, *pour_le_maitre])
        processus.append(maitre)
        maitre.wait()
    except KeyboardInterrupt:
        print("\nArrêt de la simulation.")
    finally:
        for p in reversed(processus):
            p.terminate()
        for p in processus:
            try:
                p.wait(5)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    main()
