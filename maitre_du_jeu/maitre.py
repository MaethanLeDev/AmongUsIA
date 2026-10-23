"""Maître du jeu : l'arbitre de la partie.

Il inscrit les joueurs, tire l'espion, puis enchaîne les manches :
mesures -> débat (chacun son tour) -> vote -> verdict (un joueur éliminé, ou personne),
jusqu'à ce que l'espion soit éliminé ou qu'il ne reste que deux joueurs.

Usage : uv run maitre_du_jeu/maitre.py [--auto 30] [--tp]
Protocole : docs/protocole.md
"""
import argparse
import json
import random
import sys
import threading
import time
from collections import Counter
from pathlib import Path

import paho.mqtt.client as mqtt

DUREE_ECHANGE = 5   # secondes entre deux températures, fixé par le sujet
MAX_JOUEURS = 12    # nombre de sièges autour de la table de l'interface
STATS_PAR_DEFAUT = Path(__file__).with_name("stats.json")


class FinDePartie(Exception):
    """Levée quand la partie s'arrête avant son terme (espion parti, plus assez de joueurs)."""

    def __init__(self, gagnant, raison):
        super().__init__(raison)
        self.gagnant, self.raison = gagnant, raison


class MaitreDuJeu:
    def __init__(self, reglages):
        self.reglages = reglages
        self.cond = threading.Condition()  # protège l'état ci-dessous et réveille les phases en attente
        self.joueurs = {}          # id -> message de présence, joueurs en ligne, dans l'ordre d'arrivée
        self.arrivees = 0          # compteur d'arrivées : relance le compte à rebours de l'inscription
        self.lancer = False        # Entrée a été pressée
        self.partie = None         # id de la partie en cours
        self.espion = None
        self.participants = []     # joueurs de la partie, éliminés compris
        self.vivants = []
        self.elimines = []         # [{"id": ..., "manche": ...}]
        self.manche = 0
        self.manches_max = 0
        self.mesures = Counter()   # id -> nombre de températures reçues pendant la manche
        self.parole = None         # id du joueur qui a la parole
        self.reponse = None        # ce qu'il a dit
        self.vote_ouvert = False
        self.votes = {}            # votant -> message de vote
        self.stats = charger_stats(reglages.stats)

        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="maitre-du-jeu")
        # Si le maître plante, le broker prévient tout le monde à sa place
        self.client.will_set("iot/partie/etat", json.dumps({"etat": "arret"}), qos=1, retain=True)
        # Une erreur dans un callback est affichée, sans arrêter le thread réseau (sinon on n'entend plus rien)
        self.client.suppress_exceptions = True
        self.client.enable_logger()
        self.client.on_connect = self._on_connect
        self.client.message_callback_add("iot/joueurs/+", self._on_presence)
        self.client.message_callback_add("iot/capteurs/+/temperature", self._on_temperature)
        self.client.message_callback_add("iot/chat/+", self._on_chat)
        self.client.message_callback_add("iot/votes/+", self._on_vote)
        self.broker = connecter(self.client, reglages.broker, reglages.port)
        self.client.loop_start()

    # --- Réception MQTT -------------------------------------------------

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        print(f"Connecté au broker {self.broker} ({reason_code})")
        client.subscribe([("iot/joueurs/+", 1), ("iot/capteurs/+/temperature", 0),
                          ("iot/chat/+", 1), ("iot/votes/+", 1)])
        self.publier("iot/partie/stats", self.stats, retain=True)

    def _on_presence(self, client, userdata, msg):
        id_joueur = expediteur(msg)
        presence = lire_json(msg.payload)
        with self.cond:
            if presence.get("en_ligne"):
                nouveau = id_joueur not in self.joueurs
                self.joueurs[id_joueur] = presence
                if nouveau:
                    self.arrivees += 1
                    print(f"  + {decrire(id_joueur, presence)}")
                    if id_joueur in self.vivants:
                        # Un joueur qui redémarre en pleine partie a perdu son rôle : on le lui renvoie
                        self.envoyer_role(id_joueur)
            elif id_joueur in self.joueurs:
                print(f"  - {self.nom(id_joueur)} est parti")
                del self.joueurs[id_joueur]
            self.cond.notify_all()

    def _on_temperature(self, client, userdata, msg):
        mesure = lire_json(msg.payload)
        with self.cond:
            id_joueur = msg.topic.split("/")[2]
            if id_joueur in self.vivants and self.de_cette_manche(mesure):
                self.mesures[id_joueur] += 1
                self.cond.notify_all()

    def _on_chat(self, client, userdata, msg):
        texte = lire_json(msg.payload).get("text")
        with self.cond:
            # On n'écoute que le joueur qui a la parole : les autres attendent leur tour
            if expediteur(msg) == self.parole and isinstance(texte, str) and texte.strip():
                self.reponse = texte.strip()
                self.cond.notify_all()

    def _on_vote(self, client, userdata, msg):
        votant = expediteur(msg)
        vote = lire_json(msg.payload)
        suspect = vote.get("suspect")
        with self.cond:
            if not self.vote_ouvert or votant not in self.vivants or votant in self.votes:
                return
            if not self.de_cette_manche(vote) or suspect not in self.vivants or suspect == votant:
                print(f"  Vote invalide de {self.nom(votant)} : {suspect!r}")
                return
            self.votes[votant] = vote
            print(f"  🗳  {self.nom(votant)} vote contre {self.nom(suspect)}")
            self.cond.notify_all()

    # --- Outils ---------------------------------------------------------

    def publier(self, topic, contenu, retain=False):
        return self.client.publish(topic, json.dumps(contenu, ensure_ascii=False), qos=1, retain=retain)

    def publier_etat(self, etat, fin=None, **champs):
        contenu = {"etat": etat, "partie": self.partie, "manche": self.manche, "manches_max": self.manches_max,
                   "joueurs": self.participants, "vivants": self.vivants, "elimines": self.elimines,
                   "fin": fin, **champs}
        self.publier("iot/partie/etat", contenu, retain=True)

    def envoyer_role(self, id_joueur):
        role = "espion" if id_joueur == self.espion else "normal"
        self.publier(f"iot/role/{id_joueur}", {"role": role, "partie": self.partie})

    def de_cette_manche(self, message):
        """Un message d'une partie ou d'une manche précédente (en retard) ne compte pas."""
        return message.get("partie", self.partie) == self.partie and message.get("manche", self.manche) == self.manche

    def nom(self, id_joueur):
        return self.joueurs.get(id_joueur, {}).get("nom") or id_joueur

    def vivants_en_ligne(self):
        return [i for i in self.vivants if i in self.joueurs]

    def abandon(self):
        return self.espion not in self.joueurs or len(self.vivants_en_ligne()) < 2

    def controler(self):
        """Arrête la partie si l'espion est parti ou s'il ne reste plus assez de joueurs en ligne."""
        with self.cond:
            if self.espion not in self.joueurs:
                raise FinDePartie("capteurs", "l'espion a quitté la partie")
            if len(self.vivants_en_ligne()) < 2:
                raise FinDePartie(None, "plus assez de joueurs en ligne")

    def attendre(self, condition, delai):
        """Attend que condition() soit vraie, au plus delai secondes. Renvoie False si le délai expire."""
        with self.cond:
            fini = self.cond.wait_for(lambda: condition() or self.abandon(), delai)
        self.controler()
        return fini

    def ecouter_clavier(self):
        try:
            while True:
                input()
                with self.cond:
                    self.lancer = True
                    self.cond.notify_all()
        except EOFError:
            pass  # lancé sans terminal (service) : seul --auto démarre les parties

    # --- Inscription ----------------------------------------------------

    def inscription(self):
        """Attend les joueurs. La partie démarre sur Entrée, ou toute seule avec --auto."""
        r = self.reglages
        with self.cond:
            self.partie, self.espion, self.participants, self.vivants, self.elimines = None, None, [], [], []
            self.manche, self.lancer, self.parole, self.vote_ouvert = 0, False, None, False
        lancement = f"Entrée pour lancer, ou automatiquement {r.auto} s après le dernier arrivé" if r.auto \
            else "Entrée pour lancer"
        print(f"\n=== INSCRIPTION === ({r.min_joueurs} à {r.max_joueurs} joueurs) — {lancement}")
        debut, arrivees, publie = None, -1, None
        while True:
            with self.cond:
                inscrits = list(self.joueurs)[:r.max_joueurs]
                assez = len(inscrits) >= r.min_joueurs
                if self.lancer:
                    self.lancer = False
                    if assez:
                        return inscrits
                    print(f"Seulement {len(inscrits)} joueur(s) : {', '.join(inscrits) or 'personne'}")
                if r.auto and assez:
                    if debut is None or self.arrivees != arrivees:
                        debut = time.time() + r.auto  # chaque arrivée laisse le temps aux autres de s'asseoir
                    if time.time() >= debut:
                        return inscrits
                else:
                    debut = None
                arrivees = self.arrivees
            if publie != (debut, len(inscrits)):
                publie = (debut, len(inscrits))
                self.publier("iot/partie/etat", {"etat": "inscription", "min": r.min_joueurs, "max": r.max_joueurs,
                                                 "debut": debut}, retain=True)
                if debut:
                    print(f"  Lancement dans {debut - time.time():.0f} s ({len(inscrits)} joueurs)")
            with self.cond:
                self.cond.wait(1)

    # --- Partie ---------------------------------------------------------

    def jouer(self, inscrits):
        r = self.reglages
        with self.cond:
            self.partie = int(time.time())
            self.espion = random.choice(inscrits)
            self.participants, self.vivants, self.elimines = list(inscrits), list(inscrits), []
            self.manches_max = r.manches_max or max(1, len(inscrits) - 1)
        print(f"\n######## PARTIE {self.partie} : {', '.join(self.nom(i) for i in inscrits)}")
        print(f"Espion : {self.nom(self.espion)} (chut). {self.manches_max} manche(s) au plus.")
        for id_joueur in inscrits:
            self.envoyer_role(id_joueur)

        verdict = None
        try:
            while True:
                self.manche += 1
                print(f"\n======== MANCHE {self.manche}/{self.manches_max} — "
                      f"vivants : {', '.join(self.nom(i) for i in self.vivants)}")
                self.phase_mesures()
                self.phase_debat()
                self.phase_vote()
                verdict = self.phase_verdict()
                gagnant, raison = self.issue(verdict)
                self.pause_verdict(verdict)
                if gagnant:
                    break
        except FinDePartie as fin:
            gagnant, raison = fin.gagnant, fin.raison
        self.annoncer(gagnant, raison, verdict)
        time.sleep(self.reglages.pause_fin)  # les spectateurs découvrent l'espion avant la partie suivante

    def phase_mesures(self):
        self.controler()
        echanges = self.reglages.echanges
        delai = echanges * DUREE_ECHANGE + 15
        print(f"\n=== MESURES === ({echanges} échanges de {DUREE_ECHANGE} s)")
        with self.cond:
            self.mesures.clear()
        self.publier_etat("mesures", fin=time.time() + delai, echanges=echanges)
        if not self.attendre(lambda: all(self.mesures[i] >= echanges for i in self.vivants_en_ligne()), delai):
            print("  Certains capteurs n'ont pas fini leurs mesures, on continue.")

    def phase_debat(self):
        r = self.reglages
        if r.tours <= 0:
            return
        ordre = random.sample(self.vivants, len(self.vivants))
        print(f"\n=== DÉBAT === ({r.tours} tours, {r.delai_parole} s max par prise de parole)")
        self.publier_etat("debat", tours=r.tours)
        for tour in range(1, r.tours + 1):
            print(f"--- Tour {tour}/{r.tours} ---")
            for rang, id_joueur in enumerate(ordre, start=1):
                self.controler()
                if id_joueur not in self.joueurs:
                    continue
                with self.cond:
                    self.parole, self.reponse = id_joueur, None
                self.publier("iot/partie/parole", {
                    "partie": self.partie, "manche": self.manche, "joueur": id_joueur, "tour": tour,
                    "tours": r.tours, "rang": rang, "sur": len(ordre), "delai": r.delai_parole,
                    "fin": time.time() + r.delai_parole})
                self.attendre(lambda: self.reponse is not None or self.parole not in self.joueurs, r.delai_parole)
                texte = self.reponse or ""
                print(f"  {self.nom(id_joueur)} : {texte or '(silence)'}")
                # Les spectateurs lisent la bulle avant le suivant : plus le message est long, plus on attend
                time.sleep(r.pause + min(6, len(texte) / 50))
        with self.cond:
            self.parole = None

    def phase_vote(self):
        self.controler()
        delai = self.reglages.delai_vote
        print(f"\n=== VOTE === ({delai} s max)")
        with self.cond:
            self.votes, self.vote_ouvert = {}, True
        self.publier_etat("vote", fin=time.time() + delai)
        try:
            if not self.attendre(lambda: all(i in self.votes for i in self.vivants_en_ligne()), delai):
                print("  Temps écoulé : certains joueurs n'ont pas voté.")
        finally:
            with self.cond:
                self.vote_ouvert = False

    def phase_verdict(self):
        with self.cond:
            votes = {votant: vote["suspect"] for votant, vote in self.votes.items()}
            compte = Counter(votes.values())
            classement = compte.most_common()
            elimine, egalite = None, False
            if classement:
                premier, nb = classement[0]
                egalite = len(classement) > 1 and classement[1][1] == nb
                majorite = nb > len(self.vivants) / 2
                if not egalite and (majorite or not self.reglages.majorite):
                    elimine = premier
            self.compter_votes(self.votes.values())
            if elimine:
                self.vivants.remove(elimine)
                self.elimines.append({"id": elimine, "manche": self.manche})

        verdict = {"partie": self.partie, "manche": self.manche, "votes": votes, "compte": dict(compte),
                   "elimine": elimine, "egalite": egalite,
                   "etait_espion": (elimine == self.espion) if elimine else None}
        self.publier("iot/partie/verdict", verdict)

        print("\n=== VERDICT ===")
        for suspect, nb in classement:
            print(f"  {self.nom(suspect)} : {nb} vote(s)")
        if elimine:
            print(f"  {self.nom(elimine)} est éliminé·e : {'c’était l’espion !' if verdict['etait_espion'] else 'innocent·e.'}")
        else:
            print("  Égalité : personne n'est éliminé." if egalite else "  Personne n'est éliminé.")
        return verdict

    def issue(self, verdict):
        """(gagnant, raison) si la partie est finie après ce verdict, (None, "") sinon."""
        if verdict["etait_espion"]:
            return "capteurs", "l'espion a été éliminé"
        if len(self.vivants) <= 2:
            return "espion", "il ne reste que deux joueurs"
        if self.manche >= self.manches_max:
            return "espion", "l'espion a tenu jusqu'à la dernière manche"
        return None, ""

    def pause_verdict(self, verdict):
        """Le temps de l'animation d'élimination, et pour que chaque IA mette à jour sa mémoire."""
        pause = self.reglages.pause_verdict
        self.publier_etat("verdict", fin=time.time() + pause, elimine=verdict["elimine"])
        time.sleep(pause)

    def annoncer(self, gagnant, raison, verdict):
        verdict = verdict or {}
        compte = Counter(verdict.get("votes", {}).values())
        designe = verdict.get("elimine") or (compte.most_common(1)[0][0] if compte else None)
        self.publier("iot/partie/resultat", {
            "partie": self.partie, "espion": self.espion, "designe": designe, "votes": verdict.get("votes", {}),
            "gagnant": gagnant, "raison": raison, "manches": self.manche, "elimines": self.elimines}, retain=True)
        if gagnant:
            self.stats["parties"] += 1
            self.stats["victoires"][gagnant] += 1
        sauver_stats(self.stats, self.reglages.stats)
        self.publier("iot/partie/stats", self.stats, retain=True)
        self.publier("iot/partie/etat", {"etat": "fini", "partie": self.partie, "gagnant": gagnant}, retain=True)

        print("\n=== RÉSULTAT ===")
        print(f"  L'espion était {self.nom(self.espion)}. "
              + (f"Victoire : {gagnant.upper()} ({raison})." if gagnant else f"Partie annulée ({raison})."))
        v = self.stats["votes"]
        print(f"  Votes justes depuis le début — LLM : {pourcentage(v['llm'])}, calcul : {pourcentage(v['calcul'])}")

    def compter_votes(self, votes):
        """Extension du TP : le LLM vote-t-il mieux que la méthode de calcul ?"""
        for vote in votes:
            if vote.get("strategie") == "llm":
                self.stats["votes"]["llm"]["total"] += 1
                self.stats["votes"]["llm"]["justes"] += vote["suspect"] == self.espion
            if vote.get("calcul"):
                self.stats["votes"]["calcul"]["total"] += 1
                self.stats["votes"]["calcul"]["justes"] += vote["calcul"] == self.espion

    def fermer(self):
        # Une déconnexion propre ne déclenche pas le Last Will : on annonce l'arrêt nous-mêmes
        try:
            self.publier("iot/partie/etat", {"etat": "arret"}, retain=True).wait_for_publish(2)
        except (RuntimeError, ValueError):
            pass  # broker déjà perdu : le Last Will s'en chargera
        self.client.loop_stop()
        self.client.disconnect()


