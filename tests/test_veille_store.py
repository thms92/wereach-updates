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
            "fiche_entreprise", "contacts_veille", "passages_veille"} <= tables
    assert "actualites" not in tables  # plus créée : la veille ne lit plus l'actualité


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


def test_les_nouveautes_ne_portent_plus_d_actualite(tmp_path):
    s, _ = store(tmp_path)
    assert set(s.nouveautes_depuis(None)) == {"contacts", "changements"}


def _base_avec_actualites(tmp_path):
    """Base d'une version précédente de cette branche : table et colonne d'actualité présentes."""
    db = str(tmp_path / "avec_actus.db")
    con = sqlite3.connect(db)
    con.executescript("""CREATE TABLE entreprises_suivies (id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom TEXT NOT NULL, nom_cle TEXT NOT NULL UNIQUE, url_linkedin TEXT, company_id TEXT,
        etat TEXT NOT NULL DEFAULT 'a_identifier', ajoutee_le TEXT NOT NULL, derniere_veille TEXT,
        curseur_page INTEGER NOT NULL DEFAULT 0, signature_familles TEXT, derniere_actualite TEXT);
        CREATE TABLE actualites (id INTEGER PRIMARY KEY AUTOINCREMENT, entreprise_id INTEGER NOT NULL,
        lien TEXT NOT NULL, titre TEXT NOT NULL, source TEXT, publie_le TEXT, categorie TEXT NOT NULL,
        trouve_le TEXT NOT NULL, UNIQUE (entreprise_id, lien));
        INSERT INTO entreprises_suivies (nom, nom_cle, ajoutee_le, derniere_actualite)
            VALUES ('Orbique', 'orbique', '2026-10-15', '2026-10-15T08:00:00');
        INSERT INTO actualites (entreprise_id, lien, titre, categorie, trouve_le)
            VALUES (1, 'https://n/1', 'Orbique rachète Zéphyr', 'Rachat / fusion', '2026-10-15');""")
    con.commit()
    con.close()
    return db


def test_retirer_nettoie_l_actualite_d_une_base_qui_en_a_encore_et_ne_la_supprime_pas(tmp_path):
    db = _base_avec_actualites(tmp_path)
    s = VeilleStore(db)
    [e] = s.entreprises()  # la colonne héritée ne gêne pas la lecture
    s.retirer_entreprise(e["id"])
    con = sqlite3.connect(db)
    assert s.entreprises() == []
    assert con.execute("SELECT COUNT(*) FROM actualites").fetchone()[0] == 0  # table conservée, lignes parties
    con.close()


def test_retirer_fonctionne_sans_table_d_actualite(tmp_path):
    s, _ = store(tmp_path)
    i = s.ajouter_entreprise("Orbique", "2026-10-15")
    s.retirer_entreprise(i)
    assert s.entreprises() == []


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


# ── Degré de relation et coordonnées des contacts ─────────────────────

def _invitation_acceptee(db, url):
    base = DatabaseManager(db_file=db)
    pid = base.ajouter_profil("Paul", "PM", "Orbique", "", url)
    base.ajouter_invitation(pid)
    assert base.marquer_acceptee(url)


def test_le_degre_lu_sur_la_carte_est_garde(tmp_path):
    s, _ = store(tmp_path)
    i = s.ajouter_entreprise("Orbique", "2026-10-15")
    s.relier_contact(i, contact("jeanne", connexions=""), "Product", "2026-10-15", set())
    s.maj_degre(i, "http://linkedin.com/in/Jeanne?trk=x", "1er")
    assert s.contacts(i)[0]["degre"] == "1er"


def test_relation_par_degre_ou_par_invitation_acceptee(tmp_path):
    s, db = store(tmp_path)
    i = s.ajouter_entreprise("Orbique", "2026-10-15")
    for v in ("jeanne", "paul", "lea"):
        s.relier_contact(i, contact(v, connexions=""), "Product", "2026-10-15", set())
    s.maj_degre(i, "https://www.linkedin.com/in/jeanne/", "1er")
    s.maj_degre(i, "https://www.linkedin.com/in/lea/", "2e")
    # Au fichier sous une autre écriture du même lien.
    _invitation_acceptee(db, "http://linkedin.com/in/Paul?miniProfileUrn=x")
    urls = [c["url"] for c in s.contacts_en_relation(i, "2026-10-15T09:00:00")]
    assert sorted(urls) == ["https://www.linkedin.com/in/jeanne/", "https://www.linkedin.com/in/paul/"]


def test_une_invitation_seulement_envoyee_ne_met_pas_en_relation(tmp_path):
    s, db = store(tmp_path)
    i = s.ajouter_entreprise("Orbique", "2026-10-15")
    s.relier_contact(i, contact("paul", connexions=""), "Product", "2026-10-15", set())
    base = DatabaseManager(db_file=db)
    base.ajouter_invitation(base.ajouter_profil("Paul", "PM", "Orbique", "", "https://www.linkedin.com/in/paul/"))
    assert s.contacts_en_relation(i, "2026-10-15") == []


