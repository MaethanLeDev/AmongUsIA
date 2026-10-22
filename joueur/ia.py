"""Le cerveau d'un joueur : il parle pendant le débat et vote, avec un LLM Ollama.

Tout ce qui se personnalise (modèle, personnalité) vient de config.json.
"""
import json
import re
import statistics

import requests

REGLES = """Tu joues à un jeu de déduction comme le Loup-Garou ou Among Us, assis à une table avec d'autres IA.
Chaque joueur est un capteur météo qui a publié 5 fois la température de sa ville.
L'un des joueurs est un espion : ses températures sont fausses. Les autres doivent le démasquer en débattant, puis voter.

Tu es {nom} (identifiant {id}).
Ta personnalité : {personnalite}

{role}

Façon de parler : en français, comme à l'oral, 1 à 3 phrases courtes. Pas de liste, pas de markdown.
Ne commence pas par ton nom. Appelle les autres joueurs par leur nom et appuie-toi sur leurs chiffres."""

ROLES = {
    "normal": "Ton rôle secret : CAPTEUR HONNÊTE. Tes températures sont vraies. "
              "Une vraie température change très peu en 25 secondes : méfie-toi de celui dont les valeurs "
              "sautent d'une mesure à l'autre ou s'écartent nettement des autres.",
    "espion": "Ton rôle secret : ESPION. Tes températures sont fausses. Ne l'avoue jamais et ne te désigne jamais "
              "comme espion. Justifie tes valeurs (microclimat, capteur au soleil, altitude…) et détourne "
              "les soupçons vers un autre joueur, de façon crédible.",
}

REPLI_PAROLE = "Je préfère écouter les autres avant de me prononcer."
SEUIL_STABLE = 0.5  # °C : une vraie température varie moins que ça en 25 s
# Un petit modèle se trahit (ou s'accuse à tort) facilement : on remplace ces phrases
AVEU = re.compile(r"\bje suis\s+(l['’]\s*|un |le )?espion", re.IGNORECASE)


class Partie:
    """Ce que le joueur sait de la partie en cours."""

    def __init__(self, moi, role):
        self.moi = moi
        self.role = role
        self.participants = []  # ids des joueurs de la partie
        self.noms = {}          # id -> nom affiché
        self.villes = {}        # id -> ville
        self.mesures = {}       # id -> températures, dans l'ordre des manches (y compris les siennes)
        self.debat = []         # (id, texte), dans l'ordre

    def nom(self, id_joueur):
        return self.noms.get(id_joueur) or id_joueur

    def autres(self):
        return [i for i in (self.participants or self.mesures) if i != self.moi]


# --- Analyse des températures --------------------------------------------

def analyser(mesures):
    """Pour chaque joueur : écart moyen à la médiane des autres (°C, signé) et amplitude de ses valeurs."""
    analyse = {}
    for id_joueur, valeurs in mesures.items():
        ecarts = []
        for manche, valeur in enumerate(valeurs):
            autres = [v[manche] for i, v in mesures.items() if i != id_joueur and manche < len(v)]
            if autres:
                ecarts.append(valeur - statistics.median(autres))
        analyse[id_joueur] = {
            "ecart": statistics.mean(ecarts) if ecarts else 0.0,
            "amplitude": max(valeurs) - min(valeurs) if valeurs else 0.0,
        }
    return analyse


def suspect_par_calcul(partie):
    """Méthode sans LLM (jeu de base du TP) : le plus gros écart + la plus grosse amplitude."""
    analyse = analyser(partie.mesures)
    score = {i: abs(a["ecart"]) + a["amplitude"] for i, a in analyse.items() if i in partie.autres()}
    if not score:
        return None, "aucune donnée"
    suspect = max(score, key=score.get)
    return suspect, f"écart {analyse[suspect]['ecart']:+.1f} °C, amplitude {analyse[suspect]['amplitude']:.1f} °C"


def tableau_mesures(partie):
    analyse = analyser(partie.mesures)
    lignes = []
    for id_joueur in partie.participants or partie.mesures:
        valeurs = partie.mesures.get(id_joueur, [])
        if not valeurs:
            lignes.append(f"- {partie.nom(id_joueur)} : aucune mesure")
            continue
        a = analyse[id_joueur]
        moi = " (toi)" if id_joueur == partie.moi else ""
        # Les petits modèles lisent mal les chiffres : on leur traduit l'essentiel en mots
        stabilite = "STABLE" if a["amplitude"] < SEUIL_STABLE else f"INSTABLE, varie de {a['amplitude']:.1f} °C"
        lignes.append(f"- {partie.nom(id_joueur)}{moi}, {partie.villes.get(id_joueur, '?')} : "
                      f"{', '.join(f'{v:.1f}' for v in valeurs)} °C → {stabilite}, "
                      f"écart aux autres {a['ecart']:+.1f} °C")
    return "\n".join(lignes)


