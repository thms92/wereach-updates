# -*- coding: utf-8 -*-
"""Garde-fous de la récolte des profils voisins, sans lancer de navigateur.

Deux choses se vérifient sans Chrome, et ce sont celles qui cassent : qu'une
URL qui n'est pas un profil soit refusée AVANT tout lancement — sinon on
ouvre un navigateur pour rien et l'erreur arrive deux minutes trop tard — et
que le wrapper synchrone remonte fidèlement ce que la couche async a trouvé.
"""

import asyncio

import pytest

from scraper_v2 import SESSION_EXPIREE, LinkedInScraperV2
from scraper_v2_sync import LinkedInScraperV2Sync
from utils.dom_selectors import DOMSelectors


@pytest.fixture
def scraper(tmp_path):
    return LinkedInScraperV2(use_database=False, config_dir=str(tmp_path))


@pytest.fixture
def sans_navigateur(monkeypatch):
    """Toute tentative de lancer Playwright fait échouer le test."""
    def interdit(*a, **k):
        raise AssertionError("un navigateur a été lancé")
    monkeypatch.setattr("scraper_v2.async_playwright", interdit)


def recolter(scraper, url):
    return asyncio.run(
        scraper.recolter_browsemap_async(cookie="COOKIE-DE-TEST", url_reference=url)
    )


def test_une_page_entreprise_est_refusee_sans_lancer_de_navigateur(scraper, sans_navigateur):
    suggestions, entreprise = recolter(scraper, "https://www.linkedin.com/company/thiga/")

    assert suggestions == []
    assert entreprise is None
    assert any("profil LinkedIn" in e for e in scraper.errors)


def test_une_saisie_vide_est_refusee(scraper, sans_navigateur):
    suggestions, entreprise = recolter(scraper, "")

    assert (suggestions, entreprise) == ([], None)
    assert scraper.errors


def test_le_wrapper_synchrone_remonte_ce_qu_a_trouve_la_couche_async(tmp_path, monkeypatch):
    attendu = ([{"nom": "Jean Dupont", "url": "https://www.linkedin.com/in/jd/"}], "Thiga")
    wrapper = LinkedInScraperV2Sync(use_database=False, config_dir=str(tmp_path))

    async def fausse_recolte(cookie, url_reference, status_callback=None):
        return attendu

    monkeypatch.setattr(wrapper.scraper, "recolter_browsemap_async", fausse_recolte)

    assert wrapper.recolter_browsemap("COOKIE", "https://www.linkedin.com/in/jd/") == attendu


def test_le_wrapper_synchrone_ne_leve_pas_sur_un_echec(tmp_path, monkeypatch):
    # Streamlit afficherait une trace à l'écran : le wrapper rend une liste
    # vide et consigne l'erreur, comme ses voisins.
    wrapper = LinkedInScraperV2Sync(use_database=False, config_dir=str(tmp_path))

    async def recolte_qui_echoue(cookie, url_reference, status_callback=None):
        raise RuntimeError("Chrome introuvable")

    monkeypatch.setattr(wrapper.scraper, "recolter_browsemap_async", recolte_qui_echoue)

    assert wrapper.recolter_browsemap("COOKIE", "https://www.linkedin.com/in/jd/") == ([], None)
    assert any("Chrome introuvable" in e for e in wrapper.errors)


def test_l_extracteur_javascript_lit_bien_le_panneau():
    # Garde-fou minimal : le JS n'est pas testable sans navigateur, mais une
    # suppression accidentelle de ses points d'ancrage doit se voir.
    js = DOMSelectors.extract_browsemap_js()

    # Un argument : la racine à lire (« panneau » ou « section »).
    assert js.strip().startswith("(mode) =>")
    for ancre in ('role="dialog"', '/in/', 'invitable', 'intitule', 'degre'):
        assert ancre in js, f"ancre manquante dans l'extracteur : {ancre}"


# ---------------------------------------------------------------------------
# Déroulé de la récolte avec une couche navigateur factice
# ---------------------------------------------------------------------------

REF = "https://www.linkedin.com/in/ref/"
URL_OVERLAY = REF + "overlay/browsemap-recommendations/"


class FausseBrowser:
    def __init__(self):
        self.ferme = False

    async def close(self):
        self.ferme = True


class FauxLien:
    """Le lien « Tout afficher » : le cliquer ouvre (ou non) le panneau."""

    def __init__(self, page):
        self.page = page

    async def scroll_into_view_if_needed(self):
        self.page.journal.append("defiler_vers_lien")

    async def bounding_box(self):
        return None

    async def click(self):
        self.page.journal.append("clic")
        # Routage côté client : l'URL devient celle de l'overlay.
        self.page.url = self.page.url_apres_clic
        self.page.panneau_ouvert = self.page.panneau_apparait


