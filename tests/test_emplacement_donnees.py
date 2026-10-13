# -*- coding: utf-8 -*-
"""Les données utilisateur vivent hors du dossier de l'application.

Posé sur le Bureau, le dossier est synchronisé par iCloud, qui décharge des
fichiers pour gagner de la place : l'environnement Python se casse et la base
SQLite devient instable. Téléchargements, lui, n'est pas synchronisé — d'où
un outil qui ne marchait qu'à cet endroit.

En rangeant l'état mutable dans l'emplacement que macOS réserve aux
applications, le dossier devient déplaçable n'importe où, et retélécharger
le zip ne fait plus perdre ni cookie ni historique.
"""

import os
from pathlib import Path

from utils.user_context import (
    migrer_donnees_locales,
    racine_donnees,
    user_id_from_email,
    user_paths_for,
)


# --- Où sont rangées les données ------------------------------------------


def test_sur_mac_les_donnees_vont_dans_application_support(monkeypatch, tmp_path):
    monkeypatch.delenv("WEREACH_DATA_DIR", raising=False)
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))

    attendu = tmp_path / "Library" / "Application Support" / "We.Reach" / "data" / "users"
    assert racine_donnees() == attendu


def test_une_variable_d_environnement_a_le_dernier_mot(monkeypatch, tmp_path):
    # Indispensable au déploiement serveur, où Application Support n'existe pas.
    monkeypatch.setenv("WEREACH_DATA_DIR", str(tmp_path / "ailleurs"))
    assert racine_donnees() == tmp_path / "ailleurs"


def test_hors_mac_le_comportement_actuel_est_conserve(monkeypatch):
    monkeypatch.delenv("WEREACH_DATA_DIR", raising=False)
    monkeypatch.setattr("sys.platform", "linux")
    assert racine_donnees() == Path("data/users")


# --- Migration depuis l'ancien emplacement --------------------------------


def test_les_donnees_existantes_sont_recuperees(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    uid = user_id_from_email("lea@wefiit.com")
    ancien = tmp_path / "data" / "users" / uid / "config"
    ancien.mkdir(parents=True)
    (ancien / "cookie.txt").write_text("li_at=precieux", encoding="utf-8")

    racine = tmp_path / "support" / "data" / "users"
    assert migrer_donnees_locales(uid, racine) is True
    assert (racine / uid / "config" / "cookie.txt").read_text(encoding="utf-8") == "li_at=precieux"
    assert not (tmp_path / "data" / "users" / uid).exists()


def test_rien_n_est_ecrase_si_le_nouvel_emplacement_existe(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    uid = user_id_from_email("lea@wefiit.com")
    ancien = tmp_path / "data" / "users" / uid / "config"
    ancien.mkdir(parents=True)
    (ancien / "cookie.txt").write_text("ancien", encoding="utf-8")

    racine = tmp_path / "support" / "data" / "users"
    (racine / uid / "config").mkdir(parents=True)
    (racine / uid / "config" / "cookie.txt").write_text("recent", encoding="utf-8")

    assert migrer_donnees_locales(uid, racine) is False
    # le recent est intact, l'ancien n'est pas detruit non plus
    assert (racine / uid / "config" / "cookie.txt").read_text(encoding="utf-8") == "recent"
    assert (ancien / "cookie.txt").read_text(encoding="utf-8") == "ancien"


def test_sans_rien_a_migrer_la_migration_ne_fait_rien(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    uid = user_id_from_email("neuf@wefiit.com")
    assert migrer_donnees_locales(uid, tmp_path / "support") is False


# --- Bout en bout ----------------------------------------------------------


def test_un_utilisateur_retrouve_son_cookie_apres_un_retelechargement(tmp_path, monkeypatch):
    """Le scenario vecu : elle retelecharge le zip, le dossier est vierge,
    mais ses donnees l'attendent dans l'emplacement stable."""
    monkeypatch.setenv("WEREACH_DATA_DIR", str(tmp_path / "support" / "users"))
    (tmp_path / "dossier_v1").mkdir()
    monkeypatch.chdir(tmp_path / "dossier_v1")
    p1 = user_paths_for("lea@wefiit.com")
    p1.cookie_file.write_text("li_at=precieux", encoding="utf-8")

    # elle jette le dossier et en retelecharge un autre, ailleurs
    (tmp_path / "dossier_v2").mkdir()
    monkeypatch.chdir(tmp_path / "dossier_v2")
    p2 = user_paths_for("lea@wefiit.com")

    assert p2.cookie_file.read_text(encoding="utf-8") == "li_at=precieux"
