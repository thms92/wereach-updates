# -*- coding: utf-8 -*-
"""Coque et tableau de bord (phase 4, corrections après tests)."""

import re

import pytest

import wefiit_theme as theme
from wefiit_theme import theme_css


# --- contraste WCAG, opacité comprise ----------------------------------------

def _rvb(hexa: str):
    h = hexa.strip().lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def _luminance(hexa: str) -> float:
    def canal(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (canal(c) for c in _rvb(hexa))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def melange(texte: str, fond: str, opacite: float) -> str:
    """Couleur réellement vue : le texte à `opacite` posé sur le fond."""
    t, f = _rvb(texte), _rvb(fond)
    return "#" + "".join(f"{round(a * opacite + b * (1 - opacite)):02X}" for a, b in zip(t, f))


def _jetons_sombres() -> dict:
    return dict(re.findall(r"--wf-([\w-]+):\s*([^;]+);", theme._VARS_SUR_SOMBRE))


def test_helper_de_contraste_et_melange():
    assert contraste("#000000", "#FFFFFF") == pytest.approx(21, rel=1e-3)
    # La mesure de la critique : #C9CEE6 à 0.6 sur #152679 donnait #818BBA, 4.0:1.
    vu = melange("#C9CEE6", "#152679", 0.6)
    assert contraste(vu, "#152679") == pytest.approx(4.0, abs=0.1)


def _opacite_legende_laterale(css: str) -> float:
    """Opacité déclarée pour les légendes de la barre ; 0.6 (Streamlit) sinon."""
    regles = re.findall(r'section\[data-testid="stSidebar"\] \[data-testid="stCaptionContainer"\][^{]*\{([^}]*)\}', css)
    for corps in regles:
        m = re.search(r"opacity:\s*([\d.]+)", corps)
        if m:
            return float(m.group(1))
    return 0.6


@pytest.mark.parametrize("fond", ["#152679", theme.WF_MARINE, theme.WF_MARINE_PROFOND])
def test_la_version_dans_la_barre_laterale_tient_4_5(fond):
    opacite = _opacite_legende_laterale(theme_css())
    vu = melange(_jetons_sombres()["muted"].strip(), fond, opacite)
    assert contraste(vu, fond) >= 4.5, (vu, fond, opacite)


# --- formulation unique du budget --------------------------------------------

from ui.composants import (ICONES, carte_action, etat_vide, jauge_budget,  # noqa: E402
                           texte_budget)


def _texte(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html).replace("&#x27;", "'")


def test_la_jauge_dit_restantes_sur_le_plafond_du_jour_jamais_utilisees():
    texte = " ".join(_texte(jauge_budget(17, 20)).split())
    assert "3 restantes sur 20" in texte
    assert "conseill" not in texte
    assert "utilisée" not in texte


def test_texte_court_du_budget():
    assert texte_budget(17, 20) == "3 invitations restantes sur 20"
    assert texte_budget(19, 20) == "1 invitation restante sur 20"
    # Plafond bloquant : un compteur au-delà (ancien) se lit « 0 restante ».
    assert texte_budget(25, 20) == "0 invitation restante sur 20"


def test_le_sens_de_l_aria_ne_change_pas():
    assert 'aria-valuetext="3 invitations restantes sur 20"' in jauge_budget(17, 20)


# --- composants ----------------------------------------------------------------

def test_carte_vedette_et_icone_de_reussite():
    html = carte_action("2 personnes ont accepté", "", "ok", "accepte", vedette=True)
    assert "wf-action--vedette" in html and ICONES["accepte"] in html
    assert "wf-action--vedette" not in carte_action("x", "", "ok")


def test_etat_vide_avec_etapes_numerotees():
    html = etat_vide("Titre", "Texte", etapes=("Un", "Deux <b>", "Trois"))
    assert html.count("<li>") == 3 and '<ol class="wf-vide__etapes">' in html
    assert "Deux &lt;b&gt;" in html
    assert "<ol" not in etat_vide("Titre", "Texte")


# --- thème -------------------------------------------------------------------

def test_le_point_en_direct_pulse_trois_fois_puis_s_arrete():
    css = theme_css()
    regle = re.search(r"\.wf-direct::after \{[^}]*\}", css).group(0)
    assert "wf-pouls" in regle and " 3;" in regle and "infinite" not in regle


def test_l_icone_d_onglet_est_la_marque_en_svg():
    from streamlit.elements.lib.image_utils import image_to_url
    from streamlit.elements.lib.layout_utils import LayoutConfig
    assert theme.FAVICON_SVG.startswith("<svg") and theme.WF_ORANGE in theme.FAVICON_SVG
    url = image_to_url(theme.FAVICON_SVG, layout_config=LayoutConfig(width="stretch"),
                       clamp=False, channels="RGB", output_format="auto", image_id="favicon")
    assert url.startswith("data:image/svg+xml;base64,")


def test_select_all_de_streamlit_est_traduit():
    script = theme._SCRIPT_FRANCAIS
    assert "document.documentElement.lang='fr'" in script
    assert "Tout sélectionner" in script and "Sélectionner les $1 résultats" in script
    # Les motifs correspondent exactement aux textes du bundle Streamlit 1.58.
    # DOMPurify retire un <script> dont le texte contient « < » + caractère
    # de mot : le script entier (langue comprise) disparaissait.
    assert not re.search(r"<[/\w!]", script)
    (tout, _), (resultats, _) = theme.TRADUCTIONS_INTERFACE
    assert re.match(tout, "Select all") and not re.match(tout, "Select all rows")
    assert re.match(resultats, "Select 12 matches")


# --- sources de la coque -----------------------------------------------------

from pathlib import Path  # noqa: E402

RACINE = Path(__file__).resolve().parents[1]
APP = (RACINE / "app_advanced.py").read_text(encoding="utf-8")
TDB = (RACINE / "ui" / "page_tableau_de_bord.py").read_text(encoding="utf-8")


def test_page_config_sans_emoji_et_barre_auto():
    assert "💼" not in APP
    assert "page_icon=FAVICON_SVG" in APP
    assert 'initial_sidebar_state="auto"' in APP


@pytest.mark.parametrize("source", [APP, TDB], ids=["app_advanced", "tableau_de_bord"])
def test_titres_sans_ancre(source):
    appels = re.findall(r"st\.(?:sidebar\.)?(?:title|header|subheader)\((.*?)\)\n", source)
    assert appels
    assert all("anchor=False" in a for a in appels), appels


def test_plus_de_file_d_attente_inutilisee():
    assert "QueueManager" not in APP and "queue_manager" not in APP


def test_la_jauge_est_reservee_puis_redessinee_apres_la_page():
    fin = APP.rindex("afficher_page_journal()")
    assert "_dessiner_jauge()" in APP[fin:]
    assert "_jauge = st.sidebar.empty()" in APP


# --- tableau de bord rendu, avec des données fictives --------------------------

import json  # noqa: E402
from datetime import date  # noqa: E402

from tests.conftest import EMAIL_DE_TEST, lancer_app, verifier_page_affichee  # noqa: E402


@pytest.fixture
def donnees(tmp_path, monkeypatch):
    """Base fictive : 10 profils, 6 invités, 3 acceptés, 1 messagé ; 17/20."""
    monkeypatch.setenv("WEREACH_DATA_DIR", str(tmp_path))
    from cookie_utils import CookieManager
    from database import DatabaseManager
    from utils.user_context import user_paths_for
    chemins = user_paths_for(EMAIL_DE_TEST)

    def budget(envoyees):
        (chemins.config_dir / "daily_limits.json").write_text(json.dumps(
            {"date": date.today().isoformat(), "profiles_scraped": 0,
             "invitations_sent": envoyees, "sessions": 1}), encoding="utf-8")

    def remplir(session=True, envoyees=17, profils=10):
        db = DatabaseManager(db_file=str(chemins.db_file))
        for i in range(profils):
            url = f"https://exemple.test/in/demo-{i}/"
            pid = db.ajouter_profil(f"Camille Exemple{i}", "Poste fictif", "Société Fictive",
                                    "École Exemple", url, "Ville")
            if i < 6:
                db.ajouter_invitation(pid, "Bonjour (démo)")
            if i < 3:
                db.marquer_acceptee(url)
            if i < 1:
                db.marquer_messagee(url)
        if session:
            CookieManager(config_dir=str(chemins.config_dir)).save_cookie("AQEDEMO" + "x" * 150)
        budget(envoyees)
        return chemins

    remplir.budget = budget
    return remplir


def _principal(at):
    # Sans la feuille de style injectée, qui cite toutes les classes wf-*.
    return " ".join(m.value for m in at.main.markdown
                    if not m.value.lstrip().startswith("<style")).replace("&#x27;", "'")


def _jauges_laterales(at):
    """Les jauges d'invitations de la barre latérale (celle des pages est à part)."""
    return [m.value for m in at.sidebar.markdown
            if 'aria-label="Invitations du jour"' in m.value]


def test_tableau_de_bord_rempli(donnees):
    donnees()
    at = lancer_app("📊 Dashboard")
    verifier_page_affichee(at, "📊 Dashboard")
    html = _principal(at)
    # Budget : la jauge de la barre latérale + une puce, jamais de jauge dans la page.
    assert 'role="meter"' not in html
    assert len(_jauges_laterales(at)) == 1
    assert "3 invitations restantes sur 20" in html
    assert "utilisée" not in html
    # Alerte dès 80 % consommés, pas seulement à la limite.
    assert "Plus que 3 invitations avant la limite du jour" in html
    # La réussite en tête, seule en vedette.
    cartes = re.findall(r'<div class="wf-action[^"]*">.*?wf-action__titre">([^<]+)', html)
    # 3 acceptés dont 1 déjà messagé : 2 à qui écrire.
    assert cartes[0] == "2 personnes ont accepté votre invitation", cartes
    assert html.count("wf-action--vedette") == 1
    # h1, puis h2 « À faire » et « Vos chiffres », dont les tableaux sont
    # les h3 ; aucune ancre.
    assert [h.value for h in at.header] == ["À faire", "Vos chiffres"]
    assert [h.value for h in at.main.subheader] == ["Par école", "Par entreprise",
                                                    "Par poste"]
    assert all(h.proto.hide_anchor
               for h in list(at.header) + list(at.title) + list(at.main.subheader))
    # Le parcours a laissé la place aux chiffres de la période.
    assert '<ol class="wf-entonnoir"' not in html
    assert [m.value for m in at.main.metric][:2] == ["6", "3"]


def test_premier_lancement_un_seul_bouton_principal(donnees):
    donnees(session=False, envoyees=0, profils=0)
    at = lancer_app("📊 Dashboard")
    verifier_page_affichee(at, "📊 Dashboard")
    principaux = [b.key for b in at.main.button if b.proto.type == "primary"]
    assert principaux == ["tdb_aller_recherche"]
    html = _principal(at)
    assert "Lancez votre première recherche" in html and '<ol class="wf-entonnoir"' not in html
    for etape in ("Connecter la session LinkedIn", "Lancer une recherche",
                  "Suivre les réponses dans Messages"):
        assert f"<li>{etape}</li>" in html


def test_pas_d_alerte_de_budget_sous_80_pour_cent():
    from ui.page_tableau_de_bord import actions_du_jour
    assert actions_du_jour(0, 0, True, budget_utilisees=15, budget_plafond=20) == []
    alerte = actions_du_jour(0, 0, True, budget_utilisees=19, budget_plafond=20)
    assert [a[0] for a in alerte] == ["Plus que 1 invitation avant la limite du jour"]
    assert alerte[0][2] == "attention"
    # Au plafond (bloquant) : l'outil n'invite plus et dit quand reprendre.
    for n in (20, 27):
        atteinte = actions_du_jour(0, 0, True, budget_utilisees=n, budget_plafond=20)
        assert [a[0] for a in atteinte] == ["Limite du jour atteinte : 20 invitations envoyées"]
        assert atteinte[0][2] == "attention" and "reprendre demain" in atteinte[0][1]


def test_la_jauge_suit_un_envoi_fait_par_la_page(donnees, monkeypatch):
    """La page consomme le budget pendant le rendu : la jauge le montre."""
    donnees(envoyees=5)
    import streamlit as st
    import ui.page_tableau_de_bord as tdb

    def page_qui_envoie():
        st.title("Tableau de bord", anchor=False)
        donnees.budget(19)

    monkeypatch.setattr(tdb, "afficher_page_tableau_de_bord", page_qui_envoie)
    at = lancer_app("📊 Dashboard")
    assert not at.exception, [str(e.value) for e in at.exception]
    jauges = _jauges_laterales(at)
    assert len(jauges) == 1
    assert 'aria-valuenow="1"' in jauges[0], jauges[0][:300]