class FaussePage:
    """Une page dont on dicte ce que voit chaque étape de la récolte.

    `bruts` : ce que l'extracteur rend selon son mode (« panneau » ou
    « section ») ; `lien` : le lien « Tout afficher » existe-t-il ;
    `panneau_apparait` : le clic ouvre-t-il le dialogue.
    """

    def __init__(self, bruts, url=REF, lien=True, panneau_apparait=True,
                 url_apres_clic=URL_OVERLAY):
        self.bruts = bruts
        self.url = url
        self.lien = lien
        self.panneau_apparait = panneau_apparait
        self.panneau_ouvert = False
        self.url_apres_clic = url_apres_clic
        self.journal = []

    async def wait_for_selector(self, selecteur, **k):
        self.journal.append(("attendre_lien", selecteur))
        if not self.lien:
            raise TimeoutError("lien introuvable")
        return FauxLien(self)

    async def wait_for_function(self, js, **k):
        self.journal.append("attendre_panneau")
        if not self.panneau_ouvert:
            raise TimeoutError("panneau absent")
        return True

    async def evaluate(self, js, arg=None):
        if js == DOMSelectors.extract_browsemap_js():
            mode = arg or "panneau"
            self.journal.append(("lire", mode))
            if mode == "panneau" and not self.panneau_ouvert:
                return {"entrees": [], "html": "<body/>"}
            return self.bruts.get(mode, {"entrees": [], "html": "<body/>"})
        return None


class FauxPlaywright:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *exc):
        return False


def entree(vanity, nom, degre="2e", invitable=True):
    return {"nom": nom, "url": f"https://www.linkedin.com/in/{vanity}/",
            "degre": degre, "intitule": "Dev", "invitable": invitable}


@pytest.fixture
def faux(scraper, monkeypatch):
    """Branche un navigateur factice ; rend une fonction qui lance la récolte.

    `entrees` sont celles du panneau ouvert, `section` celles de la section
    du profil (lecture de repli).
    """
    navigateur = FausseBrowser()

    def installer(entrees, entreprise="Thiga", url_page=None, dump=True,
                  lien=True, panneau_apparait=True, section=None,
                  url_apres_clic=URL_OVERLAY):
        bruts = {"panneau": {"entrees": entrees, "html": "<div/>"}}
        if section is not None:
            bruts["section"] = {"entrees": section, "html": "<section/>"}
        page = FaussePage(bruts, url=url_page or REF, lien=lien,
                          panneau_apparait=panneau_apparait,
                          url_apres_clic=url_apres_clic)
        scraper.page_factice = page
        scraper.navigations = []

        async def ouvrir(p, cookie, status_callback=None):
            return navigateur, page

        async def aller(pg, url, *a, **k):
            scraper.navigations.append(url)
            return True

        async def rien(*a, **k):
            return None

        async def societe(p):
            return entreprise

        monkeypatch.setattr("scraper_v2.async_playwright", lambda: FauxPlaywright())
        monkeypatch.setattr(scraper, "_open_linkedin_page", ouvrir)
        monkeypatch.setattr(scraper.network_manager, "safe_page_goto", aller)
        monkeypatch.setattr(scraper.human, "human_delay", rien)
        monkeypatch.setattr(scraper, "_derouler_panneau", rien)
        monkeypatch.setattr(scraper, "_entreprise_reference", societe)
        # Jamais d'écriture dans le logs/ du dépôt : on note ce qui aurait
        # été enregistré, pour vérifier QUAND la récolte décide de dumper.
        scraper.dumps_demandes = []

        def dumper(html):
            scraper.dumps_demandes.append(html)
            return dump

        monkeypatch.setattr(scraper, "_dumper_panneau", dumper)
        return recolter(scraper, REF)

    return installer, navigateur


def test_seul_le_lien_de_reference_lu_donne_une_erreur_et_pas_un_silence(scraper, faux):
    installer, navigateur = faux

    suggestions, entreprise = installer([entree("ref", "Moi Meme")])

    assert suggestions == []
    assert scraper.errors and any("Aucun profil voisin" in e for e in scraper.errors)
    assert navigateur.ferme


def test_la_reference_est_retiree_et_les_voisins_gardes(scraper, faux):
    installer, navigateur = faux

    suggestions, entreprise = installer(
        [entree("ref", "Moi Meme"), entree("a", "Alice"), entree("b", "Bob")]
    )

    assert [e["nom"] for e in suggestions] == ["Alice", "Bob"]
    assert entreprise == "Thiga"
    assert scraper.errors == []
    assert navigateur.ferme


