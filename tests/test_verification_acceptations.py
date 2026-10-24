# -*- coding: utf-8 -*-
"""Chaque invitation garde la date de sa dernière vérification."""

import sqlite3
from datetime import datetime, timezone

from database import DatabaseManager
from utils.verification import derniere_verification, enregistrer_verification

URL_A = "https://exemple.test/in/a"
URL_B = "https://exemple.test/in/b"
URL_C = "https://exemple.test/in/c"


def _base_avec_trois_invitations(tmp_path):
    """A : envoyée J-10, vérifiée J-1. B : J-5, jamais. C : J-2, jamais."""
    db = DatabaseManager(db_file=str(tmp_path / "verif.db"))
    con = sqlite3.connect(db.db_file)
    pids = [con.execute("INSERT INTO profiles (nom, url) VALUES (?, ?)",
                        (url[-1], url)).lastrowid
            for url in (URL_A, URL_B, URL_C)]
    con.commit()
    con.close()
    for pid in pids:
        db.ajouter_invitation(pid)
    con = sqlite3.connect(db.db_file)
    for pid, envoi, verif in ((pids[0], "-10 days", "-1 days"),
                              (pids[1], "-5 days", None),
                              (pids[2], "-2 days", None)):
        con.execute("UPDATE invitations SET date_envoi = datetime('now', ?), "
                    "date_verification = CASE WHEN ? IS NULL THEN NULL "
                    "ELSE datetime('now', ?) END WHERE profile_id = ?",
                    (envoi, verif, verif, pid))
    con.commit()
    con.close()
    return db


def test_jamais_verifiees_d_abord_les_plus_recentes_en_tete(tmp_path):
    db = _base_avec_trois_invitations(tmp_path)
    assert [p["url"] for p in db.invitations_en_attente()] == [URL_C, URL_B, URL_A]


def test_marquer_verifiees_fait_passer_en_fin_de_liste(tmp_path):
    db = _base_avec_trois_invitations(tmp_path)
    db.marquer_verifiees([URL_C])
    assert [p["url"] for p in db.invitations_en_attente()][-1] == URL_C


def test_marquer_verifiees_ignore_les_invitations_acceptees(tmp_path):
    db = _base_avec_trois_invitations(tmp_path)
    db.marquer_acceptee(URL_B)
    db.marquer_verifiees([URL_B])
    con = sqlite3.connect(db.db_file)
    (date,) = con.execute(
        "SELECT i.date_verification FROM invitations i JOIN profiles p "
        "ON i.profile_id = p.id WHERE p.url = ?", (URL_B,)).fetchone()
    con.close()
    assert date is None


def test_derniere_verification_aller_retour(tmp_path):
    moment = datetime(2026, 10, 24, 9, 30, tzinfo=timezone.utc)
    enregistrer_verification(str(tmp_path), moment)
    assert derniere_verification(str(tmp_path)) == moment


def test_derniere_verification_sans_moment_donne_l_heure_courante(tmp_path):
    avant = datetime.now(timezone.utc)
    enregistrer_verification(str(tmp_path))
    lu = derniere_verification(str(tmp_path))
    assert avant <= lu <= datetime.now(timezone.utc)


def test_derniere_verification_absente_ou_illisible(tmp_path):
    assert derniere_verification(str(tmp_path)) is None
    (tmp_path / "derniere_verification.json").write_text("{pas du json")
    assert derniere_verification(str(tmp_path)) is None
