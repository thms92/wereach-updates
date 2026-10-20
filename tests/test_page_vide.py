# -*- coding: utf-8 -*-
import asyncio

from scraper_v2 import lecture_ratee
from utils.dom_selectors import DOMSelectors
from utils.page_vide import diagnostiquer_page_vide


class Page:
    url = "https://www.linkedin.com/search/results/people/?keywords=x"

    def __init__(self, etat):
        self.etat = etat

    async def evaluate(self, js):
        assert js == DOMSelectors.etat_resultats_personnes_js()
        if isinstance(self.etat, Exception):
            raise self.etat
        return self.etat


def _diag(etat, enregistre=True):
    pages = []

    def dumper(html, nom_fichier):
        pages.append((html, nom_fichier))
        return enregistre

    return asyncio.run(diagnostiquer_page_vide(Page(etat), dumper, "x_dump.html")), pages


def test_aucun_resultat_affiche_est_une_absence_sans_enregistrement():
    assert _diag({"aucunResultat": True, "html": "<main/>"}) == (None, [])


def test_sans_aucun_resultat_la_page_est_enregistree():
    ou, pages = _diag({"aucunResultat": False, "html": "<main>cartes</main>"})
    assert ou == "page enregistrée dans logs/"
    assert pages == [("<main>cartes</main>", "x_dump.html")]


def test_un_etat_illisible_n_est_pas_une_absence():
    ou, _ = _diag(RuntimeError("Execution context was destroyed"), enregistre=False)
    assert ou == "page non enregistrée"


def test_le_message_de_la_recherche_dit_quoi_faire():
    m = lecture_ratee("page enregistrée dans logs/")
    assert "aucun profil n'a pu être lu" in m and "Signaler un problème" in m
