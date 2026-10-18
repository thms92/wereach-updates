# -*- coding: utf-8 -*-
"""Refonte des pages de suivi : Journal, Messages, Historique.

Toutes les données sont synthétiques (lignes de journal et profils inventés).
"""

import re
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

import scraper_v2_sync
from database import DatabaseManager
from tests.conftest import chemins_de_test, lancer_app, verifier_page_affichee
from ui import page_journal as pj
from ui import page_historique as ph
from ui import page_messages as pm

RACINE = Path(__file__).resolve().parent.parent

# --------------------------------------------------------------- Journal

JOURNAL = """\
2026-01-05 09:00:00 - linkedin_scraper - INFO - 🚀 Lancement du navigateur...
2026-01-05 09:00:01 - linkedin_scraper - DEBUG - détail interne
2026-01-05 09:00:02 - linkedin_scraper - INFO -   📄 Page profil dumpée → logs/message_profile_dump.html
2026-01-05 09:00:03 - linkedin_scraper - WARNING - ⚠️ Message Exemple: délai dépassé
2026-01-05 09:00:04 - linkedin_scraper - ERROR - ❌ Erreur envoi messages: boum
Traceback (most recent call last):
  File "/chemin/vers/projet/module.py", line 12, in fonction
    resultat = appel()
             ^^^^^^^
ValueError: valeur invalide dans '/chemin/vers/projet/fichier.txt'
2026-01-05 09:00:05 - linkedin_scraper - INFO - ✅ 3 profils enregistrés
""".splitlines(keepends=True)


def test_le_journal_est_decoupe_en_evenements():
    evs = pj.analyser_journal(JOURNAL)
    assert [e["niveau"] for e in evs] == ["INFO", "DEBUG", "INFO", "WARNING", "ERROR", "INFO"]
    assert evs[4]["suite"][0].startswith("Traceback")


def test_une_suite_orpheline_en_tete_d_extrait_est_ignoree():
    evs = pj.analyser_journal(["    resultat = appel()\n", "ValueError: x\n"] + JOURNAL[:1])
    assert len(evs) == 1 and evs[0]["suite"] == []


def test_la_vue_lisible_est_recente_d_abord_sans_trace_ni_chemin():
    lignes = pj.evenements_lisibles(JOURNAL)
    assert [l["Type"] for l in lignes] == ["Information", "Erreur", "Attention", "Information"]
    assert lignes[0] == {"Heure": "05/01 09:00:05", "Type": "Information",
                         "Événement": "3 profils enregistrés"}
    erreur = lignes[1]["Événement"]
    assert erreur.startswith("Erreur envoi messages: boum")
    assert "Erreur technique : ValueError: valeur invalide" in erreur
    texte = " ".join(l["Événement"] for l in lignes)
    for interdit in ("Traceback", "File ", "/chemin/", ".py", "^^^", "dump", "DEBUG", "détail interne"):
        assert interdit not in texte, interdit
    # Pas d'émoji de tête.
    assert all(l["Événement"][0].isalnum() for l in lignes)


def test_le_filtre_ne_garde_que_les_alertes():
    lignes = pj.evenements_lisibles(JOURNAL, pj.FILTRE_ALERTES)
    assert [l["Type"] for l in lignes] == ["Erreur", "Attention"]


def test_les_chemins_et_liens_sont_masques():
    assert pj.nettoyer_message("Enregistré dans /tmp/a/b.csv") == "Enregistré dans (fichier)"
    assert "exemple" not in pj.nettoyer_message("Ouvre https://exemple.test/in/x")
    assert pj.derniere_ligne_exception(["Traceback (most recent call last):",
                                        '  File "x.py", line 1', "KeyError: 'k'"]) == "KeyError: 'k'"


def test_la_page_journal_se_lit_sans_jargon(tmp_path, monkeypatch):
    from config import ScraperConfig
    f = tmp_path / "journal.log"
    f.write_text("".join(JOURNAL), encoding="utf-8")
    monkeypatch.setattr(ScraperConfig, "LOG_FILE", str(f))
    at = lancer_app("📜 Logs")
    verifier_page_affichee(at, "📜 Logs")
    assert [t.value for t in at.title] == ["Journal d'exécution"]
    df = at.dataframe[0].value
    assert list(df.columns) == ["Heure", "Type", "Événement"]
    assert not df["Événement"].str.contains("Traceback").any()
    assert [e.label for e in at.main.expander] == ["Détail technique (pour le support)"]
    assert "Traceback" in at.code[0].value
    at.segmented_control(key="journal_filtre").set_value(pj.FILTRE_ALERTES).run()
    assert set(at.dataframe[0].value["Type"]) == {"Erreur", "Attention"}


# --------------------------------------------------------------- Messages

URLS = [f"https://www.linkedin.com/in/profil-test-suivi-{i}/" for i in range(3)]


class ScraperInterdit:
    def __init__(self, **k):
        raise AssertionError("aucune session LinkedIn ne doit s'ouvrir")


@pytest.fixture
def acceptees(monkeypatch):
    monkeypatch.setattr(scraper_v2_sync, "LinkedInScraperV2Sync", ScraperInterdit)
    db_file = str(chemins_de_test().db_file)
    db = DatabaseManager(db_file=db_file)
    for i, url in enumerate(URLS):
        db.ajouter_invitation(db.ajouter_profil(f"Personne Test {i}", "PM", "Orbique", "", url), "")
        db.marquer_acceptee(url)
    yield db
    con = sqlite3.connect(db_file)
    for url in URLS:
        con.execute("DELETE FROM invitations WHERE profile_id IN (SELECT id FROM profiles WHERE url = ?)", (url,))
        con.execute("DELETE FROM profiles WHERE url = ?", (url,))
    con.commit()
    con.close()