def test_coordonnees_relues_au_plus_tous_les_90_jours(tmp_path):
    s, _ = store(tmp_path)
    i = s.ajouter_entreprise("Orbique", "2026-10-15")
    s.relier_contact(i, contact("jeanne", connexions="1er"), "Product", "2026-01-01", set())
    s.enregistrer_coordonnees("https://www.linkedin.com/in/jeanne/", "jeanne@orbique.example", "", "2026-07-20T10:00:00")
    assert s.contacts_en_relation(i, "2026-10-15") == []          # 87 jours
    assert len(s.contacts_en_relation(i, "2026-10-18")) == 1      # 90 jours


def test_rien_de_partage_est_enregistre_et_date(tmp_path):
    s, _ = store(tmp_path)
    i = s.ajouter_entreprise("Orbique", "2026-10-15")
    s.relier_contact(i, contact("jeanne", connexions="1er"), "Product", "2026-10-15", set())
    s.enregistrer_coordonnees("http://linkedin.com/in/Jeanne/", "", None, "2026-10-15T10:00:00")
    assert s.coordonnees("https://www.linkedin.com/in/jeanne/") == {
        "url": "https://www.linkedin.com/in/jeanne/", "email": "", "telephone": "",
        "partage": "rien", "releve_le": "2026-10-15T10:00:00"}
    # « Rien de partagé » compte comme une lecture : pas relue avant 90 jours.
    assert s.contacts_en_relation(i, "2026-10-16") == []


def test_coordonnees_partagees(tmp_path):
    s, _ = store(tmp_path)
    s.enregistrer_coordonnees("https://www.linkedin.com/in/jeanne/", "jeanne@orbique.example",
                              "+33 6 12 34 56 78", "2026-10-15T10:00:00")
    c = s.coordonnees("https://www.linkedin.com/in/jeanne/")
    assert c["partage"] == "oui" and c["email"] == "jeanne@orbique.example"
    assert s.coordonnees("https://www.linkedin.com/in/inconnu/") is None


def test_coordonnees_table_creee_sans_rien_detruire(tmp_path):
    s, db = store(tmp_path)
    s.enregistrer_coordonnees("https://www.linkedin.com/in/jeanne/", "j@o.example", "", "2026-10-15")
    VeilleStore(db)  # rouverte : la table existe, rien n'est effacé
    assert VeilleStore(db).coordonnees("https://www.linkedin.com/in/jeanne/")["email"] == "j@o.example"


def test_un_essai_en_echec_ne_bloque_pas_la_file(tmp_path):
    s, _ = store(tmp_path)
    i = s.ajouter_entreprise("Orbique", "2026-10-15")
    for v in ("a", "b", "c", "d"):
        s.relier_contact(i, contact(v, connexions="1er"), "Product", "2026-10-01", set())
    s.noter_echec_coordonnees("https://www.linkedin.com/in/b/", "2026-10-15T08:00:00")
    s.noter_echec_coordonnees("http://linkedin.com/in/A?trk=x", "2026-10-14T08:00:00")
    s.noter_echec_coordonnees("https://www.linkedin.com/in/c/", "2026-10-13T08:00:00")
    url = "https://www.linkedin.com/in/{}/".format
    # Jamais essayé d'abord ; un échec n'est retenté qu'après 7 jours.
    assert [c["url"] for c in s.contacts_en_relation(i, "2026-10-16")] == [url("d")]
    assert [c["url"] for c in s.contacts_en_relation(i, "2026-10-21")] == [url("d"), url("c"), url("a")]
    assert [c["url"] for c in s.contacts_en_relation(i, "2026-10-22")] == [url("d"), url("c"), url("a"), url("b")]
    # Un échec n'est pas une lecture : rien à afficher pour lui.
    assert s.coordonnees(url("a")) is None


def test_une_lecture_reussie_efface_l_echec(tmp_path):
    s, _ = store(tmp_path)
    i = s.ajouter_entreprise("Orbique", "2026-10-15")
    s.relier_contact(i, contact("a", connexions="1er"), "Product", "2026-10-01", set())
    s.noter_echec_coordonnees("https://www.linkedin.com/in/a/", "2026-10-01")
    s.enregistrer_coordonnees("https://www.linkedin.com/in/a/", "", "", "2026-10-15")
    assert s.contacts_en_relation(i, "2026-10-20") == []
    assert len(s.contacts_en_relation(i, "2027-01-20")) == 1  # 90 jours, pas 7


