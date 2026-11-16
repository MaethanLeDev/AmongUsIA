"""Tout le côté serveur en une commande : broker (si aucun ne tourne), interface 3D et maître du jeu.

1. Broker : on prend le premier qui répond parmi localhost, amongus.local, 10.109.150.215.
   S'il n'y en a aucun, on démarre celui de broker/ (Docker), ou à défaut le broker de test (outils/broker_dev.py).
2. Interface : node interface/server.js, si Node est installé (sinon la partie se joue sans spectateurs).
3. Maître du jeu, au premier plan : Entrée lance la partie tout de suite. Ctrl+C arrête tout
   (sauf le broker Docker, qui reste pour la prochaine fois).

Usage :
    uv run serveur.py                    partie normale
    uv run serveur.py --tp               les options inconnues vont au maître du jeu (ici, le jeu de base du sujet)
    uv run serveur.py --broker 10.0.0.5  ne cherche pas, n'en démarre pas : utilise ce broker
    uv run serveur.py --sans-interface
Mode d'emploi : docs/mode-emploi.md
"""
import argparse
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent
BROKERS_CONNUS = ["localhost", "amongus.local", "10.109.150.215"]   # même ordre que le maître et l'interface
PORT_MQTT = 1883
DEMARRAGE_BROKER = 20   # secondes : le premier « docker compose up » télécharge l'image


def joignable(hote, port=PORT_MQTT, delai=1.0):
    try:
        with socket.create_connection((hote, port), timeout=delai):
            return True
    except OSError:
        return False


def attendre_broker(delai=DEMARRAGE_BROKER):
    fin = time.monotonic() + delai
    while time.monotonic() < fin:
        if joignable("localhost"):
            return True
        time.sleep(0.5)
    return False


def demarrer_broker(processus):
    """Aucun broker sur le réseau : Mosquitto en Docker s'il est là, sinon le broker de test en Python."""
    if shutil.which("docker"):
        print("Aucun broker trouvé : démarrage de Mosquitto (docker compose, dossier broker/)…")
        lancement = subprocess.run(["docker", "compose", "up", "-d"], cwd=RACINE / "broker")
        if lancement.returncode == 0 and attendre_broker():
            return
        print("Docker n'a pas démarré le broker (Docker Desktop est-il lancé ?) : broker de test à la place.")
    else:
        print("Aucun broker trouvé et Docker absent : broker de test (outils/broker_dev.py).")
    processus.append(subprocess.Popen([sys.executable, "-u", str(RACINE / "outils" / "broker_dev.py")], cwd=RACINE))
    if not attendre_broker(5):
        sys.exit(f"Le broker ne démarre pas : le port {PORT_MQTT} est-il pris par un autre programme ?")


def adresse_reseau():
    """L'IP de cette machine vue des autres (aucun paquet n'est envoyé : connect en UDP choisit juste l'interface)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "l'IP de cette machine"


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)  # console Windows : pas de plantage sur un emoji
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Broker, interface et maître du jeu en une commande",
                                     epilog="Les autres options sont passées au maître du jeu (--tp, --tours 3…).")
    parser.add_argument("--broker", help="broker à utiliser (par défaut : le premier qui répond, sinon on en démarre un)")
    parser.add_argument("--sans-interface", action="store_true", help="ne pas lancer l'interface 3D")
    args, pour_le_maitre = parser.parse_known_args()

    processus = []
    try:
        hote = args.broker or next((h for h in BROKERS_CONNUS if joignable(h)), None)
        if hote is None:
            demarrer_broker(processus)
            hote = "localhost"
        if hote == "localhost":
            print(f"Broker sur cette machine. Les joueurs le trouvent par amongus.local, sinon : \"broker\": "
                  f"{{\"hote\": \"{adresse_reseau()}\"}} dans leur config.json")
        else:
            print(f"Broker : {hote}:{PORT_MQTT}")

        if args.sans_interface:
            pass
        elif shutil.which("node"):
            processus.append(subprocess.Popen(["node", "server.js", "--broker", hote], cwd=RACINE / "interface"))
            time.sleep(1)   # l'interface affiche ses adresses avant que le maître ne parle
        else:
            print("Node.js absent : pas d'interface 3D (https://nodejs.org, version 18 ou plus).")

        maitre = subprocess.Popen([sys.executable, "-u", str(RACINE / "maitre_du_jeu" / "maitre.py"),
                                   "--broker", hote, *pour_le_maitre], cwd=RACINE)
        processus.append(maitre)
        maitre.wait()
    except KeyboardInterrupt:
        print("\nArrêt du serveur.")
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
