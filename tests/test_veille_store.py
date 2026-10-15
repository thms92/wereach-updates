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
    from utils.browsemap import normaliser_url
    # L'appelant (le moteur) passe des URL canoniques, normalisées une fois par passage.
    au_fichier = {normaliser_url("http://LINKEDIN.com/in/Jeanne-Exemple?miniProfileUrn=x")}
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


# ── Correctifs de la revue finale ────────────────────────────────────────

def test_une_fiche_relue_a_l_identique_est_datee_de_sa_lecture(tmp_path):
    s, _ = store(tmp_path)
    i = s.ajouter_entreprise("Orbique", "2026-10-15")
    s.enregistrer_fiche(i, {"taille": "x"}, "linkedin", "2026-10-01T08:00:00")
    s.marquer_lecture(i, "linkedin", "2026-10-01T08:00:00")
    s.enregistrer_fiche(i, {"taille": "x"}, "linkedin", "2026-11-15T08:00:00")  # rien de changé
    s.marquer_lecture(i, "linkedin", "2026-11-15T08:00:00")
    assert s.age_fiche_jours(i, "linkedin", "2026-11-16") == 1
    assert s.lectures(i) == {"linkedin": "2026-11-15T08:00:00"}


def test_sans_lecture_datee_le_constat_de_recherche_ne_rajeunit_pas_la_fiche(tmp_path):
    s, _ = store(tmp_path)
    i = s.ajouter_entreprise("Orbique", "2026-10-15")
    s.enregistrer_fiche(i, {"taille": "x"}, "linkedin", "2026-09-01T08:00:00")
    s.enregistrer_fiche(i, {"recherche": "aucun profil trouvé"}, "linkedin", "2026-10-14T08:00:00")
    assert s.age_fiche_jours(i, "linkedin", "2026-10-15") == 44


def test_une_base_de_la_version_precedente_est_completee_sans_rien_perdre(tmp_path):
    db = str(tmp_path / "ancienne.db")
    con = sqlite3.connect(db)
    con.executescript("""CREATE TABLE entreprises_suivies (id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom TEXT NOT NULL, nom_cle TEXT NOT NULL UNIQUE, url_linkedin TEXT, company_id TEXT,
        etat TEXT NOT NULL DEFAULT 'a_identifier', ajoutee_le TEXT NOT NULL, derniere_veille TEXT,
        curseur_page INTEGER NOT NULL DEFAULT 0, signature_familles TEXT, derniere_actualite TEXT);
        INSERT INTO entreprises_suivies (nom, nom_cle, ajoutee_le) VALUES ('Orbique', 'orbique', '2026-10-15');""")
    con.commit()
    con.close()
    s = VeilleStore(db)
    [e] = s.entreprises()
    s.marquer_lecture(e["id"], "linkedin", "2026-10-15T08:00:00")
    assert e["nom"] == "Orbique" and s.age_fiche_jours(e["id"], "linkedin", "2026-10-16") == 1


def test_coller_un_lien_a_une_entreprise_existante_la_fait_reidentifier(tmp_path):
    s, _ = store(tmp_path)
    i = s.ajouter_entreprise("Orbique", "2026-10-15")
    s.maj_identification(i, "non_identifiee", company_id="999")
    s.attacher_lien(i, "https://www.linkedin.com/company/orbique-conseil/")
    [e] = s.entreprises()
    assert (e["nom"], e["url_linkedin"], e["etat"], e["company_id"]) == \
        ("Orbique", "https://www.linkedin.com/company/orbique-conseil/", "a_identifier", None)


def test_renommer(tmp_path):
    s, _ = store(tmp_path)
    i = s.ajouter_entreprise("Orbique Conseil", "2026-10-15")
    assert s.renommer(i, "Orbique")
    assert [e["nom"] for e in s.entreprises()] == ["Orbique"]
    assert s.ajouter_entreprise("orbique", "2026-10-16") == i  # la clé suit le nouveau nom


def test_renommer_vers_un_nom_deja_suivi_est_refuse(tmp_path):
    s, _ = store(tmp_path)
    s.ajouter_entreprise("Orbique", "2026-10-15")
    j = s.ajouter_entreprise("Orbique Conseil", "2026-10-15")
    assert s.renommer(j, "ORBIQUE") is False
    assert sorted(e["nom"] for e in s.entreprises()) == ["Orbique", "Orbique Conseil"]


def test_seuls_les_changements_qui_comptent_vont_au_recap(tmp_path):
    s, _ = store(tmp_path)
    i = s.ajouter_entreprise("Orbique", "2026-10-15")
    avant = {"taille": "11-50", "membres": "40", "description": "A", "siege": "Paris", "secteur": "Conseil"}
    apres = {"taille": "51-200", "membres": "45", "description": "B", "siege": "Lyon", "secteur": "Logiciels"}
    s.enregistrer_fiche(i, avant, "linkedin", "2026-10-01")
    s.enregistrer_fiche(i, apres, "linkedin", "2026-10-15")
    s.enregistrer_fiche(i, {"dirigeants": "X", "effectif": "10", "rapprochement": "rapprochée"}, "annuaire",
                        "2026-10-01")
    s.enregistrer_fiche(i, {"dirigeants": "Y", "effectif": "20", "rapprochement": "plusieurs"}, "annuaire",
                        "2026-10-15")
    champs = {(c["source"], c["champ"]) for c in s.nouveautes_depuis("2026-10-10")["changements"]}
    assert champs == {("linkedin", "taille"), ("linkedin", "siege"), ("linkedin", "secteur"),
                      ("annuaire", "dirigeants"), ("annuaire", "effectif")}


def test_un_refus_ne_remplace_pas_le_dernier_vrai_passage(tmp_path):
    s, _ = store(tmp_path)
    s.enregistrer_passage("2026-10-15T08:00", "2026-10-15T08:20", ["Orbique"], 3, "budget", [])
    s.enregistrer_passage("2026-10-15T09:00", "2026-10-15T09:00", [], 0, "occupe", ["occupé"])
    s.enregistrer_passage("2026-10-15T10:00", "2026-10-15T10:00", [], 0, "rien_a_faire", [])
    assert s.dernier_passage()["cause"] == "budget"
