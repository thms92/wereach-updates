# -*- coding: utf-8 -*-
"""Phase 4, écrans d'action (Recherche, bloc Invitations, Messages).

Tout ce qui part depuis le compte LinkedIn est irréversible : le premier
clic montre un récapitulatif, seul « Confirmer et lancer » lance, et toute
modification du formulaire annule la confirmation en attente. Le scraper est
toujours remplacé (aucune session LinkedIn ne s'ouvre) et le budget est
dicté par le test.
"""

import ast
import re
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

import scraper_v2_sync
import ui.invitations
from database import DatabaseManager
from scraper_v2 import BUDGET_ATTEINT
from tests.conftest import chemins_de_test, lancer_app, verifier_page_affichee
from ui import page_messages as pm
from ui.invitations import echapper_markdown, recap_invitations
from utils.budget import Budget

RACINE = Path(__file__).resolve().parent.parent
MES_FICHIERS = ("ui/page_recherche.py", "ui/invitations.py", "ui/page_messages.py")
RECHERCHE = "🔍 Recherche"


@pytest.fixture
def budget_dicte(monkeypatch):
    etat = {"budget": Budget(utilisees=17, plafond=20)}
    monkeypatch.setattr(ui.invitations, "budget_du_jour", lambda _dir: etat["budget"])
    return etat


@pytest.fixture
def espion(monkeypatch):
    etat = {"recherches": [], "recuperations": [], "messages": [],
            "df": pd.DataFrame(), "erreurs": [], "restantes": 1000}

    class FauxScraper:
        def __init__(self, **kwargs):
            self.errors = []
            self.use_database = False
            self.scraper = SimpleNamespace(human=SimpleNamespace(
                daily_limits=SimpleNamespace(
                    remaining_invitations=lambda: etat["restantes"])))

        def run_scraper(self, **kwargs):
            etat["recherches"].append(kwargs)
            self.errors = list(etat["erreurs"])
            return etat["df"]

        def recolter_browsemap(self, **kwargs):
            return ([{"nom": f"P{i}", "url": f"https://www.linkedin.com/in/p-{i}/",
                      "degre": "2e", "intitule": "PM", "invitable": True}
                     for i in range(2)], None)

        def run_url_scraper(self, **kwargs):
            etat["recuperations"].append(kwargs)
            return pd.DataFrame()

        def envoyer_messages(self, **kwargs):
            etat["messages"].append(kwargs)
            return []

    monkeypatch.setattr(scraper_v2_sync, "LinkedInScraperV2Sync", FauxScraper)
    return etat


def _recherche(cookie="COOKIE-DE-TEST"):
    at = lancer_app(RECHERCHE)
    verifier_page_affichee(at, RECHERCHE)
    at.session_state["global_cookie"] = cookie
    at.run()
    return at


def _candidats_avec_invitations(at, nb=3, message=""):
    at.text_input[0].set_value("Product Manager")  # Mots-clés (Candidats)
    at.number_input[0].set_value(nb)
    at.toggle(key="inviter_candidat").set_value(True)
    at.run()
    if message:
        at.text_area(key="message_candidat").set_value(message)
        at.run()
    return at


def _recap(at):
    return [m.value for m in at.markdown if m.value.startswith("Jusqu'à")]


# --- 1. Confirmation avant les invitations --------------------------------

def test_recap_invitations_singulier_pluriel_et_message():
    assert recap_invitations(3, 3) == (
        "Jusqu'à 3 invitations partiront depuis votre compte LinkedIn ; il vous "
        "en restera 0 aujourd'hui. Sans message.")
    assert recap_invitations(1, 5, "Bonjour *toi*").startswith(
        "Jusqu'à 1 invitation partira depuis votre compte LinkedIn ; il vous en restera 4")
    assert recap_invitations(1, 5, "Bonjour *toi*").endswith("Message joint : « Bonjour \\*toi\\* »")


