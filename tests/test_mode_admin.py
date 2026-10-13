# -*- coding: utf-8 -*-
"""Les réglages techniques ne s'affichent que pour l'administrateur.

Le proxy n'a aucun sens dans l'usage actuel — chacun scrape depuis son propre
Mac, donc sa propre IP — et le volet Réglages contient un bouton qui efface
toute la base. Ni l'un ni l'autre n'a sa place sous la main de l'équipe.
"""

from utils.user_context import mode_admin, racine_application


def test_un_utilisateur_ordinaire_ne_voit_rien(tmp_path, monkeypatch):
    monkeypatch.setenv("WEREACH_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("WEREACH_ADMIN", raising=False)
    assert mode_admin() is False


def test_un_fichier_marqueur_ouvre_les_reglages(tmp_path, monkeypatch):
    # Thomas le crée une fois ; il survit aux mises à jour, puisqu'il vit
    # hors du dossier de l'application.
    monkeypatch.setenv("WEREACH_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("WEREACH_ADMIN", raising=False)
    (racine_application() / "admin").write_text("", encoding="utf-8")
    assert mode_admin() is True


def test_la_variable_d_environnement_a_le_dernier_mot(tmp_path, monkeypatch):
    monkeypatch.setenv("WEREACH_DATA_DIR", str(tmp_path))
    (racine_application() / "admin").write_text("", encoding="utf-8")

    monkeypatch.setenv("WEREACH_ADMIN", "0")
    assert mode_admin() is False      # refuse malgré le marqueur

    monkeypatch.setenv("WEREACH_ADMIN", "1")
    assert mode_admin() is True
