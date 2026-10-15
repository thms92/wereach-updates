# -*- coding: utf-8 -*-
"""Le moteur de veille, sans navigateur : chaque page LinkedIn est simulée.

On vérifie l'enchaînement — budget, identification, annuaire recoupé,
recherche paginée avec curseur, nouveautés — et surtout les arrêts : budget
épuisé, cookie expiré, entreprise introuvable. Aucune visite LinkedIn,
aucun appel à l'annuaire réel.
"""

import asyncio
import json

import pytest

import veille
from database import DatabaseManager
from utils.annuaire import AnnuaireIndisponible
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

    async def human_delay(self, *a, **k):
        pass

    async def check_safety(self, page):
        return self.sur

    async def browse_page_naturally(self, page):
        self.parcours += 1


class FauxReseau:
    def __init__(self, page):
        self.page = page

    async def safe_page_goto(self, page, url):
        self.page.url = url
        self.page.visites.append(url)
        return True


class FaussePage:
    def __init__(self, about=ABOUT_OK, resultats=None, url_apres_goto=None):
        self.about = about
        self.resultats = resultats or {}
        self.visites = []
        self.url = ""
        self.url_apres_goto = url_apres_goto

    async def evaluate(self, js):
        return self.about


class FauxNavigateur:
    def __init__(self):
        self.ferme = False

    async def close(self):
        self.ferme = True


class FauxScraper:
    def __init__(self, page, limites, typeahead="7654321", cookie_ok=True):
        self.page = page
        self.navigateur = FauxNavigateur()
        self.human = FauxHumain(limites)
        self.network_manager = FauxReseau(page)
        self.typeahead = typeahead
        self.cookie_ok = cookie_ok
        self.dumps = []
        self.noms_dumps = []
        self.errors = []
        self.typeahead_appels = []
        self.explose = set()           # noms dont l'identification lève une erreur Playwright
        self.extraction_en_echec = False

    async def _resoudre_company_urn_via_typeahead(self, nom, page):
        self.typeahead_appels.append(nom)
        if nom in self.explose:
            raise RuntimeError("Execution context was destroyed")
        return self.typeahead

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


def passer(store, db, scraper, reglages=None, annuaire=lambda nom: ANNUAIRE_OK, maintenant="2026-10-15T08:00:00",
           actualite=lambda nom: []):
    return asyncio.run(veille.passage_async(
        scraper, store, db, reglages or ReglagesVeille(["Product", "Data", "IA"], [], 20),
        "COOKIE", maintenant, annuaire=annuaire, actualite=actualite))


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
    assert limites.pages_veille_today == r.pages == 3  # « À propos » + page 1 + page 2 vide
    assert page.visites[0] == "https://www.linkedin.com/company/7654321/about/"


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
    limites = FauxLimites(deja=18)  # 2 pages restantes sur 20
    r = passer(store, db, FauxScraper(page, limites))
    assert r.cause == "budget"
    assert len(page.visites) == 2  # « À propos » + page 1, pas de page 2
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
    page = FaussePage()
    r = passer(store, db, FauxScraper(page, FauxLimites(), typeahead=None))
    assert store.entreprises()[0]["etat"] == "non_identifiee"
    assert page.visites == []  # aucune recherche lancée sans identifiant
    assert any("Inconnue" in e for e in r.erreurs)


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
    assert [v for v in page.visites if "search" in v] == []