def connecter(client, hotes, port):
    """Se connecte au premier broker joignable de la liste "amongus.local,10.109.150.215"."""
    for hote in (h.strip() for h in hotes.split(",") if h.strip()):
        try:
            client.connect(hote, port)
            return hote
        except OSError as erreur:
            print(f"Broker {hote}:{port} injoignable ({erreur})")
    sys.exit("Aucun broker joignable : vérifie --broker et que le broker est lancé (voir broker/README.md).")


def charger_stats(fichier):
    vides = {"parties": 0, "victoires": {"capteurs": 0, "espion": 0},
             "votes": {"llm": {"total": 0, "justes": 0}, "calcul": {"total": 0, "justes": 0}}}
    try:
        stats = json.loads(Path(fichier).read_text(encoding="utf-8"))
        return stats if stats.keys() == vides.keys() else vides
    except (OSError, ValueError):
        return vides


def sauver_stats(stats, fichier):
    try:
        Path(fichier).write_text(json.dumps(stats, indent=2), encoding="utf-8")
    except OSError as erreur:
        print(f"  Statistiques non sauvegardées ({erreur})")


def pourcentage(compteur):
    if not compteur["total"]:
        return "aucun vote"
    return f"{compteur['justes']}/{compteur['total']} ({100 * compteur['justes'] / compteur['total']:.0f} %)"


