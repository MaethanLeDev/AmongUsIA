"""Le cerveau d'un joueur : il débat, vote et se souvient des manches passées, avec un LLM Ollama.

Tout ce qui se personnalise (modèle, personnalité, mémoire) vient de config.json.
"""
import json
import re
import statistics

import requests

REGLES = """Tu joues à un jeu de déduction comme le Loup-Garou ou Among Us, assis à une table avec d'autres IA.
Chaque joueur est un capteur météo : à chaque manche, il publie 5 fois la température de sa ville (des villes voisines).
L'un des joueurs est un espion : ses températures sont fausses. À chaque manche, on débat puis on vote :
le joueur le plus désigné est éliminé. Si c'est l'espion, les capteurs gagnent. Sinon la partie continue,
jusqu'à ce qu'il ne reste que deux joueurs : l'espion a alors gagné.

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

AGENT = """Tu es {nom}, un agent conversationnel qui tourne sur un Raspberry Pi avec le modèle {modele}.
Ta personnalité : {personnalite}
Réponds en français, en 1 à 4 phrases, sans markdown. Tu te souviens de toute la conversation."""

REPLI_PAROLE = "Je préfère écouter les autres avant de me prononcer."
SEUIL_STABLE = 0.5  # °C : une vraie température varie moins que ça en 25 s
CITATION = 110      # caractères gardés de chaque réplique d'une manche passée
# Un petit modèle se trahit (ou s'accuse à tort) facilement : on remplace ces phrases
AVEU = re.compile(r"\bje suis\s+(l['’]\s*|un |le )?espion", re.IGNORECASE)


class Manche:
    def __init__(self, numero):
        self.numero = numero
        self.mesures = {}     # id -> températures, dans l'ordre des échanges (y compris les siennes)
        self.debat = []       # (id, texte), dans l'ordre
        self.votes = {}       # votant -> suspect
        self.verdict = None   # message iot/partie/verdict


class Partie:
    """Ce que le joueur sait de la partie en cours, manche après manche."""

    def __init__(self, id_partie, moi, role):
        self.id = id_partie
        self.moi = moi
        self.role = role
        self.participants = []  # ids des joueurs de la partie, éliminés compris
        self.vivants = []
        self.numero = 0         # manche en cours
        self.manches = {}       # numéro -> Manche
        self.souvenirs = {}     # numéro -> notes écrites par le LLM à la fin de la manche ("memoire": "resume")
        self.noms = {}          # id -> nom affiché
        self.villes = {}        # id -> ville

    def manche(self, numero=None):
        numero = numero or self.numero
        return self.manches.setdefault(numero, Manche(numero))

    def nom(self, id_joueur):
        return self.noms.get(id_joueur) or id_joueur

    def autres(self):
        return [i for i in (self.vivants or self.participants or self.manche().mesures) if i != self.moi]

    def elimines(self):
        return [i for i in self.participants if i not in self.vivants]


# --- Analyse des températures --------------------------------------------

def analyser(mesures):
    """Pour chaque joueur : écart moyen à la médiane des autres (°C, signé) et amplitude de ses valeurs."""
    analyse = {}
    for id_joueur, valeurs in mesures.items():
        ecarts = []
        for echange, valeur in enumerate(valeurs):
            autres = [v[echange] for i, v in mesures.items() if i != id_joueur and echange < len(v)]
            if autres:
                ecarts.append(valeur - statistics.median(autres))
        analyse[id_joueur] = {
            "ecart": statistics.mean(ecarts) if ecarts else 0.0,
            "amplitude": max(valeurs) - min(valeurs) if valeurs else 0.0,
        }
    return analyse


def suspect_par_calcul(partie):
    """Méthode sans LLM (jeu de base du TP) : le plus gros écart + la plus grosse amplitude, parmi les vivants."""
    mesures = {i: v for i, v in partie.manche().mesures.items() if v and (i in partie.vivants or not partie.vivants)}
    analyse = analyser(mesures)
    score = {i: abs(a["ecart"]) + a["amplitude"] for i, a in analyse.items() if i in partie.autres()}
    if not score:
        return None, "aucune donnée"
    suspect = max(score, key=score.get)
    return suspect, f"écart {analyse[suspect]['ecart']:+.1f} °C, amplitude {analyse[suspect]['amplitude']:.1f} °C"


def tableau_mesures(partie):
    mesures = partie.manche().mesures
    analyse = analyser({i: v for i, v in mesures.items() if v and (i in partie.vivants or not partie.vivants)})
    lignes = []
    for id_joueur in partie.vivants or mesures:
        valeurs = mesures.get(id_joueur, [])
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
    debat = partie.manche().debat
    if not debat:
        return "Personne n'a encore parlé."
    return "\n".join(f"- {partie.nom(i)} a dit « {texte} »" for i, texte in debat)


def faits_manche(partie, numero):
    """Ce qu'il faut retenir d'une manche terminée : des faits sûrs, calculés sans LLM."""
    manche = partie.manches.get(numero)
    if manche is None:
        return []
    lignes = [f"Manche {numero} :"]
    verdict = manche.verdict or {}
    votes = verdict.get("votes") or manche.votes
    if verdict.get("elimine"):
        elimine = verdict["elimine"]
        nature = "C'ÉTAIT l'espion" if verdict.get("etait_espion") else "il n'était PAS l'espion"
        lignes.append(f"- {partie.nom(elimine)} a été éliminé avec {verdict.get('compte', {}).get(elimine, '?')} vote(s) : "
                      f"{nature}.")
    elif verdict:
        lignes.append("- Égalité aux votes : personne n'a été éliminé.")
    if votes:
        lignes.append("- Votes : " + ", ".join(f"{partie.nom(a)} contre {partie.nom(s)}" for a, s in votes.items()) + ".")
    derniers = dict(manche.debat)  # la dernière réplique de chacun
    for id_joueur, texte in derniers.items():
        coupe = texte if len(texte) <= CITATION else texte[:CITATION].rsplit(" ", 1)[0] + "…"
        lignes.append(f"- {partie.nom(id_joueur)} a dit : « {coupe} »")
    if numero in partie.souvenirs:
        lignes.append(f"- Tes notes : {partie.souvenirs[numero]}")
    return lignes


def memoire(partie):
    """Les manches précédentes, pour que l'IA s'en souvienne au début de la suivante."""
    lignes = []
    for numero in sorted(n for n in partie.manches if n < partie.numero):
        lignes += faits_manche(partie, numero)
    return "\n".join(lignes)


def situation(partie):
    vivants = ", ".join(partie.nom(i) + (" (toi)" if i == partie.moi else "") for i in partie.vivants)
    texte = f"Manche {partie.numero}. Joueurs encore en jeu : {vivants}."
    if partie.elimines():
        texte += f" Éliminés : {', '.join(partie.nom(i) for i in partie.elimines())}."
    return texte


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
        self.memoire = config.get("memoire", "faits")

    def discuter(self, messages, delai, max_tokens, json_attendu=False, temperature=0.8):
        """Un appel à Ollama (/api/chat). Lève requests.RequestException si Ollama ne répond pas."""
        messages = [dict(m) for m in messages]
        if self.modele.lower().startswith("qwen3"):
            # Un vieux Ollama ignore "think": false ; qwen3 comprend aussi cette consigne écrite
            messages[-1]["content"] += " /no_think"
        corps = {
            "model": self.modele,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": {"temperature": temperature, "num_ctx": 4096, "num_predict": max_tokens},
        }
        if json_attendu:
            corps["format"] = "json"
        reponse = requests.post(f"{self.url}/api/chat", json=corps, timeout=delai)
        reponse.raise_for_status()
        return reponse.json()["message"]["content"]

    def disponible(self):
        try:
            return requests.get(f"{self.url}/api/tags", timeout=2).ok
        except requests.RequestException:
            return False

    # --- Le jeu ---

    def _systeme(self, partie):
        return REGLES.format(nom=self.nom, id=self.id, personnalite=self.personnalite, role=ROLES[partie.role])

    def _demander(self, partie, consigne, delai, max_tokens, json_attendu=False, temperature=0.8):
        passe = memoire(partie)
        contexte = (f"{situation(partie)}\n\n"
                    + (f"Ce qui s'est passé aux manches précédentes :\n{passe}\n\n" if passe else "")
                    + f"Températures publiées pendant cette manche :\n{tableau_mesures(partie)}\n\n"
                    f"Débat de cette manche jusqu'ici :\n{resume_debat(partie)}\n\n{conseil(partie)}{consigne}")
        messages = [{"role": "system", "content": self._systeme(partie)}, {"role": "user", "content": contexte}]
        return self.discuter(messages, delai, max_tokens, json_attendu, temperature)

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
        """Renvoie (suspect, raison, calcul). calcul = le suspect de la méthode sans LLM, pour comparer (extension du TP).
        Repli sur le calcul si le LLM ne donne pas de réponse exploitable."""
        calcul, detail = suspect_par_calcul(partie)
        if self.strategie != "llm":
            return calcul, detail, calcul

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
            suspect, raison = calcul, f"(réponse du LLM inexploitable, calcul : {detail})"
        return suspect, raison, calcul

    def resumer(self, partie, delai):
        """Notes personnelles sur la manche qui vient de finir ("memoire": "resume"). None si le LLM échoue."""
        faits = "\n".join(faits_manche(partie, partie.numero))
        contexte = (f"{situation(partie)}\n\nTempératures de la manche :\n{tableau_mesures(partie)}\n\n"
                    f"Débat :\n{resume_debat(partie)}\n\nRésultat :\n{faits}\n\n"
                    "La manche est terminée. Écris pour toi-même deux phrases de notes : qui te paraît suspect "
                    "et pourquoi, et qui te paraît fiable. Reste fidèle à ce qui s'est vraiment passé.")
        messages = [{"role": "system", "content": self._systeme(partie)}, {"role": "user", "content": contexte}]
        try:
            texte = nettoyer(self.discuter(messages, delai, max_tokens=120, temperature=0.3))
        except requests.RequestException as erreur:
            print(f"  LLM indisponible pour les notes ({erreur})")
            return None
        return texte or None

    # --- L'agent conversationnel (TP « RPi & Ollama ») ---

    def repondre(self, historique, message, delai=120):
        """Réponse libre à un message, en se souvenant de l'historique [{"role", "content"}, ...]."""
        systeme = AGENT.format(nom=self.nom, modele=self.modele, personnalite=self.personnalite)
        messages = [{"role": "system", "content": systeme}, *historique, {"role": "user", "content": message}]
        return nettoyer(self.discuter(messages, delai, max_tokens=200), limite=800)


def nettoyer(texte, limite=400):
    texte = re.sub(r"<think>.*?(</think>|$)", "", texte, flags=re.DOTALL)  # réflexion, même coupée en route
    texte = re.sub(r"^\s*\**[\w\- ]{1,20}\**\s*:\s*", "", texte.strip())  # « Sherlock : … » ou « Mimi : … »
    texte = " ".join(texte.replace("*", "").split()).strip('"« »')
    return texte[:limite]


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