def test_rechercher_et_inviter_demande_confirmation(budget_dicte, espion):
    at = _candidats_avec_invitations(_recherche(), nb=3, message="Bonjour")
    bouton = at.button(key="btn_rechercher_candidats")
    assert bouton.label == "Rechercher et inviter (jusqu'à 3)"
    bouton.click()
    at.run()
    assert espion["recherches"] == [], "le premier clic ne doit rien lancer"
    assert _recap(at) == ["Jusqu'à 3 invitations partiront depuis votre compte "
                          "LinkedIn ; il vous en restera 0 aujourd'hui. "
                          "Message joint : « Bonjour »"]
    assert at.button(key="confirmer_candidats_ok").label == "Confirmer et lancer"
    assert at.button(key="confirmer_candidats_ok").proto.type == "primary"
    assert at.button(key="confirmer_candidats_annuler").label == "Annuler"

    at.button(key="confirmer_candidats_ok").click()
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert len(espion["recherches"]) == 1
    assert espion["recherches"][0]["inviter"] is True
    assert espion["recherches"][0]["nb_profils"] == 3
    assert not _recap(at), "le récapitulatif disparaît une fois lancé"


def test_annuler_ne_lance_rien(budget_dicte, espion):
    at = _candidats_avec_invitations(_recherche())
    at.button(key="btn_rechercher_candidats").click()
    at.run()
    at.button(key="confirmer_candidats_annuler").click()
    at.run()
    assert espion["recherches"] == []
    assert not _recap(at)
    assert "confirmer_candidats" not in at.session_state


def test_changer_le_nombre_annule_la_confirmation(budget_dicte, espion):
    at = _candidats_avec_invitations(_recherche(), nb=3)
    at.button(key="btn_rechercher_candidats").click()
    at.run()
    assert _recap(at)
    at.number_input[0].set_value(2)
    at.run()
    assert not _recap(at), "un paramètre changé doit annuler la confirmation"
    assert not [b for b in at.button if b.key == "confirmer_candidats_ok"]
    assert espion["recherches"] == []


def test_rechercher_sans_inviter_part_tout_de_suite(budget_dicte, espion):
    at = _recherche()
    at.text_input(key="keyword_client").set_value("Head of Data")
    at.run()
    at.button(key="btn_rechercher_clients").click()
    at.run()
    assert len(espion["recherches"]) == 1
    assert espion["recherches"][0]["inviter"] is False
    assert not _recap(at)


def test_budget_epuise_refuse_avant_toute_confirmation(budget_dicte, espion):
    budget_dicte["budget"] = Budget(utilisees=20, plafond=20)
    at = _recherche()
    at.toggle(key="inviter_client").set_value(True)
    at.run()
    at.button(key="btn_rechercher_clients").click()
    at.run()
    assert espion["recherches"] == [] and not _recap(at)


def test_le_bloc_recuperer_demande_confirmation(budget_dicte, espion):
    budget_dicte["budget"] = Budget(utilisees=5, plafond=20)
    at = _recherche()
    at.text_input(key="sim_url").set_value("https://www.linkedin.com/in/reference/")
    at.button(key="sim_btn_trouver").click()
    at.run()
    # Même contrôle que Recherche : un interrupteur.
    at.toggle(key="sim_inviter").set_value(True)
    at.run()
    assert at.button(key="sim_btn_recuperer").label == (
        "Récupérer les infos et inviter (jusqu'à 2)")
    at.button(key="sim_btn_recuperer").click()
    at.run()
    assert espion["recuperations"] == []
    espion_recap = _recap(at)
    assert espion_recap and espion_recap[0].startswith("Jusqu'à 2 invitations partiront")

    at.button(key="confirmer_sim_annuler").click()
    at.run()
    assert espion["recuperations"] == [] and not _recap(at)

    at.button(key="sim_btn_recuperer").click()
    at.run()
    at.button(key="confirmer_sim_ok").click()
    at.run()
    assert len(espion["recuperations"]) == 1
    assert espion["recuperations"][0]["inviter"] is True


def test_recuperer_sans_inviter_part_tout_de_suite(budget_dicte, espion):
    at = _recherche()
    at.text_input(key="sim_url").set_value("https://www.linkedin.com/in/reference/")
    at.button(key="sim_btn_trouver").click()
    at.run()
    at.button(key="sim_btn_recuperer").click()
    at.run()
    assert len(espion["recuperations"]) == 1


# --- 3. Une seule façon de dire le budget ---------------------------------

def test_jamais_utilisees_dans_ces_ecrans():
    for fichier in MES_FICHIERS:
        source = (RACINE / fichier).read_text(encoding="utf-8")
        # Le budget se dit en restantes (« N restantes sur P ») ; « les 3
        # premières seront utilisées », sur les entreprises, n'en parle pas.
        assert not re.search(r"utilisées? sur|'utilisée|invitations? utilisée", source), fichier


