# -*- coding: utf-8 -*-
"""Onglet « Par critères » : chercher sans inviter, choisir, puis inviter."""

import pandas as pd
import pytest

from utils.verrou_linkedin import VerrouOccupe

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
            self.errors = list(etat.get("erreurs_recherche", []))
            return etat["df"]

        def run_url_scraper(self, **kwargs):
            etat["invitations"].append(kwargs)
            self.errors = list(etat.get("erreurs_invitation", []))
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


# ── Refus de séance (pause, séances du jour) : dit en clair ──
PAUSE = "Pause entre deux séances : prochaine action possible à 10:51."


def test_une_recherche_refusee_dit_le_refus_et_pas_aucun_profil(espion):
    espion["df"] = pd.DataFrame()
    espion["erreurs_recherche"] = [PAUSE]
    at = _rechercher()
    assert any(PAUSE in w.value for w in at.warning)
    assert not any("Aucun nouveau profil" in i.value for i in at.info)
    assert at.session_state["crit_profils"] is None


def test_une_invitation_refusee_dit_le_refus_et_pas_aucun_profil(espion):
    espion["erreurs_invitation"] = [PAUSE]
    at = _rechercher()
    at.button(key="crit_btn_recuperer").click().run()
    at.button(key="confirmer_crit_ok").click().run()
    assert not at.exception
    assert any(PAUSE in e.value for e in at.error)
    assert not any("Aucun profil récupéré" in w.value for w in at.warning)


# ── Arrêt sans résultat (session occupée, limite du jour) : la cause en clair ──

LIMITE_PAGES = ("Limite du jour atteinte : 60 pages LinkedIn consultées. "
                "Vous pourrez reprendre demain.")


def test_une_invitation_refusee_faute_de_pages_le_dit_en_clair(espion):
    # Pages du jour épuisées : refus avant Chrome, dit comme les autres refus.
    espion["erreurs_invitation"] = [LIMITE_PAGES]
    at = _rechercher()
    at.button(key="crit_btn_recuperer").click().run()
    at.button(key="confirmer_crit_ok").click().run()
    assert not at.exception
    assert [e.value for e in at.error] == [LIMITE_PAGES]
    assert not any("Aucun profil récupéré" in w.value for w in at.warning)


def test_une_recherche_arretee_par_la_limite_garde_ses_profils(espion):
    # Limite atteinte en cours de recherche : les profils déjà lus restent,
    # la limite est dite au-dessus.
    espion["erreurs_recherche"] = [LIMITE_PAGES]
    at = _rechercher()
    assert len(at.session_state["crit_profils"]) == 3
    assert any(LIMITE_PAGES in w.value for w in at.warning)


@pytest.mark.parametrize("erreur", [str(VerrouOccupe("veille"))])
def test_une_invitation_arretee_sans_resultat_dit_pourquoi(espion, erreur):
    espion["erreurs_invitation"] = [erreur]
    at = _rechercher()
    at.button(key="crit_btn_recuperer").click().run()
    at.button(key="confirmer_crit_ok").click().run()
    assert not at.exception
    assert any(erreur in w.value for w in at.warning)
    assert not any("Aucun profil récupéré" in w.value for w in at.warning)
    assert not any(e.label.startswith("Incidents") for e in at.expander)