def test_des_noms_tous_identiques_sont_un_panneau_illisible(scraper, faux):
    installer, navigateur = faux

    suggestions, _ = installer([entree("a", "Alice"), entree("b", "Alice")])

    assert suggestions == []
    assert scraper.errors
    assert navigateur.ferme


def test_une_entreprise_non_lue_reste_none(scraper, faux):
    installer, navigateur = faux

    suggestions, entreprise = installer([entree("a", "Alice")], entreprise=None)

    assert len(suggestions) == 1
    assert entreprise is None
    assert navigateur.ferme


def test_un_dump_impossible_n_est_pas_annonce_comme_fait(scraper, faux):
    installer, _ = faux

    installer([], dump=False)

    assert any("n'a pas pu être enregistré" in e for e in scraper.errors)


def test_un_vanity_contenant_login_n_est_pas_pris_pour_une_page_de_connexion(scraper, faux):
    installer, navigateur = faux

    suggestions, _ = installer(
        [entree("a", "Alice")],
        url_page="https://www.linkedin.com/in/jean-loginov/",
    )

    assert len(suggestions) == 1
    assert navigateur.ferme


def test_une_vraie_page_de_connexion_est_refusee_et_le_navigateur_ferme(scraper, faux):
    installer, navigateur = faux

    suggestions, _ = installer(
        [entree("a", "Alice")], url_page="https://www.linkedin.com/login?x=1"
    )

    assert suggestions == []
    assert SESSION_EXPIREE in scraper.errors
    assert navigateur.ferme


# --- Lectures crédibles mais fausses : avertir et dumper ------------------


def test_aucun_degre_lu_avertit_dumpe_et_garde_les_suggestions(scraper, faux):
    installer, _ = faux

    suggestions, _ = installer([entree("a", "Alice", degre=""), entree("b", "Bob", degre="")])

    assert len(suggestions) == 2
    assert any("Degré de relation illisible" in e for e in scraper.errors)
    assert scraper.dumps_demandes == ["<div/>"]


def test_aucun_bouton_se_connecter_lu_avertit_dumpe_et_garde_les_suggestions(scraper, faux):
    installer, _ = faux

    suggestions, _ = installer(
        [entree("a", "Alice", invitable=False), entree("b", "Bob", invitable=False)]
    )

    assert len(suggestions) == 2
    assert any("Aucun bouton « Se connecter » lu" in e for e in scraper.errors)
    assert scraper.dumps_demandes == ["<div/>"]


def test_une_lecture_saine_ne_dumpe_pas(scraper, faux):
    installer, _ = faux

    installer([entree("a", "Alice"), entree("b", "Bob")])

    assert scraper.errors == []
    assert scraper.dumps_demandes == []


def test_noms_identiques_et_liste_vide_dumpent_aussi(scraper, faux):
    installer, _ = faux
    installer([entree("a", "Alice"), entree("b", "Alice")])
    assert scraper.dumps_demandes == ["<div/>"]


def test_une_liste_vide_dumpe_le_html_rendu_par_le_js(scraper, faux):
    installer, _ = faux
    installer([])
    assert scraper.dumps_demandes == ["<div/>"]


def test_l_extracteur_rend_toujours_le_html_et_choisit_le_dialogue_le_plus_fourni():
    # Le comportement est vérifié pour de vrai dans test_extracteur_browsemap ;
    # ici, seulement que les trois scripts partagent le même choix de panneau.
    js = DOMSelectors.extract_browsemap_js()

    assert "1000000" in js and "20000" not in js
    assert "html: racine.innerHTML" in js          # plus conditionnel aux entrées vides
    assert "relations? en commun" in js
    for script in (js, DOMSelectors.compter_panneau_browsemap_js(),
                   DOMSelectors.derouler_panneau_browsemap_js()):
        assert "choisirPanneau" in script
        assert "dialog[open]" in script


def test_le_deroulement_attend_deux_lectures_stables(scraper, monkeypatch):
    # Un seul compte inchangé peut tomber pendant le chargement de la suite.
    comptes = iter([5, 5, 9, 9, 9, 9, 9])
    nb_lectures = []

    class PageDefilante:
        async def evaluate(self, js):
            if js == DOMSelectors.compter_panneau_browsemap_js():
                nb_lectures.append(1)
                return next(comptes)
            return None

    async def rien(*a, **k):
        return None

    monkeypatch.setattr(scraper.human, "human_delay", rien)

    lus = asyncio.run(scraper._derouler_panneau(PageDefilante()))

    assert lus == 9
    # 5, 5 (1re stable), 9 (relance), 9 (1re stable), 9 (2e stable) : arrêt.
    assert len(nb_lectures) == 5


