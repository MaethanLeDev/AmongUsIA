#!/usr/bin/env python3
"""Exemple d'agent Raspberry Pi pour le salon Classe Noire (bibliothèque standard uniquement).

Il fait trois choses, en boucle :
  1. il rejoint le salon         POST /api/agents/<id>/join
  2. il lit ce que dit la table  GET  /api/chat?since=<n>
  3. il répond avec son LLM      Ollama local (qwen3:0.6b) puis POST /api/agents/<id>/chat

Usage :  python3 agent_pi.py --serveur http://10.109.104.10:3939 --id rpi1 --ville Annecy
(Avec MQTT, le même échange passe par les topics iot/joueurs/<id>, iot/table/chat et iot/chat/<id> : voir ../AGENTS.md)
"""
import argparse
import json
import time
import urllib.request


def appel(url, donnees=None, timeout=120):
    req = urllib.request.Request(url, data=None if donnees is None else json.dumps(donnees).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def demander_au_llm(ollama, modele, personnalite, phrase):
    corps = {"model": modele, "stream": False, "think": False, "options": {"num_predict": 80},
             "messages": [{"role": "system", "content": personnalite}, {"role": "user", "content": phrase}]}
    return appel(ollama + "/api/chat", corps)["message"]["content"].strip()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--serveur", required=True, help="adresse du serveur Classe Noire, ex. http://10.109.104.10:3939")
    p.add_argument("--id", required=True, help="identifiant du joueur (rpi1, rpi2...), le même que dans le TP")
    p.add_argument("--ville", default="Annecy")
    p.add_argument("--ollama", default="http://127.0.0.1:11434")
    p.add_argument("--modele", default="qwen3:0.6b")
    a = p.parse_args()
    base = a.serveur.rstrip("/") + "/api"
    personnalite = ("Tu es un joueur autour d'une table ronde. Tu soupçonnes que l'un des capteurs météo ment. "
                    "Réponds en une seule phrase courte, en français.")

    appel(f"{base}/agents/{a.id}/join", {"ville": a.ville})
    print("Rejoint le salon en tant que", a.id)
    vu = appel(f"{base}/chat?since=0")["dernier"]          # on ignore l'historique déjà écrit
    try:
        while True:
            reponse = appel(f"{base}/chat?since={vu}")
            for m in reponse["messages"]:
                vu = max(vu, m["seq"])
                if m.get("fromAgent") == a.id or m["kind"] == "rumor":
                    continue                               # on ne répond pas à soi-même
                phrase = f'{m["name"]} dit : {m["text"]}'
                print(phrase)
                texte = demander_au_llm(a.ollama, a.modele, personnalite, phrase)
                # chuchoter en retour si on nous a chuchoté (champ "to" = id de joueur de la table)
                corps = {"text": texte}
                if m["kind"] == "whisper":
                    corps["to"] = m["from"]
                print("  ->", texte, appel(f"{base}/agents/{a.id}/chat", corps))
                time.sleep(8)                              # laisse la table respirer
            time.sleep(2)
    finally:
        appel(f"{base}/agents/{a.id}/leave", {})


if __name__ == "__main__":
    main()
