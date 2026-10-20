# -*- coding: utf-8 -*-
"""Tutoriel guidé : les étapes et la mémoire « tutoriel vu »."""

import ast
from pathlib import Path

from utils.tutoriel import (ETAPES, TEXTE_BIENVENUE_MAJ, etapes_pour,
                            marquer_vu, tutoriel_a_afficher)

RACINE = Path(__file__).resolve().parents[1]


def _pages_du_menu():
    arbre = ast.parse((RACINE / "app_advanced.py").read_text(encoding="utf-8"))
    for noeud in arbre.body:
        if isinstance(noeud, ast.Assign) and getattr(noeud.targets[0], "id", "") == "PAGES":
            return ast.literal_eval(noeud.value)
    raise AssertionError("PAGES introuvable")


def test_quinze_etapes_dans_l_ordre_du_parcours():
    assert len(ETAPES) == 15
    assert ETAPES[0]["titre"] == "Bienvenue sur We.Reach"
    assert ETAPES[2]["titre"] == "Votre budget du jour"
    assert ETAPES[14]["titre"] == "C'est parti"
    pages = set(_pages_du_menu())
    assert {e["page"] for e in ETAPES if e["page"]} <= pages
    for e in ETAPES:
        assert set(e) == {"page", "cible", "contient", "onglet", "titre", "texte"}


def test_textes_sans_chevron():
    for e in ETAPES:
        assert "<" not in e["titre"] and "<" not in e["texte"]


def test_a_afficher_tant_que_non_vu(tmp_path):
    assert tutoriel_a_afficher(tmp_path)
    marquer_vu(tmp_path)
    assert not tutoriel_a_afficher(tmp_path)
    assert (tmp_path / "tutoriel_vu.txt").exists()


def test_marquer_vu_cree_le_dossier(tmp_path):
    dossier = tmp_path / "config"
    marquer_vu(dossier)
    assert not tutoriel_a_afficher(dossier)


def test_variante_mise_a_jour():
    origine = ETAPES[0]["texte"]
    assert etapes_pour(True)[0]["texte"] == TEXTE_BIENVENUE_MAJ
    assert etapes_pour(False)[0]["texte"] == origine
    assert ETAPES[0]["texte"] == origine


def test_aucune_cible_n_est_un_bouton_d_envoi():
    interdits = ("btn_trouver", "msg_envoyer", "_btn_recuperer", "veille_btn_retirer", "confirmer")
    for e in ETAPES:
        assert not any(i in (e["cible"] or "") for i in interdits), e["titre"]
