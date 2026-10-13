# -*- coding: utf-8 -*-
"""Rapport de problème pré-rempli.

Jusqu'ici, un utilisateur bloqué devait photographier son écran. Le rapport
rassemble tout seul ce qui sert au diagnostic et ouvre un mail déjà rédigé.

Ce qui part dans un mail doit être expurgé : le cookie LinkedIn vaut un accès
au compte de la personne.
"""

from utils.diagnostic import expurger, lien_mailto, rapport


# --- Expurgement ----------------------------------------------------------


def test_un_cookie_linkedin_est_masque():
    sortie = expurger("li_at=AQEDATf9kQ0BxYzVAAABlPqZ2dAAAAGVHqZ9VE0Axc")
    assert "AQEDAT" not in sortie
    assert "[masqué]" in sortie


def test_une_cle_de_chiffrement_est_masquee():
    sortie = expurger("secret.key: oyhAUd-ZB4Cm2lvZa2PtTWzB4W0_E2KAu7iAdqs7pM4=")
    assert "oyhAUd" not in sortie


def test_le_texte_utile_est_preserve():
    texte = "/Users/lea/Downloads/We.Reach 8/app : python: command not found"
    assert expurger(texte) == texte


# --- Contenu du rapport ---------------------------------------------------


def test_le_rapport_porte_de_quoi_diagnostiquer():
    texte = rapport(erreur="python: command not found")
    for attendu in ("We.Reach", "Version", "macOS", "Dossier", "python: command not found"):
        assert attendu in texte


def test_le_rapport_est_expurge(tmp_path, monkeypatch):
    journal = tmp_path / "scraper.log"
    journal.write_text("INFO - cookie li_at=AQEDATf9kQ0BxYzVAAABlPqZ2dAAAAG\n", encoding="utf-8")
    monkeypatch.setattr("utils.diagnostic.FICHIER_JOURNAL", journal)

    assert "AQEDAT" not in rapport(erreur="peu importe")


# --- Lien mailto ----------------------------------------------------------


def test_le_lien_mailto_cible_le_destinataire():
    lien = lien_mailto("support@exemple.fr", "un rapport")
    assert lien.startswith("mailto:support@exemple.fr?")
    assert "subject=" in lien and "body=" in lien


def test_le_lien_mailto_encode_les_caracteres_speciaux():
    lien = lien_mailto("a@b.fr", "ligne 1\nligne & 2")
    assert " " not in lien
    assert "\n" not in lien
    assert "%26" in lien  # l'esperluette casserait l'URL sans encodage
