# -*- coding: utf-8 -*-
"""Le moteur de veille, sans navigateur : chaque page LinkedIn est simulée.

On vérifie l'enchaînement — budget, identification, annuaire recoupé,
recherche paginée avec curseur, nouveautés — et surtout les arrêts : budget
épuisé, cookie expiré, entreprise introuvable. Aucune visite LinkedIn,
aucun appel à l'annuaire réel.
"""

import asyncio
import json
import re
import urllib.parse

import pytest

import veille
from database import DatabaseManager
from utils.annuaire import AnnuaireIndisponible
from utils.dom_selectors import DOMSelectors
from utils.veille_regles import ReglagesVeille
from veille_store import VeilleStore

ABOUT_OK = {
    "nom": "Orbique", "company_id": "7654321", "description": "Conseil produit", "html": "",
    "champs": {"Site web": ["https://www.orbique.example"], "Siège social": ["Paris, Paris"],
               "Taille de l’entreprise": ["201-500 employés", "198 membres associés"],
               "Secteur": ["Conseil"]},
}
ANNUAIRE_OK = [{
    "siren": "333333333", "nom_complet": "ORBIQUE", "nom_raison_sociale": "ORBIQUE", "sigle": None,
    "activite_principale": "70.22Z", "tranche_effectif_salarie": "22", "annee_tranche_effectif_salarie": "2024",
    "date_creation": "2014-04-28", "etat_administratif": "A", "categorie_entreprise": "PME",
    "siege": {"libelle_commune": "PARIS"},
    "dirigeants": [{"type_dirigeant": "personne physique", "nom": "EXEMPLE", "prenoms": "Jeanne", "qualite": "Présidente"}],
}]


def personne(v, poste):
    return {"nom": v.title(), "poste": poste, "entreprise": "Orbique",
            "url": f"https://www.linkedin.com/in/{v}/", "localisation": "Paris", "connexions": "2e"}


class FauxLimites:
    def __init__(self, deja=0):
        self.pages_veille_today = deja

    def increment_pages_veille(self, n=1):
        self.pages_veille_today += n


class FauxHumain:
    def __init__(self, limites):
        self.daily_limits = limites
        self.sur = True  # ce que répond le moniteur de sécurité
        self.parcours = 0
        self.delais = 0

    async def human_delay(self, *a, **k):
        self.delais += 1

    async def check_safety(self, page):
        return self.sur

    async def browse_page_naturally(self, page):
        self.parcours += 1

    async def human_hover_and_click(self, page, locator):
        await locator.click()


class FauxReseau:
    def __init__(self, page):
        self.page = page

    async def safe_page_goto(self, page, url):
        self.page.url = url
        self.page.visites.append(url)
        return True


RECHERCHE_JS = DOMSelectors.extract_recherche_entreprises_js()
DEGRES_JS = DOMSelectors.extract_degres_js()
COORDONNEES_JS = DOMSelectors.extract_coordonnees_js()
ETAT_RESULTATS_JS = DOMSelectors.etat_resultats_personnes_js()
FENETRE_OUVERTE_JS = DOMSelectors.fenetre_coordonnees_ouverte_js()
RIEN_PARTAGE = {"dialogue": True, "email": "", "telephone": "", "html": ""}


def vanity_de(url):
    m = re.search(r"/in/([^/?#]+)", url or "")
    return m.group(1) if m else None


class FauxLien:
    """Le lien « Coordonnées » d'un profil : présent ou non, un clic ouvre la fenêtre."""

    def __init__(self, page, present):
        self.page, self.present = page, present

    @property
    def first(self):
        return self

    async def count(self):
        return 1 if self.present else 0

    async def click(self):
        self.page.clics.append(self.page.url)


def carte(nom, slug):
    return {"nom": nom, "url": f"https://www.linkedin.com/company/{slug}/"}


def recherche_de(*cartes, html=""):
    return {"resultats": list(cartes), "html": html}


class FaussePage:
    """`recherche` : ce que lit la recherche d'entreprises ; par défaut, la
    carte du nom cherché au milieu d'une filiale, comme sur la vraie page."""

    def __init__(self, about=ABOUT_OK, resultats=None, url_apres_goto=None, recherche=None):
        self.about = about
        self.resultats = resultats or {}
        self.recherche = recherche
        self.visites = []
        self.url = ""
        self.url_apres_goto = url_apres_goto
        self.fermee = False
        self.explose = set()  # noms dont la lecture de la recherche lève une erreur Playwright
        self.recherches = []  # noms cherchés, dans l'ordre
        self.ferme_pendant = set()  # noms pendant la lecture desquels la fenêtre se ferme
        self.degres = {}  # ce que lit `extract_degres_js` sur chaque page de résultats
        self.fenetres = {}  # vanity → lecture de la fenêtre « Coordonnées » (défaut : rien de partagé)
        self.sans_lien = set()  # vanity dont le profil n'a pas de lien « Coordonnées »
        self.sans_fenetre = set()  # vanity dont la fenêtre ne s'ouvre jamais
        self.clics = []  # profils sur lesquels « Coordonnées » a été cliqué
        self.fenetre_explose = set()  # vanity dont la lecture de la fenêtre lève une erreur Playwright
        # Ce que montre une page de résultats vide : par défaut, le « Aucun
        # résultat » de LinkedIn — une vraie absence.
        self.etat_resultats = {"aucunResultat": True, "html": "<main>Aucun résultat</main>"}

    def locator(self, selecteur):
        assert selecteur == 'a[href*="overlay/contact-info"]'
        return FauxLien(self, vanity_de(self.url) not in self.sans_lien)

    async def wait_for_function(self, js, **k):
        # Le petit test dédié, pas l'extracteur entier, sondé à chaque image.
        assert js == FENETRE_OUVERTE_JS and k.get("timeout", 30000) <= 8000
        if vanity_de(self.url) in self.sans_fenetre:
            raise TimeoutError("Timeout 8000ms exceeded.")

    def is_closed(self):
        return self.fermee

    async def evaluate(self, js):
        if js == ETAT_RESULTATS_JS:
            if self.etat_resultats is None:
                raise RuntimeError("Execution context was destroyed")
            return dict(self.etat_resultats)
        if js == DEGRES_JS:
            if self.degres is None:
                raise RuntimeError("Execution context was destroyed")
            return dict(self.degres)
        if js == COORDONNEES_JS:
            if vanity_de(self.url) in self.fenetre_explose:
                raise RuntimeError("Execution context was destroyed")
            return self.fenetres.get(vanity_de(self.url), RIEN_PARTAGE)
        if js == RECHERCHE_JS:
            nom = urllib.parse.parse_qs(urllib.parse.urlparse(self.url).query)["keywords"][0]
            self.recherches.append(nom)
            if nom in self.explose:
                raise RuntimeError("Execution context was destroyed")
            if nom in self.ferme_pendant:
                self.fermee = True
                raise RuntimeError("Target page, context or browser has been closed")
            if self.recherche is not None:
                return self.recherche
            slug = nom.lower().replace(" ", "-")
            return recherche_de(carte(f"{nom} Assurances", f"{slug}-assurances"), carte(nom, slug))
        return self.about


class FauxNavigateur:
    def __init__(self):
        self.ferme = False

    async def close(self):
        self.ferme = True


