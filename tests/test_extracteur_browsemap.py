# -*- coding: utf-8 -*-
"""L'extracteur JavaScript du panneau, exécuté pour de vrai sur un DOM fictif.

Pourquoi un vrai navigateur ici : le premier essai réel a lu zéro profil alors
que tous les tests passaient. L'extracteur n'était vérifié que par la présence
de quelques mots dans sa source ; il choisissait en fait un dialogue caché du
lecteur vidéo (video.js) et cherchait des `<li>` qui n'existent plus. Seule
une exécution sur un DOM qui reproduit la structure réelle attrape ce genre
d'erreur.

Les pages ci-dessous imitent fidèlement la structure relevée sur LinkedIn lors
de cet essai — dialogues video.js cachés AVANT le panneau, `<dialog>` natifs
vides, un `<dialog open>` dont les cartes sont de simples `div` imbriqués, des
liens doublés par carte, un vanity encodé —, mais tout y est inventé : noms,
vanity, entreprises. Aucune donnée réelle n'entre dans le dépôt.

Garanties de sûreté : le Chromium headless est lancé une fois pour le module ;
le HTML est injecté par `set_content`, jamais par une navigation, et toute
requête réseau (images, etc.) est interrompue avant de partir.
"""

import pytest

from utils.dom_selectors import DOMSelectors

REF = "https://www.linkedin.com/in/ref-exemple/"
LIEN_TOUT_AFFICHER = REF + "overlay/browsemap-recommendations/"


# ---------------------------------------------------------------------------
# Construction du DOM fictif
# ---------------------------------------------------------------------------


def carte(href, nom, degre, intitule, bouton="Se connecter", aria=None, extra=""):
    """Une carte telle que LinkedIn la rend : pas de li, des div imbriqués.

    Le lien du profil y figure plusieurs fois (avatar, bloc texte, nom) —
    c'est ce qui rend la déduplication nécessaire, et la carte doit être
    trouvée à partir de n'importe lequel d'entre eux.
    """
    if aria is None:
        aria = (f"Inviter {nom} à rejoindre votre réseau" if bouton == "Se connecter"
                else f"{bouton} {nom}")
    return f"""
<div>
 <div><div>
  <div data-display-contents="true">
   <a tabindex="0" href="{href}"></a>
   <div>
    <a tabindex="0" href="{href}"><figure aria-hidden="true"><img alt=""></figure></a>
    <div>
     <a tabindex="0" href="{href}"></a>
     <div>
      <a tabindex="0" href="{href}"></a>
      <div>
       <a tabindex="0" href="{href}"></a>
       <p><a tabindex="0" href="{href}"><span></span></a><a href="{href}">{nom}</a></p>
      </div>
      <p>· {degre}</p>
     </div>
     <div><p><span>{intitule}</span></p></div>
     {extra}
    </div>
   </div>
  </div>
 </div></div>
 <div><div><div data-display-contents="true"><div><div data-display-contents="true">
  <button type="button" aria-label="{aria}"><span><div><span><span>{bouton}</span></span></div></span></button>
 </div></div></div></div></div>
</div>"""


def liste(*cartes):
    return '<hr role="presentation">'.join(cartes)


# Les parasites relevés sur la vraie page, placés AVANT le panneau : c'est
# exactement ce qui a trompé l'ancien extracteur.
PARASITES = """
<div class="vjs-error-display vjs-modal-dialog vjs-hidden" role="dialog" tabindex="-1">
  <div class="vjs-modal-dialog-content" role="document"></div>
</div>
<div class="vjs-modal-dialog vjs-hidden vjs-text-track-settings" role="dialog">
  <div class="vjs-modal-dialog-content" role="document"><a href="https://www.linkedin.com/in/piege-video/">piège</a></div>
</div>
<dialog class="obf1 obf2"></dialog>
<dialog class="obf1 obf2"></dialog>
"""

CARTES_SECTION = liste(
    carte("https://www.linkedin.com/in/jeanne-exemple-1a2b3c/", "Jeanne Exemple", "3e",
          "Product Manager @Exemplaire"),
    carte("https://www.linkedin.com/in/marc-fictif/", "Marc Fictif", "2e",
          "Consultant Product Owner"),
    carte("https://www.linkedin.com/in/lucie-inventee/", "Lucie Inventée", "3e",
          "Product Manager", bouton="Suivre"),
)

SECTION_PROFIL = f"""
<section>
 <div><div><div><div><h3><span>Plus de profils pour vous</span></h3></div></div></div></div>
 <div><div>{CARTES_SECTION}</div></div>
 <div><a aria-label="Afficher tout : “Plus de profils pour vous”" href="{LIEN_TOUT_AFFICHER}"><span>Tout afficher</span></a></div>
</section>
"""

