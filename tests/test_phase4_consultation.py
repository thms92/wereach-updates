# -*- coding: utf-8 -*-
"""Phase 4, consultation : Veille, Historique, Journal et rapport de problème.

Aucune session LinkedIn n'est ouverte : la base est celle de l'utilisateur de test.
"""

import io
from datetime import datetime, timezone

import pandas as pd
import pytest

from tests.conftest import chemins_de_test, lancer_app, verifier_page_affichee


def test_date_locale_historique():
    from ui.page_historique import date_locale, moment_local
    attendu = datetime(2026, 1, 15, 9, 30, tzinfo=timezone.utc).astimezone().strftime("%d/%m/%Y %H:%M")
    assert date_locale("2026-01-15 09:30:00") == attendu
    assert date_locale(None) == "—"
    assert date_locale("pas une date") == "pas une date"
    assert moment_local("2026-01-15 09:30:00").tzinfo is None


def test_le_filtre_de_periode_compte_en_heure_locale():
    from ui.page_historique import filtrer_profils, moment_local
    brut = "2026-10-11 10:00:00"  # UTC
    limite_locale = moment_local(brut)
    df = pd.DataFrame([{"nom": "A", "date_scraping": brut}])
    maintenant = limite_locale.replace() + pd.Timedelta(days=7)
    assert len(filtrer_profils(df, periode="7 derniers jours", maintenant=maintenant)) == 1
    trop_tard = maintenant + pd.Timedelta(minutes=1)
    assert len(filtrer_profils(df, periode="7 derniers jours", maintenant=trop_tard)) == 0


def test_l_export_historique_a_les_colonnes_de_l_ecran():
    from ui.page_historique import tableau_export
    df = pd.DataFrame([{"id": 1, "nom": "=Personne Fictive", "poste": "Poste", "entreprise": "Ent",
                        "ecole": "École Exemple", "localisation": "Paris", "url": "https://www.linkedin.com/in/x/",
                        "photo_url": "p", "resume": "r", "derniere_mise_a_jour": "2026-10-11 10:00:00",
                        "invitation_envoyee": "Oui", "date_scraping": "2026-10-11 10:00:00"}])
    export = tableau_export(df)
    assert list(export.columns) == ["Nom", "Poste", "Entreprise", "École", "Ajouté le", "Profil",
                                    "Invitation", "Localisation"]
    assert export.loc[0, "Ajouté le"] == datetime(2026, 10, 11, 10, 0, tzinfo=timezone.utc) \
        .astimezone().strftime("%d/%m/%Y %H:%M")
    assert export.loc[0, "Nom"] == "'=Personne Fictive"


def test_les_telechargements_de_l_historique(monkeypatch):
    from database import DatabaseManager
    db = DatabaseManager(db_file=str(chemins_de_test().db_file))
    db.ajouter_profil("Camille Exemple", "Poste fictif", "Société Fictive", "École Exemple",
                      "https://www.linkedin.com/in/phase4-historique/", "Paris (démo)")
    at = lancer_app("💾 Historique")
    verifier_page_affichee(at, "💾 Historique")
    assert [t.value for t in at.title] == ["Historique des profils"]
    boutons = at.get("download_button")
    assert len(boutons) == 2
    for b in boutons:
        assert b.proto.ignore_rerun
    csv = [b for b in boutons if "CSV" in b.proto.label][0]
    assert csv.proto.label


# ── Journal ──────────────────────────────────────────────────────────────

def _ligne(message, niveau="INFO"):
    return f"2026-10-18 09:00:00 - linkedin_scraper - {niveau} - {message}\n"


@pytest.mark.parametrize("message", [
    "🏢 URN entreprise 'Société Fictive' (cache): 12345",
    "🏢 URN entreprise 'Société Fictive' (seed): 12345",
    "🚀 Lancement du scraper V2 (mode synchrone)",
    "Écriture du dump de la page",
    "Base de données initialisée avec succès",
])
def test_le_journal_cache_les_lignes_internes(message):
    from ui.page_journal import evenements_lisibles
    assert evenements_lisibles([_ligne(message)]) == []


