# -*- coding: utf-8 -*-
"""La règle CSS du menu ne doit toucher que le menu.

Écrite pour la barre latérale entière, elle privait de bordure et de fond
« 🚪 Déconnexion », « 💾 Enregistrer mon proxy » et le bouton destructif
« 🗑️ Réinitialiser la base de données », réduits à du texte aligné à gauche.

Le menu est scopé par la classe que Streamlit pose sur le conteneur de tout
widget doté d'une clé : `st-key-<clé assainie>`, ici `st-key-nav_…`.
"""

import re
from pathlib import Path

import streamlit

import wefiit_theme
from tests.conftest import lancer_app
from tests.test_navigation import arbre_app, pages_du_menu

PAGES = pages_du_menu(arbre_app())
PREFIXE_CLE_NAV = "nav_"
SELECTEUR_NAV = "st-key-" + PREFIXE_CLE_NAV


def css_du_theme() -> str:
    """Le CSS réellement injecté par `inject_theme()`."""
    capture = []
    vrai_markdown = wefiit_theme.st.markdown
    wefiit_theme.st.markdown = lambda corps, **kwargs: capture.append(corps)
    try:
        wefiit_theme.inject_theme()
    finally:
        wefiit_theme.st.markdown = vrai_markdown
    assert len(capture) == 1
    return capture[0]


def regles_css(css: str):
    """Les règles du thème, sous forme (sélecteur, corps), commentaires ôtés."""
    sans_commentaires = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    regles = []
    for morceau in sans_commentaires.split("}"):
        if "{" not in morceau:
            continue
        selecteur, corps = morceau.split("{", 1)
        regles.append((" ".join(selecteur.split()), corps.strip()))
    return regles


def test_la_regle_du_menu_ne_deborde_pas_sur_les_autres_boutons():
    deborde = [
        selecteur
        for selecteur, _ in regles_css(css_du_theme())
        if "stSidebar" in selecteur
        and ".stButton > button" in selecteur
        and SELECTEUR_NAV not in selecteur
    ]
    assert deborde == [], (
        "ces règles s'appliquent à TOUS les boutons de la barre latérale — "
        "Déconnexion, Enregistrer mon proxy, Réinitialiser la base de données "
        f"y perdent bordure et fond : {deborde}"
    )


def test_le_menu_reste_bien_mis_en_forme():
    """Le scope ne doit pas avoir supprimé la mise en forme du menu."""
    selecteurs = [s for s, _ in regles_css(css_du_theme()) if SELECTEUR_NAV in s]
    assert selecteurs, "plus aucune règle ne met en forme le menu"
    assert any("[kind=\"primary\"]" in s for s in selecteurs), (
        "l'item actif du menu n'est plus distingué"
    )


def test_le_css_du_theme_n_a_aucune_accolade_mal_echappee():
    """Le thème est une f-string : une accolade simple casse le démarrage.

    L'appel lui-même lèverait l'erreur ; on vérifie en plus qu'aucune accolade
    doublée n'a survécu au formatage.
    """
    css = css_du_theme()
    assert css.count("{") == css.count("}")
    assert "{{" not in css and "}}" not in css


def test_le_selecteur_du_menu_correspond_aux_cles_des_boutons_de_navigation():
    at = lancer_app("📊 Dashboard")
    cles = [b.key for b in at.sidebar.button if b.key]

    assert cles == [f"{PREFIXE_CLE_NAV}{page}" for page in PAGES]
    assert SELECTEUR_NAV in css_du_theme()


def test_les_boutons_hors_navigation_restent_hors_de_portee_de_la_regle():
    """Ceux que la règle débordait : aucun ne porte de clé `nav_`."""
    at = lancer_app("📊 Dashboard")
    hors_nav = {
        b.label: b.key
        for b in at.sidebar.button
        if not (b.key or "").startswith(PREFIXE_CLE_NAV)
    }

    for libelle in (
        "🚪 Déconnexion",
        "💾 Enregistrer mon proxy",
        "🗑️ Réinitialiser la base de données",
    ):
        assert libelle in hors_nav, f"bouton « {libelle} » absent de la barre latérale"
    assert all(not (cle or "").startswith(PREFIXE_CLE_NAV) for cle in hors_nav.values())


def test_streamlit_emet_bien_une_classe_st_key_pour_une_cle_de_widget():
    """Le scope repose sur une classe produite par le front de Streamlit.

    Vérifié sur le bundle réellement installé plutôt que sur parole : si une
    version future cessait de l'émettre, le menu perdrait sa mise en forme.
    """
    statique = Path(streamlit.__file__).parent / "static"
    trouve = any(
        "st-key-" in fichier.read_text(encoding="utf-8", errors="ignore")
        for fichier in statique.rglob("*.js")
    )
    assert trouve, f"aucune trace de `st-key-` sous {statique}"
