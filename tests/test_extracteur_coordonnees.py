# -*- coding: utf-8 -*-
"""Les vrais JavaScript du degré de relation et de la fenêtre « Coordonnées ».

Fenêtre « Coordonnées » : fixture inventée, structure copiée de la capture
réelle du 2026-10-15 (gardée hors dépôt) — sur le profil, plusieurs <dialog>
fermés (menus de LinkedIn) et, après le clic, un `<dialog open>` dont l'en-tête
porte « Coordonnées » ; chaque rubrique est un `<p>` libellé (« Votre profil »,
« E-mail »…) suivi d'un `<p>` avec la valeur, l'email en lien `mailto:`.

Degrés : aucune capture d'une page de résultats de personnes n'existe ; la
forme « Nom · 1er » dans des cartes `div[role="listitem"]` est celle vue sur
d'autres listes LinkedIn. D'où un extracteur tolérant (« • », anglais).
Réseau coupé : rien ne sort.
"""

import pytest

from utils.dom_selectors import DOMSelectors

playwright = pytest.importorskip("playwright.sync_api")


DIALOGUE_FERME = """<dialog class="m"><button type="button" aria-label="Fermer"></button>
<div><header><h2>Envoyer le profil</h2></header><div><button type="button"><div><p>Par message</p>
<p>Partager en privé</p></div></button></div></div></dialog>"""


def rubrique(libelle, valeur_html):
    return f"""<div componentkey="k"><svg aria-hidden="true"></svg><div>
      <p class="t">{libelle}</p><p class="v">{valeur_html}</p></div></div>"""


def profil(*rubriques, titre="Coordonnées"):
    return f"""<!doctype html><html><body><main><h1>Jeanne Exemple</h1>
<a href="https://www.linkedin.com/in/jeanne-exemple/overlay/contact-info/">Coordonnées</a></main>
{DIALOGUE_FERME}
<dialog class="d" data-testid="dialog" aria-labelledby="h" open>
  <button type="button" aria-label="Fermer"><span><svg></svg></span></button>
  <div><header id="h"><h2>{titre}</h2></header>
    <div data-testid="contenu"><div data-sdui-screen="x"><div><div componentkey="a"><div id="b">
      <div><div data-testid="liste" data-component-type="x">{"".join(rubriques)}</div>
      <div><hr role="presentation"><a aria-disabled="false" href="https://www.linkedin.com/x">
        <span><span>Modifier les coordonnées</span></span></a></div></div>
    </div></div></div></div></div>
  </div>
</dialog>
{DIALOGUE_FERME}
</body></html>"""


VOTRE_PROFIL = rubrique("Votre profil",
                        '<a href="https://www.linkedin.com/in/jeanne-exemple">linkedin.com/in/jeanne-exemple</a>')


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


def coordonnees(page, html):
    page.set_content(html)
    return page.evaluate(DOMSelectors.extract_coordonnees_js())


def test_email_partage(navigateur):
    lu = coordonnees(navigateur, profil(
        VOTRE_PROFIL,
        rubrique("E-mail", '<a href="mailto:jeanne.exemple@orbique.example" target="_blank">'
                           'jeanne.exemple@orbique.example</a>')))
    assert lu == {"dialogue": True, "email": "jeanne.exemple@orbique.example", "telephone": "", "html": ""}


def test_telephone_en_lien_et_en_texte(navigateur):
    en_lien = coordonnees(navigateur, profil(
        VOTRE_PROFIL, rubrique("Téléphone", '<a href="tel:+33612345678">+33 6 12 34 56 78</a> (Mobile)')))
    assert en_lien["telephone"] == "+33612345678" and en_lien["email"] == ""
    en_texte = coordonnees(navigateur, profil(
        VOTRE_PROFIL, rubrique("Téléphone", '<span>06 12 34 56 78</span> <span>(Travail)</span>')))
    assert en_texte == {"dialogue": True, "email": "", "telephone": "06 12 34 56 78", "html": ""}


