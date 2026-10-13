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


# --- Ouverture du client mail ---------------------------------------------

from utils.diagnostic import ouvrir_mail


def test_un_navigateur_detourne_le_mailto_on_force_mail(monkeypatch):
    """Sur le Mac de Thomas, macOS avait designe Chrome comme gestionnaire des
    liens mailto : `open` faisait son travail, Chrome avalait le lien, et rien
    ne s'ouvrait. Quand le gestionnaire est un navigateur, on le contourne."""
    appels = []
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr("utils.diagnostic._gestionnaire_mailto", lambda: "com.google.chrome")
    monkeypatch.setattr("subprocess.run", lambda *a, **k: appels.append(a[0]) or _ok())

    assert ouvrir_mail("mailto:a@b.fr") is True
    assert appels == [["open", "-a", "Mail", "mailto:a@b.fr"]]


def test_un_vrai_client_mail_est_respecte(monkeypatch):
    # Quelqu'un qui a choisi Outlook doit garder Outlook : on ne force Mail
    # que pour echapper a un navigateur.
    appels = []
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr("utils.diagnostic._gestionnaire_mailto",
                        lambda: "com.microsoft.outlook")
    monkeypatch.setattr("subprocess.run", lambda *a, **k: appels.append(a[0]) or _ok())

    assert ouvrir_mail("mailto:a@b.fr") is True
    assert appels == [["open", "mailto:a@b.fr"]]


def test_un_echec_est_rapporte_comme_tel(monkeypatch):
    """L'ancienne version renvoyait True quoi qu'il arrive : l'interface
    annoncait « ta messagerie s'ouvre » alors que rien ne s'ouvrait."""
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr("utils.diagnostic._gestionnaire_mailto", lambda: "")
    monkeypatch.setattr("subprocess.run", lambda *a, **k: _echec())

    assert ouvrir_mail("mailto:a@b.fr") is False


def test_hors_mac_on_n_ouvre_rien(monkeypatch):
    # Sur un deploiement serveur, `open` s'executerait sur le serveur.
    monkeypatch.setattr("sys.platform", "linux")
    assert ouvrir_mail("mailto:a@b.fr") is False


def test_une_exception_ne_fait_pas_planter(monkeypatch):
    def boum(*a, **k):
        raise OSError("pas de client mail")

    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr("utils.diagnostic._gestionnaire_mailto", lambda: "")
    monkeypatch.setattr("subprocess.run", boum)
    assert ouvrir_mail("mailto:a@b.fr") is False


class _Resultat:
    def __init__(self, code):
        self.returncode = code


def _ok():
    return _Resultat(0)


def _echec():
    return _Resultat(1)
