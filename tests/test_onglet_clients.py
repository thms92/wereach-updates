# -*- coding: utf-8 -*-
"""Onglet « Clients/Entreprises » : même saisie, même filtre que « Candidats ».

Les deux onglets de la page Recherche proposent le même champ « entreprises ».
Ils doivent comprendre la même chose : « Thiga, Kering » vise deux sociétés,
pas une seule dont le nom contient une virgule. Faute de quoi LinkedIn ne
renvoie rien et l'app accuse à tort le filtre entreprise de n'avoir pas été
résolu.
"""

import pandas as pd
import pytest

import scraper_v2_sync
from tests.conftest import lancer_app, verifier_page_affichee

SAISIE = "Thiga, Kering"
LIBELLE_CANDIDATS = "Entreprises (optionnel)"
BOUTON_CANDIDATS = "🔍 Lancer le scraping"
BOUTON_CLIENTS = "🔍 Lancer recherche clients"


@pytest.fixture
def scraper_espion(monkeypatch):
    """Remplace le scraper par un espion : rien n'est lancé, tout est capturé."""
    appels = []

    class FauxScraper:
        def __init__(self, **kwargs):
            self.errors = []

        def run_scraper(self, **kwargs):
            appels.append(kwargs)
            return pd.DataFrame()

    monkeypatch.setattr(scraper_v2_sync, "LinkedInScraperV2Sync", FauxScraper)
    return appels


def _page_recherche():
    at = lancer_app("🔍 Recherche")
    verifier_page_affichee(at, "🔍 Recherche")
    # Un cookie est exigé avant de lancer une recherche.
    at.session_state["global_cookie"] = "COOKIE-DE-TEST"
    return at


def _bouton(at, libelle):
    return [b for b in at.button if b.label == libelle][0]


def _entreprises_transmises(at, appels, libelle_bouton) -> list:
    _bouton(at, libelle_bouton).click()
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert len(appels) == 1, f"le scraper a été appelé {len(appels)} fois"
    return appels[-1]["entreprises"]


def test_l_onglet_clients_decoupe_les_entreprises_sur_les_virgules(scraper_espion):
    at = _page_recherche()
    at.text_input(key="entreprise_client").set_value(SAISIE)

    assert _entreprises_transmises(at, scraper_espion, BOUTON_CLIENTS) == [
        "Thiga", "Kering"
    ]


def test_les_deux_onglets_comprennent_la_meme_saisie(scraper_espion):
    at = _page_recherche()
    champ_candidats = [t for t in at.text_input if t.label == LIBELLE_CANDIDATS][0]
    champ_candidats.set_value(SAISIE)
    cote_candidats = _entreprises_transmises(at, scraper_espion, BOUTON_CANDIDATS)

    scraper_espion.clear()
    at.text_input(key="entreprise_client").set_value(SAISIE)
    cote_clients = _entreprises_transmises(at, scraper_espion, BOUTON_CLIENTS)

    assert cote_clients == cote_candidats


def test_une_saisie_vide_ne_transmet_aucune_entreprise(scraper_espion):
    at = _page_recherche()
    at.text_input(key="entreprise_client").set_value("")

    assert _entreprises_transmises(at, scraper_espion, BOUTON_CLIENTS) == []


def test_le_champ_entreprises_des_clients_annonce_la_virgule():
    at = _page_recherche()
    champ_clients = at.text_input(key="entreprise_client")
    champ_candidats = [t for t in at.text_input if t.label == LIBELLE_CANDIDATS][0]

    assert champ_clients.label.startswith("Entreprises")
    assert "virgule" in champ_clients.help.lower(), (
        "l'onglet voisin annonce la virgule, celui-ci doit le faire aussi : "
        f"aide actuelle = {champ_clients.help!r}"
    )
    assert "virgule" in champ_candidats.help.lower()