def test_un_lien_colle_est_utilise_au_lieu_du_nom(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14", url_linkedin="https://www.linkedin.com/company/orbique/")
    page = FaussePage()
    passer(store, db, FauxScraper(page, FauxLimites(), typeahead=None))
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


def test_l_actualite_est_relue_pour_toutes_meme_sans_budget(base):
    store, db = base
    a = store.ajouter_entreprise("Orbique", "2026-10-14")
    b = store.ajouter_entreprise("Zéphyr", "2026-10-14")
    demandees = []

    def actu(nom):
        demandees.append(nom)
        return [dict(ARTICLE, lien=f"https://n/{nom}")]

    page = FaussePage()
    r = passer(store, db, FauxScraper(page, FauxLimites(deja=20)), actualite=actu)
    assert sorted(demandees) == ["Orbique", "Zéphyr"]
    assert r.nouvelles_actualites == 2 and r.cause == "budget" and page.visites == []
    assert len(store.actualites(a)) == len(store.actualites(b)) == 1


def test_l_actualite_n_est_relue_qu_une_fois_par_jour(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    demandees = []
    actu = lambda nom: demandees.append(nom) or []
    passer(store, db, FauxScraper(FaussePage(), FauxLimites(deja=20)), actualite=actu, maintenant="2026-10-15T08:00:00")
    passer(store, db, FauxScraper(FaussePage(), FauxLimites(deja=20)), actualite=actu, maintenant="2026-10-15T14:00:00")
    passer(store, db, FauxScraper(FaussePage(), FauxLimites(deja=20)), actualite=actu, maintenant="2026-10-16T08:00:00")
    assert demandees == ["Orbique", "Orbique"]


def test_google_news_injoignable_un_seul_message_et_la_veille_continue(base):
    from utils.actualite import ActualiteIndisponible
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    store.ajouter_entreprise("Zéphyr", "2026-10-14")

    def panne(nom):
        raise ActualiteIndisponible("délai dépassé")

    r = passer(store, db, FauxScraper(FaussePage(resultats={1: [personne("a", "PM")]}), FauxLimites()), actualite=panne)
    assert sum("actualité" in e.lower() for e in r.erreurs) == 1
    assert r.nouveaux_contacts >= 1


def test_lancer_passage_respecte_le_verrou_et_enregistre(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from utils.verrou_linkedin import session_linkedin

    db_file = str(tmp_path / "p.db")
    DatabaseManager(db_file=db_file)
    chemins = SimpleNamespace(db_file=db_file, profiles_csv=str(tmp_path / "p.csv"), config_dir=str(tmp_path))
    with session_linkedin(tmp_path, "recherche"):
        r = veille.lancer_passage(chemins, "COOKIE")
    assert r.cause == "occupe"
    assert VeilleStore(db_file).dernier_passage()["cause"] == "occupe"


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
    assert [v for v in page.visites if "search" in v] == []
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
    passer(store, db, FauxScraper(FaussePage(about=dict(ABOUT_OK, nom="AB")), FauxLimites()),
           annuaire=lambda nom: appels.append(nom) or ANNUAIRE_OK)
    assert appels == []
    assert store.fiche(i)["annuaire.rapprochement"]["valeur"] == "nom trop court pour l'annuaire"


def test_un_lien_colle_avec_sa_sous_page_n_est_pas_double(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14",
                             url_linkedin="https://www.linkedin.com/company/orbique/about/?trk=x")
    page = FaussePage()
    passer(store, db, FauxScraper(page, FauxLimites(), typeahead=None))
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
    assert [v for v in page.visites if "search" in v] == []
    assert any("Orbital Conseil" in x and "collez le lien" in x for x in r.erreurs)


def test_le_nom_suivi_contenu_dans_le_nom_de_la_page_est_accepte(base):
    store, db = base
    i = store.ajouter_entreprise("Décathlon", "2026-10-14")
    page = FaussePage(about=dict(ABOUT_OK, nom="DECATHLON France"))
    passer(store, db, FauxScraper(page, FauxLimites()))
    assert store.entreprises()[0]["etat"] == "identifiee"
    assert "linkedin.taille" in store.fiche(i)


def test_un_lien_colle_n_est_pas_soumis_a_la_comparaison_des_noms(base):
    store, db = base
    store.ajouter_entreprise("Mon client", "2026-10-14", url_linkedin="https://www.linkedin.com/company/orbique/")
    passer(store, db, FauxScraper(FaussePage(), FauxLimites(), typeahead=None))
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
    assert s.human.parcours == r.pages == 3  # « À propos », page 1, page 2


def test_une_erreur_inattendue_sur_une_entreprise_n_arrete_pas_le_passage(base):
    store, db = base
    store.ajouter_entreprise("Bombe", "2026-10-14")
    store.ajouter_entreprise("Orbique", "2026-10-14")
    s = FauxScraper(FaussePage(resultats={1: [personne("a", "PM")]}), FauxLimites())
    s.explose = {"Bombe"}
    r = passer(store, db, s)
    assert r.cause == "termine" and r.entreprises == ["Orbique"]
    assert any("Bombe" in x and "RuntimeError" in x for x in r.erreurs)


def test_le_budget_est_verifie_avant_d_identifier_l_entreprise_suivante(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    store.ajouter_entreprise("Zorbique", "2026-10-14")
    s = FauxScraper(FaussePage(about=dict(ABOUT_OK, nom="Orbique Zorbique"),
                               resultats={1: [personne("a", "PM")], 2: [personne("b", "PM")]}),
                    FauxLimites(deja=17))
    r = passer(store, db, s)
    assert r.cause == "budget" and s.typeahead_appels == ["Orbique"]


def test_l_annuaire_est_interroge_avec_le_nom_de_la_page_linkedin(base):
    store, db = base
    store.ajouter_entreprise("Mon client", "2026-10-14", url_linkedin="https://www.linkedin.com/company/orbique/")
    appels = []
    passer(store, db, FauxScraper(FaussePage(), FauxLimites(), typeahead=None),
           annuaire=lambda nom: appels.append(nom) or ANNUAIRE_OK)
    assert appels == ["Orbique"]


def test_une_page_illisible_passe_en_fin_de_rotation(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage(about={"nom": "", "champs": {}, "company_id": "", "description": "", "html": "x"})
    passer(store, db, FauxScraper(page, FauxLimites()))
    assert store.entreprises()[0]["derniere_veille"] == "2026-10-15T08:00:00"
