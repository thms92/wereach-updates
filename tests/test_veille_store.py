# -*- coding: utf-8 -*-
"""Stockage de la veille : dans la base de l'utilisateur, à côté des profils.

Ce qui compte : un contact déjà au fichier n'est pas « nouveau » ; un
changement de fiche se voit ; rien n'est détruit chez quelqu'un qui a déjà
une base.
"""

import sqlite3

from database import DatabaseManager
from veille_store import VeilleStore


def store(tmp_path):
    db = str(tmp_path / "profils.db")
    DatabaseManager(db_file=db)  # la base existe déjà chez tout le monde
    return VeilleStore(db), db


def contact(vanity, poste="Product Manager", connexions="2e"):
    return {"nom": vanity.title(), "poste": poste, "url": f"https://www.linkedin.com/in/{vanity}/",
            "connexions": connexions}


def test_les_tables_de_la_base_existante_sont_intactes(tmp_path):
    s, db = store(tmp_path)
    tables = {r[0] for r in sqlite3.connect(db).execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"profiles", "invitations", "recherches", "entreprises_suivies",
            "fiche_entreprise", "contacts_veille", "passages_veille", "actualites"} <= tables


def test_ajout_et_doublon_insensible_a_la_casse(tmp_path):
    s, _ = store(tmp_path)
    a = s.ajouter_entreprise("Orbique", "2026-10-15")
    assert s.ajouter_entreprise("orbique ", "2026-10-16") == a
    [e] = s.entreprises()
    assert e["nom"] == "Orbique" and e["etat"] == "a_identifier" and e["nb_contacts"] == 0


def test_un_lien_colle_est_garde(tmp_path):
    s, _ = store(tmp_path)
    s.ajouter_entreprise("Orbique", "2026-10-15", url_linkedin="https://www.linkedin.com/company/orbique/")
    assert s.entreprises()[0]["url_linkedin"] == "https://www.linkedin.com/company/orbique/"


def test_identification_curseur_et_passage(tmp_path):
    s, _ = store(tmp_path)
    i = s.ajouter_entreprise("Orbique", "2026-10-15")
    s.maj_identification(i, "identifiee", company_id="123", url_linkedin="https://www.linkedin.com/company/orbique/")
    s.maj_curseur(i, 2, "sig")
    s.marquer_passage(i, "2026-10-15T08:00:00")
    e = s.entreprises()[0]
    assert (e["etat"], e["company_id"], e["curseur_page"], e["signature_familles"], e["derniere_veille"]) == \
        ("identifiee", "123", 2, "sig", "2026-10-15T08:00:00")


def test_la_premiere_fiche_n_est_pas_un_changement(tmp_path):
    s, _ = store(tmp_path)
    i = s.ajouter_entreprise("Orbique", "2026-10-15")
    assert s.enregistrer_fiche(i, {"taille": "11-50 employés"}, "linkedin", "2026-10-15") == []
    assert s.fiche(i)["linkedin.taille"]["valeur"] == "11-50 employés"


def test_une_valeur_identique_n_est_pas_reenregistree_et_un_changement_se_voit(tmp_path):
    s, _ = store(tmp_path)
    i = s.ajouter_entreprise("Orbique", "2026-10-15")
    s.enregistrer_fiche(i, {"taille": "11-50 employés"}, "linkedin", "2026-10-15")
    assert s.enregistrer_fiche(i, {"taille": "11-50 employés"}, "linkedin", "2026-11-15") == []
    assert s.enregistrer_fiche(i, {"taille": "51-200 employés"}, "linkedin", "2026-12-15") == ["taille"]
    [chg] = s.nouveautes_depuis("2026-12-01")["changements"]
    assert (chg["entreprise"], chg["champ"], chg["avant"], chg["apres"]) == \
        ("Orbique", "taille", "11-50 employés", "51-200 employés")


def test_age_de_la_fiche(tmp_path):
    s, _ = store(tmp_path)
    i = s.ajouter_entreprise("Orbique", "2026-10-15")
    assert s.age_fiche_jours(i, "linkedin", "2026-10-15") is None
    s.enregistrer_fiche(i, {"taille": "x"}, "linkedin", "2026-10-01T08:00:00")
    assert s.age_fiche_jours(i, "linkedin", "2026-10-15") == 14


def test_un_contact_inconnu_est_nouveau_une_fois(tmp_path):
    s, _ = store(tmp_path)
    i = s.ajouter_entreprise("Orbique", "2026-10-15")
    assert s.relier_contact(i, contact("jeanne-exemple"), "Product", "2026-10-15", set()) is True
    assert s.relier_contact(i, contact("jeanne-exemple"), "Product", "2026-10-16", set()) is False
    assert len(s.contacts(i)) == 1