def test_retirer_une_entreprise_efface_les_coordonnees_de_ses_seuls_contacts(tmp_path):
    s, db = store(tmp_path)
    a = s.ajouter_entreprise("Orbique", "2026-10-15")
    b = s.ajouter_entreprise("Zéphyr", "2026-10-15")
    s.relier_contact(a, contact("jeanne"), "Product", "2026-10-15", set())
    s.relier_contact(a, contact("paul"), "Product", "2026-10-15", set())
    s.relier_contact(b, contact("paul"), "Product", "2026-10-15", set())
    for v in ("jeanne", "paul"):
        s.enregistrer_coordonnees(f"https://www.linkedin.com/in/{v}/", f"{v}@o.example", "", "2026-10-15")
    s.noter_echec_coordonnees("https://www.linkedin.com/in/jeanne/", "2026-10-15")
    s.retirer_entreprise(a)
    # Donnée personnelle : plus suivie par aucune entreprise, elle ne reste pas.
    assert s.coordonnees("https://www.linkedin.com/in/jeanne/") is None
    assert sqlite3.connect(db).execute("SELECT COUNT(*) FROM essais_coordonnees").fetchone()[0] == 0
    assert s.coordonnees("https://www.linkedin.com/in/paul/")["email"] == "paul@o.example"


# ── Coordonnées pour la fiche et le récap ─────────────────────────────

def test_contacts_et_coordonnees_suivent_la_relation(tmp_path):
    s, db = store(tmp_path)
    i = s.ajouter_entreprise("Orbique", "2026-10-15")
    for v, deg in (("jeanne", "1er"), ("paul", "1er"), ("lea", "1er"), ("max", "2e"), ("zoe", "")):
        s.relier_contact(i, contact(v, connexions=deg), "Product", "2026-10-15", set())
    s.enregistrer_coordonnees("https://www.linkedin.com/in/jeanne/", "jeanne@orbique.example", "", "2026-10-15T09:00")
    s.enregistrer_coordonnees("https://www.linkedin.com/in/paul/", "", "", "2026-10-15T09:00")
    s.noter_echec_coordonnees("https://www.linkedin.com/in/lea/", "2026-10-15T09:00")
    # Lues un jour, mais la personne n'est plus en relation : rien ne sort.
    s.enregistrer_coordonnees("https://www.linkedin.com/in/max/", "max@orbique.example", "", "2026-10-15T09:00")
    _invitation_acceptee(db, "https://www.linkedin.com/in/zoe/")
    par_url = {c["url"].split("/")[-2]: c for c in s.contacts_et_coordonnees(i)}
    assert par_url["jeanne"]["en_relation"] and par_url["jeanne"]["coordonnees"]["email"] == "jeanne@orbique.example"
    assert par_url["paul"]["coordonnees"]["partage"] == "rien"
    assert par_url["lea"]["coordonnees"] is None and par_url["lea"]["echec_le"] == "2026-10-15T09:00"
    assert not par_url["max"]["en_relation"] and par_url["max"]["coordonnees"] is None
    assert par_url["zoe"]["en_relation"] and par_url["zoe"]["coordonnees"] is None
    assert par_url["zoe"]["echec_le"] is None
    # Même ordre que `contacts`.
    assert [c["url"] for c in s.contacts_et_coordonnees(i)] == [c["url"] for c in s.contacts(i)]


def test_coordonnees_nouvelles_depuis_la_derniere_visite(tmp_path):
    s, _ = store(tmp_path)
    i = s.ajouter_entreprise("Orbique", "2026-10-15")
    for v in ("jeanne", "paul", "lea"):
        s.relier_contact(i, contact(v, connexions="1er"), "Product", "2026-10-01", set())
    s.relier_contact(i, contact("max", connexions="2e"), "Product", "2026-10-01", set())
    s.enregistrer_coordonnees("https://www.linkedin.com/in/jeanne/", "jeanne@orbique.example", "", "2026-10-15T09:00")
    s.enregistrer_coordonnees("https://www.linkedin.com/in/paul/", "", "", "2026-10-15T09:00")     # rien
    s.enregistrer_coordonnees("https://www.linkedin.com/in/lea/", "", "+33 1 00", "2026-10-01T09:00")  # avant
    s.enregistrer_coordonnees("https://www.linkedin.com/in/max/", "max@x.example", "", "2026-10-15T09:00")  # hors relation
    [n] = s.coordonnees_nouvelles_depuis("2026-10-10T00:00:00")
    assert (n["entreprise"], n["nom"], n["email"], n["telephone"]) == ("Orbique", "Jeanne", "jeanne@orbique.example", "")
    assert len(s.coordonnees_nouvelles_depuis(None)) == 2
    # Lecture seule : rien n'est consommé.
    assert len(s.coordonnees_nouvelles_depuis("2026-10-10T00:00:00")) == 1