def _messages():
    at = lancer_app("✉️ Messages")
    verifier_page_affichee(at, "✉️ Messages")
    at.session_state["global_cookie"] = "COOKIE-DE-TEST"
    at.run()
    return at


def test_raison_d_envoi_impossible():
    assert pm.raison_envoi_impossible(0, "") .startswith("Cochez au moins une personne et écrivez")
    assert pm.raison_envoi_impossible(2, "  ") == "Écrivez votre message pour pouvoir envoyer."
    assert pm.raison_envoi_impossible(1, "Bonjour") is None
    assert pm.libelle_envoi(1) == "Envoyer à 1 personne"
    assert pm.libelle_envoi(3) == "Envoyer à 3 personnes"


def test_tout_selectionner_puis_tout_deselectionner(acceptees):
    at = _messages()
    assert not at.exception
    at.button(key="msg_tout").click().run()
    assert all(at.checkbox(key=pm.cle_case(u)).value for u in URLS)
    at.button(key="msg_rien").click().run()
    assert not any(at.checkbox(key=pm.cle_case(u)).value for u in URLS)
    assert not at.exception


def test_l_envoi_inactif_est_secondaire_et_explique(acceptees):
    at = _messages()
    bouton = at.button(key="msg_envoyer")
    assert bouton.disabled and bouton.proto.type == "secondary"
    assert any("Cochez au moins une personne" in c.value for c in at.caption)
    at.checkbox(key=pm.cle_case(URLS[0])).check()
    at.text_area(key="msg_modele").input("Bonjour, ravi de vous compter parmi mes relations.")
    at.run()
    bouton = at.button(key="msg_envoyer")
    assert not bouton.disabled and bouton.proto.type == "primary"
    assert bouton.label == "Envoyer à 1 personne"
    # Aperçu du texte tel quel : le moteur ne remplace aucune variable.
    assert any("ravi de vous compter" in m.value for m in at.markdown)


def test_messages_sans_emoji_ni_jargon_et_vouvoie(acceptees):
    src = (RACINE / "ui/page_messages.py").read_text(encoding="utf-8")
    for interdit in ("li_at", "🔄", "✉️", "✅", "❌", "⚠️", " ton ", " tu "):
        assert interdit not in src, interdit
    assert not re.search(r"\w\((?:e|s)\)[ \"'.!]", src)


def test_sans_invitation_en_attente_le_bouton_de_verification_parait_inactif(monkeypatch):
    monkeypatch.setattr(scraper_v2_sync, "LinkedInScraperV2Sync", ScraperInterdit)
    at = _messages()
    if at.session_state.db.invitations_en_attente():
        pytest.skip("base de test non vide")
    b = [b for b in at.button if b.label == pm.LIBELLE_VERIFIER][0]
    assert b.disabled and b.proto.type == "secondary"
    assert any("Aucune invitation en attente." in m.value for m in at.markdown)


# --------------------------------------------------------------- Historique

def _profils():
    return pd.DataFrame([
        {"nom": "Alice Exemple", "poste": "Product Manager", "entreprise": "Orbique",
         "ecole": "Dauphine / ESCP", "localisation": "Paris", "invitation_envoyee": "Oui",
         "date_scraping": "2026-01-30 10:00:00", "url": "u1"},
        {"nom": "Bruno Fictif", "poste": "Data Analyst", "entreprise": "Néant SA",
         "ecole": "HEC", "localisation": "Lyon", "invitation_envoyee": "Non",
         "date_scraping": "2026-01-10 10:00:00", "url": "u2"},
        {"nom": "Chloé Modèle", "poste": None, "entreprise": "Orbique",
         "ecole": None, "localisation": "Lille", "invitation_envoyee": "Non",
         "date_scraping": "2025-06-01 10:00:00", "url": "u3"},
    ])


MAINTENANT = datetime(2026, 2, 1, 12, 0, 0)


@pytest.mark.parametrize("recherche, attendus", [
    ("", ["u1", "u2", "u3"]),
    ("orbique", ["u1", "u3"]),
    ("PRODUCT manager", ["u1"]),
    ("lyon analyst", ["u2"]),
    ("introuvable", []),
])
def test_la_recherche_porte_sur_nom_poste_entreprise(recherche, attendus):
    assert list(ph.filtrer_profils(_profils(), recherche)["url"]) == attendus


def test_filtres_ecole_et_periode():
    df = _profils()
    assert list(ph.filtrer_profils(df, ecoles=["ESCP"])["url"]) == ["u1"]
    assert list(ph.filtrer_profils(df, ecoles=["ESCP", "HEC"])["url"]) == ["u1", "u2"]
    assert list(ph.filtrer_profils(df, periode="7 derniers jours", maintenant=MAINTENANT)["url"]) == ["u1"]
    assert list(ph.filtrer_profils(df, periode="30 derniers jours", maintenant=MAINTENANT)["url"]) == ["u1", "u2"]
    assert list(ph.filtrer_profils(df, seulement_invites=True)["url"]) == ["u1"]
    assert ph.filtrer_profils(df.iloc[0:0], "x").empty


def test_la_page_historique_a_recherche_filtres_et_export_sans_emoji():
    at = lancer_app("💾 Historique")
    verifier_page_affichee(at, "💾 Historique")
    assert [t.value for t in at.title] == ["Historique des profils"]
    src = (RACINE / "ui/page_historique.py").read_text(encoding="utf-8")
    assert "Rechercher un nom, un poste, une entreprise…" in src
    assert 'placeholder="Choisir des écoles…"' in src
    assert "📥" not in src and 'display_text="Ouvrir"' in src
    assert list(ph.PERIODES) == ["Tout", "7 derniers jours", "30 derniers jours"]
