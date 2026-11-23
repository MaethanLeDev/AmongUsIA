"""Simulation (simulation.py) : configs des joueurs lancés, et option --bots pour compléter une vraie partie."""
import argparse

import pytest
import simulation


def arguments(**reglages):
    valeurs = {"bots": False, "broker": None, "ollama": None, "modele": "qwen3:0.6b", "resume": False}
    return argparse.Namespace(**{**valeurs, **reglages})


def test_simulation_une_ia_sur_quatre_vote_par_calcul():
    strategies = [simulation.config_joueur(i, arguments())["strategie"] for i in range(8)]

    assert strategies == ["ecart", "llm", "llm", "llm", "ecart", "llm", "llm", "llm"]


def test_bots_votent_tous_par_llm():
    args = arguments(bots=True, broker="amongus.local")

    assert {simulation.config_joueur(i, args)["strategie"] for i in range(8)} == {"llm"}


def test_bots_identifiants_distincts_des_simulations():
    args = arguments(bots=True, broker="amongus.local")

    assert [simulation.config_joueur(i, args)["id"] for i in range(3)] == ["bot1", "bot2", "bot3"]


def test_bots_rejoignent_le_broker_donne_avec_le_vrai_llm():
    args = arguments(bots=True, broker="amongus.local", ollama="http://127.0.0.1:11434", modele="qwen3:4b")

    config = simulation.config_joueur(0, args)

    assert config["broker"]["hote"] == "amongus.local"
    assert config["ollama"] == {"url": "http://127.0.0.1:11434", "modele": "qwen3:4b"}


def test_bots_sans_broker_refuses(monkeypatch):
    monkeypatch.setattr("sys.argv", ["simulation.py", "--bots"])

    with pytest.raises(SystemExit):
        simulation.main()