class FauxScraper:
    def __init__(self, page, limites, cookie_ok=True):
        self.page = page
        self.navigateur = FauxNavigateur()
        self.human = FauxHumain(limites)
        self.network_manager = FauxReseau(page)
        self.cookie_ok = cookie_ok
        self.dumps = []
        self.noms_dumps = []
        self.errors = []
        self.extraction_en_echec = False

    async def _resoudre_company_urn_via_typeahead(self, nom, page, echecs=None):
        # Le service répond 404 depuis le 2026-10-15 : la veille ne doit plus l'appeler.
        raise AssertionError("la veille n'appelle plus le typeahead")

    async def _open_linkedin_page(self, p, cookie, status_callback=None):
        return (self.navigateur, self.page) if self.cookie_ok else (None, None)

    def _est_page_de_connexion(self, url):
        return "/login" in url or "/authwall" in url

    async def extraire_profils_page(self, page):
        import re
        if self.extraction_en_echec:
            # Comme le vrai : l'erreur est avalée, notée dans `errors`, liste vide.
            self.errors.append("Erreur extraction profils: boum")
            return []
        m = re.search(r"page=(\d+)", page.url)
        return list(self.page.resultats.get(int(m.group(1)) if m else 1, []))

    def _dumper_panneau(self, html, nom_fichier="browsemap_dump.html"):
        self.dumps.append(html)
        self.noms_dumps.append(nom_fichier)
        return True


class FauxPlaywright:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


@pytest.fixture(autouse=True)
def sans_vrai_playwright(monkeypatch):
    monkeypatch.setattr(veille, "async_playwright", lambda: FauxPlaywright())


@pytest.fixture
def base(tmp_path):
    db = str(tmp_path / "p.db")
    DatabaseManager(db_file=db)
    return VeilleStore(db), DatabaseManager(db_file=db)


ARTICLE = {"titre": "Orbique rachète Zéphyr", "lien": "https://n/1", "source": "Les Échos",
           "publie_le": "2026-08-31", "categorie": "Rachat / fusion"}


def site_muet(site):
    # Aucun site réel n'est lu en test : par défaut, le site ne publie rien.
    return {"emails": [], "telephones": [], "pages_lues": [site]}


def passer(store, db, scraper, reglages=None, annuaire=lambda nom: ANNUAIRE_OK, maintenant="2026-10-15T08:00:00",
           site_web=site_muet):
    return asyncio.run(veille.passage_async(
        scraper, store, db, reglages or ReglagesVeille(["Product", "Data", "IA"], [], 20),
        "COOKIE", maintenant, annuaire=annuaire, site_web=site_web))


def test_premier_passage_complet(base):
    store, db = base
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage(resultats={1: [personne("jeanne-exemple", "Product Manager"),
                                     personne("paul-exemple", "Data Engineer")]})
    limites = FauxLimites()
    r = passer(store, db, FauxScraper(page, limites))

    assert r.cause == "termine" and r.entreprises == ["Orbique"] and r.nouveaux_contacts == 2
    e = store.entreprises()[0]
    assert e["etat"] == "identifiee" and e["company_id"] == "7654321"
    fiche = store.fiche(i)
    assert fiche["linkedin.taille"]["valeur"] == "201-500 employés"
    assert fiche["annuaire.siren"]["valeur"] == "333333333"
    assert {c["famille"] for c in store.contacts(i)} == {"Product", "Data"}
    # recherche d'entreprises + « À propos » + page 1 + page 2 vide
    assert limites.pages_veille_today == r.pages == 4
    assert page.visites[:2] == ["https://www.linkedin.com/search/results/companies/?keywords=Orbique",
                                "https://www.linkedin.com/company/orbique/about/"]
    # Le lien trouvé est gardé : les passages suivants ne cherchent plus.
    assert e["url_linkedin"] == "https://www.linkedin.com/company/orbique/" and e["nom"] == "Orbique"


