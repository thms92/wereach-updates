# -*- coding: utf-8 -*-
"""La fonctionnalité Templates a été retirée (décision du 2026-09-16).

Ce test empêche sa réintroduction par inadvertance — du code de
persistance qui ne sert plus finit par être relu, maintenu, voire recyclé.
"""

import sqlite3

from database import DatabaseManager


def test_le_gestionnaire_n_expose_plus_de_methodes_template():
    restantes = [n for n in dir(DatabaseManager) if "template" in n.lower()]
    assert restantes == []


def test_une_base_neuve_ne_cree_plus_la_table_templates(tmp_path):
    chemin = tmp_path / "essai.db"
    DatabaseManager(db_file=str(chemin))

    conn = sqlite3.connect(chemin)
    noms = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    conn.close()

    assert "templates" not in noms
    # Les tables utiles restent créées
    assert "profiles" in noms
