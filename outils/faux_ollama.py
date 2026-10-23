"""Faux Ollama pour tester sans LLM : il imite /api/chat avec des répliques plausibles et des votes en JSON.

Il lit le contexte envoyé par joueur/ia.py (noms des joueurs, capteurs INSTABLES) pour que la partie ait l'air vraie.

Usage : python outils/faux_ollama.py [--port 11434] [--lenteur 2]
"""
import argparse
import json
import random
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PHRASES = [
    "{x}, tes valeurs bougent à chaque mesure alors que la météo est stable. Explique-toi.",
    "Je ne suis pas convaincu par {x}. {y}, tu as vu ses chiffres ?",
    "Mes températures sont stables, regardez-les. Par contre {x} m'inquiète.",
    "{y} a raison de se méfier, mais je pense plutôt à {x}.",
    "Calmez-vous. {x} est peut-être juste dans une vallée plus froide.",
    "Une vraie température ne saute pas d'un degré en cinq secondes. {x}, c'est quoi ton capteur ?",
    "{y}, pourquoi tu ne dis rien sur {x} ? C'est suspect aussi, ça.",
    "Je vote avec les chiffres, pas avec les impressions : {x} est le plus instable.",
    "Je trouve {y} un peu trop pressé d'accuser {x}. Ça cache peut-être quelque chose.",
    "{x}, tu es à côté de nous et tu as deux degrés d'écart. Ça ne colle pas.",
    "Franchement, je n'ai pas encore d'avis. {x} et {y}, défendez-vous.",
    "Si on se trompe encore, l'espion gagne. Regardons bien les valeurs de {x}.",
]
# Seulement à partir de la deuxième manche : l'IA se souvient de la précédente
PHRASES_MEMOIRE = [
    "On a éliminé un innocent la dernière fois, ne refaisons pas la même erreur : {x} est le plus louche.",
    "À la manche d'avant, {x} accusait déjà au hasard. Je ne lui fais pas confiance.",
    "{y} avait vu juste la dernière fois. Je l'écoute, et je regarde {x}.",
]


def repondre(messages, format_json):
    texte = messages[-1]["content"] if messages else ""
    systeme = messages[0]["content"] if messages else ""
    vivants = re.search(r"Joueurs encore en jeu : (.*?)\.(?:\s|$)", texte)
    noms = [n.replace(" (toi)", "") for n in vivants.group(1).split(", ")] if vivants else []
    moi = re.search(r"Tu es (.+?) \(", systeme)
    autres = [n for n in noms if not moi or n != moi.group(1)] or ["quelqu'un"]
    instables = [n for n in re.findall(r"^- (.+?)(?: \(toi\))?, .*?INSTABLE", texte, re.M) if n in autres]

    if format_json:
        ids = dict(re.findall(r"([\w-]+) \(([^)]+)\)", texte.split("Identifiants possibles :")[-1]))
        if not ids:
            return json.dumps({"suspect": "", "raison": "je ne sais pas"})
        par_nom = {nom: i for i, nom in ids.items()}
        cible = random.choice(instables) if instables and random.random() < 0.7 else random.choice(list(ids.values()))
        return json.dumps({"suspect": par_nom.get(cible, cible), "raison": f"{cible} a des températures suspectes."},
                          ensure_ascii=False)
    if "deux phrases de notes" in texte:
        return f"Je me méfie de {random.choice(instables or autres)}. {random.choice(autres)} me paraît plutôt fiable."
    if "Joueurs encore en jeu" not in texte:
        return f"Bonne question ! Je suis un faux agent de test, mais je retiens ce que tu dis : « {texte[:60]} »."
    x = random.choice(instables) if instables and random.random() < 0.6 else random.choice(autres)
    y = random.choice([n for n in autres if n != x] or autres)
    souvenirs = PHRASES_MEMOIRE if "manches précédentes" in texte else []
    return random.choice(PHRASES + souvenirs * 2).format(x=x, y=y)


def main():
    parser = argparse.ArgumentParser(description="Faux Ollama pour les tests")
    parser.add_argument("--port", type=int, default=11434)
    parser.add_argument("--lenteur", type=float, default=2, help="secondes de « réflexion » en moyenne")
    args = parser.parse_args()

    class Gestionnaire(BaseHTTPRequestHandler):
        def do_GET(self):
            self.envoyer({"models": [{"name": "faux:latest"}]})

        def do_POST(self):
            corps = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            time.sleep(random.uniform(0.5, 1.5) * args.lenteur)
            contenu = repondre(corps.get("messages", []), corps.get("format") == "json")
            self.envoyer({"model": corps.get("model"), "message": {"role": "assistant", "content": contenu}, "done": True})

        def envoyer(self, contenu):
            donnees = json.dumps(contenu, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(donnees)))
            self.end_headers()
            self.wfile.write(donnees)

        def log_message(self, *a):
            pass

    print(f"Faux Ollama sur le port {args.port}")
    try:
        ThreadingHTTPServer(("0.0.0.0", args.port), Gestionnaire).serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
