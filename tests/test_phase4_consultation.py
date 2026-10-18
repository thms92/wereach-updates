# -*- coding: utf-8 -*-
"""Phase 4, consultation : Veille, Historique, Journal et rapport de problème.

Aucune session LinkedIn n'est ouverte : la base est celle de l'utilisateur de test.
"""

import io
from datetime import datetime, timezone

import pandas as pd
import pytest

import veille
from tests.conftest import chemins_de_test, lancer_app, verifier_page_affichee
from veille_store import VeilleStore

PAGE_VEILLE = "🏢 Veille"
ANCIEN_COOKIE = "Cookie LinkedIn invalide ou expiré — renseignez un nouveau cookie li_at dans la page Recherche."


@pytest.fixture
def store():
    s = VeilleStore(str(chemins_de_test().db_file))
    for e in s.entreprises():
        s.retirer_entreprise(e["id"])
    return s


def _veille():
    at = lancer_app(PAGE_VEILLE)
    verifier_page_affichee(at, PAGE_VEILLE)
    return at


def _contact(i, famille, nom):
    return ({"nom": nom, "poste": "Poste fictif", "url": f"https://www.linkedin.com/in/phase4-{i}-{famille}/"},
            famille)


# ── Veille ───────────────────────────────────────────────────────────────

def test_le_fichier_de_visite_est_exporte():
    from ui.page_veille import FICHIER_VISITE_VEILLE
    assert FICHIER_VISITE_VEILLE == "derniere_visite_veille.txt"


def test_le_bloc_d_invitation_garde_son_libelle(monkeypatch):
    """La Veille ne force plus « Récupérer les infos » : le bloc dit lui-même s'il invite."""
    import inspect
    import ui.page_veille as page
    assert "libelle_bouton" not in inspect.getsource(page)


def test_la_cause_cookie_est_celle_du_moteur():
    from ui.page_veille import _CAUSES
    assert _CAUSES["cookie"] == veille.MESSAGES_ARRET["cookie"]


def test_un_ancien_passage_cookie_est_relu_sans_li_at_ni_doublon():
    from ui.page_veille import _texte_passage
    _, texte = _texte_passage("2026-10-15T08:12:00", "cookie", [], 0, [ANCIEN_COOKIE])
    assert "li_at" not in texte
    assert texte.count(veille.MESSAGES_ARRET["cookie"]) == 1
    assert "À vérifier" not in texte


def test_un_ancien_refus_cookie_est_dit_sans_li_at():
    from ui.page_veille import _erreurs_actuelles
    assert _erreurs_actuelles([ANCIEN_COOKIE, "autre"]) == [veille.MESSAGES_ARRET["cookie"], "autre"]


def test_l_echappement_markdown():
    from ui.page_veille import _md
    assert _md("A*B_C [x](y) #1 +-.!$~|> `z` \\") == \
        "A\\*B\\_C \\[x\\]\\(y\\) \\#1 \\+\\-\\.\\!\\$\\~\\|\\> \\`z\\` \\\\"
    assert _md(None) == ""
    assert _md("Société Alpha") == "Société Alpha"


def test_un_changement_de_fiche_ne_casse_pas_le_markdown(store):
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    store.enregistrer_fiche(i, {"taille": "11-50"}, "linkedin", "2026-10-14T08:00:00")
    store.enregistrer_fiche(i, {"taille": "*51-200*"}, "linkedin", "2099-01-01T08:00:00")
    at = _veille()
    [ligne] = [m.value for m in at.markdown if "Orbique" in m.value and "→" in m.value]
    assert "\\*51\\-200\\*" in ligne


def test_contacts_cibles_comme_la_fiche(store):
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    for k, famille in enumerate(["Product", "Data", "Autre"]):
        c, f = _contact(k, famille, f"Personne Fictive {k}")
        store.relier_contact(i, c, f, "2026-10-14T08:00:00", set())
    at = _veille()
    [tableau] = [d.value for d in at.dataframe if "État" in d.value.columns]
    assert "Contacts" not in tableau.columns
    assert list(tableau["Contacts ciblés"]) == [2]
    assert any("2 contacts ciblés" in m.value for m in at.markdown)


def _tableau(at):
    import ui.page_veille as page
    return [d for d in at.dataframe if "État" in d.value.columns][0], page


def test_un_clic_ouvre_la_fiche_puis_la_selection_est_effacee(store):
    store.ajouter_entreprise("Orbique", "2026-10-14")
    store.ajouter_entreprise("Zéphyr", "2026-10-14")
    at = _veille()
    tableau, page = _tableau(at)
    cle = tableau.key
    assert cle == page._CLE_TABLEAU
    # AppTest ne déclenche pas on_select : on joue le rappel comme le ferait Streamlit.
    etat = {cle: {"selection": {"rows": [1], "columns": []}}, "_veille_noms_tableau": ["Orbique", "Zéphyr"]}

    class FauxSt:
        session_state = etat

    vrai = page.st
    page.st = FauxSt
    try:
        page._ouvrir_fiche_selectionnee()
        assert etat["veille_fiche"] == "Zéphyr"
        # Clé nouvelle : le tableau revient sans ligne choisie.
        nouvelle = page._cle_tableau()
        assert nouvelle != cle and nouvelle not in etat
        etat[nouvelle] = {"selection": {"rows": [1], "columns": []}}
        etat["veille_fiche"] = "Orbique"
        page._ouvrir_fiche_selectionnee()
        # Même ligne cliquée de nouveau : la fiche s'ouvre encore.
        assert etat["veille_fiche"] == "Zéphyr"
    finally:
        page.st = vrai


def test_la_nouvelle_cle_est_appliquee_au_tableau(store):
    import ui.page_veille as page
    store.ajouter_entreprise("Orbique", "2026-10-14")
    at = _veille()
    at.session_state[page._CLE_GENERATION] = 3
    at.run()
    tableau, _ = _tableau(at)
    assert tableau.key == f"{page._CLE_TABLEAU}_3"


def test_retirer_dit_que_c_est_fait_une_fois(store):
    import ui.page_veille as page
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    store.ajouter_entreprise("Zéphyr", "2026-10-14")
    at = _veille()
    at.selectbox(key="veille_retirer").set_value("Orbique")
    at.run()
    at.checkbox(key=f"veille_retirer_confirme_{i}").check()
    at.run()
    generation = at.session_state[page._CLE_GENERATION] if page._CLE_GENERATION in at.session_state else 0
    at.button(key="veille_btn_retirer").click()
    at.run()
    assert not at.exception
    assert [s.value for s in at.success if "retirée" in s.value] == ["Orbique retirée de la veille."]
    assert at.session_state[page._CLE_GENERATION] == generation + 1
    at.run()
    assert not [s.value for s in at.success if "retirée" in s.value]


def test_pas_de_saut_de_titre_dans_la_veille(store):
    at = _veille()
    assert not at.subheader
    assert [h.value for h in at.header] == ["Nouveau depuis votre dernière visite", "Lancer la veille"]


# ── Historique ───────────────────────────────────────────────────────────

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
