# -*- coding: utf-8 -*-
"""Une mise à jour de profil n'efface jamais une valeur déjà connue."""

import sqlite3

from database import DatabaseManager

URL = "https://www.linkedin.com/in/ana-test"


def _profil(db, url):
    con = sqlite3.connect(db.db_file)
    try:
        poste, entreprise, ecole, localisation = con.execute(
            "SELECT poste, entreprise, ecole, localisation FROM profiles WHERE url = ?",
            (url,)).fetchone()
    finally:
        con.close()
    return {"poste": poste, "entreprise": entreprise,
            "ecole": ecole, "localisation": localisation}


def test_mise_a_jour_vide_garde_l_ecole_et_le_reste(tmp_path):
    db = DatabaseManager(db_file=str(tmp_path / "p.db"))
    pid = db.ajouter_profil("Ana Test", "PM", "Orbique", "Dauphine", URL, localisation="Paris")
    assert db.ajouter_profil("Ana Test", "", "", "", URL) == pid
    assert _profil(db, URL) == {"poste": "PM", "entreprise": "Orbique",
                                "ecole": "Dauphine", "localisation": "Paris"}


def test_nouvelle_valeur_remplace_sauf_l_ecole(tmp_path):
    db = DatabaseManager(db_file=str(tmp_path / "p.db"))
    db.ajouter_profil("Ana Test", "PM", "Orbique", "Dauphine", URL)
    db.ajouter_profil("Ana Test", "Head of Product", "Nexa", "ESCP", URL)
    assert _profil(db, URL)["poste"] == "Head of Product"
    assert _profil(db, URL)["entreprise"] == "Nexa"
    assert _profil(db, URL)["ecole"] == "Dauphine"
