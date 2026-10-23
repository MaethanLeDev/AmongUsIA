"""Tue les processus restés à l'écoute sur les ports d'une simulation (broker 1883, faux Ollama 11435, API 5100-5111).

Sous Windows, fermer une simulation autrement que par Ctrl+C laisse ces processus tourner,
et la simulation suivante se branche alors sur l'ancien broker.
Usage : uv run python .claude/skills/simulation/nettoyer.py
"""
import os
import re
import signal
import subprocess
import sys

PORTS = {1883, 11435, *range(5100, 5112)}


def pids_windows():
    sortie = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, errors="replace").stdout
    pids = set()
    for ligne in sortie.splitlines():
        morceaux = ligne.split()
        if len(morceaux) >= 5 and morceaux[3].upper() in ("LISTENING", "ÉCOUTE", "ECOUTE"):
            port = re.search(r":(\d+)$", morceaux[1])
            if port and int(port.group(1)) in PORTS:
                pids.add(int(morceaux[4]))
    return pids


def pids_unix():
    pids = set()
    for port in PORTS:
        try:
            sortie = subprocess.run(["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"], capture_output=True, text=True).stdout
        except FileNotFoundError:
            sys.exit("lsof introuvable : arrêter les processus à la main (ports 1883, 11435, 5100-5111).")
        pids.update(int(p) for p in sortie.split())
    return pids


def main():
    windows = sys.platform == "win32"
    pids = (pids_windows() if windows else pids_unix()) - {0, os.getpid()}
    for pid in sorted(pids):
        if windows:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        else:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    print(f"{len(pids)} processus arrêtés : {sorted(pids)}" if pids else "Aucun reste de simulation.")


if __name__ == "__main__":
    main()
