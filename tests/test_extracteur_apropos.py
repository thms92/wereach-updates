# -*- coding: utf-8 -*-
"""Le vrai JavaScript de lecture « À propos », exécuté dans un Chromium local.

Fixture inventée, structure copiée de la capture réelle du 2026-10-15 :
<dl> avec <dt>/<dd>, apostrophe typographique dans « Taille de l’entreprise »,
lien « voir les employés » porteur de currentCompany, et d'autres titres
(« 0 notification au total ») hors de <main>. Réseau coupé : rien ne sort.
"""

import pytest

from utils.dom_selectors import DOMSelectors

playwright = pytest.importorskip("playwright.sync_api")

PAGE = """<!doctype html><html><body>
<header><h1>0 notification au total</h1></header>
<main>
  <aside><a href="http://www.linkedin.com/search/results/people/?origin=COMPANY_PAGE_CANNED_SEARCH&currentCompany=%5B%22227766%22%5D">Autre société</a></aside>
  <section><h1>Orbique</h1>
    <a href="https://www.linkedin.com/search/results/people/?currentCompany=%5B%227654321%22%5D&origin=COMPANY_PAGE_CANNED_SEARCH">Voir les 198 employés</a>
    <a href="/search/results/people/?origin=X&currentCompany=%5B%227654321%22%5D&pastCompany=%5B%22166%22%5D">12 anciens employés</a>
  </section>
  <section><h2>Vue d’ensemble</h2><p>Orbique conseille   les entreprises
  sur le produit.</p>
    <dl>
      <dt><h3>Site web</h3></dt><dd><a href="https://www.orbique.example">https://www.orbique.example</a></dd>
      <dt><h3>Téléphone</h3></dt><dd><a href="tel:+33 1 00 00 00 00"><span aria-hidden="true">
        +33 1 00 00 00 00
      </span><span class="visually-hidden">
        Le numéro de téléphone est le +33 1 00 00 00 00
      </span></a></dd>
      <dt><h3>Page vérifiée</h3></dt><dd>1 juin 2024</dd>
      <dt><h3>Secteur</h3></dt><dd>Services et conseil aux entreprises</dd>
      <dt><h3>Taille de l’entreprise</h3></dt><dd>201-500 employés</dd><dd>198 membres associés</dd>
      <dt><h3>Siège social</h3></dt><dd>Paris, Paris</dd>
      <dt><h3>Fondée en</h3></dt><dd>2014</dd>
      <dt><h3>Spécialisations</h3></dt><dd>Product Management, Discovery</dd>
    </dl>
  </section>
  <aside><h2>Pages également consultées</h2>
    <a href="https://www.linkedin.com/search/results/people/?currentCompany=%5B%221111%22%5D">Autre</a></aside>
</main></body></html>"""

PAGE_SANS_DL = "<html><body><main><h1>Orbique</h1><p>Contenu inattendu</p></main></body></html>"


@pytest.fixture(scope="module")
def navigateur():
    with playwright.sync_playwright() as p:
        try:
            b = p.chromium.launch(headless=True)
        except Exception as e:
            pytest.skip(f"Chromium indisponible : {e}")
        page = b.new_page()
        page.route("**/*", lambda route: route.abort())
        yield page
        b.close()


def lire(page, html):
    page.set_content(html)
    return page.evaluate(DOMSelectors.extract_page_apropos_js())


def test_les_rubriques_sont_lues(navigateur):
    r = lire(navigateur, PAGE)
    assert r["champs"]["Site web"] == ["https://www.orbique.example"]
    assert r["champs"]["Taille de l’entreprise"] == ["201-500 employés", "198 membres associés"]
    assert r["champs"]["Siège social"] == ["Paris, Paris"]
    assert r["champs"]["Téléphone"] == ["+33 1 00 00 00 00"]


def test_le_nom_vient_de_main_et_pas_de_l_en_tete(navigateur):
    assert lire(navigateur, PAGE)["nom"] == "Orbique"


def test_l_identifiant_est_celui_de_la_majorite_des_liens_de_main(navigateur):
    # Un lien d'une autre société précède les deux liens propres.
    assert lire(navigateur, PAGE)["company_id"] == "7654321"


def test_une_egalite_entre_deux_identifiants_donne_vide(navigateur):
    html = """<main><h1>Orbique</h1>
    <a href="/x?currentCompany=%5B%22111%22%5D">a</a>
    <a href="/x?currentCompany=%5B%22222%22%5D">b</a></main>"""
    assert lire(navigateur, html)["company_id"] == ""


def test_la_description(navigateur):
    assert lire(navigateur, PAGE)["description"] == "Orbique conseille les entreprises sur le produit."


def test_pas_de_html_renvoye_quand_tout_est_lu(navigateur):
    assert lire(navigateur, PAGE)["html"] == ""


def test_une_page_inattendue_renvoie_son_html(navigateur):
    r = lire(navigateur, PAGE_SANS_DL)
    assert r["champs"] == {} and r["company_id"] == ""
    assert "Contenu inattendu" in r["html"]
