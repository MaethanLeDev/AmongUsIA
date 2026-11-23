"""Le menu de réglages du joueur : choisir son LLM (modèle du Pi ou API) et tout le reste, sans ouvrir config.json.

Affiché au premier lancement, puis à la demande avec l'option --reglages. Chaque choix est enregistré aussitôt.
config.json reste modifiable à la main : le menu garde les champs qu'il ne connaît pas.
"""
import copy
import getpass
import json
import re
import sys

from ia import GEMINI_MODELE, IA
from installation import (CARACTERES, NOM_MAX, VILLES, choisir_ville, demander, demarrer_ollama, modeles_installes,
                          ollama_de_cette_machine)

OLLAMA_LOCAL = "http://127.0.0.1:11434"
COULEUR = re.compile(r"#[0-9a-fA-F]{6}")
PORT_MAX = 65535
VOTES = [("llm", "llm", "par le LLM"),   # strategie, vote_honnete, ce qu'on affiche
         ("ecart", "llm", "par le calcul (le LLM ne fait que débattre)"),
         ("llm", "calcul", "par le calcul si honnête, par le LLM si espion")]
MEMOIRES = [("faits", "les faits seulement"), ("resume", "les faits + des notes écrites par le LLM")]
METEOS = [("reelle", "température actuelle"), ("historique", "historique, mode difficile (pareil chez tous les joueurs)")]


def choisir(titre, options, actuel=0):
    """Une liste numérotée. Renvoie l'indice choisi ; Entrée garde l'actuel."""
    print(f"\n{titre}")
    for numero, option in enumerate(options, 1):
        print(f"  {numero}. {option}")
    while True:
        reponse = demander("Numéro", str(actuel + 1))
        if reponse.isdecimal() and 1 <= int(reponse) <= len(options):
            return int(reponse) - 1
        print(f"Tape un numéro de 1 à {len(options)}.")


def position(choix, valeur):
    return next((i for i, option in enumerate(choix) if option[0] == valeur), 0)


# --- Le LLM ---------------------------------------------------------------

def regler_llm(config):
    """Les modèles installés d'abord, puis les API. Changer de LLM ne fait pas perdre la clé de l'autre."""
    ollama = config["ollama"]
    url = ollama["url"].rstrip("/")
    while True:
        installes = modeles_installes(url)
        if installes is None:
            installes = demarrer_ollama(url)
        if installes is None:
            passerelle = "" if ollama_de_cette_machine(url) else " (passerelle arrêtée ? lance-la, puis choisis ici « Autre adresse »)"
            print(f"\nOllama ne répond pas sur {url}{passerelle}.")
            installes = []
        connus = {ollama["modele"], f"{ollama['modele']}:latest"}
        local = next((i for i, modele in enumerate(installes) if modele in connus), 0)   # sinon le premier installé
        ou = "installé sur cette machine" if url == OLLAMA_LOCAL else url
        options = [f"{modele}  (Ollama, {ou})" for modele in installes]
        options += ["Gemini (API Google, clé nécessaire)", "Télécharger un autre modèle Ollama",
                    "Autre adresse Ollama (autre machine, ou passerelle vers une API)"]
        gemini, telechargement = len(installes), len(installes) + 1
        if IA(config).fournisseur == "Gemini":
            actuel = gemini
        else:
            actuel = local if installes else telechargement
        choix = choisir("Quel LLM pour ton IA ?", options, actuel)

        if choix < gemini:
            ollama.update(url=url, modele=installes[choix])
            config["fournisseur"] = "ollama"
            return
        if choix == gemini:
            if regler_gemini(config):
                if installes:   # le secours est un modèle déjà installé, pas un téléchargement de plus
                    ollama.update(url=url, modele=installes[local])
                return
        elif choix == telechargement:
            ollama.update(url=url, modele=demander("Nom du modèle, téléchargé au lancement", ollama["modele"]))
            config["fournisseur"] = "ollama"
            return
        else:
            adresse = demander("Adresse d'Ollama", OLLAMA_LOCAL).rstrip("/")
            url = adresse if adresse.startswith(("http://", "https://")) else f"http://{adresse}"


def regler_gemini(config):
    """Renvoie False si on repart sans clé."""
    gemini = dict(config.get("gemini") or {})
    consigne = "Entrée garde la clé enregistrée" if gemini.get("cle_api") else "Entrée pour annuler"
    cle = getpass.getpass(f"Clé API Gemini, rien ne s'affiche quand tu la colles ({consigne}) : ").strip()
    if not cle and not gemini.get("cle_api"):
        return False
    if cle:
        gemini["cle_api"] = cle
    gemini["modele"] = demander("Modèle Gemini", gemini.get("modele") or GEMINI_MODELE)
    config["gemini"], config["fournisseur"] = gemini, "gemini"
    return True


def decrire_llm(config):
    cerveau = IA(config)
    if cerveau.fournisseur == "Ollama":
        ailleurs = "" if cerveau.url == OLLAMA_LOCAL else f", sur {cerveau.url}"
        return f"{cerveau.modele} (Ollama{ailleurs})"
    return f"{cerveau.modele_actif} ({cerveau.fournisseur}, secours : {cerveau.modele})"


# --- Les autres réglages --------------------------------------------------

def indice_vote(config):
    if config.get("strategie") == "ecart":
        return 1
    return 2 if config.get("vote_honnete") == "calcul" else 0


