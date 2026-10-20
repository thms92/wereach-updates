# -*- coding: utf-8 -*-
"""Construction des recherches, testée sans moteur ni navigateur."""

import urllib.parse

import utils.requete_linkedin as requete


def _params(url):
    return dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))


def test_le_module_se_suffit_avec_un_resolveur_fourni():
    vus = []

    def resoudre(nom):
        vus.append(nom)
        return {"Thiga": "111"}.get(nom)

    url = requete.construire_url_recherche("PM", ["Thiga"], [], resoudre_urn=resoudre)
    assert vus == ["Thiga"]
    assert _params(url)["currentCompany"] == '["111"]'
    assert _params(url)["keywords"] == "PM"


def test_une_entreprise_sans_identifiant_bascule_toute_la_facette_en_mots_cles():
    url = requete.construire_url_recherche(
        "PM", ["Thiga", "Inconnue"], [], resoudre_urn=lambda n: "111" if n == "Thiga" else None)
    p = _params(url)
    assert "currentCompany" not in p
    assert p["keywords"] == 'PM AND ("Thiga" OR "Inconnue")'


def test_le_moteur_delegue_au_module():
    from scraper_v2 import LinkedInScraperV2
    assert LinkedInScraperV2._normalize_keyword is requete.normalize_keyword
    assert LinkedInScraperV2.MAX_VALEURS_PAR_FACETTE == requete.MAX_VALEURS_PAR_FACETTE