def test_un_contact_deja_au_fichier_est_relie_mais_pas_nouveau(tmp_path):
    s, _ = store(tmp_path)
    i = s.ajouter_entreprise("Orbique", "2026-10-15")
    au_fichier = {"http://LINKEDIN.com/in/Jeanne-Exemple?miniProfileUrn=x"}
    assert s.relier_contact(i, contact("jeanne-exemple"), "Product", "2026-10-15", au_fichier) is False
    assert len(s.contacts(i)) == 1
    assert s.nouveautes_depuis(None)["contacts"] == []


def test_nouveautes_depuis_une_date(tmp_path):
    s, _ = store(tmp_path)
    i = s.ajouter_entreprise("Orbique", "2026-10-15")
    s.relier_contact(i, contact("ancien"), "Data", "2026-10-14T09:00:00", set())
    s.relier_contact(i, contact("recent"), "IA", "2026-10-15T08:00:00", set())
    noms = [c["nom"] for c in s.nouveautes_depuis("2026-10-15T00:00:00")["contacts"]]
    assert noms == ["Recent"]
    assert s.nouveautes_depuis("2026-10-15T00:00:00")["contacts"][0]["entreprise"] == "Orbique"


def test_retirer_supprime_fiche_et_contacts(tmp_path):
    s, db = store(tmp_path)
    i = s.ajouter_entreprise("Orbique", "2026-10-15")
    s.enregistrer_fiche(i, {"taille": "x"}, "linkedin", "2026-10-15")
    s.relier_contact(i, contact("a"), "Data", "2026-10-15", set())
    s.retirer_entreprise(i)
    con = sqlite3.connect(db)
    assert s.entreprises() == []
    assert con.execute("SELECT COUNT(*) FROM fiche_entreprise").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM contacts_veille").fetchone()[0] == 0


def test_passages(tmp_path):
    s, _ = store(tmp_path)
    assert s.dernier_passage() is None
    s.enregistrer_passage("2026-10-15T08:00", "2026-10-15T08:20", ["Orbique"], 3, "budget", ["x"])
    p = s.dernier_passage()
    assert (p["entreprises"], p["pages"], p["cause"], p["erreurs"]) == (["Orbique"], 3, "budget", ["x"])


def test_les_societes_du_fichier(tmp_path):
    s, db = store(tmp_path)
    dbm = DatabaseManager(db_file=db)
    dbm.ajouter_profil("A", "PM", "Orbique", "", "https://www.linkedin.com/in/a/")
    dbm.ajouter_profil("B", "PM", "orbique", "", "https://www.linkedin.com/in/b/")
    dbm.ajouter_profil("C", "PM", "", "", "https://www.linkedin.com/in/c/")
    dbm.ajouter_profil("D", "PM", "Zéphyr", "", "https://www.linkedin.com/in/d/")
    assert s.societes_du_fichier() == ["Orbique", "Zéphyr"]


ARTICLE = {"titre": "Orbique rachète Zéphyr", "lien": "https://n/1", "source": "Les Échos",
           "publie_le": "2026-08-31", "categorie": "Rachat / fusion"}


def test_une_actualite_n_est_nouvelle_qu_une_fois(tmp_path):
    s, _ = store(tmp_path)
    i = s.ajouter_entreprise("Orbique", "2026-10-15")
    assert s.enregistrer_actualites(i, [ARTICLE], "2026-10-15T08:00:00") == 1
    assert s.enregistrer_actualites(i, [ARTICLE], "2026-10-16T08:00:00") == 0
    assert s.entreprises()[0]["derniere_actualite"] == "2026-10-16T08:00:00"
    assert [a["titre"] for a in s.actualites(i)] == ["Orbique rachète Zéphyr"]


def test_le_recap_inclut_les_actualites(tmp_path):
    s, _ = store(tmp_path)
    i = s.ajouter_entreprise("Orbique", "2026-10-15")
    s.enregistrer_actualites(i, [ARTICLE], "2026-10-15T08:00:00")
    [a] = s.nouveautes_depuis("2026-10-15T00:00:00")["actualites"]
    assert (a["entreprise"], a["categorie"]) == ("Orbique", "Rachat / fusion")
    assert s.nouveautes_depuis("2026-10-16T00:00:00")["actualites"] == []


def test_retirer_supprime_aussi_l_actualite(tmp_path):
    s, db = store(tmp_path)
    i = s.ajouter_entreprise("Orbique", "2026-10-15")
    s.enregistrer_actualites(i, [ARTICLE], "2026-10-15")
    s.retirer_entreprise(i)
    assert sqlite3.connect(db).execute("SELECT COUNT(*) FROM actualites").fetchone()[0] == 0
