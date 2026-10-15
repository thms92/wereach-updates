# -*- coding: utf-8 -*-
"""Le vrai JavaScript de lecture de la recherche d'entreprises, dans un Chromium local.

Fixture inventée, structure copiée de la capture réelle du 2026-10-15
(gardée hors dépôt) : dans <main>, une liste `role="list"` dont chaque
entrée est un lien vers la page de l'entreprise enveloppant un titre
(`<div id>` avec le lien du nom) et la carte `role="listitem"` qui le
désigne par `aria-labelledby`. Le HTML imbrique des <a> dans un <a> : le
navigateur les défait, d'où des liens vides hors de la carte. Une carte
peut aussi porter un lien « X suit cette page » vers la même entreprise,
dont le texte n'est pas son nom. Réseau coupé : rien ne sort.
"""

import pytest

from utils.dom_selectors import DOMSelectors

playwright = pytest.importorskip("playwright.sync_api")


def entree(ident, slug, nom, secteur, extra="", lien_nom=None):
    lien_nom = lien_nom or f"https://www.linkedin.com/company/{slug}/"
    return f"""<div><a href="https://www.linkedin.com/company/{slug}/">
      <div id="{ident}"><a href="{lien_nom}">{nom}</a><span> </span><svg></svg></div>
      <div role="listitem" aria-labelledby="{ident}"><div>
        <figure><img alt="" src="data:,"></figure>
        <div><p><a href="{lien_nom}">{nom}</a><span> </span></p>
          <div><p><span>{secteur}</span></p></div><div><p><span>Paris</span></p></div></div>
        <div><button type="button" aria-label="Suivre {nom}">Suivre</button></div>
        <div><p><span><strong>Orbique</strong> accompagne les entreprises…</span></p>
          <p><span><a href="https://www.linkedin.com/search/results/people/?currentCompany=%5B%221%22%5D">12 personnes de votre entreprise ont été recrutées ici</a> · 3 000 abonnés</span></p>
          {extra}</div>
      </div></div>
    </a></div><hr role="presentation">"""


PAGE = f"""<!doctype html><html><body>
<header><a href="https://www.linkedin.com/company/pub-orbique/">Publicité Orbique</a></header>
<main id="workspace"><section aria-label="Contenu principal"><p>4 résultats</p>
<div role="list">
{entree("t1", "orbique-assurances", "Orbique Assurances", "Assurances",
        lien_nom="https://www.linkedin.com/company/orbique-assurances/?trk=recherche")}
{entree("t2", "orbique", "Orbique", "Services bancaires")}
{entree("t3", "orbique-leasing", "Groupe Orbique Leasing", "Location")}
{entree("t4", "orbique-immobilier", "Orbique Immobilier", "Immobilier",
        extra='<a href="https://www.linkedin.com/company/orbique-immobilier/?showInNetworkFollowers=true">'
              'Jeanne Exemple et 3 autres relations suivent cette page</a>')}
</div></section></main>
<aside><a href="https://www.linkedin.com/company/hors-main/">Hors main</a></aside>
</body></html>"""

PAGE_SANS_CARTE = """<html><body><main><h2>Aucun résultat</h2>
<p>Essayez d'autres termes de recherche.</p></main></body></html>"""


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
    return page.evaluate(DOMSelectors.extract_recherche_entreprises_js())


def test_les_cartes_sont_lues_dans_l_ordre_avec_leur_lien_canonique(navigateur):
    assert lire(navigateur, PAGE)["resultats"] == [
        {"nom": "Orbique Assurances", "url": "https://www.linkedin.com/company/orbique-assurances/"},
        {"nom": "Orbique", "url": "https://www.linkedin.com/company/orbique/"},
        {"nom": "Groupe Orbique Leasing", "url": "https://www.linkedin.com/company/orbique-leasing/"},
        {"nom": "Orbique Immobilier", "url": "https://www.linkedin.com/company/orbique-immobilier/"},
    ]


def test_pas_de_html_quand_des_cartes_sont_lues(navigateur):
    assert lire(navigateur, PAGE)["html"] == ""


def test_sans_titre_designe_le_nom_vient_du_lien_de_la_carte(navigateur):
    # Si LinkedIn retire `aria-labelledby`, le nom reste celui du lien, pas
    # « … suivent cette page ».
    sans_titre = PAGE.replace('aria-labelledby="t4"', "")
    assert lire(navigateur, sans_titre)["resultats"][3]["nom"] == "Orbique Immobilier"


def test_sans_main_rien_n_est_lu_et_le_corps_est_renvoye(navigateur):
    sans_main = PAGE.replace('<main id="workspace">', "<div>").replace("</main>", "</div>")
    r = lire(navigateur, sans_main)
    assert r["resultats"] == []
    assert "Groupe Orbique Leasing" in r["html"]


def test_une_page_sans_carte_renvoie_son_html(navigateur):
    r = lire(navigateur, PAGE_SANS_CARTE)
    assert r["resultats"] == []
    assert "Aucun résultat" in r["html"]