def test_les_contacts_entrent_au_fichier(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    passer(store, db, FauxScraper(FaussePage(resultats={1: [personne("jeanne-exemple", "PM")]}), FauxLimites()))
    assert "https://www.linkedin.com/in/jeanne-exemple/" in db.urls_connues()


def test_un_contact_deja_au_fichier_n_est_pas_nouveau(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    db.ajouter_profil("Jeanne", "PM", "Orbique", "", "http://linkedin.com/in/Jeanne-Exemple?trk=x")
    r = passer(store, db, FauxScraper(FaussePage(resultats={1: [personne("jeanne-exemple", "PM")]}), FauxLimites()))
    assert r.nouveaux_contacts == 0


def test_budget_epuise_au_milieu(base):
    store, db = base
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage(resultats={1: [personne("a", "PM")], 2: [personne("b", "PM")]})
    limites = FauxLimites(deja=17)  # 3 pages restantes sur 20
    r = passer(store, db, FauxScraper(page, limites))
    assert r.cause == "budget"
    assert len(page.visites) == 3  # recherche + « À propos » + page 1, pas de page 2
    assert store.entreprises()[0]["curseur_page"] == 1


def test_budget_nul_aucune_page(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage()
    r = passer(store, db, FauxScraper(page, FauxLimites(deja=20)))
    assert r.cause == "budget" and page.visites == [] and r.pages == 0


def test_le_curseur_reprend_et_repart_a_zero_en_fin_de_liste(base):
    store, db = base
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage(resultats={1: [personne("a", "PM")], 2: [personne("b", "PM")], 3: [personne("c", "PM")]})
    passer(store, db, FauxScraper(page, FauxLimites()))
    assert store.entreprises()[0]["curseur_page"] == 2
    page.visites.clear()
    passer(store, db, FauxScraper(page, FauxLimites()), maintenant="2026-10-16T08:00:00")
    # Fiche fraîche : pas de « À propos » ; pages 3 puis 4 (vide) → curseur remis à 0
    assert [v for v in page.visites if "about" in v] == []
    assert store.entreprises()[0]["curseur_page"] == 0


def test_changer_de_familles_remet_le_curseur_a_zero(base):
    store, db = base
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    store.maj_identification(i, "identifiee", company_id="7654321")
    store.maj_curseur(i, 2, "ancienne-signature")
    store.enregistrer_fiche(i, {"site": "x"}, "linkedin", "2026-10-14")
    page = FaussePage(resultats={1: [personne("a", "PM")]})
    passer(store, db, FauxScraper(page, FauxLimites()))
    assert any("page=1" in v for v in page.visites)


def test_entreprise_introuvable_par_son_nom(base):
    store, db = base
    store.ajouter_entreprise("Inconnue", "2026-10-14")
    page = FaussePage(recherche=recherche_de(carte("Inconnue Assurances", "ia"), carte("Inconnue Lab", "il")))
    r = passer(store, db, FauxScraper(page, FauxLimites()))
    e = store.entreprises()[0]
    assert e["etat"] == "non_identifiee" and e["url_linkedin"] is None
    # La seule page lue : la recherche d'entreprises, pas de recherche d'employés.
    assert page.visites == ["https://www.linkedin.com/search/results/companies/?keywords=Inconnue"]
    assert r.erreurs == ["Inconnue : aucune entreprise « Inconnue » sur LinkedIn "
                         "(proposées : Inconnue Assurances, Inconnue Lab) — collez le lien de sa page entreprise."]


def test_page_a_propos_illisible(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage(about={"nom": "", "champs": {}, "company_id": "", "description": "", "html": "<main>?</main>"})
    s = FauxScraper(page, FauxLimites())
    r = passer(store, db, s)
    assert store.entreprises()[0]["etat"] == "illisible"
    assert s.dumps == ["<main>?</main>"]
    assert s.noms_dumps == ["apropos_dump.html"]  # n'écrase pas le dump des Profils similaires
    assert any("illisible" in e for e in r.erreurs)
    assert [v for v in page.visites if "results/people" in v] == []


def test_un_lien_colle_est_utilise_au_lieu_du_nom(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14", url_linkedin="https://www.linkedin.com/company/orbique/")
    page = FaussePage()
    passer(store, db, FauxScraper(page, FauxLimites()))
    assert page.visites[0] == "https://www.linkedin.com/company/orbique/about/"


def test_annuaire_non_rapproche(base):
    store, db = base
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    autre = [dict(ANNUAIRE_OK[0], siege={"libelle_commune": "LYON"})]
    passer(store, db, FauxScraper(FaussePage(), FauxLimites()), annuaire=lambda nom: autre)
    fiche = store.fiche(i)
    assert "annuaire.siren" not in fiche
    assert "aucune" in fiche["annuaire.rapprochement"]["valeur"]


def test_annuaire_indisponible_n_arrete_pas_la_veille(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")

    def panne(nom):
        raise AnnuaireIndisponible("délai dépassé")

    r = passer(store, db, FauxScraper(FaussePage(resultats={1: [personne("a", "PM")]}), FauxLimites()), annuaire=panne)
    assert r.cause == "termine" and r.nouveaux_contacts == 1
    assert any("annuaire" in e.lower() for e in r.erreurs)


def test_cookie_expire(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    r = passer(store, db, FauxScraper(FaussePage(), FauxLimites(), cookie_ok=False))
    assert r.cause == "cookie" and r.entreprises == []


def test_deconnexion_en_cours_de_route(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage()
    s = FauxScraper(page, FauxLimites())

    async def vers_login(p, url):
        p.url = "https://www.linkedin.com/login"
        p.visites.append(url)
        return True

    s.network_manager.safe_page_goto = vers_login
    r = passer(store, db, s)
    assert r.cause == "deconnecte"
    assert s.navigateur.ferme


def test_rien_a_faire(base):
    store, db = base
    r = passer(store, db, FauxScraper(FaussePage(), FauxLimites()))
    assert r.cause == "rien_a_faire" and r.pages == 0


def test_le_navigateur_est_toujours_ferme(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    s = FauxScraper(FaussePage(), FauxLimites())
    passer(store, db, s)
    assert s.navigateur.ferme


def test_lancer_passage_respecte_le_verrou_et_enregistre(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from utils.verrou_linkedin import session_linkedin

    db_file = str(tmp_path / "p.db")
    DatabaseManager(db_file=db_file)
    chemins = SimpleNamespace(db_file=db_file, profiles_csv=str(tmp_path / "p.csv"), config_dir=str(tmp_path))
    with session_linkedin(tmp_path, "recherche"):
        r = veille.lancer_passage(chemins, "COOKIE")
    assert r.cause == "occupe"
    import sqlite3
    causes = [c for (c,) in sqlite3.connect(db_file).execute("SELECT cause FROM passages_veille")]
    assert causes == ["occupe"]
    # Consigné, mais ce n'est pas un passage : le résumé du dernier vrai reste affiché.
    assert VeilleStore(db_file).dernier_passage() is None


# ── Ajouts : ce que le brief ne couvrait pas ─────────────────────────────

class ReseauEnPanne(FauxReseau):
    """safe_page_goto échoue pour les URL contenant `motif` : la page reste où elle était."""

    def __init__(self, page, motif):
        super().__init__(page)
        self.motif = motif

    async def safe_page_goto(self, page, url):
        self.page.visites.append(url)
        if self.motif in url:
            return False
        self.page.url = url
        return True


def test_page_a_propos_injoignable_rien_n_est_lu_sur_la_page_precedente(base):
    store, db = base
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage(resultats={1: [personne("a", "PM")]})
    s = FauxScraper(page, FauxLimites())
    s.network_manager = ReseauEnPanne(page, "/about/")
    r = passer(store, db, s)
    e = store.entreprises()[0]
    assert e["etat"] == "a_identifier" and e["derniere_veille"] is None
    assert store.fiche(i) == {} and store.contacts(i) == []
    assert [v for v in page.visites if "results/people" in v] == []
    assert any("Orbique" in x and "injoignable" in x for x in r.erreurs)
    assert s.navigateur.ferme


def test_page_de_resultats_injoignable_le_curseur_reste_a_la_derniere_page_lue(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage(resultats={1: [personne("a", "PM")], 2: [personne("b", "PM")]})
    s = FauxScraper(page, FauxLimites())
    s.network_manager = ReseauEnPanne(page, "page=2")
    r = passer(store, db, s)
    assert store.entreprises()[0]["curseur_page"] == 1
    assert r.nouveaux_contacts == 1  # la page 1 n'est pas relue sous le nom de page 2


def test_un_nom_trop_court_n_interroge_pas_l_annuaire(base):
    store, db = base
    i = store.ajouter_entreprise("AB", "2026-10-14")
    appels = []
    passer(store, db, FauxScraper(FaussePage(about=dict(ABOUT_OK, nom="AB"),
                                             recherche=recherche_de(carte("AB", "ab"))), FauxLimites()),
           annuaire=lambda nom: appels.append(nom) or ANNUAIRE_OK)
    assert appels == []
    assert store.fiche(i)["annuaire.rapprochement"]["valeur"] == "nom trop court pour l'annuaire"


def test_un_lien_colle_avec_sa_sous_page_n_est_pas_double(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14",
                             url_linkedin="https://www.linkedin.com/company/orbique/about/?trk=x")
    page = FaussePage()
    passer(store, db, FauxScraper(page, FauxLimites()))
    assert page.visites[0] == "https://www.linkedin.com/company/orbique/about/"


def test_aucune_famille_cochee_message_clair_sans_ouvrir_linkedin(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage()
    r = passer(store, db, FauxScraper(page, FauxLimites()), reglages=ReglagesVeille([], [], 20))
    assert r.cause == "erreur" and page.visites == []
    assert any("famille" in e for e in r.erreurs)


def test_lancer_passage_une_erreur_inattendue_est_nommee_et_enregistree(tmp_path, monkeypatch):
    from types import SimpleNamespace

    db_file = str(tmp_path / "p.db")
    DatabaseManager(db_file=db_file)
    chemins = SimpleNamespace(db_file=db_file, profiles_csv=str(tmp_path / "p.csv"), config_dir=str(tmp_path))

    async def boum(*a, **k):
        raise KeyError("company_id")

    monkeypatch.setattr(veille, "passage_async", boum)
    r = veille.lancer_passage(chemins, "COOKIE")
    assert r.cause == "erreur"
    assert any("KeyError" in e and "company_id" in e for e in r.erreurs)
    assert VeilleStore(db_file).dernier_passage()["cause"] == "erreur"
    assert not (tmp_path / "session_linkedin.lock").exists()


def test_le_dump_du_vrai_scraper_garde_son_nom_par_defaut():
    import inspect
    from scraper_v2 import LinkedInScraperV2
    params = inspect.signature(LinkedInScraperV2._dumper_panneau).parameters
    assert params["nom_fichier"].default == "browsemap_dump.html"


# ── Correctifs, tour 1 ───────────────────────────────────────────────────

def test_un_homonyme_propose_par_linkedin_est_refuse(base):
    store, db = base
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage(about=dict(ABOUT_OK, nom="Orbital Conseil"), resultats={1: [personne("a", "PM")]})
    r = passer(store, db, FauxScraper(page, FauxLimites()))
    e = store.entreprises()[0]
    assert e["etat"] == "non_identifiee" and e["company_id"] is None
    assert store.fiche(i) == {} and store.contacts(i) == []
    assert [v for v in page.visites if "results/people" in v] == []
    assert any("Orbital Conseil" in x and "collez le lien" in x for x in r.erreurs)


def test_le_nom_suivi_contenu_dans_le_nom_de_la_page_est_accepte(base):
    store, db = base
    i = store.ajouter_entreprise("Décathlon", "2026-10-14")
    page = FaussePage(about=dict(ABOUT_OK, nom="DECATHLON France"), recherche=recherche_de(carte("Decathlon", "dk")))
    passer(store, db, FauxScraper(page, FauxLimites()))
    assert store.entreprises()[0]["etat"] == "identifiee"
    assert "linkedin.taille" in store.fiche(i)


def test_un_lien_colle_n_est_pas_soumis_a_la_comparaison_des_noms(base):
    store, db = base
    store.ajouter_entreprise("Mon client", "2026-10-14", url_linkedin="https://www.linkedin.com/company/orbique/")
    passer(store, db, FauxScraper(FaussePage(), FauxLimites()))
    assert store.entreprises()[0]["etat"] == "identifiee"


def test_une_extraction_en_echec_n_est_pas_une_fin_de_liste(base):
    store, db = base
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    store.maj_identification(i, "identifiee", company_id="7654321")
    store.enregistrer_fiche(i, {"site": "x"}, "linkedin", "2026-10-14T08:00:00")
    sig = veille.signature_familles(["Product", "Data", "IA"], [])
    store.maj_curseur(i, 3, sig)
    s = FauxScraper(FaussePage(), FauxLimites())
    s.extraction_en_echec = True
    r = passer(store, db, s)
    e = store.entreprises()[0]
    assert e["curseur_page"] == 3 and e["derniere_veille"] is None
    assert r.entreprises == []
    assert any("Orbique" in x for x in r.erreurs)
    assert "linkedin.recherche" not in store.fiche(i)


def test_une_premiere_page_vide_est_dite_et_datee(base):
    store, db = base
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    r = passer(store, db, FauxScraper(FaussePage(), FauxLimites()))
    assert any("Orbique" in x and "aucun profil" in x and "Product" in x for x in r.erreurs)
    ligne = store.fiche(i)["linkedin.recherche"]
    assert ligne["valeur"] == "aucun profil trouvé" and ligne["releve_le"] == "2026-10-15T08:00:00"


def test_une_page_vide_sans_aucun_resultat_affiche_est_une_lecture_ratee(base):
    # Le 15/10, Amazon a donné « 0 profils extraits » sans qu'on sache si
    # LinkedIn n'avait rien trouvé ou si la page n'avait pas été lue. Sans le
    # « Aucun résultat » de LinkedIn, ce n'est pas une absence : la page est
    # gardée pour comprendre, et l'entreprise n'est pas déclarée vide.
    store, db = base
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage()
    page.etat_resultats = {"aucunResultat": False, "html": "<main>des cartes</main>"}
    s = FauxScraper(page, FauxLimites())
    r = passer(store, db, s)
    assert "recherche_personnes_dump.html" in s.noms_dumps
    assert "<main>des cartes</main>" in s.dumps
    assert any("Orbique" in x and "aucun profil n'a pu être lu" in x for x in r.erreurs), r.erreurs
    assert not any("aucun profil Product" in x for x in r.erreurs)
    assert "linkedin.recherche" not in store.fiche(i)


def test_une_page_vide_illisible_n_est_pas_une_absence(base):
    store, db = base
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage()
    page.etat_resultats = None  # la lecture de l'état elle-même échoue
    r = passer(store, db, FauxScraper(page, FauxLimites()))
    assert any("Orbique" in x and "aucun profil n'a pu être lu" in x for x in r.erreurs), r.erreurs
    assert "linkedin.recherche" not in store.fiche(i)


def test_des_profils_trouves_ensuite_effacent_le_constat_d_absence(base):
    store, db = base
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage()
    passer(store, db, FauxScraper(page, FauxLimites()))
    page.resultats = {1: [personne("a", "PM")]}
    passer(store, db, FauxScraper(page, FauxLimites()), maintenant="2026-10-16T08:00:00")
    assert store.fiche(i)["linkedin.recherche"]["valeur"] != "aucun profil trouvé"


def test_le_moniteur_de_securite_arrete_la_veille(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage(resultats={1: [personne("a", "PM")]})
    s = FauxScraper(page, FauxLimites())
    s.human.sur = False
    r = passer(store, db, s)
    assert r.cause == "securite" and len(page.visites) == 1
    assert any("sécurité" in x for x in r.erreurs)
    assert s.navigateur.ferme and store.contacts(1) == []


def test_chaque_page_lue_est_parcourue_comme_un_humain(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    s = FauxScraper(FaussePage(resultats={1: [personne("a", "PM")]}), FauxLimites())
    r = passer(store, db, s)
    assert s.human.parcours == r.pages == 4  # recherche d'entreprises, « À propos », page 1, page 2


def test_une_erreur_inattendue_sur_une_entreprise_n_arrete_pas_le_passage(base):
    store, db = base
    store.ajouter_entreprise("Bombe", "2026-10-14")
    store.ajouter_entreprise("Orbique", "2026-10-14")
    s = FauxScraper(FaussePage(resultats={1: [personne("a", "PM")]}), FauxLimites())
    s.page.explose = {"Bombe"}
    r = passer(store, db, s)
    assert r.cause == "termine" and r.entreprises == ["Orbique"]
    assert any("Bombe" in x and "RuntimeError" in x for x in r.erreurs)
    bombe = next(e for e in store.entreprises() if e["nom"] == "Bombe")
    assert bombe["etat"] == "a_identifier" and bombe["url_linkedin"] is None


def test_le_budget_est_verifie_avant_d_identifier_l_entreprise_suivante(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    store.ajouter_entreprise("Zorbique", "2026-10-14")
    s = FauxScraper(FaussePage(about=dict(ABOUT_OK, nom="Orbique Zorbique"),
                               resultats={1: [personne("a", "PM")], 2: [personne("b", "PM")]}),
                    FauxLimites(deja=16))
    r = passer(store, db, s)
    # 4 pages pour Orbique (recherche, « À propos », pages 1 et 2) : plus rien pour Zorbique.
    assert r.cause == "budget" and s.page.recherches == ["Orbique"]


def test_l_annuaire_est_interroge_avec_le_nom_de_la_page_linkedin(base):
    store, db = base
    store.ajouter_entreprise("Mon client", "2026-10-14", url_linkedin="https://www.linkedin.com/company/orbique/")
    appels = []
    passer(store, db, FauxScraper(FaussePage(), FauxLimites()),
           annuaire=lambda nom: appels.append(nom) or ANNUAIRE_OK)
    assert appels == ["Orbique"]


def test_une_page_illisible_passe_en_fin_de_rotation(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage(about={"nom": "", "champs": {}, "company_id": "", "description": "", "html": "x"})
    passer(store, db, FauxScraper(page, FauxLimites()))
    assert store.entreprises()[0]["derniere_veille"] == "2026-10-15T08:00:00"


# ── Correctifs de la revue finale ────────────────────────────────────────

def test_une_fiche_relue_a_l_identique_n_est_pas_relue_le_lendemain(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage()
    passer(store, db, FauxScraper(page, FauxLimites()), maintenant="2026-10-15T08:00:00")
    page.visites.clear()
    passer(store, db, FauxScraper(page, FauxLimites()), maintenant="2026-11-29T08:00:00")  # jour 45
    assert [v for v in page.visites if "about" in v]  # plus de 30 jours : relue, à l'identique
    page.visites.clear()
    passer(store, db, FauxScraper(page, FauxLimites()), maintenant="2026-11-30T08:00:00")  # jour 46
    assert [v for v in page.visites if "about" in v] == []


def _profil_du_fichier(db, vanity):
    import sqlite3
    return sqlite3.connect(db.db_file).execute(
        "SELECT ecole, nb_connexions, poste FROM profiles WHERE LOWER(url) LIKE ?", (f"%/in/{vanity}%",)).fetchall()


@pytest.mark.parametrize("lien_au_fichier", [
    "https://www.linkedin.com/in/jeanne-exemple/",
    "http://linkedin.com/in/Jeanne-Exemple?miniProfileUrn=x",
])
def test_un_profil_deja_au_fichier_n_est_ni_reecrit_ni_double(base, lien_au_fichier):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    db.ajouter_profil("Jeanne", "Consultante", "Orbique", "École Exemple", lien_au_fichier, "", "500+")
    passer(store, db, FauxScraper(FaussePage(resultats={1: [personne("jeanne-exemple", "Product Manager")]}),
                                  FauxLimites()))
    assert _profil_du_fichier(db, "jeanne-exemple") == [("École Exemple", "500+", "Consultante")]
    assert len(store.contacts(store.entreprises()[0]["id"])) == 1  # relié quand même


def test_une_personne_trouvee_sous_deux_entreprises_compte_une_fois(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    store.ajouter_entreprise("Orbique Studio", "2026-10-14")
    page = FaussePage(about=dict(ABOUT_OK, nom="Orbique Studio"),
                      resultats={1: [personne("jeanne-exemple", "Product Manager")]})
    r = passer(store, db, FauxScraper(page, FauxLimites()))
    assert r.entreprises == ["Orbique", "Orbique Studio"]
    assert r.nouveaux_contacts == 1
    assert len(_profil_du_fichier(db, "jeanne-exemple")) == 1


class _Interruption(BaseException):
    """Comme le StopException de Streamlit : hors de la hiérarchie `Exception`."""


def test_un_passage_interrompu_ferme_chrome_et_ne_l_avale_pas(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    s = FauxScraper(FaussePage(resultats={1: [personne("a", "PM")]}), FauxLimites())

    def status(texte):
        if texte.startswith("Orbique"):
            raise _Interruption()

    with pytest.raises(_Interruption):
        asyncio.run(veille.passage_async(s, store, db, ReglagesVeille(["Product"], [], 20), "COOKIE",
                                         "2026-10-15T08:00:00", status=status))
    assert s.navigateur.ferme


def test_lancer_passage_interrompu_est_enregistre_puis_relance(tmp_path, monkeypatch):
    from types import SimpleNamespace

    db_file = str(tmp_path / "p.db")
    DatabaseManager(db_file=db_file)
    chemins = SimpleNamespace(db_file=db_file, profiles_csv=str(tmp_path / "p.csv"), config_dir=str(tmp_path))

    async def interrompu(*a, rapport=None, **k):
        rapport.pages, rapport.entreprises = 2, ["Orbique"]
        raise _Interruption()

    monkeypatch.setattr(veille, "passage_async", interrompu)
    with pytest.raises(_Interruption):
        veille.lancer_passage(chemins, "COOKIE")
    p = VeilleStore(db_file).dernier_passage()
    assert (p["cause"], p["pages"], p["entreprises"]) == ("interrompu", 2, ["Orbique"])
    assert p["erreurs"] == [veille.MESSAGES_ARRET["interrompu"]]
    assert not (tmp_path / "session_linkedin.lock").exists()


def test_ajoutee_par_son_lien_elle_prend_le_nom_de_sa_page(base):
    store, db = base
    store.ajouter_entreprise("Orbique Conseil Sas", "2026-10-14",
                             url_linkedin="https://www.linkedin.com/company/orbique-conseil-sas/")
    r = passer(store, db, FauxScraper(FaussePage(), FauxLimites()))
    assert [e["nom"] for e in store.entreprises()] == ["Orbique"]
    assert r.entreprises == ["Orbique"]


def test_un_nom_choisi_par_la_personne_n_est_pas_remplace(base):
    store, db = base
    store.ajouter_entreprise("Mon client", "2026-10-14", url_linkedin="https://www.linkedin.com/company/orbique/")
    passer(store, db, FauxScraper(FaussePage(), FauxLimites()))
    assert [e["nom"] for e in store.entreprises()] == ["Mon client"]


def test_renommer_vers_un_nom_deja_suivi_garde_l_ancien_et_le_dit(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    store.maj_identification(1, "non_identifiee")  # hors du lot : pas de lien
    store.ajouter_entreprise("Orbique Sas", "2026-10-14", url_linkedin="https://www.linkedin.com/company/orbique-sas/")
    r = passer(store, db, FauxScraper(FaussePage(), FauxLimites()))
    assert sorted(e["nom"] for e in store.entreprises()) == ["Orbique", "Orbique Sas"]
    assert any("Orbique Sas" in x and "déjà suivi" in x for x in r.erreurs)


def test_un_identifiant_ambigu_est_dit_tel_quel(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    s = FauxScraper(FaussePage(about=dict(ABOUT_OK, company_id="", html="<main>deux sociétés</main>")),
                    FauxLimites())
    r = passer(store, db, s)
    assert any("identifiant de l'entreprise ambigu" in x and "logs/" in x for x in r.erreurs)
    assert s.dumps == ["<main>deux sociétés</main>"]


def test_une_page_non_enregistree_n_est_pas_dite_enregistree(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    s = FauxScraper(FaussePage(about={"nom": "", "champs": {}, "company_id": "", "description": "", "html": ""}),
                    FauxLimites())
    s._dumper_panneau = lambda html, nom_fichier=None: False
    r = passer(store, db, s)
    assert any("page non enregistrée" in x for x in r.erreurs)
    assert not any("enregistrée dans logs/" in x for x in r.erreurs)


def test_le_vrai_typeahead_distingue_la_panne_de_l_absence(monkeypatch):
    from scraper_v2 import LinkedInScraperV2

    sc = LinkedInScraperV2.__new__(LinkedInScraperV2)  # sans navigateur ni fichiers
    monkeypatch.setattr(sc, "_resoudre_company_urn", lambda nom: None, raising=False)

    class Contexte:
        def __init__(self, cookies):
            self._c = cookies

        async def cookies(self, url):
            return self._c

    class Page:
        url = "https://www.linkedin.com/feed/"

        def __init__(self, reponse, cookies=({"name": "JSESSIONID", "value": '"ajax:1"'},)):
            self.context, self.reponse = Contexte(list(cookies)), reponse

        async def evaluate(self, js, arg=None):
            if isinstance(self.reponse, Exception):
                raise self.reponse
            return self.reponse

    def essai(page):
        echecs = []
        r = asyncio.run(sc._resoudre_company_urn_via_typeahead("Orbique", page, echecs=echecs))
        return r, echecs

    assert essai(Page({"ok": True, "data": {"elements": []}})) == (None, [])
    assert essai(Page({"ok": False, "status": 429}))[1] == ["réponse HTTP 429"]
    assert essai(Page({"ok": False, "error": "TypeError: Failed to fetch"}))[1][0].startswith("appel impossible")
    assert essai(Page(None, cookies=()))[1] and essai(Page(RuntimeError("Target closed")))[1] == ["RuntimeError"]
    # Les appelants existants, sans `echecs`, ne voient rien changer.
    assert asyncio.run(sc._resoudre_company_urn_via_typeahead("Orbique", Page({"ok": False, "status": 500}))) is None


# ── Identification par la recherche d'entreprises (le typeahead répond 404) ──

def test_la_maison_mere_est_retenue_parmi_ses_filiales(base):
    store, db = base
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage(recherche=recherche_de(carte("Orbique Assurances", "orbique-assurances"),
                                             carte("ORBIQUE", "orbique"),
                                             carte("Groupe Orbique Leasing", "orbique-leasing")))
    s = FauxScraper(page, FauxLimites())
    passer(store, db, s)
    e = store.entreprises()[0]
    assert (e["etat"], e["company_id"], e["url_linkedin"]) == (
        "identifiee", "7654321", "https://www.linkedin.com/company/orbique/")
    assert page.visites[1] == "https://www.linkedin.com/company/orbique/about/"
    assert "linkedin.taille" in store.fiche(i)
    assert s.dumps == []


def test_deux_entreprises_au_meme_nom_ne_sont_pas_departagees(base):
    store, db = base
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage(recherche=recherche_de(carte("Orbique", "orbique"), carte("Orbique", "orbique-fr")))
    r = passer(store, db, FauxScraper(page, FauxLimites()))
    e = store.entreprises()[0]
    assert e["etat"] == "non_identifiee" and e["url_linkedin"] is None and e["company_id"] is None
    assert r.erreurs == ["Orbique : plusieurs entreprises « Orbique » sur LinkedIn : collez le lien de la bonne."]
    assert len(page.visites) == 1 and store.fiche(i) == {}


def test_la_recherche_d_entreprises_compte_une_page_du_budget(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage()
    limites = FauxLimites(deja=19)  # une seule page restante : la recherche
    r = passer(store, db, FauxScraper(page, limites))
    assert r.cause == "budget" and r.pages == 1 and limites.pages_veille_today == 20
    assert page.visites == ["https://www.linkedin.com/search/results/companies/?keywords=Orbique"]
    # Rien de confirmé : elle reste à identifier, en tête du prochain lot.
    e = store.entreprises()[0]
    assert (e["etat"], e["url_linkedin"], e["derniere_veille"]) == ("a_identifier", None, None)


def test_la_page_de_recherche_est_parcourue_comme_un_humain(base):
    store, db = base
    store.ajouter_entreprise("Inconnue", "2026-10-14")
    s = FauxScraper(FaussePage(recherche=recherche_de()), FauxLimites())
    passer(store, db, s)
    assert s.human.parcours == 1 and s.human.delais >= 1


def test_une_recherche_illisible_ne_declare_personne_introuvable(base):
    # Aucune carte lue sur une page affichée : LinkedIn a sans doute changé sa
    # mise en page. Ce n'est pas « introuvable » : on garde la page, on
    # n'insiste pas sur les autres noms, et les liens connus continuent.
    store, db = base
    store.ajouter_entreprise("Alpha", "2026-10-14")
    store.ajouter_entreprise("Bêta", "2026-10-14")
    store.ajouter_entreprise("Orbique", "2026-10-14", url_linkedin="https://www.linkedin.com/company/orbique/")
    store.ajouter_entreprise("Gamma", "2026-10-14")
    page = FaussePage(recherche=recherche_de(html="<main>nouvelle mise en page</main>"))
    s = FauxScraper(page, FauxLimites())
    r = passer(store, db, s)
    etats = {e["nom"]: (e["etat"], e["url_linkedin"], e["derniere_veille"]) for e in store.entreprises()}
    assert etats["Alpha"] == ("a_identifier", None, "2026-10-15T08:00:00")  # en fin de rotation
    assert etats["Bêta"] == ("a_identifier", None, None) and etats["Gamma"] == ("a_identifier", None, None)
    assert etats["Orbique"][0] == "identifiee"  # un lien collé ne dépend pas de la recherche par nom
    assert page.recherches == ["Alpha"]
    assert len([v for v in page.visites if "results/companies" in v]) == 1
    assert s.dumps == ["<main>nouvelle mise en page</main>"]
    assert s.noms_dumps == ["recherche_entreprises_dump.html"]
    lignes = [x for x in r.erreurs if "Alpha" in x]
    assert len(lignes) == 1 and "Bêta" in lignes[0] and "Gamma" in lignes[0]
    assert "structure" in lignes[0] and "logs/" in lignes[0]
    assert not any("aucune entreprise « " in x for x in r.erreurs)
    assert r.entreprises == ["Orbique"]


def test_une_recherche_illisible_non_enregistree_ne_le_pretend_pas(base):
    store, db = base
    store.ajouter_entreprise("Alpha", "2026-10-14")
    s = FauxScraper(FaussePage(recherche=recherche_de(html="<main>?</main>")), FauxLimites())
    s._dumper_panneau = lambda html, nom_fichier=None: False
    r = passer(store, db, s)
    assert any("Alpha" in x and "page non enregistrée" in x for x in r.erreurs)
    assert not any("enregistrée dans logs/" in x for x in r.erreurs)


def test_une_recherche_sans_carte_ni_html_n_enregistre_rien(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    s = FauxScraper(FaussePage(recherche=recherche_de()), FauxLimites())
    r = passer(store, db, s)
    assert s.dumps == []
    assert r.erreurs == ["Orbique : aucune entreprise « Orbique » sur LinkedIn (proposées : aucune) "
                         "— collez le lien de sa page entreprise."]


def test_un_refus_apres_a_propos_ne_garde_pas_le_lien_trouve(base):
    # Gardé, le lien ferait reprendre l'entreprise au passage suivant comme un
    # lien collé — sans plus comparer les noms.
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage(about=dict(ABOUT_OK, nom="Orbital Conseil"))
    passer(store, db, FauxScraper(page, FauxLimites()))
    e = store.entreprises()[0]
    assert e["etat"] == "non_identifiee" and e["url_linkedin"] is None
    page.visites.clear()
    passer(store, db, FauxScraper(page, FauxLimites()), maintenant="2026-10-16T08:00:00")
    assert page.visites == []


def test_le_nom_saisi_reste_meme_s_il_ressemble_au_lien_trouve(base):
    store, db = base
    store.ajouter_entreprise("Orbique Conseil", "2026-10-14")
    page = FaussePage(about=dict(ABOUT_OK, nom="Orbique Conseil SAS"),
                      recherche=recherche_de(carte("ORBIQUE CONSEIL SAS", "orbique-conseil")))
    passer(store, db, FauxScraper(page, FauxLimites()))
    e = store.entreprises()[0]
    assert e["nom"] == "Orbique Conseil" and e["etat"] == "identifiee"


def test_une_fenetre_fermee_arrete_le_passage(base):
    store, db = base
    store.ajouter_entreprise("Alpha", "2026-10-14")
    store.ajouter_entreprise("Bêta", "2026-10-14")
    page = FaussePage()
    s = FauxScraper(page, FauxLimites())
    page.ferme_pendant = {"Alpha"}
    r = passer(store, db, s)
    assert r.cause == "erreur" and page.recherches == ["Alpha"] and r.pages == 1
    assert any("fenêtre LinkedIn s'est fermée" in x for x in r.erreurs)
    assert {e["etat"] for e in store.entreprises()} == {"a_identifier"}
    assert s.navigateur.ferme


# ── Coordonnées : site de l'entreprise, personnes en relation ─────────

PROFIL = "https://www.linkedin.com/in/{}/"


def test_le_site_de_l_entreprise_est_lu_et_garde_dans_la_fiche(base):
    store, db = base
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    lus = []

    def site_web(site):
        lus.append(site)
        return {"emails": ["contact@orbique.example", "rh@orbique.example"],
                "telephones": ["01 23 45 67 89"], "pages_lues": [site]}

    r = passer(store, db, FauxScraper(FaussePage(), FauxLimites()), site_web=site_web)
    assert lus == ["https://www.orbique.example"] and r.cause == "termine"
    fiche = store.fiche(i)
    assert fiche["site.email"]["valeur"] == "contact@orbique.example, rh@orbique.example"
    assert fiche["site.telephone"]["valeur"] == "01 23 45 67 89"
    assert store.lectures(i)["site"] == "2026-10-15T08:00:00"
    # Relu tous les 30 jours, pas à chaque passage.
    passer(store, db, FauxScraper(FaussePage(), FauxLimites()), site_web=site_web, maintenant="2026-10-20T08:00:00")
    assert len(lus) == 1
    passer(store, db, FauxScraper(FaussePage(), FauxLimites()), site_web=site_web, maintenant="2026-11-15T08:00:00")
    assert len(lus) == 2


def test_un_site_qui_ne_publie_rien_est_dit_et_date(base):
    store, db = base
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    passer(store, db, FauxScraper(FaussePage(), FauxLimites()))
    assert store.fiche(i)["site.email"]["valeur"] == "non publié"
    assert store.fiche(i)["site.telephone"]["valeur"] == "non publié"
    assert store.lectures(i)["site"] == "2026-10-15T08:00:00"


def test_un_site_injoignable_est_signale_sans_arreter_la_veille(base):
    store, db = base
    i = store.ajouter_entreprise("Orbique", "2026-10-14")

    def site_web(site):
        raise veille.SiteInjoignable("délai dépassé")

    page = FaussePage(resultats={1: [personne("jeanne-exemple", "PM")]})
    r = passer(store, db, FauxScraper(page, FauxLimites()), site_web=site_web)
    assert r.cause == "termine" and r.entreprises == ["Orbique"] and r.nouveaux_contacts == 1
    assert r.erreurs == ["Orbique : site https://www.orbique.example injoignable (délai dépassé) "
                         "— coordonnées générales non relues."]
    assert "site" not in store.lectures(i)  # nouvel essai au prochain passage


def test_un_site_en_panne_n_est_ni_reessaye_ni_redit_pendant_7_jours(base):
    store, db = base
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    appels = []

    def lignes_site(r):  # le passage dit aussi autre chose (aucun profil trouvé…)
        return [e for e in r.erreurs if "site" in e]

    def panne(site):
        appels.append(site)
        raise veille.SiteInjoignable("HTTP 403")

    r = passer(store, db, FauxScraper(FaussePage(), FauxLimites()), site_web=panne)
    assert len(appels) == 1 and len(lignes_site(r)) == 1
    assert store.lectures(i)["site_echec"] == "2026-10-15T08:00:00"
    # Pendant le délai : aucune requête, aucune nouvelle ligne.
    r = passer(store, db, FauxScraper(FaussePage(), FauxLimites()), site_web=panne, maintenant="2026-10-21T08:00:00")
    assert len(appels) == 1 and lignes_site(r) == []
    # Passé 7 jours : un nouvel essai, donc une nouvelle ligne si ça échoue encore.
    r = passer(store, db, FauxScraper(FaussePage(), FauxLimites()), site_web=panne, maintenant="2026-10-22T08:00:00")
    assert len(appels) == 2 and len(lignes_site(r)) == 1


def test_une_lecture_reussie_efface_l_echec_du_site(base):
    store, db = base
    i = store.ajouter_entreprise("Orbique", "2026-10-14")

    def panne(site):
        raise veille.SiteInjoignable("délai dépassé")

    passer(store, db, FauxScraper(FaussePage(), FauxLimites()), site_web=panne)
    passer(store, db, FauxScraper(FaussePage(), FauxLimites()), maintenant="2026-10-23T08:00:00")  # site_muet : lu
    lectures = store.lectures(i)
    assert "site_echec" not in lectures and lectures["site"] == "2026-10-23T08:00:00"


def test_sans_site_sur_la_fiche_rien_n_est_lu(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    about = dict(ABOUT_OK, champs={k: v for k, v in ABOUT_OK["champs"].items() if k != "Site web"})

    def site_web(site):
        raise AssertionError("aucun site à lire")

    assert passer(store, db, FauxScraper(FaussePage(about=about), FauxLimites()), site_web=site_web).cause == "termine"


def test_les_coordonnees_des_personnes_en_relation_sont_lues(base):
    store, db = base
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage(resultats={1: [personne("jeanne-exemple", "PM"), personne("paul-exemple", "PM")]})
    page.degres = {"jeanne-exemple": "1er", "paul-exemple": "2e"}
    page.fenetres = {"jeanne-exemple": {"dialogue": True, "email": "jeanne@orbique.example",
                                        "telephone": "+33 6 12 34 56 78", "html": ""}}
    limites = FauxLimites()
    r = passer(store, db, FauxScraper(page, limites))
    assert r.cause == "termine" and r.erreurs == []
    # Paul (2e degré, sans invitation acceptée) n'est jamais visité.
    assert page.visites[-1] == PROFIL.format("jeanne-exemple")
    assert PROFIL.format("paul-exemple") not in page.visites
    assert page.clics == [PROFIL.format("jeanne-exemple")]
    assert r.pages == limites.pages_veille_today == 5  # 4 + le profil
    c = store.coordonnees(PROFIL.format("jeanne-exemple"))
    assert c["email"] == "jeanne@orbique.example" and c["partage"] == "oui"
    assert {x["url"]: x["degre"] for x in store.contacts(i)}[PROFIL.format("paul-exemple")] == "2e"
    # Lues : pas relues au passage suivant.
    page.visites.clear()
    passer(store, db, FauxScraper(page, FauxLimites()), maintenant="2026-10-16T08:00:00")
    assert PROFIL.format("jeanne-exemple") not in page.visites


def test_une_invitation_acceptee_ouvre_les_coordonnees(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    pid = db.ajouter_profil("Paul", "PM", "Orbique", "", "http://linkedin.com/in/Paul-Exemple?trk=x")
    db.ajouter_invitation(pid)
    db.marquer_acceptee("http://linkedin.com/in/Paul-Exemple?trk=x")
    page = FaussePage(resultats={1: [personne("paul-exemple", "PM"), personne("lea-exemple", "PM")]})
    passer(store, db, FauxScraper(page, FauxLimites()))
    assert page.clics == [PROFIL.format("paul-exemple")]


def test_une_fenetre_sans_email_est_rien_de_partage(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage(resultats={1: [personne("jeanne-exemple", "PM")]})
    page.degres = {"jeanne-exemple": "1er"}
    r = passer(store, db, FauxScraper(page, FauxLimites()))
    assert r.erreurs == []
    c = store.coordonnees(PROFIL.format("jeanne-exemple"))
    assert c["partage"] == "rien" and c["releve_le"] == "2026-10-15T08:00:00"


def test_sans_lien_coordonnees_rien_n_est_enregistre(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage(resultats={1: [personne("jeanne-exemple", "PM")]})
    page.degres = {"jeanne-exemple": "1er"}
    page.sans_lien = {"jeanne-exemple"}
    r = passer(store, db, FauxScraper(page, FauxLimites()))
    assert r.cause == "termine" and r.entreprises == ["Orbique"]
    assert r.erreurs == ["Orbique : Jeanne-Exemple — lien « Coordonnées » absent du profil ; "
                         "nouvel essai dans 7 jours."]
    assert store.coordonnees(PROFIL.format("jeanne-exemple")) is None


def test_une_fenetre_qui_ne_s_ouvre_pas_n_enregistre_rien(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage(resultats={1: [personne("jeanne-exemple", "PM")]})
    page.degres = {"jeanne-exemple": "1er"}
    page.sans_fenetre = {"jeanne-exemple"}
    r = passer(store, db, FauxScraper(page, FauxLimites()))
    assert r.erreurs == ["Orbique : Jeanne-Exemple — la fenêtre « Coordonnées » ne s'est pas ouverte ; "
                         "nouvel essai dans 7 jours."]
    assert store.coordonnees(PROFIL.format("jeanne-exemple")) is None


def test_une_fenetre_illisible_est_enregistree_pour_diagnostic(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage(resultats={1: [personne("jeanne-exemple", "PM")]})
    page.degres = {"jeanne-exemple": "1er"}
    page.fenetres = {"jeanne-exemple": {"dialogue": True, "email": "", "telephone": "", "html": "<dialog>?</dialog>"}}
    s = FauxScraper(page, FauxLimites())
    r = passer(store, db, s)
    assert s.noms_dumps == ["coordonnees_dump.html"] and s.dumps == ["<dialog>?</dialog>"]
    assert r.erreurs == ["Orbique : Jeanne-Exemple — fenêtre « Coordonnées » illisible, sa structure a peut-être "
                         "changé (page enregistrée dans logs/) ; rien n'est enregistré."]
    assert store.coordonnees(PROFIL.format("jeanne-exemple")) is None


def test_au_plus_trois_profils_par_entreprise_et_par_passage(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    gens = [f"p{n}-exemple" for n in range(5)]
    page = FaussePage(resultats={1: [personne(v, "PM") for v in gens]})
    page.degres = {v: "1er" for v in gens}
    passer(store, db, FauxScraper(page, FauxLimites()))
    assert len(page.clics) == veille.COORDONNEES_PAR_ENTREPRISE == 3


def test_budget_epuise_avant_les_coordonnees_arret_propre(base):
    store, db = base
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage(resultats={1: [personne("jeanne-exemple", "PM")]})
    page.degres = {"jeanne-exemple": "1er"}
    limites = FauxLimites(deja=16)  # 4 pages : recherche, « À propos », page 1, page 2 vide
    r = passer(store, db, FauxScraper(page, limites))
    assert r.cause == "budget" and r.pages == 4 and limites.pages_veille_today == 20
    assert PROFIL.format("jeanne-exemple") not in page.visites and page.clics == []
    # Ce qui a été lu est gardé.
    assert [c["url"] for c in store.contacts(i)] == [PROFIL.format("jeanne-exemple")]
    assert store.fiche(i)["site.email"]["valeur"] == "non publié"


def test_degres_illisibles_la_relation_vient_des_seules_invitations(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage(resultats={1: [personne("jeanne-exemple", "PM")]})
    page.degres = {}
    r = passer(store, db, FauxScraper(page, FauxLimites()))
    assert r.cause == "termine" and r.erreurs == [] and page.clics == []


def test_une_erreur_sur_une_personne_n_empeche_ni_les_suivantes_ni_le_passage(base):
    store, db = base
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage(resultats={1: [personne("jeanne-exemple", "PM"), personne("paul-exemple", "PM")]})
    page.degres = {"jeanne-exemple": "1er", "paul-exemple": "1er"}
    page.fenetre_explose = {"jeanne-exemple"}
    r = passer(store, db, FauxScraper(page, FauxLimites()))
    assert r.entreprises == ["Orbique"] and store.entreprises()[0]["derniere_veille"] == "2026-10-15T08:00:00"
    assert len(r.erreurs) == 1 and "Jeanne-Exemple" in r.erreurs[0] and "RuntimeError" in r.erreurs[0]
    assert store.coordonnees(PROFIL.format("jeanne-exemple")) is None
    assert store.coordonnees(PROFIL.format("paul-exemple"))["partage"] == "rien"


def test_un_profil_injoignable_est_dit_et_reessaye(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage(resultats={1: [personne("jeanne-exemple", "PM")]})
    page.degres = {"jeanne-exemple": "1er"}
    s = FauxScraper(page, FauxLimites())
    s.network_manager = ReseauEnPanne(page, "/in/jeanne-exemple")
    r = passer(store, db, s)
    assert r.entreprises == ["Orbique"] and page.clics == []
    assert r.erreurs == ["Orbique : Jeanne-Exemple — page LinkedIn injoignable ; nouvel essai dans 7 jours."]
    assert store.coordonnees(PROFIL.format("jeanne-exemple")) is None


def test_un_essai_manque_n_est_pas_retente_avant_7_jours(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage(resultats={1: [personne("jeanne-exemple", "PM")]})
    page.degres = {"jeanne-exemple": "1er"}
    page.sans_lien = {"jeanne-exemple"}
    passer(store, db, FauxScraper(page, FauxLimites()))
    assert store.coordonnees(PROFIL.format("jeanne-exemple")) is None  # pas une lecture
    page.visites.clear()
    r = passer(store, db, FauxScraper(page, FauxLimites()), maintenant="2026-10-16T08:00:00")
    assert PROFIL.format("jeanne-exemple") not in page.visites and r.erreurs == []
    passer(store, db, FauxScraper(page, FauxLimites()), maintenant="2026-10-22T08:00:00")
    assert PROFIL.format("jeanne-exemple") in page.visites


def test_les_echecs_ne_prennent_pas_les_places_des_autres(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    gens = ["a-exemple", "b-exemple", "c-exemple", "d-exemple"]
    page = FaussePage(resultats={1: [personne(v, "PM") for v in gens]})
    page.degres = {v: "1er" for v in gens}
    page.sans_fenetre = {"a-exemple", "b-exemple", "c-exemple"}
    passer(store, db, FauxScraper(page, FauxLimites()))
    assert page.clics == [PROFIL.format(v) for v in gens[:3]]
    page.clics.clear()
    passer(store, db, FauxScraper(page, FauxLimites()), maintenant="2026-10-16T08:00:00")
    assert page.clics == [PROFIL.format("d-exemple")]


def test_une_fenetre_illisible_compte_comme_un_essai(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage(resultats={1: [personne("jeanne-exemple", "PM")]})
    page.degres = {"jeanne-exemple": "1er"}
    page.fenetres = {"jeanne-exemple": {"dialogue": True, "email": "", "telephone": "", "html": "<dialog>?</dialog>"}}
    passer(store, db, FauxScraper(page, FauxLimites()))
    page.clics.clear()
    passer(store, db, FauxScraper(page, FauxLimites()), maintenant="2026-10-16T08:00:00")
    assert page.clics == []


def test_degres_en_erreur_ne_sont_pas_une_erreur(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage(resultats={1: [personne("jeanne-exemple", "PM")]})
    page.degres = None  # la lecture du degré lève une erreur Playwright
    r = passer(store, db, FauxScraper(page, FauxLimites()))
    assert r.cause == "termine" and r.entreprises == ["Orbique"] and r.erreurs == [] and r.nouveaux_contacts == 1


def test_un_site_inutilisable_est_dit_dans_la_fiche_et_relu_dans_30_jours(base):
    store, db = base
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    about = dict(ABOUT_OK, champs=dict(ABOUT_OK["champs"], **{"Site web": ["https://www.facebook.com/orbique"]}))

    def site_web(site):
        raise AssertionError("une page de réseau social n'est pas lue")

    page = FaussePage(about=about, resultats={1: [personne("jeanne-exemple", "PM")]})
    r = passer(store, db, FauxScraper(page, FauxLimites()), site_web=site_web)
    assert r.erreurs == []
    assert store.fiche(i)["site.lecture"]["valeur"] == (
        "site non lisible (le site indiqué est une page de réseau social)")
    assert store.lectures(i)["site"] == "2026-10-15T08:00:00"
    passer(store, db, FauxScraper(page, FauxLimites()), site_web=site_web, maintenant="2026-11-10T08:00:00")
    assert store.lectures(i)["site"] == "2026-10-15T08:00:00"  # pas revu avant 30 jours


def test_un_site_lu_le_dit_dans_la_fiche(base):
    store, db = base
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    passer(store, db, FauxScraper(FaussePage(), FauxLimites()))
    assert store.fiche(i)["site.lecture"]["valeur"] == "site lu"


def test_une_coordonnee_que_le_site_ne_publie_plus_est_remplacee(base):
    """Sans cela, l'ancien numéro resterait affiché comme actuel, avec une date de relevé récente."""
    store, db = base
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    lu = {"emails": ["contact@orbique.example"], "telephones": ["01 23 45 67 89"], "pages_lues": []}
    passer(store, db, FauxScraper(FaussePage(), FauxLimites()), site_web=lambda site: lu)
    lu = {"emails": [], "telephones": [], "pages_lues": []}
    passer(store, db, FauxScraper(FaussePage(), FauxLimites()), site_web=lambda site: lu,
           maintenant="2026-11-15T08:00:00")
    fiche = store.fiche(i)
    assert fiche["site.telephone"]["valeur"] == "non publié"
    assert fiche["site.email"]["valeur"] == "non publié"
    assert fiche["site.telephone"]["releve_le"] == "2026-11-15T08:00:00"


def test_le_telephone_d_une_personne_est_normalise_en_francais(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage(resultats={1: [personne("jeanne-exemple", "PM"), personne("paul-exemple", "PM")]})
    page.degres = {"jeanne-exemple": "1er", "paul-exemple": "1er"}
    page.fenetres = {
        "jeanne-exemple": {"dialogue": True, "email": "", "telephone": "06 12 34 56 78", "html": ""},
        "paul-exemple": {"dialogue": True, "email": "", "telephone": "+44 20 7946 0958", "html": ""}}
    passer(store, db, FauxScraper(page, FauxLimites()))
    # Texte « +33 6 12 34 56 78 » (jamais un nombre pour Excel) ; l'étranger reste tel que lu.
    assert store.coordonnees(PROFIL.format("jeanne-exemple"))["telephone"] == "+33 6 12 34 56 78"
    assert store.coordonnees(PROFIL.format("paul-exemple"))["telephone"] == "+44 20 7946 0958"
