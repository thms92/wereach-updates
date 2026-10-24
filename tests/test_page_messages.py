# -*- coding: utf-8 -*-
"""Page Messages : une session LinkedIn déjà en cours est dite en clair.

Les enveloppes synchrones rangent le refus du verrou parmi leurs erreurs et
rendent une liste vide ; la page affichait alors « Aucune nouvelle
acceptation » ou « 0 message envoyé », puis se relançait. Le scraper
est remplacé : aucune session LinkedIn ne s'ouvre.
"""

import sqlite3

import pytest

import scraper_v2_sync
from scraper_v2 import SESSION_EXPIREE
from database import DatabaseManager
from tests.conftest import chemins_de_test, lancer_app, verifier_page_affichee
from utils.verification import derniere_verification
from utils.verrou_linkedin import VerrouOccupe, message_occupe

PAGE = "✉️ Messages"
URL = "https://www.linkedin.com/in/profil-de-test-messages/"
OCCUPE = str(VerrouOccupe("veille"))


class ScraperOccupe:
    instances = []

    def __init__(self, **k):
        self.errors = []
        self.verifiees = []
        ScraperOccupe.instances.append(self)

    def verifier_acceptations(self, **k):
        self.errors = [OCCUPE]
        return []

    def envoyer_messages(self, **k):
        self.errors = [OCCUPE]
        return []


@pytest.fixture
def invitation(monkeypatch):
    monkeypatch.setattr(scraper_v2_sync, "LinkedInScraperV2Sync", ScraperOccupe)
    db_file = str(chemins_de_test().db_file)
    db = DatabaseManager(db_file=db_file)
    db.ajouter_invitation(db.ajouter_profil("Profil Test", "PM", "Orbique", "", URL), "")
    yield db
    con = sqlite3.connect(db_file)
    con.execute("DELETE FROM invitations WHERE profile_id IN (SELECT id FROM profiles WHERE url = ?)", (URL,))
    con.execute("DELETE FROM profiles WHERE url = ?", (URL,))
    con.commit()
    con.close()


def _page():
    at = lancer_app(PAGE)
    verifier_page_affichee(at, PAGE)
    at.session_state["global_cookie"] = "COOKIE-DE-TEST"
    at.run()
    return at


def test_message_occupe():
    assert message_occupe(["autre chose", OCCUPE]) == OCCUPE
    assert message_occupe(["Cookie invalide"]) is None and message_occupe(None) is None


def test_verification_refusee_par_le_verrou_le_dit(invitation):
    at = _page()
    [b for b in at.button if b.label == "Vérifier qui a accepté"][0].click()
    at.run()
    assert not at.exception
    assert any(OCCUPE in e.value for e in at.error)
    assert not any("Aucune nouvelle acceptation" in i.value for i in at.info)


def test_envoi_refuse_par_le_verrou_le_dit_sans_relancer_la_page(invitation):
    invitation.marquer_acceptee(URL)
    at = _page()
    at.checkbox(key=f"msg_{URL}").check()
    at.text_area[0].input("Bonjour !")
    at.run()
    at.button(key="msg_envoyer").click()
    at.run()
    at.button(key="confirmer_messages_ok").click()
    at.run()
    assert not at.exception
    assert any(OCCUPE in e.value for e in at.error)
    assert not any("envoy" in s.value for s in at.success)


URL_B = "https://www.linkedin.com/in/autre-profil-de-test-messages/"


class ScraperVerifie:
    """Scraper factice : rend ce que `lire` a été réglé à lire."""
    verifiees = []
    erreurs = []

    def __init__(self, **k):
        self.errors = []
        self.verifiees = []

    def verifier_acceptations(self, **k):
        self.errors = list(ScraperVerifie.erreurs)
        self.verifiees = list(ScraperVerifie.verifiees)
        return []


@pytest.fixture
def deux_invitations(monkeypatch, invitation):
    monkeypatch.setattr(scraper_v2_sync, "LinkedInScraperV2Sync", ScraperVerifie)
    invitation.ajouter_invitation(invitation.ajouter_profil("Autre Test", "PM", "Orbique", "", URL_B), "")
    fichier = chemins_de_test().config_dir / "derniere_verification.json"
    fichier.unlink(missing_ok=True)
    yield invitation
    fichier.unlink(missing_ok=True)
    con = sqlite3.connect(str(chemins_de_test().db_file))
    con.execute("DELETE FROM invitations WHERE profile_id IN (SELECT id FROM profiles WHERE url = ?)", (URL_B,))
    con.execute("DELETE FROM profiles WHERE url = ?", (URL_B,))
    con.commit()
    con.close()


def _dates(db):
    con = sqlite3.connect(db.db_file)
    rows = dict(con.execute(
        "SELECT p.url, i.date_verification FROM invitations i "
        "JOIN profiles p ON i.profile_id = p.id WHERE p.url IN (?, ?)", (URL, URL_B)))
    con.close()
    return rows


def _verifier():
    at = _page()
    [b for b in at.button if b.label == "Vérifier qui a accepté"][0].click()
    at.run()
    assert not at.exception
    return at


def test_session_expiree_ne_marque_que_les_pages_lues(deux_invitations):
    ScraperVerifie.verifiees = [URL]
    ScraperVerifie.erreurs = [SESSION_EXPIREE]
    _verifier()
    dates = _dates(deux_invitations)
    assert dates[URL] is not None and dates[URL_B] is None
    assert derniere_verification(str(chemins_de_test().config_dir)) is None


def test_verification_reussie_enregistre_la_date(deux_invitations):
    ScraperVerifie.verifiees = [URL, URL_B]
    ScraperVerifie.erreurs = []
    _verifier()
    assert all(d is not None for d in _dates(deux_invitations).values())
    assert derniere_verification(str(chemins_de_test().config_dir)) is not None


def test_session_occupee_n_enregistre_aucune_verification(deux_invitations):
    ScraperVerifie.verifiees = []
    ScraperVerifie.erreurs = [OCCUPE]
    _verifier()
    assert derniere_verification(str(chemins_de_test().config_dir)) is None


ILLISIBLE = "Degré de relation illisible pour 1 profil : ils restent en attente."


def test_erreur_generique_n_enregistre_aucune_verification(deux_invitations):
    ScraperVerifie.verifiees = []
    ScraperVerifie.erreurs = ["Erreur: navigateur introuvable"]
    _verifier()
    assert derniere_verification(str(chemins_de_test().config_dir)) is None


def test_aucune_page_lue_n_enregistre_aucune_verification(deux_invitations):
    ScraperVerifie.verifiees = []
    ScraperVerifie.erreurs = []
    _verifier()
    assert derniere_verification(str(chemins_de_test().config_dir)) is None


def test_degre_illisible_dit_dans_les_details_sans_bloquer_la_date(deux_invitations):
    ScraperVerifie.verifiees = [URL]
    ScraperVerifie.erreurs = [ILLISIBLE]
    at = _verifier()
    dates = _dates(deux_invitations)
    assert dates[URL] is not None and dates[URL_B] is None
    assert derniere_verification(str(chemins_de_test().config_dir)) is not None
    assert not at.error
    assert any("Aucune nouvelle acceptation" in i.value for i in at.info)
    assert any(ILLISIBLE in m.value for m in at.markdown)
