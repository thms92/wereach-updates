# -*- coding: utf-8 -*-
"""Refonte de la page Recherche : le budget d'invitations est visible et
expliqué là où l'on invite, les boutons disent l'action, la langue est
celle de l'interface (vouvoiement, pas de jargon technique).

Le budget est dicté par le test (remplacement de `budget_du_jour`) : jamais
le compteur réel du poste.
"""

import re

import pandas as pd
import pytest

import scraper_v2_sync
import ui.invitations
from tests.conftest import lancer_app, verifier_page_affichee
from ui.invitations import resume_resultats
from ui.page_recherche import ONGLETS
from utils.budget import Budget

PAGE = "🔍 Recherche"
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⭐✅❌]")


@pytest.fixture
def budget_dicte(monkeypatch):
    etat = {"budget": Budget(utilisees=5, plafond=20)}
    monkeypatch.setattr(ui.invitations, "budget_du_jour", lambda _dir: etat["budget"])
    return etat


@pytest.fixture
def scraper_espion(monkeypatch):
    etat = {"appels": [], "df": pd.DataFrame()}

    class FauxScraper:
        def __init__(self, **kwargs):
            self.errors = []

        def run_scraper(self, **kwargs):
            etat["appels"].append(kwargs)
            return etat["df"]

    monkeypatch.setattr(scraper_v2_sync, "LinkedInScraperV2Sync", FauxScraper)
    return etat


def _page():
    at = lancer_app(PAGE)
    verifier_page_affichee(at, PAGE)
    at.session_state["global_cookie"] = "COOKIE-DE-TEST"
    at.run()
    return at


def _textes_visibles(at):
    # La zone principale seulement : la barre latérale n'est pas à cette page.
    racine = at.main
    textes = [t.label for t in racine.tabs] + [b.label for b in racine.button]
    textes += [e.label for e in racine.expander] + [w.label for w in racine.toggle]
    textes += [w.label for w in racine.checkbox] + [w.label for w in racine.text_input]
    textes += [w.label for w in racine.multiselect] + [w.label for w in racine.text_area]
    # Hors feuilles de style injectées par le thème (pas du texte affiché).
    textes += [m.value for m in racine.markdown if not m.value.lstrip().startswith("<style")]
    textes += [c.value for c in racine.caption]
    textes += [x.value for x in list(racine.warning) + list(racine.error) + list(racine.success)]
    textes += [w.help or "" for w in list(racine.text_input) + list(racine.toggle) + list(racine.checkbox)]
    textes += [w.placeholder or "" for w in racine.text_input]
    return textes


# --- Libellés -------------------------------------------------------------

def test_onglets_sans_emoji_et_bouton_qui_dit_l_action():
    assert ONGLETS == ["Par critères", "Profils similaires"]


def test_aucun_jargon_ni_emoji_dans_la_page(budget_dicte):
    at = _page()
    textes = _textes_visibles(at)
    tout = "\n".join(textes)
    for interdit in ("scraping", "scrapé", "Logs", "(s)", "Colle ", "sépare-les"):
        assert interdit not in tout, interdit
    # Le nom du cookie n'apparaît qu'une fois, dans l'aide, pour le retrouver.
    assert tout.count("li_at") == 1
    sans_emoji = [t for t in textes if EMOJI.search(t)]
    assert not sans_emoji, sans_emoji


def test_bandeau_de_contexte_avec_la_session_sans_doubler_la_jauge(budget_dicte):
    at = _page()
    assert at.title[0].value == "Nouvelle recherche"
    bandeau = [m.value for m in at.markdown if m.value.startswith('<div class="wf-bandeau"')]
    assert bandeau and "Session LinkedIn active" in bandeau[0]
    # Le budget est déjà sous le menu (jauge de la barre latérale).
    assert "restante" not in bandeau[0]


# --- Budget là où l'on invite --------------------------------------------

# --- Écoles et bilan ------------------------------------------------------

def test_les_ecoles_sont_un_menu_et_partent_dans_la_recherche(budget_dicte, scraper_espion):
    at = _page()
    menu = at.multiselect(key="ecoles_pills_candidat")
    assert menu.placeholder.startswith("Choisir")
    menu.set_value(["Dauphine"])
    at.run()
    at.button(key="btn_rechercher").click()
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    from config import ECOLES
    assert scraper_espion["appels"][0]["ecoles_ids"] == [ECOLES["Dauphine"]]


def test_le_bilan_omet_les_invitations_inconnues():
    df = pd.DataFrame([{"Nom": "A"}])
    assert resume_resultats(df, inviter=True) == "1 profil trouvé"
    df = pd.DataFrame([{"Nom": "A", "Invitation": "Oui"}, {"Nom": "B", "Invitation": "Oui"}])
    assert resume_resultats(df, inviter=False) == "2 profils trouvés"


# --- Profils similaires : même jauge, même logique de libellé -------------

def test_le_bloc_recuperer_montre_la_jauge_et_refuse_d_avance(budget_dicte, monkeypatch):
    voisins = [{"nom": f"P{i}", "url": f"https://www.linkedin.com/in/p-{i}/",
                "degre": "2e", "intitule": "PM", "invitable": True} for i in range(3)]

    class FauxScraper:
        def __init__(self, **kwargs):
            self.errors = []
            self.use_database = False

        def recolter_browsemap(self, **kwargs):
            return voisins, None

    monkeypatch.setattr(scraper_v2_sync, "LinkedInScraperV2Sync", FauxScraper)
    budget_dicte["budget"] = Budget(utilisees=18, plafond=20)
    at = _page()
    at.text_input(key="sim_url").set_value("https://www.linkedin.com/in/reference/")
    at.button(key="sim_btn_trouver").click()
    at.run()
    assert at.button(key="sim_btn_recuperer").label == "Enregistrer 3 profils choisis"

    at.toggle(key="sim_inviter").set_value(True)
    at.run()
    # 3 profils pour 2 restantes : refusé d'avance, le bouton est grisé.
    assert at.button(key="sim_btn_recuperer").label == "Inviter 3 profils choisis"
    assert [m for m in at.markdown if m.value.startswith('<div class="wf-jauge')]
    assert [e.value for e in at.error] == [
        "Il vous reste 2 invitations aujourd'hui : sélectionnez-en 2 au plus."]
    assert at.button(key="sim_btn_recuperer").disabled
