# -*- coding: utf-8 -*-
"""Tableau de bord (refonte phase 2) : « que dois-je faire aujourd'hui ? »."""

import sqlite3

from database import DatabaseManager
from tests.conftest import lancer_app, verifier_page_affichee
from ui.page_tableau_de_bord import (PAGE_MESSAGES, PAGE_RECHERCHE,
                                     actions_du_jour)


# --- compter_parcours ------------------------------------------------------

def _base(tmp_path):
    db = DatabaseManager(db_file=str(tmp_path / "parcours.db"))
    ids = []
    con = sqlite3.connect(db.db_file)
    for i in range(5):
        cur = con.execute("INSERT INTO profiles (nom, url) VALUES (?, ?)",
                          (f"P{i}", f"https://exemple.test/in/p{i}"))
        ids.append(cur.lastrowid)
    con.commit()
    con.close()
    return db, ids


def test_parcours_d_une_base_vide(tmp_path):
    db = DatabaseManager(db_file=str(tmp_path / "vide.db"))
    assert db.compter_parcours() == {"trouves": 0, "invites": 0,
                                     "acceptes": 0, "messages": 0}


def test_parcours_compte_des_profils_distincts(tmp_path):
    db, ids = _base(tmp_path)
    # p0 invité deux fois (doublon), p1 et p2 acceptés, p2 messagé.
    db.ajouter_invitation(ids[0])
    db.ajouter_invitation(ids[0])
    db.ajouter_invitation(ids[1])
    db.ajouter_invitation(ids[2])
    db.marquer_acceptee("https://exemple.test/in/p1")
    db.marquer_acceptee("https://exemple.test/in/p2")
    db.marquer_messagee("https://exemple.test/in/p2")
    assert db.compter_parcours() == {"trouves": 5, "invites": 3,
                                     "acceptes": 2, "messages": 1}


def test_parcours_sans_colonne_date_message(tmp_path):
    chemin = tmp_path / "ancienne.db"
    con = sqlite3.connect(chemin)
    con.execute("CREATE TABLE profiles (id INTEGER PRIMARY KEY, nom TEXT, url TEXT)")
    con.execute("CREATE TABLE invitations (id INTEGER PRIMARY KEY, profile_id INTEGER, "
                "statut TEXT)")
    con.execute("INSERT INTO profiles (nom, url) VALUES ('A', 'u')")
    con.execute("INSERT INTO invitations (profile_id, statut) VALUES (1, 'acceptee')")
    con.commit()
    con.close()
    db = DatabaseManager.__new__(DatabaseManager)  # sans migration
    db.db_file = str(chemin)
    assert db.compter_parcours() == {"trouves": 1, "invites": 1,
                                     "acceptes": 1, "messages": 0}


# --- fonctions pures --------------------------------------------------------

def test_rien_d_urgent_quand_tout_est_a_jour():
    assert actions_du_jour(0, 0, True) == []


def test_actions_qui_s_appliquent():
    actions = actions_du_jour(3, 12, False, budget_utilisees=20, budget_plafond=20)
    titres = [a[0] for a in actions]
    # La réussite d'abord (phase 4), puis la session manquante.
    assert titres[0] == "3 personnes ont accepté votre invitation"
    assert titres[1] == "Connectez votre session LinkedIn"
    assert actions[1][4][2] == PAGE_RECHERCHE
    assert "3 personnes ont accepté votre invitation" in titres
    assert [a for a in actions if a[0].startswith("3 personnes")][0][4][2] == PAGE_MESSAGES
    assert "12 invitations en attente de réponse" in titres
    assert "Limite conseillée de 20 invitations atteinte" in titres
    assert not any("(s)" in t for t in titres)


def test_singulier():
    titres = [a[0] for a in actions_du_jour(1, 1, True)]
    assert "1 personne a accepté votre invitation" in titres
    assert "1 invitation en attente de réponse" in titres


# --- page rendue ------------------------------------------------------------

def test_la_page_repond_a_que_faire_aujourd_hui(tmp_path, monkeypatch):
    # Données propres à ce test : la base partagée de la session de tests
    # peut contenir des profils laissés par d'autres tests.
    monkeypatch.setenv("WEREACH_DATA_DIR", str(tmp_path))
    at = lancer_app("📊 Dashboard")
    verifier_page_affichee(at, "📊 Dashboard")
    html = " ".join(m.value for m in at.main.markdown)
    assert "Ce qui vous attend aujourd&#x27;hui." in html or "Ce qui vous attend aujourd'hui." in html
    # Base vide : l'état vide apprend quoi faire au lieu d'un mur de zéros.
    assert '<div class="wf-vide">' in html and "Lancez votre première recherche" in html
    assert '<ol class="wf-entonnoir"' not in html
    assert "wf-action" in html
    assert [h.value for h in at.header][:1] == ["À faire"]
    # Plus de bandeau « Alertes et limites » ni de camembert.
    assert "Alertes et limites" not in [h.value for h in at.header]


def test_connecter_la_session_mene_a_la_page_recherche(tmp_path, monkeypatch):
    # Le bouton « Nouvelle recherche » est parti avec le bloc « Dernière
    # recherche » ; sans session, c'est la carte « À faire » qui y mène.
    monkeypatch.setenv("WEREACH_DATA_DIR", str(tmp_path))
    at = lancer_app("📊 Dashboard")
    at.button(key="tdb_aller_recherche").click().run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert at.session_state["page"] == PAGE_RECHERCHE
