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


# ── Moteur : seul un degré lu fait d'une page une page vérifiée ──

import asyncio

from scraper_v2 import LinkedInScraperV2


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


class _FaussePage:
    """En-tête rendu selon l'URL visitée ; `None` = chargement raté."""

    def __init__(self, entetes):
        self.entetes = entetes
        self.url = ""

    def locator(self, selecteur):
        return _FauxLocator(self.entetes[self.url])


def _verifier(tmp_path, monkeypatch, entetes):
    scraper = LinkedInScraperV2(use_database=False, config_dir=str(tmp_path))
    page = _FaussePage(entetes)

    async def ouvrir(p, cookie, status_callback=None):
        return _FauxNavigateur(), page

    async def aller(pg, url, *a, **k):
        if entetes.get(url) is None:
            return False
        page.url = url
        return True

    async def rien(*a, **k):
        return None

    monkeypatch.setattr("scraper_v2.async_playwright", lambda: _FauxPlaywright())
    monkeypatch.setattr(scraper, "_open_linkedin_page", ouvrir)
    monkeypatch.setattr(scraper.network_manager, "safe_page_goto", aller)
    monkeypatch.setattr(scraper.human, "human_delay", rien)
    monkeypatch.setattr(scraper.human, "pause_entre_pages", rien)
    profils = [{"url": url, "nom": url[-2]} for url in entetes]
    acceptees = asyncio.run(scraper.verifier_acceptations_async("COOKIE-DE-TEST", profils))
    return scraper, [a["url"] for a in acceptees]


LISIBLE = "https://exemple.test/in/a/"
SANS_DEGRE = "https://exemple.test/in/b/"
EN_ECHEC = "https://exemple.test/in/c/"
EXPIRE = "https://exemple.test/in/d/"


def test_un_degre_lu_vaut_acceptation_et_verification(tmp_path, monkeypatch):
    scraper, acceptees = _verifier(tmp_path, monkeypatch, {LISIBLE: "Ana Test · 1er\nPM"})
    assert acceptees == [LISIBLE]
    assert scraper.verifiees == [LISIBLE]
    assert scraper.errors == []


def test_un_degre_illisible_laisse_la_personne_en_attente_et_le_dit(tmp_path, monkeypatch):
    scraper, acceptees = _verifier(tmp_path, monkeypatch, {
        LISIBLE: "Ana Test · 2e\nPM", SANS_DEGRE: "Bob Test\nPM",
        EXPIRE: TimeoutError("en-tête absent"),
    })
    assert acceptees == []
    assert scraper.verifiees == [LISIBLE]
    assert scraper.errors == [
        "Degré de relation illisible pour 2 profils : ils restent en attente."]


def test_un_seul_degre_illisible_s_accorde_au_singulier(tmp_path, monkeypatch):
    scraper, _ = _verifier(tmp_path, monkeypatch, {SANS_DEGRE: "Bob Test\nPM"})
    assert scraper.verifiees == []
    assert scraper.errors == [
        "Degré de relation illisible pour 1 profil : ils restent en attente."]


def test_un_chargement_rate_n_est_pas_verifie(tmp_path, monkeypatch):
    scraper, acceptees = _verifier(tmp_path, monkeypatch, {
        EN_ECHEC: None, LISIBLE: "Ana Test · 3e\nPM"})
    assert acceptees == []
    assert scraper.verifiees == [LISIBLE]
    assert scraper.errors == []


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
