# -*- coding: utf-8 -*-
"""Une requête mal formée ou trop ambitieuse ne doit plus rendre zéro résultat.

Trois défauts constatés en réel chez une utilisatrice :
  - une parenthèse oubliée dans ses mots-clés, que notre code enveloppait,
    produisant une expression booléenne invalide — LinkedIn renvoie alors
    « Aucun résultat » sans la moindre erreur ;
  - trois écoles sans identifiant faisaient basculer la TOTALITÉ du filtre
    école en recherche textuelle, bien moins fiable ;
  - un plafond de 10 écoles, inventé sans fondement, en écartait 31 sur 41
    en silence.
"""

import urllib.parse

import pytest

from config import ECOLES
from scraper_v2 import LinkedInScraperV2
from utils.search_filters import ecoles_sans_identifiant, equilibrer_parentheses


@pytest.fixture
def scraper():
    return LinkedInScraperV2(use_database=False)


def _keywords(url: str) -> str:
    return urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("keywords", [""])[0]


def _params(url: str) -> dict:
    return {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(url).query).items()}


# --- Réparation des parenthèses -------------------------------------------


def test_une_fermante_manquante_est_ajoutee():
    assert equilibrer_parentheses('("A" OR ("B")') == '("A" OR ("B"))'


def test_une_fermante_orpheline_est_retiree():
    assert equilibrer_parentheses('"A") OR "B"') == '"A" OR "B"'


def test_une_requete_correcte_n_est_pas_touchee():
    correcte = '("A" OR "B") AND "C"'
    assert equilibrer_parentheses(correcte) == correcte


def test_la_requete_envoyee_est_toujours_equilibree(scraper):
    # Le cas reel : sa saisie avait une ouvrante de trop.
    url = scraper.construire_url_recherche(
        '("Product Builder IA" OR ("Senior PM IA")',
        entreprises=["Boite Inconnue"], ecoles_ids=[],
    )
    q = _keywords(url)
    assert q.count("(") == q.count(")"), q


# --- Écoles sans identifiant ----------------------------------------------


def test_les_ecoles_sans_identifiant_sont_nommees():
    assert set(ecoles_sans_identifiant(list(ECOLES.values()))) == {
        "Bootcamp Noé", "ESGI", "ESITV"
    }


def test_une_ecole_sans_identifiant_n_empoisonne_plus_le_filtre(scraper):
    """Avant : une seule école sans identifiant faisait basculer tout le
    filtre en texte. Désormais elle est écartée, le filtre précis demeure."""
    url = scraper.construire_url_recherche(
        "Product Manager", entreprises="",
        ecoles_ids=[ECOLES["Dauphine"], ECOLES["ESGI"], ECOLES["ESCP"]],
    )
    params = _params(url)
    assert params["schoolFilter"] == '["15092700","308907"]'
    assert "ESGI" not in params["keywords"]


def test_sans_aucun_identifiant_le_repli_textuel_demeure(scraper):
    # Sinon il n'y aurait plus aucun critere d'ecole du tout.
    url = scraper.construire_url_recherche(
        "", entreprises="", ecoles_ids=[ECOLES["ESGI"], ECOLES["ESITV"]],
    )
    params = _params(url)
    assert "schoolFilter" not in params
    assert "ESGI" in params["keywords"] and "ESITV" in params["keywords"]


# --- Plus de plafond sur les écoles ---------------------------------------


def test_toutes_les_ecoles_peuvent_etre_selectionnees(scraper):
    """Le plafond de 10 n'avait aucun fondement : l'URL complete fait 742
    caracteres pour une limite pratique de 8 000, et les identifiants sont
    deja connus localement — aucun appel reseau."""
    url = scraper.construire_url_recherche(
        "Product Manager", entreprises="", ecoles_ids=list(ECOLES.values()),
    )
    avec_id = [i for i in ECOLES.values() if str(i).isdigit()]
    assert _params(url)["schoolFilter"].count(",") == len(avec_id) - 1