# --- 4. et 5. Session : première connexion, modification annulable -------

def test_premiere_connexion_depliee_et_boutons_inactifs(budget_dicte, espion):
    at = _recherche(cookie="")
    assert "Première connexion à LinkedIn" in [h.value for h in at.header]
    assert not [e for e in at.expander if "Comment récupérer" in e.label], (
        "les étapes sont dépliées, pas dans un panneau replié")
    assert any(m.value.startswith("1. Dans Chrome") for m in at.markdown)
    assert at.text_input(key="cookie_shared").placeholder == (
        "Collez ici la valeur copiée depuis Chrome")
    for cle in ("btn_rechercher_candidats", "btn_rechercher_clients", "sim_btn_trouver"):
        assert at.button(key=cle).disabled, cle
    legendes = [c.value for c in at.caption]
    assert legendes.count("Connectez d'abord votre session LinkedIn (ci-dessus).") == 3


def test_avec_session_le_mode_d_emploi_reste_replie(budget_dicte):
    at = _recherche()
    assert "Première connexion à LinkedIn" not in [h.value for h in at.header]
    assert [e for e in at.expander if "Comment récupérer" in e.label]
    assert not at.button(key="btn_rechercher_candidats").disabled


def test_modifier_puis_annuler(budget_dicte):
    at = _recherche()
    at.button(key="cookie_modifier").click()
    at.run()
    assert at.text_input(key="cookie_shared").placeholder == (
        "Collez ici la valeur copiée depuis Chrome")
    at.button(key="cookie_annuler").click()
    at.run()
    assert not at.session_state["cookie_editing"]
    assert at.button(key="test_cookie_btn").label == "Tester"
    assert not [t for t in at.text_input if t.key == "cookie_shared"]


def test_apres_enregistrement_le_test_est_propose(budget_dicte, monkeypatch, tmp_path):
    at = _recherche(cookie="")
    enregistrees = []
    monkeypatch.setattr(type(at.session_state["cookie_manager"]), "save_cookie",
                        lambda self, v: enregistrees.append(v))
    at.text_input(key="cookie_shared").set_value("AQE" + "x" * 150)
    at.button(key="cookie_enregistrer").click()
    at.run()
    assert enregistrees
    bouton = at.button(key="test_cookie_btn")
    assert bouton.label == "Tester la session" and bouton.proto.type == "primary"


# --- 6. Messages -----------------------------------------------------------

def test_echapper_markdown():
    assert echapper_markdown("*Marie* _A_ [x](y) $1 #2") == (
        "\\*Marie\\* \\_A\\_ \\[x\\]\\(y\\) \\$1 \\#2")
    assert pm.echapper_markdown is echapper_markdown


def test_apercu_multiligne_fidele():
    html = pm.apercu_html("Bonjour,\n\n- a *b* $c$")
    assert "\n" not in html, "une ligne vide casserait le bloc HTML"
    assert "Bonjour,<br><br>- a *b* &#36;c&#36;" in html


def test_recap_messages():
    assert pm.recap_messages(["A", "B", "C"]) == "3 messages partiront tels quels, à : A, B, C."
    assert pm.recap_messages(["*A*"]) == "1 message partira tel quel, à : \\*A\\*."


URLS = [f"https://www.linkedin.com/in/profil-test-phase4-{i}/" for i in range(2)]


@pytest.fixture
def acceptees(espion):
    db_file = str(chemins_de_test().db_file)
    db = DatabaseManager(db_file=db_file)
    for i, url in enumerate(URLS):
        db.ajouter_invitation(db.ajouter_profil(f"Personne *Test* {i}", "PM", "Orbique", "", url), "")
        db.marquer_acceptee(url)
    yield espion
    con = sqlite3.connect(db_file)
    for url in URLS:
        con.execute("DELETE FROM invitations WHERE profile_id IN (SELECT id FROM profiles WHERE url = ?)", (url,))
        con.execute("DELETE FROM profiles WHERE url = ?", (url,))
    con.commit()
    con.close()


