# -*- coding: utf-8 -*-
"""Chaque invitation garde la date de sa dernière vérification."""

import sqlite3

import pytest
from datetime import datetime, timezone

from database import DatabaseManager
from scraper_v2 import degre_depuis_entete
from utils.verification import derniere_verification, enregistrer_verification

URL_A = "https://exemple.test/in/a"
URL_B = "https://exemple.test/in/b"
URL_C = "https://exemple.test/in/c"


def _base_avec_trois_invitations(tmp_path):
    """A : envoyée J-10, vérifiée J-1. B : J-5, jamais. C : J-2, jamais."""
    db = DatabaseManager(db_file=str(tmp_path / "verif.db"))
    con = sqlite3.connect(db.db_file)
    pids = [con.execute("INSERT INTO profiles (nom, url) VALUES (?, ?)",
                        (url[-1], url)).lastrowid
            for url in (URL_A, URL_B, URL_C)]
    con.commit()
    con.close()
    for pid in pids:
        db.ajouter_invitation(pid)
    con = sqlite3.connect(db.db_file)
    for pid, envoi, verif in ((pids[0], "-10 days", "-1 days"),
                              (pids[1], "-5 days", None),
                              (pids[2], "-2 days", None)):
        con.execute("UPDATE invitations SET date_envoi = datetime('now', ?), "
                    "date_verification = CASE WHEN ? IS NULL THEN NULL "
                    "ELSE datetime('now', ?) END WHERE profile_id = ?",
                    (envoi, verif, verif, pid))
    con.commit()
    con.close()
    return db


def test_jamais_verifiees_d_abord_les_plus_recentes_en_tete(tmp_path):
    db = _base_avec_trois_invitations(tmp_path)
    assert [p["url"] for p in db.invitations_en_attente()] == [URL_C, URL_B, URL_A]


def test_marquer_verifiees_fait_passer_en_fin_de_liste(tmp_path):
    db = _base_avec_trois_invitations(tmp_path)
    db.marquer_verifiees([URL_C])
    assert [p["url"] for p in db.invitations_en_attente()][-1] == URL_C


def test_marquer_verifiees_ignore_les_invitations_acceptees(tmp_path):
    db = _base_avec_trois_invitations(tmp_path)
    db.marquer_acceptee(URL_B)
    db.marquer_verifiees([URL_B])
    con = sqlite3.connect(db.db_file)
    (date,) = con.execute(
        "SELECT i.date_verification FROM invitations i JOIN profiles p "
        "ON i.profile_id = p.id WHERE p.url = ?", (URL_B,)).fetchone()
    con.close()
    assert date is None


def test_derniere_verification_aller_retour(tmp_path):
    moment = datetime(2026, 10, 24, 9, 30, tzinfo=timezone.utc)
    enregistrer_verification(str(tmp_path), moment)
    assert derniere_verification(str(tmp_path)) == moment


def test_derniere_verification_sans_moment_donne_l_heure_courante(tmp_path):
    avant = datetime.now(timezone.utc)
    enregistrer_verification(str(tmp_path))
    lu = derniere_verification(str(tmp_path))
    assert avant <= lu <= datetime.now(timezone.utc)


def test_derniere_verification_absente_ou_illisible(tmp_path):
    assert derniere_verification(str(tmp_path)) is None
    (tmp_path / "derniere_verification.json").write_text("{pas du json")
    assert derniere_verification(str(tmp_path)) is None


# En-tête réel d'un profil de 3e degré (page enregistrée le 2026-10-20) :
# il montre pourtant un bouton « Message ».
ENTETE_3E = "\n".join([
    "Rodolphe LE BLEVENEC", "· 3e", "Product Builder @Roole chez WeFiiT", "WeFiiT",
    "Paris, Île-de-France, France", "·", "Coordonnées", "WeFiiT", "500 ou +",
    "relations", "Se connecter", "Message",
])


