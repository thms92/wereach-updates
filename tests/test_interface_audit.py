# -*- coding: utf-8 -*-
"""Corrections de l'audit d'interface du 2026-10-18, figées.

Chacune corrige un défaut constaté à l'écran : libellés anglais, deux noms
de produit à la fois, titres doublés d'émojis lus à voix haute, plafond
d'invitations dessiné comme une hausse, colonnes techniques de la base.
"""

import re
from pathlib import Path

from tests.conftest import lancer_app, verifier_page_affichee

RACINE = Path(__file__).resolve().parents[1]


def _textes(at):
    return " ".join(
        [m.value for m in at.markdown] + [t.value for t in at.title]
        + [h.value for h in at.header] + [s.value for s in at.subheader]
    )


def test_le_menu_est_en_francais():
    at = lancer_app("📊 Dashboard")
    verifier_page_affichee(at, "📊 Dashboard")
    libelles = [b.label for b in at.sidebar.button if (b.key or "").startswith("nav_")]
    assert "Tableau de bord" in libelles and "Journal" in libelles
    assert "Dashboard" not in libelles and "Logs" not in libelles


def test_un_seul_nom_de_produit_et_pas_de_pied_de_page_perime():
    at = lancer_app("📊 Dashboard")
    assert "LinkedIn Scraper Pro" not in _textes(at)


def test_les_titres_de_page_sont_des_h1_sans_emoji():
    for page, titre in [("📊 Dashboard", "Tableau de bord"),
                        ("🔍 Recherche", "Nouvelle recherche"),
                        ("💾 Historique", "Historique des profils"),
                        ("📜 Logs", "Journal d'exécution")]:
        at = lancer_app(page)
        assert [t.value for t in at.title] == [titre], (page, [t.value for t in at.title])


def test_le_plafond_d_invitations_n_est_pas_une_hausse():
    # Le plafond se lit en crans restants (jauge « Budget du jour », rôle
    # meter, « n sur max »), plus en métrique : aucune flèche de hausse.
    # Phase 4 : la jauge vit dans la barre latérale (toujours visible) ; la
    # page n'en reprend que la puce courte « N restantes sur P ».
    at = lancer_app("📊 Dashboard")
    jauges = [m.value for m in at.sidebar.markdown if 'role="meter"' in m.value]
    assert jauges, "la jauge du budget n'est pas dessinée à côté du tableau de bord"
    assert "Invitations du jour" in jauges[0] and " sur " in jauges[0]
    page = " ".join(m.value for m in at.main.markdown)
    assert re.search(r"restantes? sur 20|\(20 conseillées\)", page)
    assert not [x for x in at.metric if x.delta]


def test_plus_de_libelles_anglais_dans_le_tableau_de_bord():
    assert "Keyword" not in _textes(lancer_app("📊 Dashboard"))


def test_les_menus_deroulants_ont_un_texte_d_aide_en_francais():
    # « Choose options » est le texte par défaut de Streamlit : chaque
    # st.multiselect doit fournir le sien.
    # Toute source qui en contient un : l'app et chaque module de page.
    fichiers = [RACINE / "app_advanced.py"] + sorted((RACINE / "ui").glob("*.py"))
    avec_menu = [f for f in fichiers if ".multiselect(" in f.read_text(encoding="utf-8")]
    assert RACINE / "ui/page_recherche.py" in avec_menu
    for f in avec_menu:
        src = f.read_text(encoding="utf-8")
        assert src.count(".multiselect(") == src.count('placeholder="Choisir'), f


def test_l_historique_masque_l_index_et_les_noms_techniques():
    bloc = (RACINE / "ui/page_historique.py").read_text(encoding="utf-8")
    assert "hide_index=True" in bloc and '"Poste"' in bloc


def test_la_configuration_declare_inter_et_cache_deploy():
    cfg = (RACINE / ".streamlit/config.toml").read_text(encoding="utf-8")
    assert 'font                     = "Inter:' in cfg
    assert 'toolbarMode = "minimal"' in cfg