def resume_debat(partie):
    if not partie.debat:
        return "Personne n'a encore parlé."
    return "\n".join(f"- {partie.nom(i)} a dit « {texte} »" for i, texte in partie.debat)


def conseil(partie):
    """L'espion reçoit une cible crédible vers qui détourner les soupçons."""
    if partie.role != "espion":
        return ""
    cible, _ = suspect_par_calcul(partie)
    return f"Conseil secret : pour te couvrir, oriente les soupçons vers {partie.nom(cible)}.\n" if cible else ""


# --- Le LLM --------------------------------------------------------------

class IA:
    def __init__(self, config):
        self.id = config["id"]
        self.nom = config.get("interface", {}).get("nom") or self.id
        self.personnalite = config.get("personnalite", "Tu es calme et logique.")
        self.url = config["ollama"]["url"].rstrip("/")
        self.modele = config["ollama"]["modele"]
        self.strategie = config.get("strategie", "llm")

    def _systeme(self, partie):
        return REGLES.format(nom=self.nom, id=self.id, personnalite=self.personnalite, role=ROLES[partie.role])

    def _demander(self, partie, consigne, delai, max_tokens, json_attendu=False):
        contexte = (f"Températures publiées :\n{tableau_mesures(partie)}\n\n"
                    f"Débat jusqu'ici :\n{resume_debat(partie)}\n\n{conseil(partie)}{consigne}")
        corps = {
            "model": self.modele,
            "messages": [{"role": "system", "content": self._systeme(partie)},
                         {"role": "user", "content": contexte}],
            "stream": False,
            "think": False,
            "options": {"temperature": 0.8, "num_ctx": 4096, "num_predict": max_tokens},
        }
        if json_attendu:
            corps["format"] = "json"
        reponse = requests.post(f"{self.url}/api/chat", json=corps, timeout=delai)
        reponse.raise_for_status()
        return reponse.json()["message"]["content"]

    def parler(self, partie, tour, tours, delai):
        consigne = (f"C'est ton tour de parler (tour {tour}/{tours}). Réagis à ce qui vient d'être dit : "
                    "accuse, défends-toi ou pose une question à quelqu'un.")
        try:
            texte = nettoyer(self._demander(partie, consigne, delai, max_tokens=120))
        except requests.RequestException as erreur:
            print(f"  LLM indisponible ({erreur})")
            return REPLI_PAROLE
        if not texte or AVEU.search(texte):
            return REPLI_PAROLE
        return texte

    def voter(self, partie, delai):
        """Renvoie (suspect, raison). Repli sur le calcul si le LLM ne donne pas de réponse exploitable."""
        if self.strategie == "ecart":
            return suspect_par_calcul(partie)

        candidats = {i: partie.nom(i) for i in partie.autres()}
        liste = ", ".join(f"{i} ({nom})" for i, nom in candidats.items())
        consigne = ("Le débat est terminé, c'est l'heure du vote. Qui est l'espion ? Tu ne peux pas voter pour toi. "
                    f"Identifiants possibles : {liste}.\n"
                    'Réponds uniquement en JSON : {"suspect": "<identifiant>", "raison": "<une phrase courte>"}')
        try:
            brut = self._demander(partie, consigne, delai, max_tokens=200, json_attendu=True)
        except requests.RequestException as erreur:
            print(f"  LLM indisponible ({erreur})")
            brut = ""

        suspect, raison = lire_vote(brut, candidats)
        if suspect is None:
            suspect, calcul = suspect_par_calcul(partie)
            raison = f"(réponse du LLM inexploitable, calcul : {calcul})"
        return suspect, raison


def nettoyer(texte):
    texte = re.sub(r"<think>.*?</think>", "", texte, flags=re.DOTALL)
    texte = re.sub(r"^\s*\**[\w\- ]{1,20}\**\s*:\s*", "", texte.strip())  # « Sherlock : … » ou « Mimi : … »
    texte = " ".join(texte.replace("*", "").split()).strip('"« »')
    return texte[:400]


def lire_vote(brut, candidats):
    """Trouve un suspect valide dans la réponse : le JSON d'abord, sinon un id ou un nom cité dans le texte."""
    raison = ""
    try:
        donnees = json.loads(brut)
        suspect, raison = str(donnees.get("suspect", "")), str(donnees.get("raison", ""))
        if suspect in candidats:
            return suspect, raison[:200]
        brut = suspect
    except (ValueError, AttributeError):
        pass  # JSON coupé ou invalide : on cherche un nom dans le texte brut
    # Le nom le plus long d'abord, pour ne pas confondre rpi1 et rpi10
    for id_joueur, nom in sorted(candidats.items(), key=lambda c: -len(c[0])):
        if id_joueur in brut or nom.lower() in brut.lower():
            return id_joueur, raison[:200]
    return None, ""
