# -*- coding: utf-8 -*-
"""Recherche par critères : la relation et l'invitation en attente sont lues
sur chaque carte, pour écarter ceux qui sont déjà dans le réseau ou déjà
invités (retour d'une collègue, 2026-10-22).

Exécuté dans un vrai Chromium sur un DOM fictif (noms et vanity inventés),
sans aucun accès réseau ; même principe que test_extracteur_browsemap.py.
"""

import pytest

from utils.dom_selectors import DOMSelectors
from utils.profile_extractor import ProfileExtractor


def carte(vanity, nom, degre, bouton, aria=None):
    aria = aria or f"{bouton} {nom}"
    return f"""
    <li class="reusable-search__result-container"><div class="entity-result">
      <a href="https://www.linkedin.com/in/{vanity}/?miniProfileUrn=x">
        <span aria-hidden="true">{nom}</span></a>
      <div><span>• {degre}</span></div>
      <div class="entity-result__primary-subtitle">Product Owner chez Exemple</div>
      <div class="entity-result__secondary-subtitle">Paris</div>
      <button aria-label="{aria}"><span>{bouton}</span></button>
    </div></li>"""


PAGE = "<main><ul>" + "".join([
    carte("exemple-libre", "Alice Exemple", "2e", "Se connecter", "Inviter Alice Exemple à rejoindre votre réseau"),
    carte("exemple-attente", "Bruno Exemple", "2e", "En attente", "En attente, cliquez pour retirer l'invitation envoyée à Bruno Exemple"),
    carte("exemple-reseau", "Chloé Exemple", "1er", "Message"),
    carte("exemple-ouvert", "David Exemple", "3e et +", "Message"),
]) + "</ul></main>"


@pytest.fixture(scope="module")
def profils():
    sync_api = pytest.importorskip("playwright.sync_api")
    try:
        pw = sync_api.sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
    except Exception as err:  # pragma: no cover - dépend du poste
        pytest.skip(f"Chromium headless indisponible : {err}")
    contexte = browser.new_context()
    contexte.route("**/*", lambda route: route.abort())
    page = contexte.new_page()
    page.set_content(PAGE, wait_until="domcontentloaded")
    brut = page.evaluate(DOMSelectors.extract_profiles_data_js())
    browser.close()
    pw.stop()
    nets = [ProfileExtractor.extract_from_data(p) for p in brut["profiles"]]
    return {p["url"].rstrip("/").rsplit("/", 1)[-1]: p for p in nets if p}


def test_les_quatre_cartes_sont_lues(profils):
    assert set(profils) == {"exemple-libre", "exemple-attente", "exemple-reseau", "exemple-ouvert"}


def test_relation_lue(profils):
    assert profils["exemple-libre"]["degre"] == "2e"
    assert profils["exemple-reseau"]["degre"] == "1er"
    assert profils["exemple-ouvert"]["degre"] == "3e"


def test_invitation_en_attente_reperee(profils):
    assert profils["exemple-attente"]["en_attente"] is True
    assert profils["exemple-libre"]["en_attente"] is False


def test_a_ecarter(profils):
    """Déjà en relation (1er) ou déjà invité : écarté. Un 3e degré au profil
    ouvert affiche aussi « Message » mais reste invitable : gardé."""
    from scraper_v2 import deja_en_relation_ou_invite
    assert deja_en_relation_ou_invite(profils["exemple-reseau"])
    assert deja_en_relation_ou_invite(profils["exemple-attente"])
    assert not deja_en_relation_ou_invite(profils["exemple-libre"])
    assert not deja_en_relation_ou_invite(profils["exemple-ouvert"])


def test_la_recherche_exclut_le_reseau_direct():
    """Filtre LinkedIn « 2e et 3e degré et + » : les relations directes ne
    remontent même pas."""
    from utils.requete_linkedin import construire_url_recherche
    url = construire_url_recherche("Product Owner", [], [], resoudre_urn=lambda e: None)
    assert "network=%5B%22S%22%2C%22O%22%5D" in url
