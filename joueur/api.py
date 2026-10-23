"""API HTTP de l'agent (TP « RPi & Ollama ») :

    POST /message   {"message": "...", "de": "rpi2"}       -> {"reponse": "..."}   (l'agent se souvient de la conversation)
    GET  /health                                            -> l'agent et son Ollama sont-ils vivants ?
    GET  /agent                                             -> ce que l'agent sait faire
    POST /discuter  {"avec": "http://ip:5000", "sujet": "...", "tours": 4}
                    -> l'agent lance une conversation avec un autre agent, en appelant son /message

Sans dépendance : le serveur HTTP de la bibliothèque standard, dans un thread à côté du jeu.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

MAX_HISTORIQUE = 40  # messages gardés par interlocuteur (le contexte d'un petit modèle est limité)
MAX_TOURS = 10


class Conversations:
    """L'historique de chaque interlocuteur, pour que l'agent se souvienne de toute la conversation."""

    def __init__(self):
        self.verrou = threading.Lock()
        self.historiques = {}  # interlocuteur -> [{"role", "content"}, ...]

    def lire(self, qui):
        with self.verrou:
            return list(self.historiques.get(qui, []))

    def ajouter(self, qui, question, reponse):
        with self.verrou:
            historique = self.historiques.setdefault(qui, [])
            historique += [{"role": "user", "content": question}, {"role": "assistant", "content": reponse}]
            del historique[:-MAX_HISTORIQUE]


def demarrer_api(joueur, port):
    """Lance l'API en arrière-plan. joueur fournit .ia, .fiche() et .sante()."""
    conversations = Conversations()

    def repondre_a(qui, message):
        reponse = joueur.ia.repondre(conversations.lire(qui), message)
        conversations.ajouter(qui, message, reponse)
        return reponse

    def discuter(url, sujet, tours):
        """Partie 5 du TP : notre agent ouvre la conversation et appelle le /message de l'autre, à tour de rôle."""
        url = url.rstrip("/")
        replique = repondre_a(url, f"Lance une conversation avec un autre agent sur ce sujet : {sujet}. "
                                   "Dis seulement ta première phrase.")
        echanges = [{"de": joueur.id, "texte": replique}]
        for _ in range(tours):
            reponse = requests.post(f"{url}/message", json={"message": replique, "de": joueur.id}, timeout=150)
            reponse.raise_for_status()
            sa_replique = reponse.json().get("reponse") or reponse.json().get("response") or ""
            echanges.append({"de": url, "texte": sa_replique})
            replique = repondre_a(url, sa_replique)
            echanges.append({"de": joueur.id, "texte": replique})
        return echanges

    class Gestionnaire(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                self.envoyer(200, joueur.sante())
            elif self.path == "/agent":
                self.envoyer(200, joueur.fiche())
            else:
                self.envoyer(404, {"erreur": "routes : POST /message, GET /health, GET /agent, POST /discuter"})

        def do_POST(self):
            corps = self.lire_corps()
            if corps is None:
                return self.envoyer(400, {"erreur": "corps JSON invalide"})
            try:
                if self.path == "/message":
                    message = str(corps.get("message", "")).strip()
                    if not message:
                        return self.envoyer(400, {"erreur": "champ \"message\" manquant"})
                    qui = str(corps.get("de") or self.client_address[0])
                    return self.envoyer(200, {"reponse": repondre_a(qui, message[:2000])})
                if self.path == "/discuter":
                    if not str(corps.get("avec", "")).startswith("http"):
                        return self.envoyer(400, {"erreur": "champ \"avec\" : URL de l'autre agent (http://ip:port)"})
                    tours = max(1, min(int(corps.get("tours", 3)), MAX_TOURS))
                    sujet = str(corps.get("sujet") or "la météo de vos villes")
                    return self.envoyer(200, {"echanges": discuter(corps["avec"], sujet, tours)})
            except (requests.RequestException, ValueError, KeyError) as erreur:
                return self.envoyer(502, {"erreur": f"LLM ou agent injoignable : {erreur}"})
            self.envoyer(404, {"erreur": "route inconnue"})

        def lire_corps(self):
            try:
                taille = min(int(self.headers.get("Content-Length", 0)), 64 * 1024)
                contenu = json.loads(self.rfile.read(taille) or b"{}")
                return contenu if isinstance(contenu, dict) else None
            except ValueError:
                return None

        def envoyer(self, code, contenu):
            corps = json.dumps(contenu, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(corps)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(corps)

        def log_message(self, *args):
            pass  # pas de ligne dans la console à chaque requête

    serveur = ThreadingHTTPServer(("0.0.0.0", port), Gestionnaire)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    return serveur
