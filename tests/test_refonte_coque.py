# -*- coding: utf-8 -*-
"""Coque de l'application (refonte phase 2) : barre latérale.

Wordmark en tête de la barre latérale, jauge du budget sous le menu sur
toutes les pages, libellés sans émoji, pied discret, et une remise à zéro
de la base dont la confirmation fonctionne réellement.
"""

import re

import pytest

from tests.conftest import lancer_app, verifier_page_affichee

PAGES = ["📊 Dashboard", "🔍 Recherche", "🏢 Veille", "✉️ Messages",
         "💾 Historique", "📜 Logs"]

EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⬆⬇]")


def _markdown_lateral(at):
    return [m.value for m in at.sidebar.markdown]


def test_le_wordmark_est_dans_la_barre_laterale_et_plus_dans_la_page():
    at = lancer_app("📊 Dashboard")
    verifier_page_affichee(at, "📊 Dashboard")
    assert any("wf-wordmark--sombre" in m for m in _markdown_lateral(at))
    assert not any('<div class="wf-wordmark' in m.value for m in at.main.markdown)


@pytest.mark.parametrize("page", PAGES)
def test_la_jauge_du_budget_est_sous_le_menu_sur_chaque_page(page):
    at = lancer_app(page)
    assert not at.exception, [str(e.value) for e in at.exception]
    jauges = [m for m in _markdown_lateral(at) if 'role="meter"' in m]
    assert len(jauges) == 1
    assert "wf-jauge--sombre" in jauges[0]


def test_aucun_emoji_dans_les_libelles_de_la_barre_laterale(monkeypatch):
    monkeypatch.setenv("WEREACH_ADMIN", "1")
    at = lancer_app("📊 Dashboard")
    libelles = [b.label for b in at.sidebar.button]
    libelles += [e.label for e in at.sidebar.expander]
    libelles += [c.value for c in at.sidebar.caption]
    fautifs = [l for l in libelles if EMOJI.search(l or "")]
    assert fautifs == []


def test_la_version_est_un_pied_discret():
    at = lancer_app("📊 Dashboard")
    legendes = [c.value for c in at.sidebar.caption]
    assert any(re.fullmatch(r"We\.Reach \d+\.\d+\.\d+", l) for l in legendes), legendes
    bouton = [b for b in at.sidebar.button if b.key == "btn_verif_maj"][0]
    assert bouton.proto.type != "primary"


def test_la_reinitialisation_attend_la_case_cochee(monkeypatch):
    monkeypatch.setenv("WEREACH_ADMIN", "1")
    at = lancer_app("📊 Dashboard")
    bouton = [b for b in at.sidebar.button
              if b.label == "Réinitialiser la base de données"][0]
    assert bouton.disabled, "le bouton destructif est armé sans confirmation"

    at.sidebar.checkbox(key="confirm_reset_db").check().run()
    bouton = [b for b in at.sidebar.button
              if b.label == "Réinitialiser la base de données"][0]
    assert not bouton.disabled, "la case cochée ne déverrouille pas le bouton"