def _messages(cookie="COOKIE-DE-TEST"):
    at = lancer_app("✉️ Messages")
    verifier_page_affichee(at, "✉️ Messages")
    at.session_state["global_cookie"] = cookie
    at.run()
    return at


def test_envoyer_demande_confirmation(acceptees):
    at = _messages()
    for url in URLS:
        at.checkbox(key=pm.cle_case(url)).check()
    at.text_area(key="msg_modele").input("Bonjour,\n\n- a *b* $c$")
    at.run()
    # Les noms venus de LinkedIn sont échappés dans les libellés.
    assert at.checkbox(key=pm.cle_case(URLS[0])).label.startswith("**Personne \\*Test\\* 0**")
    assert any("Bonjour,<br><br>- a *b* &#36;c&#36;" in m.value for m in at.markdown)

    at.button(key="msg_envoyer").click()
    at.run()
    assert acceptees["messages"] == []
    assert any(m.value == "2 messages partiront tels quels, à : Personne \\*Test\\* 0, "
               "Personne \\*Test\\* 1." for m in at.markdown)

    # Décocher une personne annule la confirmation.
    at.checkbox(key=pm.cle_case(URLS[1])).uncheck()
    at.run()
    assert not [b for b in at.button if b.key == "confirmer_messages_ok"]

    at.button(key="msg_envoyer").click()
    at.run()
    at.button(key="confirmer_messages_ok").click()
    at.run()
    assert len(acceptees["messages"]) == 1
    assert [c["url"] for c in acceptees["messages"][0]["cibles"]] == [URLS[0]]


def test_sans_session_un_bouton_mene_a_recherche(espion):
    at = _messages(cookie="")
    at.button(key="msg_vers_recherche").click()
    at.run()
    assert at.session_state["page"] == RECHERCHE
    assert at.title[0].value == "Nouvelle recherche"


# --- 7. et 8. Résultats : bilan, suite, budget atteint --------------------

def test_bilan_suite_et_budget_atteint(budget_dicte, espion):
    budget_dicte["budget"] = Budget(utilisees=5, plafond=20)
    espion["df"] = pd.DataFrame([
        {"Nom": "A", "URL du profil": "https://www.linkedin.com/in/a/", "Invitation envoyée": "Oui"},
        {"Nom": "B", "URL du profil": "https://www.linkedin.com/in/b/", "Invitation envoyée": "Oui"},
    ])
    espion["erreurs"] = [BUDGET_ATTEINT, "Autre incident"]
    at = _recherche()
    at.text_input(key="keyword_client").set_value("Head of Data")
    at.toggle(key="inviter_client").set_value(True)
    at.run()
    at.button(key="btn_rechercher_clients").click()
    at.run()
    at.button(key="confirmer_clients_ok").click()
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert any("2 profils trouvés · 2 invitations envoyées" in m.value for m in at.markdown)
    assert BUDGET_ATTEINT in [i.value for i in at.info]
    incidents = [e for e in at.expander if e.label.startswith("Incidents")]
    assert incidents and incidents[0].label == "Incidents pendant la recherche (1)"

    at.button(key="clients_vers_messages").click()
    at.run()
    assert at.session_state["page"] == "✉️ Messages"


def test_les_telechargements_ne_relancent_pas_la_page():
    source = (RACINE / "ui/invitations.py").read_text(encoding="utf-8")
    appels = [n for n in ast.walk(ast.parse(source))
              if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "download_button"]
    assert len(appels) == 2
    for appel in appels:
        assert any(k.arg == "on_click" and getattr(k.value, "value", None) == "ignore"
                   for k in appel.keywords)


# --- 10. Titres -----------------------------------------------------------

def test_titres_sans_ancre_et_sans_saut_de_niveau():
    for fichier in MES_FICHIERS:
        arbre = ast.parse((RACINE / fichier).read_text(encoding="utf-8"))
        for n in ast.walk(arbre):
            if (isinstance(n, ast.Call)
                    and getattr(n.func, "attr", "") in ("title", "header", "subheader")
                    and getattr(n.func.value, "id", "") == "st"):
                assert any(k.arg == "anchor" and k.value.value is False
                           for k in n.keywords), f"{fichier}:{n.lineno}"
    source = (RACINE / "ui/page_messages.py").read_text(encoding="utf-8")
    assert "st.subheader(" not in source  # sous le titre : des h2