def test_rien_de_partage(navigateur):
    lu = coordonnees(navigateur, profil(VOTRE_PROFIL))
    # Fenêtre lue (rubrique reconnue) : rien n'est partagé, ce n'est pas une panne.
    assert lu == {"dialogue": True, "email": "", "telephone": "", "html": ""}


def test_fenetre_ouverte_mais_illisible_renvoie_son_html(navigateur):
    lu = coordonnees(navigateur, profil(rubrique("Rubrique inconnue", "quelque chose")))
    assert lu["dialogue"] is True and lu["email"] == "" and lu["telephone"] == ""
    assert "Rubrique inconnue" in lu["html"]


def test_aucune_fenetre_ouverte_renvoie_la_page(navigateur):
    html = profil(VOTRE_PROFIL).replace(" open>", ">")
    lu = coordonnees(navigateur, html)
    assert lu["dialogue"] is False and lu["email"] == "" and lu["telephone"] == ""
    assert "Jeanne Exemple" in lu["html"]


def test_en_anglais(navigateur):
    lu = coordonnees(navigateur, profil(
        rubrique("Your Profile", '<a href="https://www.linkedin.com/in/jeanne-exemple">x</a>'),
        rubrique("Email", '<a href="mailto:jeanne@orbique.example">jeanne@orbique.example</a>'),
        rubrique("Phone", "<span>+33 6 12 34 56 78 (Mobile)</span>"),
        titre="Contact info"))
    assert lu == {"dialogue": True, "email": "jeanne@orbique.example", "telephone": "+33 6 12 34 56 78",
                  "html": ""}


# ── Degré de relation sur les résultats de personnes ───────────────────

def carte_personne(vanity, nom, degre_texte, titre="Product Manager chez Orbique"):
    return f"""<div role="listitem"><div><a href="https://www.linkedin.com/in/{vanity}/?miniProfileUrn=x">
      <img alt="" src="data:,"></a>
      <div><a href="https://www.linkedin.com/in/{vanity}/?miniProfileUrn=x"><span>{nom}</span></a>
        <span>{degre_texte}</span></div>
      <div>{titre}</div><div>Paris</div>
      <button type="button">Se connecter</button></div></div>"""


RESULTATS = f"""<!doctype html><html><body><main><div role="list">
{carte_personne("jeanne-exemple", "Jeanne Exemple", " · 1er")}
{carte_personne("paul-exemple", "Paul Exemple", "• 2e")}
{carte_personne("C%C3%A9line-Exemple", "Céline Exemple", "· 3e et +")}
{carte_personne("john-example", "John Example", "• 1st")}
{carte_personne("anne-exemple", "Anne Exemple", "")}
<div role="listitem"><p>Personnes que vous pourriez connaître · 2e</p></div>
</div></main></body></html>"""


def test_degres_lus_sur_les_cartes(navigateur):
    navigateur.set_content(RESULTATS)
    assert navigateur.evaluate(DOMSelectors.extract_degres_js()) == {
        "jeanne-exemple": "1er", "paul-exemple": "2e", "céline-exemple": "3e", "john-example": "1er"}


def test_aucune_carte_aucun_degre(navigateur):
    navigateur.set_content("<html><body><main><p>Aucun résultat</p></main></body></html>")
    assert navigateur.evaluate(DOMSelectors.extract_degres_js()) == {}


def test_un_titre_contenant_1er_n_est_pas_un_degre(navigateur):
    # Le badge est seul en fin de ligne ; « · 1er cabinet » dans un titre ne
    # doit pas faire passer une inconnue pour une relation (page perdue, et
    # ses coordonnées publiques lues hors relation).
    navigateur.set_content(f"""<html><body><main><div role="list">
    {carte_personne("lea-exemple", "Léa Exemple", "", titre="Consultante · 1er cabinet de conseil")}
    {carte_personne("max-example", "Max Example", "", titre="Founder • 1st time founder, ex-Orbique")}
    {carte_personne("noe-exemple", "Noé Exemple", "• 3e", titre="Directeur · 1er réseau de franchise")}
    </div></main></body></html>""")
    assert navigateur.evaluate(DOMSelectors.extract_degres_js()) == {"noe-exemple": "3e"}