# Une autre section de la colonne, avec ses propres profils : la lecture de
# repli ne doit lire que la bonne.
AUTRE_SECTION = f"""
<section>
 <div><h3><span>Personnes que vous pourriez connaître</span></h3></div>
 <div>{liste(carte("https://www.linkedin.com/in/autre-section/", "Hors Sujet", "2e", "Rien à voir"))}</div>
</section>
"""

PROFIL = f"""
<main>
 <section>
  <h1>Référence Exemple</h1>
  <a href="{REF}">Référence Exemple</a>
  <p>Directrice Produit @Societe Modele</p>
 </section>
 <aside>{SECTION_PROFIL}{AUTRE_SECTION}</aside>
</main>
"""

CARTES_PANNEAU = liste(
    carte("https://www.linkedin.com/in/jeanne-exemple-1a2b3c/", "Jeanne Exemple", "3e",
          "Product Manager @Exemplaire"),
    carte("https://www.linkedin.com/in/marc-fictif/", "Marc Fictif", "2e",
          "Consultant Product Owner",
          extra="<div><p>Paul Témoin, Anne Témoin et 12 autres relations en commun</p></div>"),
    carte("https://www.linkedin.com/in/lucie-inventee/", "Lucie Inventée", "3e",
          "Product Manager", bouton="Suivre"),
    carte("https://www.linkedin.com/in/c%C3%A9line-modele/", "Céline Modèle", "3e",
          "Fondatrice @Imaginaire, on recrute !"),
    carte("https://www.linkedin.com/in/hugo-imaginaire/", "Hugo Imaginaire", "2e",
          "Lead Product Designer"),
)

PANNEAU = f"""
<dialog data-testid="dialog" aria-labelledby="dialog-header" open>
 <button type="button" aria-label="Ignorer"><span>✕</span></button>
 <div>
  <header><h2 id="dialog-header">Plus de profils pour vous</h2></header>
  <div data-testid="dialog-content">
   <div data-sdui-screen="com.exemple.ProfileOverlayBrowsemap">
    <div data-testid="lazy-column"><div>{CARTES_PANNEAU}</div></div>
   </div>
  </div>
 </div>
</dialog>
"""


def page_html(*morceaux):
    return "<!doctype html><html><body>" + "".join(morceaux) + "</body></html>"


# Page après le clic sur « Tout afficher » : le profil reste dessous.
PAGE_PANNEAU_OUVERT = page_html(PARASITES, PROFIL, PANNEAU)
# Page du profil sans panneau ouvert : seule la section de la colonne existe.
PAGE_PROFIL_SEUL = page_html(PARASITES, PROFIL)


# ---------------------------------------------------------------------------
# Navigateur
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def navigateur():
    """Un seul Chromium headless pour tout le module : la suite reste rapide."""
    sync_api = pytest.importorskip("playwright.sync_api")
    try:
        pw = sync_api.sync_playwright().start()
    except Exception as err:  # pragma: no cover - dépend du poste
        pytest.skip(f"Playwright indisponible : {err}")
    try:
        browser = pw.chromium.launch(headless=True)
    except Exception as err:  # pragma: no cover - dépend du poste
        pw.stop()
        pytest.skip(f"Chromium headless ne se lance pas sur ce poste : {err}")
    yield browser
    browser.close()
    pw.stop()


@pytest.fixture
def evaluer(navigateur):
    """Charge un HTML fictif et y exécute un script, sans aucun accès réseau."""
    contexte = navigateur.new_context()
    # Toute requête est coupée : les fixtures n'en déclenchent pas, mais une
    # image ou un lien chargé par erreur ne doit jamais sortir du poste.
    contexte.route("**/*", lambda route: route.abort())
    page = contexte.new_page()

    def _evaluer(html, js, arg=None):
        page.set_content(html, wait_until="domcontentloaded")
        return page.evaluate(js, arg) if arg is not None else page.evaluate(js)

    yield _evaluer
    contexte.close()


def par_vanity(entrees):
    from utils.browsemap import vanity_depuis_url
    return {vanity_depuis_url(e["url"]): e for e in entrees}


# ---------------------------------------------------------------------------
# Le panneau ouvert
# ---------------------------------------------------------------------------


def test_le_panneau_ouvert_est_lu_carte_par_carte(evaluer):
    brut = evaluer(PAGE_PANNEAU_OUVERT, DOMSelectors.extract_browsemap_js())
    entrees = brut["entrees"]

    lues = {v: (e["nom"], e["degre"], e["intitule"], e["invitable"])
            for v, e in par_vanity(entrees).items()}
    assert lues == {
        "jeanne-exemple-1a2b3c": ("Jeanne Exemple", "3e", "Product Manager @Exemplaire", True),
        "marc-fictif": ("Marc Fictif", "2e", "Consultant Product Owner", True),
        "lucie-inventee": ("Lucie Inventée", "3e", "Product Manager", False),
        "céline-modele": ("Céline Modèle", "3e", "Fondatrice @Imaginaire, on recrute !", True),
        "hugo-imaginaire": ("Hugo Imaginaire", "2e", "Lead Product Designer", True),
    }
    # Une entrée par personne, malgré les six liens de chaque carte.
    assert len(entrees) == 5