def expediteur(msg):
    return msg.topic.split("/")[-1]


def decrire(id_joueur, presence):
    details = ", ".join(str(presence[c]) for c in ("ville", "modele") if presence.get(c))
    nom = presence.get("nom") or id_joueur
    return f"{nom} [{id_joueur}]" + (f" ({details})" if details else "")


def lire_json(payload):
    try:
        contenu = json.loads(payload)
        return contenu if isinstance(contenu, dict) else {}
    except ValueError:
        return {}


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)  # console Windows : pas de plantage sur un emoji
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Maître du jeu de l'espion")
    parser.add_argument("--broker", default="amongus.local,10.109.150.215",
                        help="adresse du broker MQTT (plusieurs, séparées par des virgules, essayées dans l'ordre)")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--min-joueurs", type=int, default=3)
    parser.add_argument("--max-joueurs", type=int, default=MAX_JOUEURS)
    parser.add_argument("--auto", type=int, default=30,
                        help="lance la partie N s après le dernier arrivé dès qu'il y a assez de joueurs (0 : Entrée seulement)")
    parser.add_argument("--echanges", type=int, default=5, help="températures publiées par manche (5 dans le sujet)")
    parser.add_argument("--tours", type=int, default=2, help="tours de parole du débat (0 : pas de débat)")
    parser.add_argument("--delai-parole", type=int, default=90,
                        help="secondes max pour une prise de parole (un gros modèle est lent sur un Pi)")
    parser.add_argument("--pause", type=float, default=2, help="secondes entre deux prises de parole, plus le temps de lecture")
    parser.add_argument("--delai-vote", type=int, default=120)
    parser.add_argument("--pause-verdict", type=float, default=12, help="secondes après le verdict (animation, mémoire)")
    parser.add_argument("--pause-fin", type=float, default=20, help="secondes d'affichage du résultat avant la partie suivante")
    parser.add_argument("--manches-max", type=int, default=0, help="0 : nombre de joueurs - 1")
    parser.add_argument("--majorite", action="store_true", help="éliminer seulement à la majorité stricte (règle du TP)")
    parser.add_argument("--stats", default=STATS_PAR_DEFAUT, help="fichier où cumuler les statistiques LLM / calcul")
    parser.add_argument("--tp", action="store_true", help="jeu de base du TP : une manche, pas de débat, majorité stricte")
    reglages = parser.parse_args()
    reglages.max_joueurs = max(2, min(reglages.max_joueurs, MAX_JOUEURS))
    if reglages.tp:
        reglages.manches_max, reglages.tours, reglages.majorite = 1, 0, True

    maitre = MaitreDuJeu(reglages)
    threading.Thread(target=maitre.ecouter_clavier, daemon=True).start()
    try:
        while True:
            maitre.jouer(maitre.inscription())
    except KeyboardInterrupt:
        print("\nArrêt du maître du jeu.")
    finally:
        maitre.fermer()


if __name__ == "__main__":
    main()