@pytest.mark.parametrize("texte,attendu", [
    ("Ana Test · 1er\nProduct Manager chez Orbique", "1er"),
    ("Ana Test\n· 2e\nPM", "2e"),
    ("Ana Test · 1st\nPM", "1er"),
    ("Ana Test · 2nd\nPM", "2e"),
    ("Ana Test · 3rd\nPM", "3e"),
    ("Ana Test\n1er\nPM", "1er"),
    ("Ana Test\nAlternante 2e année · Paris", ""),
    ("", ""),
    (ENTETE_3E, "3e"),
    # Plus bas que les 4 premières lignes, ce n'est plus l'en-tête du nom.
    ("Jean\nÉtudiant\nParis\nOrbique\nÉtudiant · 1er cycle", ""),
])
def test_degre_depuis_entete(texte, attendu):
    assert degre_depuis_entete(texte) == attendu


# ── Lecture des listes : analyse du HTML ──

import asyncio

from scraper_v2 import LinkedInScraperV2
from tests.listes_linkedin_fictives import page_envoyees, page_relations, personne
from utils.listes_linkedin import (LIBELLE_LISTE_ILLISIBLE, MOTIF_TOTAL_ENVOYEES,
                                   MOTIF_TOTAL_RELATIONS, URL_INVITATIONS_ENVOYEES,
                                   URL_RELATIONS, ListeLue, classer, est_urn,
                                   lire_liste, slug_profil)

ENVOYEES_18 = [personne(i, "eva") for i in range(18)]
RELATIONS_20 = [personne(i, "bob") for i in range(20)]


def test_lit_les_18_personnes_de_la_liste_des_envoyees():
    lue = lire_liste(page_envoyees(ENVOYEES_18), URL_INVITATIONS_ENVOYEES,
                     MOTIF_TOTAL_ENVOYEES)
    assert lue.slugs == [p["slug"] for p in ENVOYEES_18]
    assert lue.annonce == 18 and lue.complete
    assert lue.suivante is None


def test_lit_les_20_relations_une_fois_chacune():
    # Chaque carte de relation porte deux fois le lien du profil.
    lue = lire_liste(page_relations(RELATIONS_20), URL_RELATIONS, MOTIF_TOTAL_RELATIONS)
    assert lue.slugs == [p["slug"] for p in RELATIONS_20]
    assert lue.annonce == 20 and lue.complete


def test_les_liens_hors_de_la_liste_ne_comptent_pas():
    # Suggestion à côté, son propre profil dans l'en-tête, texte de script.
    lue = lire_liste(page_relations(RELATIONS_20), URL_RELATIONS, MOTIF_TOTAL_RELATIONS)
    assert not {"zoe-suggestion-9z9z9z", "moi-meme-0a0a0a", "script-1"} & set(lue.slugs)


def test_une_liste_partiellement_chargee_n_est_pas_complete():
    lue = lire_liste(page_envoyees(ENVOYEES_18[:10], total=18), URL_INVITATIONS_ENVOYEES,
                     MOTIF_TOTAL_ENVOYEES)
    assert len(lue.slugs) == 10 and lue.annonce == 18 and not lue.complete


def test_total_avec_separateur_de_milliers():
    html = page_relations(RELATIONS_20, total="1 234")
    assert lire_liste(html, URL_RELATIONS, MOTIF_TOTAL_RELATIONS).annonce == 1234


def test_un_autre_nombre_avant_le_total_ne_s_y_colle_pas():
    html = page_relations(RELATIONS_20).replace("<body>", "<body><span>5</span>")
    assert lire_liste(html, URL_RELATIONS, MOTIF_TOTAL_RELATIONS).annonce == 20


