"""Fait discuter deux agents (TP « RPi & Ollama », partie 5).

L'agent A lance la conversation en appelant la route /message de l'agent B, à tour de rôle.
Chacun se souvient de toute la conversation. Marche avec joueur.py et avec tout agent qui répond
à POST /message {"message": "..."} -> {"reponse": "..."}.

Usage : uv run joueur/discuter.py http://10.109.150.60:5000 http://10.109.150.61:5000 --sujet "la pluie" --tours 3
"""
import argparse
import sys

import requests


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)  # console Windows : pas de plantage sur un emoji
    parser = argparse.ArgumentParser(description="Fait discuter deux agents")
    parser.add_argument("agent_a", help="URL de l'agent qui lance la conversation (un joueur.py)")
    parser.add_argument("agent_b", help="URL de l'autre agent")
    parser.add_argument("--sujet", default="la météo de vos villes")
    parser.add_argument("--tours", type=int, default=3)
    args = parser.parse_args()

    a, b = args.agent_a.rstrip("/"), args.agent_b.rstrip("/")
    for url in (a, b):
        try:
            print(f"{url}/health : {requests.get(f'{url}/health', timeout=5).json()}")
        except (requests.RequestException, ValueError) as erreur:
            sys.exit(f"{url} ne répond pas ({erreur})")

    noms = {}
    for url in (a, b):
        try:
            noms[url] = requests.get(f"{url}/agent", timeout=5).json().get("nom", url)
        except (requests.RequestException, ValueError):
            noms[url] = url  # agent sans route /agent

    print(f"\n{noms[a]} lance la conversation avec {noms[b]} sur « {args.sujet} » ({args.tours} tours)…\n")
    try:
        reponse = requests.post(f"{a}/discuter", json={"avec": b, "sujet": args.sujet, "tours": args.tours},
                                timeout=200 * (args.tours + 1))
        reponse.raise_for_status()
    except requests.RequestException as erreur:
        sys.exit(f"La conversation a échoué ({erreur})")
    for echange in reponse.json()["echanges"]:
        qui = noms[b] if echange["de"] == b else noms[a]
        print(f"{qui} : {echange['texte']}\n")


if __name__ == "__main__":
    main()