# --- Navigation : profil, clic sur « Tout afficher », panneau -------------
#
# Charger l'URL de l'overlay directement redirige vers le profil nu (premier
# essai réel) : on va sur le profil et on clique, comme une personne.


def test_on_ouvre_le_profil_puis_on_clique_sur_tout_afficher(scraper, faux):
    installer, navigateur = faux

    suggestions, _ = installer([entree("a", "Alice"), entree("b", "Bob")])

    assert scraper.navigations == [REF]           # jamais l'URL de l'overlay
    journal = scraper.page_factice.journal
    assert ("attendre_lien", 'a[href*="/overlay/browsemap-recommendations"]') in journal
    assert journal.index("defiler_vers_lien") < journal.index("clic") < journal.index("attendre_panneau")
    assert ("lire", "panneau") in journal
    assert ("lire", "section") not in journal
    assert [e["nom"] for e in suggestions] == ["Alice", "Bob"]
    assert scraper.errors == []
    assert navigateur.ferme


def test_sans_lien_tout_afficher_la_section_du_profil_est_lue_avec_un_avertissement(scraper, faux):
    installer, navigateur = faux

    suggestions, entreprise = installer(
        [], lien=False, section=[entree("a", "Alice"), entree("b", "Bob")]
    )

    assert [e["nom"] for e in suggestions] == ["Alice", "Bob"]
    assert entreprise == "Thiga"
    assert "clic" not in scraper.page_factice.journal
    assert len(scraper.errors) == 1
    assert "seuls les 2 profils visibles" in scraper.errors[0]
    assert navigateur.ferme


def test_un_panneau_qui_ne_s_ouvre_pas_donne_la_section_avec_un_avertissement(scraper, faux):
    installer, navigateur = faux

    suggestions, _ = installer(
        [entree("x", "Xavier")], panneau_apparait=False,
        section=[entree("a", "Alice")],
    )

    assert [e["nom"] for e in suggestions] == ["Alice"]
    assert "clic" in scraper.page_factice.journal
    assert len(scraper.errors) == 1
    assert "ne s'est pas ouvert" in scraper.errors[0]
    assert "seuls les 1 profils visibles" in scraper.errors[0]
    assert navigateur.ferme


def test_ni_panneau_ni_section_est_une_erreur_bruyante(scraper, faux):
    installer, navigateur = faux

    suggestions, _ = installer([], lien=False, section=[])

    assert suggestions == []
    assert any("Aucun profil voisin" in e for e in scraper.errors)
    assert scraper.dumps_demandes == ["<section/>"]
    assert navigateur.ferme


def test_la_section_introuvable_dumpe_la_page(scraper, faux):
    # Aucune section : l'extracteur rend le HTML du document, à enregistrer.
    installer, _ = faux

    installer([], lien=False)

    assert any("Aucun profil voisin" in e for e in scraper.errors)
    assert scraper.dumps_demandes == ["<body/>"]


def test_un_panneau_ouvert_mais_illisible_reste_une_erreur_et_pas_un_repli(scraper, faux):
    # Le panneau est là mais rien n'y est lu : c'est un changement de
    # structure, à crier — pas à masquer par les 5 profils de la section.
    installer, _ = faux

    suggestions, _ = installer([], section=[entree("a", "Alice")])

    assert suggestions == []
    assert any("Aucun profil voisin" in e for e in scraper.errors)
    assert ("lire", "section") not in scraper.page_factice.journal


def test_un_clic_renvoye_vers_la_connexion_est_refuse(scraper, faux):
    installer, navigateur = faux

    suggestions, _ = installer(
        [entree("a", "Alice")],
        url_apres_clic="https://www.linkedin.com/authwall?trk=x",
    )

    assert suggestions == []
    assert SESSION_EXPIREE in scraper.errors
    assert navigateur.ferme


def test_un_vanity_encode_va_sur_l_url_canonique_du_profil(scraper, faux):
    installer, _ = faux
    installer([entree("a", "Alice")])         # installe les faux (récolte sur REF)
    scraper.navigations.clear()

    asyncio.run(scraper.recolter_browsemap_async(
        cookie="C", url_reference="https://www.linkedin.com/in/C%C3%A9line-Ref/?trk=x"
    ))

    assert scraper.navigations == ["https://www.linkedin.com/in/c%C3%A9line-ref/"]