def test_une_page_qui_n_est_pas_une_liste_est_illisible():
    connexion = "<html><body><h1>S'identifier</h1><a href='/in/x/'>x</a></body></html>"
    assert lire_liste(connexion, URL_RELATIONS, MOTIF_TOTAL_RELATIONS) is None
    sans_conteneur = page_envoyees(ENVOYEES_18).replace('data-component-type="LazyColumn"', "")
    assert lire_liste(sans_conteneur, URL_INVITATIONS_ENVOYEES, MOTIF_TOTAL_ENVOYEES) is None
    sans_total = page_envoyees(ENVOYEES_18).replace("Personnes (18)", "Personnes")
    assert lire_liste(sans_total, URL_INVITATIONS_ENVOYEES, MOTIF_TOTAL_ENVOYEES) is None


def test_aucune_invitation_envoyee_se_lit_comme_une_liste_vide_complete():
    html = "<html><body><nav><a href='#'>Personnes (0)</a></nav><p>Aucune invitation</p></body></html>"
    lue = lire_liste(html, URL_INVITATIONS_ENVOYEES, MOTIF_TOTAL_ENVOYEES)
    assert lue.slugs == [] and lue.complete


def test_lien_vers_la_page_suivante_rendu_complet():
    html = page_envoyees(ENVOYEES_18, total=40, suivante="/mynetwork/invitation-manager/sent/?page=2")
    lue = lire_liste(html, URL_INVITATIONS_ENVOYEES, MOTIF_TOTAL_ENVOYEES)
    assert lue.suivante == URL_INVITATIONS_ENVOYEES + "?page=2"


@pytest.mark.parametrize("url,attendu", [
    ("https://www.linkedin.com/in/Ana-Test-1a2b3c/", "ana-test-1a2b3c"),
    ("https://www.linkedin.com/in/ana-test-1a2b3c?miniProfileUrn=x", "ana-test-1a2b3c"),
    ("https://www.linkedin.com/in/c%C3%A9line-test/", "céline-test"),
    ("https://www.linkedin.com/in/C%C3%89LINE-TEST", "céline-test"),
    ("/in/ana-test-1a2b3c/", "ana-test-1a2b3c"),
    ("https://www.linkedin.com/company/orbique/", None),
    ("", None),
])
def test_slug_profil(url, attendu):
    assert slug_profil(url) == attendu


def test_une_adresse_urn_est_reconnue():
    assert est_urn(slug_profil("https://www.linkedin.com/in/ACoAABxyz123/"))
    assert not est_urn("ana-test-1a2b3c")


# ── Les quatre règles ──

def _prof(slug):
    return {"url": f"https://www.linkedin.com/in/{slug}/", "nom": slug}


ENVOYEES = ListeLue(["en-attente-1"], annonce=1)
RELATIONS = ListeLue(["acceptee-1"], annonce=1)


def test_dans_les_relations_acceptee_et_verifiee():
    c = classer([_prof("Acceptee-1")], ENVOYEES, RELATIONS)
    assert [p["nom"] for p in c.acceptees] == ["Acceptee-1"]
    assert c.verifiees == ["https://www.linkedin.com/in/Acceptee-1/"]


def test_dans_les_envoyees_verifiee_toujours_en_attente():
    c = classer([_prof("en-attente-1")], ENVOYEES, RELATIONS)
    assert c.acceptees == [] and len(c.en_attente) == 1
    assert c.verifiees == ["https://www.linkedin.com/in/en-attente-1/"]


def test_dans_aucune_des_deux_listes_lues_en_entier_verifiee_non_acceptee():
    c = classer([_prof("disparue-1")], ENVOYEES, RELATIONS)
    assert c.acceptees == [] and len(c.absentes) == 1
    assert c.verifiees == ["https://www.linkedin.com/in/disparue-1/"]


@pytest.mark.parametrize("envoyees,relations", [
    (ListeLue(["en-attente-1"], annonce=5), RELATIONS),   # envoyées pas toutes lues
    (ENVOYEES, ListeLue(["acceptee-1"], annonce=500)),     # relations pas toutes lues
    (None, RELATIONS),                                    # envoyées illisibles
    (ENVOYEES, None),                                     # relations illisibles
])
def test_dans_aucune_des_deux_sans_preuve_non_verifiee(envoyees, relations):
    c = classer([_prof("disparue-1")], envoyees, relations)
    assert c.verifiees == [] and [p["nom"] for p in c.restants] == ["disparue-1"]