def test_un_badge_seul_sur_sa_ligne_est_lu(navigateur):
    navigateur.set_content("""<html><body><main><div role="list"><div role="listitem">
      <a href="https://www.linkedin.com/in/jeanne-exemple/">Jeanne Exemple</a>
      <div>· 1er</div><div>Consultante · 1er cabinet de conseil</div></div></div></main></body></html>""")
    assert navigateur.evaluate(DOMSelectors.extract_degres_js()) == {"jeanne-exemple": "1er"}


# ── La fenêtre sur le profil de quelqu'un d'autre ──────────────────────
# Libellés différents de ceux de son propre profil : « Profil de Jeanne »,
# « Relation depuis », sans « Modifier les coordonnées ».

PROFIL_D_AUTRUI = rubrique("Profil de Jeanne",
                           '<a href="https://www.linkedin.com/in/jeanne-exemple">linkedin.com/in/jeanne-exemple</a>')
RELATION = rubrique("Relation depuis", "<span>12 mars 2024</span>")


def test_autrui_qui_ne_partage_rien_est_lu(navigateur):
    lu = coordonnees(navigateur, profil(PROFIL_D_AUTRUI, RELATION))
    assert lu == {"dialogue": True, "email": "", "telephone": "", "html": ""}


def test_autrui_avec_seulement_le_lien_de_son_profil_est_lu(navigateur):
    # Libellé inconnu, mais le lien du profil dans la fenêtre suffit : c'est
    # bien la fenêtre « Coordonnées » de quelqu'un, qui ne partage rien.
    lu = coordonnees(navigateur, profil(rubrique(
        "Libellé jamais vu", '<a href="https://www.linkedin.com/in/jeanne-exemple/">linkedin.com/in/jeanne-exemple</a>')))
    assert lu == {"dialogue": True, "email": "", "telephone": "", "html": ""}


def test_autrui_qui_partage_email_et_telephone(navigateur):
    lu = coordonnees(navigateur, profil(
        PROFIL_D_AUTRUI,
        rubrique("E-mail", '<a href="mailto:jeanne@orbique.example">jeanne@orbique.example</a>'),
        rubrique("Téléphone", "<span>06 12 34 56 78</span> <span>(Mobile)</span>"),
        RELATION))
    assert lu == {"dialogue": True, "email": "jeanne@orbique.example", "telephone": "06 12 34 56 78", "html": ""}


def test_autrui_en_anglais(navigateur):
    lu = coordonnees(navigateur, profil(
        rubrique("Jeanne’s Profile", '<a href="https://www.linkedin.com/in/jeanne-exemple">x</a>'),
        rubrique("Connected", "<span>Mar 12, 2024</span>"), titre="Contact info"))
    assert lu == {"dialogue": True, "email": "", "telephone": "", "html": ""}


def test_l_attente_ne_reconnait_que_la_fenetre_coordonnees(navigateur):
    ouverte = DOMSelectors.fenetre_coordonnees_ouverte_js()
    navigateur.set_content(profil(PROFIL_D_AUTRUI))
    assert navigateur.evaluate(ouverte) is True
    navigateur.set_content(profil(PROFIL_D_AUTRUI).replace(" open>", ">"))
    assert navigateur.evaluate(ouverte) is False
    autre = profil(PROFIL_D_AUTRUI, titre="Envoyer le profil")
    navigateur.set_content(autre.replace("Coordonnées", "Lien").replace("Modifier les coordonnées", "Modifier"))
    assert navigateur.evaluate(ouverte) is False
