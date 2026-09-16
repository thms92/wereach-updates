# -*- coding: utf-8 -*-
"""Garde-fou : le menu et les pages définies doivent coïncider.

C'est l'absence de cette vérification qui a laissé quatre pages
inatteignables pendant deux mois (commit c6035c0).
L'analyse est statique — Streamlit n'est pas exécuté.
"""

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app_advanced.py"


def arbre_app() -> ast.Module:
    return ast.parse(APP.read_text(encoding="utf-8"))


def pages_du_menu(arbre: ast.Module) -> list:
    """Libellés de la constante PAGES — la source de vérité du menu."""
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Assign):
            for cible in noeud.targets:
                if isinstance(cible, ast.Name) and cible.id == "PAGES":
                    return [e.value for e in noeud.value.elts]
    raise AssertionError("Constante PAGES introuvable dans app_advanced.py")


def pages_definies(arbre: ast.Module) -> list:
    """Libellés comparés à `page` dans les branches if/elif."""
    trouves = []
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Compare) and isinstance(noeud.left, ast.Name):
            if noeud.left.id != "page":
                continue
            for comp in noeud.comparators:
                if isinstance(comp, ast.Constant) and isinstance(comp.value, str):
                    trouves.append(comp.value)
    return trouves


@pytest.mark.xfail(
    strict=True,
    reason="4 pages orphelines depuis c6035c0 — résorbé par la Tâche 6 du plan "
           "2026-09-16-refonte-navigation ; retirer ce marqueur à ce moment-là.",
)
def test_toute_page_definie_est_atteignable_depuis_le_menu():
    arbre = arbre_app()
    orphelines = set(pages_definies(arbre)) - set(pages_du_menu(arbre))
    assert orphelines == set()


def test_toute_entree_de_menu_correspond_a_une_page():
    arbre = arbre_app()
    fantomes = set(pages_du_menu(arbre)) - set(pages_definies(arbre))
    assert fantomes == set()


def test_aucun_doublon_dans_le_menu():
    pages = pages_du_menu(arbre_app())
    assert len(pages) == len(set(pages))