def test_une_adresse_urn_reste_a_verifier_sur_le_profil():
    c = classer([_prof("ACoAAB123")], ListeLue(["acoaab123"], annonce=1), RELATIONS)
    assert c.verifiees == [] and len(c.restants) == 1


# ── Moteur : listes d'abord, profil par profil en repli ──

class _FauxPlaywright:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *exc):
        return False


class _FauxNavigateur:
    async def close(self):
        pass


class _FauxLocator:
    def __init__(self, entete):
        self.entete = entete

    @property
    def first(self):
        return self

    async def inner_text(self, timeout=None):
        if isinstance(self.entete, Exception):
            raise self.entete
        return self.entete


class _FausseSouris:
    async def move(self, *a, **k):
        pass

    async def wheel(self, *a, **k):
        pass


class _FaussePage:
    """`listes` : URL → états successifs du HTML (un par défilement) ;
    `entetes` : URL de profil → en-tête rendu. Absente des deux, ou valeur
    None : chargement raté."""

    def __init__(self, listes, entetes):
        self.listes, self.entetes = listes, entetes
        self.url = ""
        self.defilements = 0
        self.mouse = _FausseSouris()
        self.viewport_size = {"width": 1280, "height": 800}

    async def content(self):
        etats = self.listes[self.url]
        return etats[min(self.defilements, len(etats) - 1)]

    async def wait_for_selector(self, *a, **k):
        return None

    def locator(self, selecteur):
        return _FauxLocator(self.entetes[self.url])


def _verifier(tmp_path, monkeypatch, profils, listes=None, entetes=None, **reglages):
    """Lance la vérification ; rend (scraper, URL acceptées, pages chargées)."""
    listes, entetes = listes or {}, entetes or {}
    scraper = LinkedInScraperV2(use_database=False, config_dir=str(tmp_path))
    for nom, valeur in reglages.items():
        setattr(scraper, nom, valeur)
    page = _FaussePage(listes, entetes)
    chargees = []

    async def ouvrir(p, cookie, status_callback=None):
        return _FauxNavigateur(), page

    async def aller(pg, url, *a, **k):
        chargees.append(url)
        if listes.get(url) is None and entetes.get(url) is None:
            return False
        page.url, page.defilements = url, 0
        return True

    async def defiler(pg, *a, **k):
        page.defilements += 1

    async def rien(*a, **k):
        return None

    monkeypatch.setattr("scraper_v2.async_playwright", lambda: _FauxPlaywright())
    monkeypatch.setattr(scraper, "_open_linkedin_page", ouvrir)
    monkeypatch.setattr(scraper.network_manager, "safe_page_goto", aller)
    monkeypatch.setattr(scraper.human, "human_delay", rien)
    monkeypatch.setattr(scraper.human, "pause_entre_pages", rien)
    monkeypatch.setattr(scraper.human, "human_scroll_down", defiler)
    acceptees = asyncio.run(scraper.verifier_acceptations_async("COOKIE-DE-TEST", profils))
    return scraper, [a["url"] for a in acceptees], chargees


A = personne(1, "ana")      # a accepté : dans les relations
B = personne(2, "ana")      # toujours en attente : dans les envoyées
C = personne(3, "ana")      # dans aucune des deux
EN_ATTENTE = [{"url": p["href"], "nom": p["nom"]} for p in (A, B, C)]
RELATIONS_AVEC_A = [personne(i, "bob") for i in range(5)] + [A]


def _listes(envoyees, relations):
    return {URL_INVITATIONS_ENVOYEES: envoyees, URL_RELATIONS: relations}


