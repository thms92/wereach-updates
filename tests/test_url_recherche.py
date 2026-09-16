# -*- coding: utf-8 -*-
"""Construction de l'URL de recherche LinkedIn (multi-écoles, multi-entreprises, secteurs).

Rappel de la sémantique LinkedIn : les valeurs d'une MÊME facette sont
combinées en OU, et les facettes entre elles en ET.
"""

import urllib.parse

import pytest

from scraper_v2 import LinkedInScraperV2


@pytest.fixture
def scraper():
    return LinkedInScraperV2(use_database=False)


def _params(url: str) -> dict:
    """Décode la query string en dict {param: valeur décodée}."""
    query = urllib.parse.urlparse(url).query
    return {k: v[0] for k, v in urllib.parse.parse_qs(query).items()}


# --- Entreprises ---------------------------------------------------------


def test_plusieurs_entreprises_resolues_tiennent_dans_une_facette(scraper):
    # "thiga" et "kering" sont dans le seed config.COMPANY_URNS
    url = scraper.construire_url_recherche(
        "Product Manager", ["Thiga", "Kering"], []
    )
    assert _params(url)["currentCompany"] == '["4998677","165528"]'


def test_une_entreprise_non_resolue_bascule_toute_la_facette_en_mots_cles(scraper):
    url = scraper.construire_url_recherche(
        "Product Manager", ["Thiga", "Zzz Inconnue SAS"], []
    )
    params = _params(url)
    assert "currentCompany" not in params
    assert params["keywords"] == 'Product Manager AND ("Thiga" OR "Zzz Inconnue SAS")'


def test_entreprise_unique_en_chaine_reste_supportee(scraper):
    url = scraper.construire_url_recherche("Product Manager", "Thiga", [])
    assert _params(url)["currentCompany"] == '["4998677"]'


# --- Écoles --------------------------------------------------------------


def test_plusieurs_ecoles_numeriques_tiennent_dans_une_facette(scraper):
    # Dauphine=15092700, ESCP=308907
    url = scraper.construire_url_recherche("", "", ["15092700", "308907"])
    assert _params(url)["schoolFilter"] == '["15092700","308907"]'


def test_une_ecole_sans_id_bascule_toute_la_facette_en_mots_cles(scraper):
    # "Bootcamp Noé" n'a pas d'ID numérique dans ECOLES : repli par nom,
    # et Dauphine repart en mot-clé avec elle pour préserver le OU.
    url = scraper.construire_url_recherche("", "", ["15092700", "Bootcamp Noé"])
    params = _params(url)
    assert "schoolFilter" not in params
    assert params["keywords"] == '"Dauphine" OR "Bootcamp Noé"'


# --- Secteurs ------------------------------------------------------------


def test_les_secteurs_ajoutent_la_facette_industry(scraper):
    url = scraper.construire_url_recherche(
        "Data", "", [], secteurs_ids=["11", "4"]
    )
    assert _params(url)["industry"] == '["11","4"]'


def test_aucun_secteur_ne_produit_pas_de_facette_industry(scraper):
    url = scraper.construire_url_recherche("Data", "", [], secteurs_ids=[])
    assert "industry" not in _params(url)


# --- Combinaison et encodage --------------------------------------------


def test_ecoles_entreprises_et_secteurs_coexistent(scraper):
    url = scraper.construire_url_recherche(
        "PM", ["Thiga"], ["15092700"], secteurs_ids=["11"]
    )
    params = _params(url)
    assert params["currentCompany"] == '["4998677"]'
    assert params["schoolFilter"] == '["15092700"]'
    assert params["industry"] == '["11"]'


def test_la_facette_est_encodee_au_format_attendu_par_linkedin(scraper):
    url = scraper.construire_url_recherche("", ["Thiga", "Kering"], [])
    assert "currentCompany=%5B%224998677%22%2C%22165528%22%5D" in url


def test_une_facette_est_plafonnee_a_dix_valeurs(scraper):
    ecoles = [str(1000 + i) for i in range(15)]
    url = scraper.construire_url_recherche("", "", ecoles)
    assert _params(url)["schoolFilter"].count(",") == 9


def test_un_repli_sans_mot_cle_n_est_pas_entierement_parenthese(scraper):
    # LinkedIn renvoie 0 résultat quand TOUTE la requête est entourée d'une
    # seule paire de parenthèses — cf. _normalize_keyword.
    url = scraper.construire_url_recherche("", ["Zzz Un SAS", "Zzz Deux SAS"], [])
    keywords = _params(url)["keywords"]
    assert not (keywords.startswith("(") and keywords.endswith(")"))
    assert keywords == '"Zzz Un SAS" OR "Zzz Deux SAS"'
