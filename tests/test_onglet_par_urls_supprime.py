# -*- coding: utf-8 -*-
"""L'onglet « Par URLs » a été retiré de la page Recherche (2026-10-15).

Jugé sans intérêt à l'usage. Sa chaîne, `run_url_scraper`, reste : l'étape 2
des Profils similaires s'en sert pour lire poste et société et inviter.
"""

from tests.conftest import lancer_app, verifier_page_affichee


def test_la_page_recherche_n_a_plus_d_onglet_par_urls():
    at = lancer_app("🔍 Recherche")
    verifier_page_affichee(at, "🔍 Recherche")

    libelles = [t.label for t in at.tabs]
    assert libelles == [
        "Par critères", "Profils similaires"
    ], libelles


def test_ses_widgets_ont_disparu():
    at = lancer_app("🔍 Recherche")
    cles = {w.key for w in list(at.text_area) + list(at.text_input) + list(at.button)}
    assert not cles & {"urls_input", "cookie_urls", "btn_url_scraping"}, cles
