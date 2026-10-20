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
from ui.page_recherche import ONGLETS, libelle_bouton_recherche
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
    assert ONGLETS == ["Candidats", "Clients et entreprises", "Profils similaires"]
    assert libelle_bouton_recherche(False) == "Rechercher"
    assert libelle_bouton_recherche(True) == "Rechercher et inviter"
    assert libelle_bouton_recherche(True, 3) == "Rechercher et inviter (jusqu'à 3)"


def test_le_bouton_devient_rechercher_et_inviter_quand_on_invite(budget_dicte):
    at = _page()
    for prefixe in ("candidat", "client"):
        cle_btn = "btn_rechercher_candidats" if prefixe == "candidat" else "btn_rechercher_clients"
        assert at.button(key=cle_btn).label == "Rechercher"
        at.toggle(key=f"inviter_{prefixe}").set_value(True)
        at.run()
        # 10 profils demandés, 15 restantes : jusqu'à 10 invitations.
        assert at.button(key=cle_btn).label == "Rechercher et inviter (jusqu'à 10)"


def test_aucun_jargon_ni_emoji_dans_la_page(budget_dicte):
    at = _page()
    at.toggle(key="inviter_candidat").set_value(True)
    at.toggle(key="inviter_client").set_value(True)
    at.run()
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

def test_la_jauge_n_apparait_qu_avec_les_invitations(budget_dicte):
    at = _page()
    # La barre latérale porte sa propre jauge, sur toutes les pages.
    jauges = lambda: [m for m in at.main.markdown if m.value.startswith('<div class="wf-jauge')]
    assert not jauges()
    at.toggle(key="inviter_candidat").set_value(True)
    at.run()
    assert len(jauges()) == 1


def test_avertit_quand_on_demande_plus_que_le_budget(budget_dicte):
    budget_dicte["budget"] = Budget(utilisees=17, plafond=20)
    at = _page()
    at.toggle(key="inviter_client").set_value(True)
    at.number_input(key="nb_client").set_value(10)
    at.run()
    messages = [w.value for w in at.warning]
    assert any("vous en serez à 27 invitations" in m and "Rien n'est bloqué" in m
               for m in messages), messages


def test_limite_atteinte_previent_sans_bloquer(budget_dicte):
    # Limite conseillée, pas bloquante : aucune erreur, aucun bouton grisé.
    budget_dicte["budget"] = Budget(utilisees=20, plafond=20)
    at = _page()
    at.toggle(key="inviter_candidat").set_value(True)
    at.run()
    assert not at.error, [e.value for e in at.error]
    assert not at.button(key="btn_rechercher_candidats").disabled
    assert any("Rien n'est bloqué" in w.value for w in at.warning)


def test_les_options_d_invitation_sont_groupees(budget_dicte):
    at = _page()
    at.toggle(key="inviter_candidat").set_value(True)
    at.run()
    assert at.checkbox(key="reinviter_candidat").label == (
        "Réinviter les profils déjà dans votre fichier")
    assert at.text_area(key="message_candidat").max_chars == 200
    assert any(m.value == "**Invitations**" for m in at.markdown)


# --- Écoles et bilan ------------------------------------------------------

def test_les_ecoles_sont_un_menu_et_partent_dans_la_recherche(budget_dicte, scraper_espion):
    at = _page()
    menu = at.multiselect(key="ecoles_pills_candidat")
    assert menu.placeholder.startswith("Choisir")
    menu.set_value(["Dauphine"])
    at.run()
    at.button(key="btn_rechercher_candidats").click()
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    from config import ECOLES
    assert scraper_espion["appels"][0]["ecoles_ids"] == [ECOLES["Dauphine"]]


def test_le_bilan_compte_profils_et_invitations(budget_dicte, scraper_espion):
    scraper_espion["df"] = pd.DataFrame([
        {"Nom": "A", "URL du profil": "https://www.linkedin.com/in/a/", "Invitation envoyée": "Oui"},
        {"Nom": "B", "URL du profil": "https://www.linkedin.com/in/b/", "Invitation envoyée": "Non"},
    ])
    at = _page()
    at.text_input(key="keyword_client").set_value("Head of Data")
    at.toggle(key="inviter_client").set_value(True)
    at.run()
    at.button(key="btn_rechercher_clients").click()
    at.run()
    at.button(key="confirmer_clients_ok").click()
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert any("2 profils trouvés · 1 invitation envoyée" in m.value for m in at.markdown)


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
    assert at.button(key="sim_btn_recuperer").label == "Récupérer les infos"

    at.toggle(key="sim_inviter").set_value(True)
    at.run()
    # 3 profils pour 2 restantes : un avertissement, pas de refus.
    assert at.button(key="sim_btn_recuperer").label == "Récupérer les infos et inviter (jusqu'à 3)"
    assert [m for m in at.markdown if m.value.startswith('<div class="wf-jauge')]
    assert not at.error
    assert any("vous en serez à 21 invitations" in w.value for w in at.warning), [w.value for w in at.warning]
