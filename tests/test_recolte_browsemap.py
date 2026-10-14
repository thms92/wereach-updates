# -*- coding: utf-8 -*-
"""Garde-fous de la récolte des profils voisins, sans lancer de navigateur.

Deux choses se vérifient sans Chrome, et ce sont celles qui cassent : qu'une
URL qui n'est pas un profil soit refusée AVANT tout lancement — sinon on
ouvre un navigateur pour rien et l'erreur arrive deux minutes trop tard — et
que le wrapper synchrone remonte fidèlement ce que la couche async a trouvé.
"""

import asyncio

import pytest

from scraper_v2 import LinkedInScraperV2
from scraper_v2_sync import LinkedInScraperV2Sync
from utils.dom_selectors import DOMSelectors


@pytest.fixture
def scraper(tmp_path):
    return LinkedInScraperV2(use_database=False, config_dir=str(tmp_path))


def recolter(scraper, url):
    return asyncio.run(
        scraper.recolter_browsemap_async(cookie="COOKIE-DE-TEST", url_reference=url)
    )


def test_une_page_entreprise_est_refusee_sans_lancer_de_navigateur(scraper):
    suggestions, entreprise = recolter(scraper, "https://www.linkedin.com/company/thiga/")

    assert suggestions == []
    assert entreprise is None
    assert any("profil LinkedIn" in e for e in scraper.errors)


def test_une_saisie_vide_est_refusee(scraper):
    suggestions, entreprise = recolter(scraper, "")

    assert (suggestions, entreprise) == ([], None)
    assert scraper.errors


def test_le_wrapper_synchrone_remonte_ce_qu_a_trouve_la_couche_async(tmp_path, monkeypatch):
    attendu = ([{"nom": "Jean Dupont", "url": "https://www.linkedin.com/in/jd/"}], "Thiga")
    wrapper = LinkedInScraperV2Sync(use_database=False, config_dir=str(tmp_path))

    async def fausse_recolte(cookie, url_reference, status_callback=None):
        return attendu

    monkeypatch.setattr(wrapper.scraper, "recolter_browsemap_async", fausse_recolte)

    assert wrapper.recolter_browsemap("COOKIE", "https://www.linkedin.com/in/jd/") == attendu


def test_le_wrapper_synchrone_ne_leve_pas_sur_un_echec(tmp_path, monkeypatch):
    # Streamlit afficherait une trace à l'écran : le wrapper rend une liste
    # vide et consigne l'erreur, comme ses voisins.
    wrapper = LinkedInScraperV2Sync(use_database=False, config_dir=str(tmp_path))

    async def recolte_qui_echoue(cookie, url_reference, status_callback=None):
        raise RuntimeError("Chrome introuvable")

    monkeypatch.setattr(wrapper.scraper, "recolter_browsemap_async", recolte_qui_echoue)

    assert wrapper.recolter_browsemap("COOKIE", "https://www.linkedin.com/in/jd/") == ([], None)
    assert any("Chrome introuvable" in e for e in wrapper.errors)


def test_l_extracteur_javascript_lit_bien_le_panneau():
    # Garde-fou minimal : le JS n'est pas testable sans navigateur, mais une
    # suppression accidentelle de ses points d'ancrage doit se voir.
    js = DOMSelectors.extract_browsemap_js()

    assert js.strip().startswith("()")
    for ancre in ('role="dialog"', '/in/', 'invitable', 'intitule', 'degre'):
        assert ancre in js, f"ancre manquante dans l'extracteur : {ancre}"