def test_deux_listes_lues_deux_pages_et_aucun_profil_ouvert(tmp_path, monkeypatch):
    scraper, acceptees, chargees = _verifier(tmp_path, monkeypatch, EN_ATTENTE, _listes(
        [page_envoyees([B] + ENVOYEES_18[:3])], [page_relations(RELATIONS_AVEC_A)]))
    assert acceptees == [A["href"]]
    assert sorted(scraper.verifiees) == sorted(p["href"] for p in (A, B, C))
    assert scraper.errors == []
    assert chargees == [URL_INVITATIONS_ENVOYEES, URL_RELATIONS]


def test_le_defilement_charge_la_suite_sans_nouvelle_page(tmp_path, monkeypatch):
    toutes = ENVOYEES_18 + [B]
    scraper, _, chargees = _verifier(tmp_path, monkeypatch, EN_ATTENTE, _listes(
        [page_envoyees(toutes[:8], total=19), page_envoyees(toutes[:15], total=19),
         page_envoyees(toutes, total=19)],
        [page_relations(RELATIONS_AVEC_A)]))
    # B n'apparaît qu'au deuxième défilement ; la liste lue en entier,
    # C (absente des deux) est vérifiée sans visite de son profil.
    assert sorted(scraper.verifiees) == sorted(p["href"] for p in (A, B, C))
    assert chargees == [URL_INVITATIONS_ENVOYEES, URL_RELATIONS]


def test_envoyees_pas_toutes_lues_repli_sur_le_profil_des_restants(tmp_path, monkeypatch):
    # LinkedIn annonce 30 personnes, n'en montre jamais que 4.
    scraper, acceptees, chargees = _verifier(
        tmp_path, monkeypatch, EN_ATTENTE,
        _listes([page_envoyees([B] + ENVOYEES_18[:3], total=30)],
                [page_relations(RELATIONS_AVEC_A)]),
        {C["href"]: "Ana Test 3 · 2e\nPM"})
    assert acceptees == [A["href"]]
    assert sorted(scraper.verifiees) == sorted(p["href"] for p in (A, B, C))
    assert chargees == [URL_INVITATIONS_ENVOYEES, URL_RELATIONS, C["href"]]
    assert scraper.errors == []


def test_relations_pas_toutes_lues_absente_verifiee_sur_son_profil(tmp_path, monkeypatch):
    # 500 relations annoncées, 6 montrées : C a pu accepter avant la partie
    # lue. Rien n'est conclu sur la liste, son profil est ouvert.
    scraper, acceptees, chargees = _verifier(
        tmp_path, monkeypatch, EN_ATTENTE,
        _listes([page_envoyees([B] + ENVOYEES_18[:3])],
                [page_relations(RELATIONS_AVEC_A, total=500)]),
        {C["href"]: "Ana Test 3 · 1er\nPM"})
    assert acceptees == [A["href"], C["href"]]
    assert sorted(scraper.verifiees) == sorted(p["href"] for p in (A, B, C))
    assert chargees == [URL_INVITATIONS_ENVOYEES, URL_RELATIONS, C["href"]]
    assert scraper.errors == []


def test_liste_illisible_repli_profil_par_profil_et_message(tmp_path, monkeypatch):
    # Les envoyées ne se chargent pas : A se lit dans les relations, B et C
    # sont vérifiées sur leur profil.
    scraper, acceptees, chargees = _verifier(
        tmp_path, monkeypatch, EN_ATTENTE,
        _listes(None, [page_relations(RELATIONS_AVEC_A)]),
        {B["href"]: "Ana Test 2 · 1er\nPM", C["href"]: "Ana Test 3 · 3e\nPM"})
    assert acceptees == [A["href"], B["href"]]
    assert sorted(scraper.verifiees) == sorted(p["href"] for p in (A, B, C))
    assert chargees == [URL_INVITATIONS_ENVOYEES, URL_RELATIONS, B["href"], C["href"]]
    assert scraper.errors == [LIBELLE_LISTE_ILLISIBLE]