@pytest.mark.parametrize("message, attendu", [
    ("🔗 Lancement scraping URLs (12 profils)", "Récupération de 12 profils"),
    ("🔗 Lancement scraping URLs (1 profils)", "Récupération de 1 profil"),
    ("Cookie sauvegardé avec succès", "Session LinkedIn enregistrée"),
    ("Session LinkedIn enregistrée", "Session LinkedIn enregistrée"),
    ("✅ 3 profils enregistrés", "3 profils enregistrés"),
])
def test_le_journal_reformule(message, attendu):
    from ui.page_journal import evenements_lisibles
    [ev] = evenements_lisibles([_ligne(message)])
    assert ev["Événement"] == attendu


def test_le_journal_brut_reste_intact(tmp_path, monkeypatch):
    from config import ScraperConfig
    f = tmp_path / "journal.log"
    lignes = [_ligne("🚀 Lancement du scraper V2 (mode synchrone)"), _ligne("🔗 Lancement scraping URLs (2 profils)")]
    f.write_text("".join(lignes), encoding="utf-8")
    monkeypatch.setattr(ScraperConfig, "LOG_FILE", str(f))
    at = lancer_app("📜 Logs")
    verifier_page_affichee(at, "📜 Logs")
    assert list(at.dataframe[0].value["Événement"]) == ["Récupération de 2 profils"]
    assert "mode synchrone" in at.code[0].value and "Lancement scraping URLs" in at.code[0].value


def test_le_filtre_du_journal_ne_reste_jamais_vide(tmp_path, monkeypatch):
    from config import ScraperConfig
    import ui.page_journal as pj
    f = tmp_path / "journal.log"
    f.write_text(_ligne("Recherche terminée") + _ligne("Attention fictive", "WARNING"), encoding="utf-8")
    monkeypatch.setattr(ScraperConfig, "LOG_FILE", str(f))
    at = lancer_app("📜 Logs")
    assert at.segmented_control(key="journal_filtre").value == pj.FILTRE_TOUT
    at.segmented_control(key="journal_filtre").set_value(None).run()
    assert at.segmented_control(key="journal_filtre").value == pj.FILTRE_TOUT
    assert len(at.dataframe[0].value) == 2


def test_le_journal_et_le_rapport_lisent_le_meme_fichier(monkeypatch):
    from config import ScraperConfig
    from utils import diagnostic
    import ui.page_journal as pj
    monkeypatch.setattr(ScraperConfig, "LOG_FILE", "scraper.log")
    attendu = diagnostic.RACINE / "scraper.log"
    assert diagnostic.chemin_journal() == attendu
    assert pj.chemin_journal() == attendu
    assert diagnostic.FICHIER_JOURNAL == attendu
    monkeypatch.setattr(ScraperConfig, "LOG_FILE", "/tmp/ailleurs.log")
    assert pj.chemin_journal() == diagnostic.chemin_journal()
    assert str(pj.chemin_journal()) == "/tmp/ailleurs.log"


def test_le_rapport_retire_les_emojis_du_journal(tmp_path, monkeypatch):
    from utils import diagnostic
    journal = tmp_path / "scraper.log"
    journal.write_text(_ligne("🚀 Lancement de la recherche") + _ligne("⚠️ Attention fictive", "WARNING")
                       + "✅ ligne sans en-tête\n", encoding="utf-8")
    monkeypatch.setattr(diagnostic, "FICHIER_JOURNAL", journal)
    texte = diagnostic._fin_du_journal()
    assert "INFO - Lancement de la recherche" in texte
    assert "WARNING - Attention fictive" in texte
    assert "\nligne sans en-tête" in texte
    for emoji in ("🚀", "⚠", "✅"):
        assert emoji not in texte


def test_le_cookie_enregistre_se_dit_session(tmp_path, caplog):
    import logging
    from cookie_utils import CookieManager
    with caplog.at_level(logging.INFO, logger="linkedin_scraper"):
        CookieManager(config_dir=str(tmp_path)).save_cookie("AQEDEMO" + "x" * 150)
    messages = [r.getMessage() for r in caplog.records]
    assert "Session LinkedIn enregistrée" in messages
    assert not any("Cookie sauvegardé" in m for m in messages)


def test_le_logger_ecrit_la_ou_le_journal_lit():
    import logger as module_logger
    from utils.diagnostic import chemin_journal
    assert module_logger._fichier_journal() == str(chemin_journal())