def regler_vote(config):
    choix = choisir("Comment ton IA vote ?", [vote[2] for vote in VOTES], indice_vote(config))
    config["strategie"], config["vote_honnete"], _ = VOTES[choix]


def regler_nom(config):
    interface = config.setdefault("interface", {})
    interface["nom"] = demander("Nom affiché à la table", interface.get("nom") or config["id"])[:NOM_MAX]


def regler_ville(config):
    config["ville"] = choisir_ville(config["ville"])
    if config["ville"] in VILLES:
        config["coordonnees"] = VILLES[config["ville"]]
    else:
        config.pop("coordonnees", None)   # le joueur géocodera la nouvelle ville


def regler_personnalite(config):
    config["personnalite"] = demander("Son caractère, « Tu es… »", config.get("personnalite", "Tu es calme et logique."))


def regler_apparence(config):
    interface = config.setdefault("interface", {})
    archetypes = [arch for arch, _ in CARACTERES]
    actuel = archetypes.index(interface["arch"]) if interface.get("arch") in archetypes else 0
    interface["arch"] = archetypes[choisir("Quel personnage ?", archetypes, actuel)]
    couleurs = interface.setdefault("couleurs", {})
    for partie in ("cheveux", "yeux", "accent"):
        couleur = demander(f"Couleur {partie} en #rrggbb", couleurs.get(partie, "automatique"))
        if COULEUR.fullmatch(couleur):
            couleurs[partie] = couleur
        elif couleur != "automatique":
            print("Couleur ignorée : il faut la forme #1c7ed6.")


def regler_memoire(config):
    actuel = position(MEMOIRES, config.get("memoire"))
    config["memoire"] = MEMOIRES[choisir("Sa mémoire entre les manches ?", [m[1] for m in MEMOIRES], actuel)][0]


def regler_meteo(config):
    actuel = position(METEOS, config.get("meteo"))
    config["meteo"] = METEOS[choisir("Quelle météo ?", [m[1] for m in METEOS], actuel)][0]


def regler_id(config):
    reponse = demander("Identifiant, différent de celui des autres", config["id"])
    if any(c in reponse for c in " /+#"):
        print("Identifiant refusé : ni espace, ni /, ni +, ni #.")
    else:
        config["id"] = reponse


def regler_broker(config):
    broker = config.setdefault("broker", {})
    broker["hote"] = demander("Adresse du broker", broker.get("hote", "amongus.local,10.109.150.215"))


def regler_api(config):
    api = config.setdefault("api", {})
    reponse = demander("Port de l'API de l'agent (0 : pas d'API)", str(api.get("port", 5000)))
    if reponse.isdecimal() and int(reponse) <= PORT_MAX:
        api["port"] = int(reponse)
    else:
        print(f"Port refusé : un nombre de 0 à {PORT_MAX}.")


MENU = [   # ce qu'on affiche, la valeur actuelle, la fonction qui la change
    ("LLM", decrire_llm, regler_llm),
    ("Vote", lambda c: VOTES[indice_vote(c)][2], regler_vote),
    ("Nom", lambda c: c.get("interface", {}).get("nom") or c["id"], regler_nom),
    ("Ville", lambda c: c["ville"], regler_ville),
    ("Caractère", lambda c: c.get("personnalite", "calme et logique"), regler_personnalite),
    ("Apparence", lambda c: c.get("interface", {}).get("arch", "automatique"), regler_apparence),
    ("Mémoire", lambda c: MEMOIRES[position(MEMOIRES, c.get("memoire"))][1], regler_memoire),
    ("Météo", lambda c: METEOS[position(METEOS, c.get("meteo"))][1], regler_meteo),
    ("Identifiant", lambda c: c["id"], regler_id),
    ("Broker", lambda c: c.get("broker", {}).get("hote", "amongus.local"), regler_broker),
    ("Port de l'API", lambda c: c.get("api", {}).get("port", 5000), regler_api),
]


def enregistrer(chemin, config):
    chemin.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        chemin.chmod(0o600)   # le fichier peut contenir une clé d'API
    except OSError as erreur:
        print(f"Droits de {chemin.name} inchangés ({erreur}).")


def modifier(chemin, config, regler_un):
    """Un réglage abandonné en route (Ctrl+C, entrée fermée) ne laisse pas de config à moitié changée."""
    nouvelle = copy.deepcopy(config)
    regler_un(nouvelle)
    enregistrer(chemin, nouvelle)
    config.clear()
    config.update(nouvelle)


def regler(chemin, config, premiere=False):
    """Au premier lancement, le LLM d'abord. Puis le menu, jusqu'à ce qu'on appuie sur Entrée."""
    if sys.stdin is None or not sys.stdin.isatty():
        return   # service systemd : personne pour répondre
    try:
        if premiere:
            modifier(chemin, config, regler_llm)
        while True:
            print(f"\nRéglages de ton IA ({chemin})")
            for numero, (titre, valeur, _) in enumerate(MENU, 1):
                print(f"  {numero:2}. {titre:14} {valeur(config)}")
            reponse = input("Numéro à changer, ou Entrée pour jouer : ").strip()
            if not reponse:
                return
            if reponse.isdecimal() and 1 <= int(reponse) <= len(MENU):
                modifier(chemin, config, MENU[int(reponse) - 1][2])
            else:
                print(f"Tape un numéro de 1 à {len(MENU)}.")
    except EOFError:
        print("\nPas de réponse possible : réglages gardés tels quels.")
    except KeyboardInterrupt:
        sys.exit("\nArrêt : les réglages déjà validés sont enregistrés.")