def test_le_dialogue_cache_du_lecteur_video_n_est_pas_choisi(evaluer):
    brut = evaluer(PAGE_PANNEAU_OUVERT, DOMSelectors.extract_browsemap_js())

    vanities = set(par_vanity(brut["entrees"]))
    assert "piege-video" not in vanities
    # Ni la colonne du profil dessous, ni le profil de référence.
    assert "autre-section" not in vanities
    assert "ref-exemple" not in vanities
    assert "vjs-modal-dialog" not in brut["html"]
    assert "Plus de profils pour vous" in brut["html"]


def test_les_liens_d_une_carte_ne_fusionnent_pas_les_cartes_voisines(evaluer):
    # Le défaut redouté d'une carte trop haute : tous les noms identiques.
    brut = evaluer(PAGE_PANNEAU_OUVERT, DOMSelectors.extract_browsemap_js())
    assert len({e["nom"] for e in brut["entrees"]}) == len(brut["entrees"])


def test_les_cartes_en_li_restent_lues(evaluer):
    # L'ancienne structure (li) doit continuer de marcher : la règle
    # structurelle la couvre, puisqu'un li ne contient qu'une personne.
    cartes_li = "".join(
        f'<li><a href="https://www.linkedin.com/in/{v}/">{n}</a>'
        f'<p>· 2e</p><p>{i}</p><button aria-label="Inviter {n} à rejoindre votre réseau">Se connecter</button></li>'
        for v, n, i in (("alpha-exemple", "Alpha Exemple", "Data Analyst"),
                        ("beta-exemple", "Beta Exemple", "Product Owner"))
    )
    html = page_html(PARASITES, f'<div role="dialog" aria-modal="true"><ul>{cartes_li}</ul></div>')

    brut = evaluer(html, DOMSelectors.extract_browsemap_js())

    lues = {v: (e["nom"], e["degre"], e["intitule"], e["invitable"])
            for v, e in par_vanity(brut["entrees"]).items()}
    assert lues == {
        "alpha-exemple": ("Alpha Exemple", "2e", "Data Analyst", True),
        "beta-exemple": ("Beta Exemple", "2e", "Product Owner", True),
    }


def test_sans_panneau_ouvert_le_mode_panneau_ne_lit_rien_et_rend_le_html(evaluer):
    # Pas de repli silencieux sur la page : des liens /in/ qui ne sont pas des
    # suggestions vaudraient moins qu'un échec bruyant.
    brut = evaluer(PAGE_PROFIL_SEUL, DOMSelectors.extract_browsemap_js())

    assert brut["entrees"] == []
    assert brut["html"]


def test_le_compteur_du_panneau_ignore_les_dialogues_caches(evaluer):
    assert evaluer(PAGE_PROFIL_SEUL, DOMSelectors.compter_panneau_browsemap_js()) == 0
    assert evaluer(PAGE_PANNEAU_OUVERT, DOMSelectors.compter_panneau_browsemap_js()) == 5


# ---------------------------------------------------------------------------
# La lecture de repli : la section du profil
# ---------------------------------------------------------------------------


def test_la_section_du_profil_est_lue_en_repli(evaluer):
    brut = evaluer(PAGE_PROFIL_SEUL, DOMSelectors.extract_browsemap_js(), "section")

    lues = {v: (e["nom"], e["degre"], e["intitule"], e["invitable"])
            for v, e in par_vanity(brut["entrees"]).items()}
    assert lues == {
        "jeanne-exemple-1a2b3c": ("Jeanne Exemple", "3e", "Product Manager @Exemplaire", True),
        "marc-fictif": ("Marc Fictif", "2e", "Consultant Product Owner", True),
        "lucie-inventee": ("Lucie Inventée", "3e", "Product Manager", False),
    }


def test_la_section_ne_lit_ni_le_lien_tout_afficher_ni_les_autres_sections(evaluer):
    brut = evaluer(PAGE_PROFIL_SEUL, DOMSelectors.extract_browsemap_js(), "section")

    vanities = set(par_vanity(brut["entrees"]))
    assert "ref-exemple" not in vanities      # le lien « Tout afficher »
    assert "autre-section" not in vanities
    assert "piege-video" not in vanities
    assert not any("Tout afficher" in e["nom"] for e in brut["entrees"])


def test_une_page_sans_la_section_ne_lit_rien_en_repli(evaluer):
    html = page_html(PARASITES, f"<main><aside>{AUTRE_SECTION}</aside></main>")

    brut = evaluer(html, DOMSelectors.extract_browsemap_js(), "section")

    assert brut["entrees"] == []
    assert brut["html"]
