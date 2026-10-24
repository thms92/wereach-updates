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


def _scraper(tmp_path):
    from scraper_v2 import LinkedInScraperV2
    return LinkedInScraperV2(use_database=True, db_file=str(tmp_path / "s.db"),
                             config_dir=str(tmp_path))


def test_invitation_enregistree_garde_l_ecole_de_la_recherche(tmp_path):
    sc = _scraper(tmp_path)
    sc.db.ajouter_profil("Ana Test", "PM", "Orbique", "Dauphine", URL)
    sc._enregistrer_invitation(URL, "Ana Test", {"nom": "Ana Test", "poste": "PM", "entreprise": "Orbique"}, "")
    assert sc.db.compter_parcours()["invites"] == 1
    assert _profil(sc.db, URL)["ecole"] == "Dauphine"


def test_invitation_sans_extraction_garde_le_vrai_nom(tmp_path):
    sc = _scraper(tmp_path)
    sc.db.ajouter_profil("Ana Test", "PM", "Orbique", "Dauphine", URL)
    # Le nom tiré du lien (« Ana Test 4b2a1 ») n'écrase pas celui déjà lu.
    sc._enregistrer_invitation(URL, "Ana Test 4b2a1", {}, "")
    con = sqlite3.connect(sc.db.db_file)
    (nom,) = con.execute("SELECT nom FROM profiles WHERE url = ?", (URL,)).fetchone()
    con.close()
    assert nom == "Ana Test"
    assert sc.db.compter_parcours()["invites"] == 1


def test_invitation_sans_extraction_est_enregistree(tmp_path):
    sc = _scraper(tmp_path)
    sc._enregistrer_invitation(URL, "Ana Test", {}, "")
    assert sc.db.compter_parcours() == {"trouves": 1, "invites": 1, "acceptes": 0, "messages": 0}
