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
from database import DatabaseManager
from tests.conftest import chemins_de_test, lancer_app, verifier_page_affichee
from utils.verrou_linkedin import VerrouOccupe, message_occupe

PAGE = "✉️ Messages"
URL = "https://www.linkedin.com/in/profil-de-test-messages/"
OCCUPE = str(VerrouOccupe("veille"))


class ScraperOccupe:
    instances = []

    def __init__(self, **k):
        self.errors = []
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
    assert not at.exception
    assert any(OCCUPE in e.value for e in at.error)
    assert not any("envoy" in s.value for s in at.success)
