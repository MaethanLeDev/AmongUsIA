"""Hook PostToolUse : vérifie chaque fichier que Claude vient de modifier.

- .py   : compilation (erreur de syntaxe → renvoyée à Claude) ; le lint est fait par la CI
- .json : JSON valide
- .js   : node --check (sauf interface/public/vendor/)
- docs/protocole.md : rappelle de répercuter le changement dans tous les modules

Code de sortie 2 = Claude reçoit le message sur stderr et corrige. Bibliothèque standard uniquement.
"""
import json
import py_compile
import shutil
import subprocess
import sys
from pathlib import Path

RAPPEL_PROTOCOLE = (
    "docs/protocole.md a changé : c'est le contrat entre les modules. Répercute le changement dans "
    "joueur/, maitre_du_jeu/, interface/spectacle.js (+ public/ si affiché) et outils/faux_ollama.py si besoin, "
    "puis mets à jour les README concernés et lance /verifier."
)


def main():
    try:
        entree = json.load(sys.stdin)
    except ValueError:
        return 0
    chemin = (entree.get("tool_input") or {}).get("file_path")
    if not chemin:
        return 0
    fichier = Path(chemin)
    if not fichier.is_file():
        return 0
    relatif = fichier.as_posix()

    if fichier.suffix == ".py":
        try:
            py_compile.compile(str(fichier), doraise=True)
        except py_compile.PyCompileError as erreur:
            print(f"Erreur de syntaxe Python dans {fichier.name} :\n{erreur.msg}", file=sys.stderr)
            return 2

    elif fichier.suffix == ".json":
        try:
            json.loads(fichier.read_text(encoding="utf-8"))
        except ValueError as erreur:
            print(f"JSON invalide dans {fichier.name} : {erreur}", file=sys.stderr)
            return 2

    elif fichier.suffix == ".js" and "/vendor/" not in relatif and shutil.which("node"):
        resultat = subprocess.run(["node", "--check", str(fichier)], capture_output=True, text=True, encoding="utf-8")
        message = resultat.stderr
        # Un vieux Node (< 22) ne reconnaît pas les modules ES de public/ : ce n'est pas une vraie erreur
        if resultat.returncode and "Cannot use import statement" not in message and "export" not in message:
            print(f"Erreur de syntaxe JavaScript dans {fichier.name} :\n{message}", file=sys.stderr)
            return 2

    elif relatif.endswith("docs/protocole.md"):
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                                 "additionalContext": RAPPEL_PROTOCOLE}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
