# -*- coding: utf-8 -*-
"""Onglet « Par critères » : chercher sans inviter, choisir, puis inviter."""

import pandas as pd
import pytest

import scraper_v2_sync
import ui.invitations
from tests.conftest import lancer_app, verifier_page_affichee
from utils.budget import Budget

PAGE = "🔍 Recherche"
TROUVES = pd.DataFrame([
    {"Nom": f"Exemple {i}", "Poste": "Product Manager", "Entreprise": "Société Démo",
     "URL du profil": f"https://www.linkedin.com/in/exemple-{i}/", "Invitation envoyée": "Non"}
    for i in range(3)
])


@pytest.fixture
def espion(monkeypatch):
    etat = {"recherches": [], "invitations": [], "df": TROUVES}
    monkeypatch.setattr(ui.invitations, "budget_du_jour", lambda _d: Budget(utilisees=5, plafond=20))

    class FauxScraper:
        def __init__(self, **kwargs):
            self.errors = []
            self.ecartes_reseau = etat.get("ecartes", 0)

        def run_scraper(self, **kwargs):
            etat["recherches"].append(kwargs)
            return etat["df"]

        def run_url_scraper(self, **kwargs):
            etat["invitations"].append(kwargs)
            return pd.DataFrame()

    monkeypatch.setattr(scraper_v2_sync, "LinkedInScraperV2Sync", FauxScraper)
    return etat


def _rechercher(mots="Product Manager"):
    at = lancer_app(PAGE)
    verifier_page_affichee(at, PAGE)
    at.session_state["global_cookie"] = "COOKIE-DE-TEST"
    at.run()
    at.text_input(key="crit_mots").set_value(mots)
    at.button(key="btn_rechercher").click()
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


def test_la_recherche_n_invite_jamais(espion):
    at = _rechercher()
    assert len(espion["recherches"]) == 1
    assert espion["recherches"][0]["inviter"] is False
    assert len(at.session_state["crit_profils"]) == 3


def test_choisir_puis_inviter_les_seuls_profils_choisis(espion):
    at = _rechercher()
    assert at.button(key="crit_btn_recuperer").label == "Inviter 3 profils choisis"
    at.button(key="crit_rien").click().run()
    assert "Cochez au moins un profil" in " ".join(c.value for c in at.caption)
    at.button(key="crit_tout").click().run()
    at.button(key="crit_btn_recuperer").click().run()
    assert espion["invitations"] == [], "le premier clic montre le récapitulatif"
    at.button(key="confirmer_crit_ok").click().run()
    assert len(espion["invitations"]) == 1
    appel = espion["invitations"][0]
    assert appel["inviter"] is True and len(appel["urls"]) == 3


def test_une_recherche_vide_n_affiche_ni_tableau_ni_envoi(espion):
    espion["df"] = pd.DataFrame()
    at = _rechercher()
    assert any("Aucun nouveau profil" in i.value for i in at.info)
    assert not [b for b in at.button if b.key == "crit_btn_recuperer"]


def test_la_liste_survit_a_un_aller_retour(espion):
    at = _rechercher()
    at.session_state["page"] = "💾 Historique"
    at.run()
    at.session_state["page"] = PAGE
    at.run()
    assert len(at.session_state["crit_profils"]) == 3
    assert at.button(key="crit_btn_recuperer").label == "Inviter 3 profils choisis"


def test_sans_critere_rien_ne_part(espion):
    at = _rechercher(mots="")
    assert espion["recherches"] == []
    assert any("au moins un filtre" in e.value for e in at.error)


def test_les_profils_deja_en_relation_ou_invites_sont_comptes(espion):
    espion["ecartes"] = 4
    at = _rechercher()
    assert any("4 profils déjà dans votre réseau ou déjà invités ont été écartés" in c.value
               for c in at.caption)