def test_le_repli_est_plafonne_a_10_profils(tmp_path, monkeypatch):
    profils = [{"url": f"https://www.linkedin.com/in/eve-{i}/", "nom": f"Eve {i}"}
               for i in range(12)]
    entetes = {p["url"]: "Eve · 2e\nPM" for p in profils}
    scraper, _, chargees = _verifier(tmp_path, monkeypatch, profils, {}, entetes)
    visites = [u for u in chargees if "/in/" in u]
    assert visites == [p["url"] for p in profils[:10]]
    assert scraper.verifiees == visites
    assert scraper.errors == [LIBELLE_LISTE_ILLISIBLE]


def test_une_adresse_urn_est_verifiee_sur_son_profil(tmp_path, monkeypatch):
    urn = {"url": "https://www.linkedin.com/in/ACoAABxyz/", "nom": "Urn Test"}
    scraper, acceptees, chargees = _verifier(
        tmp_path, monkeypatch, [urn],
        _listes([page_envoyees(ENVOYEES_18)], [page_relations(RELATIONS_20)]),
        {urn["url"]: "Urn Test · 1er\nPM"})
    assert acceptees == [urn["url"]] and scraper.verifiees == [urn["url"]]
    assert chargees[-1] == urn["url"]


def test_trois_pages_de_listes_au_plus(tmp_path, monkeypatch):
    # Chaque page annonce plus de monde qu'elle n'en montre et propose une
    # page suivante : l'outil s'arrête à 3 pages de listes.
    suite_e = URL_INVITATIONS_ENVOYEES + "?page=2"
    suite_r = URL_RELATIONS + "?page=2"
    listes = {
        URL_INVITATIONS_ENVOYEES: [page_envoyees(ENVOYEES_18[:5], 99, suivante=suite_e)],
        suite_e: [page_envoyees(ENVOYEES_18[5:10], 99, suivante=suite_e + "0")],
        URL_RELATIONS: [page_relations(RELATIONS_20[:5], 99, suivante=suite_r)],
        suite_r: [page_relations(RELATIONS_20[5:10], 99, suivante=suite_r + "0")],
    }
    _, _, chargees = _verifier(tmp_path, monkeypatch, EN_ATTENTE, listes)
    assert [u for u in chargees if "/mynetwork/" in u] == [
        URL_INVITATIONS_ENVOYEES, URL_RELATIONS, suite_e]


def test_la_page_suivante_complete_la_liste(tmp_path, monkeypatch):
    suite = URL_INVITATIONS_ENVOYEES + "?page=2"
    listes = _listes([page_envoyees(ENVOYEES_18[:10], 11, suivante=suite)],
                     [page_relations(RELATIONS_AVEC_A)])
    listes[suite] = [page_envoyees([B], 11)]
    scraper, acceptees, chargees = _verifier(tmp_path, monkeypatch, EN_ATTENTE, listes)
    assert acceptees == [A["href"]]
    assert sorted(scraper.verifiees) == sorted(p["href"] for p in (A, B, C))
    assert chargees == [URL_INVITATIONS_ENVOYEES, URL_RELATIONS, suite]


def test_un_arret_garde_ce_qui_a_ete_lu(tmp_path, monkeypatch):
    # Fin de séance après la première page : B, lue dans les envoyées, est
    # vérifiée ; A et C restent sans statut, aucun profil n'est ouvert.
    scraper, acceptees, chargees = _verifier(
        tmp_path, monkeypatch, EN_ATTENTE,
        _listes([page_envoyees([B])], [page_relations(RELATIONS_AVEC_A)]),
        limite_pages_seance=1)
    assert acceptees == [] and scraper.verifiees == [B["href"]]
    assert chargees == [URL_INVITATIONS_ENVOYEES]
    assert scraper.errors[0].startswith("Séance terminée")


# ── Repli : seul un degré lu fait d'une page une page vérifiée ──

def _repli(tmp_path, monkeypatch, entetes):
    """Listes illisibles : chaque profil est vérifié sur sa page."""
    profils = [{"url": url, "nom": url[-2]} for url in entetes]
    scraper, acceptees, _ = _verifier(tmp_path, monkeypatch, profils, {}, entetes)
    return scraper, acceptees


LISIBLE = "https://exemple.test/in/a/"
SANS_DEGRE = "https://exemple.test/in/b/"
EN_ECHEC = "https://exemple.test/in/c/"
EXPIRE = "https://exemple.test/in/d/"


def test_un_degre_lu_vaut_acceptation_et_verification(tmp_path, monkeypatch):
    scraper, acceptees = _repli(tmp_path, monkeypatch, {LISIBLE: "Ana Test · 1er\nPM"})
    assert acceptees == [LISIBLE]
    assert scraper.verifiees == [LISIBLE]
    assert scraper.errors == [LIBELLE_LISTE_ILLISIBLE]


def test_un_degre_illisible_laisse_la_personne_en_attente_et_le_dit(tmp_path, monkeypatch):
    scraper, acceptees = _repli(tmp_path, monkeypatch, {
        LISIBLE: "Ana Test · 2e\nPM", SANS_DEGRE: "Bob Test\nPM",
        EXPIRE: TimeoutError("en-tête absent"),
    })
    assert acceptees == []
    assert scraper.verifiees == [LISIBLE]
    assert scraper.errors == [
        LIBELLE_LISTE_ILLISIBLE,
        "Degré de relation illisible pour 2 profils : ils restent en attente."]


def test_un_seul_degre_illisible_s_accorde_au_singulier(tmp_path, monkeypatch):
    scraper, _ = _repli(tmp_path, monkeypatch, {SANS_DEGRE: "Bob Test\nPM"})
    assert scraper.verifiees == []
    assert scraper.errors == [
        LIBELLE_LISTE_ILLISIBLE,
        "Degré de relation illisible pour 1 profil : ils restent en attente."]


def test_un_chargement_rate_n_est_pas_verifie(tmp_path, monkeypatch):
    scraper, acceptees = _repli(tmp_path, monkeypatch, {
        EN_ECHEC: None, LISIBLE: "Ana Test · 3e\nPM"})
    assert acceptees == []
    assert scraper.verifiees == [LISIBLE]
    assert scraper.errors == [LIBELLE_LISTE_ILLISIBLE]


# ── Départage : même seconde d'envoi ──

def _deux_invitations_meme_seconde(tmp_path):
    """A puis B, envoyées à la même seconde (B insérée après A)."""
    db = DatabaseManager(db_file=str(tmp_path / "egal.db"))
    for url in (URL_A, URL_B):
        db.ajouter_invitation(db.ajouter_profil(url[-1], "", "", "", url))
    con = sqlite3.connect(db.db_file)
    con.execute("UPDATE invitations SET date_envoi = '2026-10-20 09:00:00'")
    con.commit()
    con.close()
    return db


def test_jamais_verifiees_meme_seconde_la_derniere_inseree_d_abord(tmp_path):
    db = _deux_invitations_meme_seconde(tmp_path)
    assert [p["url"] for p in db.invitations_en_attente()] == [URL_B, URL_A]


def test_verifiees_la_plus_anciennement_verifiee_d_abord(tmp_path):
    db = _deux_invitations_meme_seconde(tmp_path)
    con = sqlite3.connect(db.db_file)
    for url, verif in ((URL_A, "2026-10-21 09:00:00"), (URL_B, "2026-10-22 09:00:00")):
        con.execute("UPDATE invitations SET date_verification = ? WHERE profile_id = "
                    "(SELECT id FROM profiles WHERE url = ?)", (verif, url))
    con.commit()
    con.close()
    assert [p["url"] for p in db.invitations_en_attente()] == [URL_A, URL_B]
