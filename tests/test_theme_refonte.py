# -*- coding: utf-8 -*-
"""Thème de la refonte (wefiit_theme.py) : garde-fous d'accessibilité et
interdits de DESIGN.md, vérifiés sur le CSS produit."""
import re
import tomllib
from pathlib import Path

import pytest

import wefiit_theme as theme

RACINE = Path(__file__).resolve().parents[1]
CSS = theme.theme_css()
CSS_SOMBRE = theme.theme_css(dark=True)


# --- contraste WCAG ------------------------------------------------------

def _luminance(hexa: str) -> float:
    hexa = hexa.lstrip("#")
    canaux = [int(hexa[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canaux]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contraste(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _jetons(bloc: str) -> dict:
    return dict(re.findall(r"--wf-([a-z0-9-]+):\s*([^;]+);", bloc))


CLAIR = _jetons(theme._LIGHT_VARS)


def test_helper_de_contraste():
    assert contraste("#000000", "#FFFFFF") == pytest.approx(21, rel=1e-3)
    assert contraste("#6B7280", "#F5F6F7") < 4.5  # l'ancien gris mesuré à 4.47


def test_placeholder_lisible_sur_le_fond_des_champs():
    # Les champs ont pour fond --wf-surface2 ; le texte d'aide --wf-placeholder.
    assert "::placeholder" in CSS and "var(--wf-placeholder)" in CSS
    assert contraste(CLAIR["placeholder"], CLAIR["surface2"]) >= 4.5


@pytest.mark.parametrize("texte", ["text", "muted", "success", "warn", "danger", "accent"])
@pytest.mark.parametrize("fond", ["bg", "surface", "surface2"])
def test_textes_aa_sur_les_fonds(texte, fond):
    assert contraste(CLAIR[texte], CLAIR[fond]) >= 4.5, (texte, fond)


@pytest.mark.parametrize("ton", ["success", "warn", "danger"])
def test_puces_aa_sur_leur_teinte(ton):
    assert contraste(CLAIR[ton], CLAIR[f"{ton}-tint"]) >= 4.5


@pytest.mark.parametrize("fond", ["bg", "surface"])
def test_contour_des_cases_eteintes_a_3_pour_1(fond):
    assert contraste(CLAIR["control"], CLAIR[fond]) >= 3


def test_orange_texte_aa_sur_blanc():
    assert contraste(CLAIR["orange-text"], "#FFFFFF") >= 4.5


def test_coque_marine_lisible():
    sombre = _jetons(theme._VARS_SUR_SOMBRE)
    for cle in ("text", "muted"):
        assert contraste(sombre[cle], theme.WF_MARINE) >= 4.5
        assert contraste(sombre[cle], theme.WF_MARINE_PROFOND) >= 4.5
    assert contraste(theme.WF_ORANGE, theme.WF_MARINE) >= 4.5  # accents du wordmark


@pytest.mark.parametrize("jeton, couleur", sorted(theme.COULEURS_CODE.items()))
def test_coloration_du_code_aa(jeton, couleur):
    assert contraste(couleur, theme.FOND_CODE) >= 4.5, jeton
    assert f".token.{jeton} " in CSS


# --- tokens --------------------------------------------------------------

def test_tous_les_tokens_utilises_sont_definis():
    utilises = set()
    for f in list(RACINE.glob("*.py")) + list(RACINE.glob("ui/*.py")):
        utilises |= set(re.findall(r"var\(--wf-([a-z0-9-]+)", f.read_text(encoding="utf-8")))
    # Variables locales à un composant (posées dans une règle ou en style
    # en ligne), pas des tokens de palette.
    locales = set(re.findall(r"--wf-([a-z0-9-]+):", theme._CSS))
    locales |= set(re.findall(r"--wf-([a-z0-9-]+):", (RACINE / "ui/composants.py").read_text(encoding="utf-8")))
    sombre = _jetons(theme._DARK_VARS)
    assert {"bg", "text", "muted", "accent", "border", "surface", "surface2"} <= utilises
    for nom in utilises - locales:
        assert nom in CLAIR, f"--wf-{nom} absent du thème clair"
        assert nom in sombre, f"--wf-{nom} absent du thème sombre"


def test_palette_de_design_md():
    assert CLAIR["bg"].strip() == "#F6F7FB"
    assert CLAIR["muted"].strip() == "#5B6472"
    assert CLAIR["accent-vif"].strip() == "#3D5AFE"
    assert CLAIR["orange-text"].strip() == "#B45F00"
    assert CLAIR["navy-deep"].strip() == "#101D5E"


def test_config_streamlit_coque_marine():
    cfg = tomllib.loads((RACINE / ".streamlit/config.toml").read_text(encoding="utf-8"))
    assert cfg["theme"]["backgroundColor"] == "#F6F7FB"
    assert cfg["theme"]["sidebar"]["backgroundColor"] == "#172982"
    assert cfg["theme"]["sidebar"]["textColor"] == "#FFFFFF"


# --- focus, mouvement ----------------------------------------------------

def test_focus_clavier_visible():
    assert ".stButton button:focus-visible" in CSS
    assert '.stTabs [data-baseweb="tab"]:focus-visible' in CSS
    assert ".st-key-nav_menu .stButton button:focus-visible { outline:2px solid #FFFFFF" in CSS
    assert "var(--wf-focus)" in CSS
    # Aucun focus retiré sans remplaçant
    assert not re.search(r":focus(-visible)?\s*\{[^}]*outline:\s*(none|0)[^}]*\}", CSS.replace(
        '[data-baseweb="select"] input:focus-visible { outline:none; }', ""
    ).replace(".stTextArea textarea:focus-visible,\n", ""))


def test_mouvement_reduit_respecte():
    assert "@media (prefers-reduced-motion: reduce)" in CSS
    bloc = CSS.split("@media (prefers-reduced-motion: reduce)")[1]
    for sel in (".wf-cran", ".wf-direct::after",
                "[data-testid=\"stMainBlockContainer\"]"):
        assert sel in bloc
    # Moins, pas rien : plus de déplacement ni de pulsation, un fondu reste.
    assert "transform:none" in bloc and "animation:none" in bloc
    assert "wf-fondu" in bloc and "wf-entree" not in bloc and "animation:wf-cran" not in bloc
    assert "@keyframes wf-fondu { from { opacity:0; } }" in CSS


def test_appui_et_survol_suivent_les_regles_du_mouvement():
    # Appui : enfoncement léger ; survol avec déplacement réservé à la souris.
    assert re.search(r"button:active[^{]*\{ transform:scale\(\.97\)", CSS)
    survol = CSS.split("@media (hover: hover) and (pointer: fine)")[1].split("}\n}")[0]
    assert "translateY(-1px)" in survol
    hors_media = CSS.split("@media (hover: hover) and (pointer: fine)")[0]
    assert not re.search(r":hover \{[^}]*translateY", hors_media)
    assert "[data-testid=\"stMetric\"]:hover" not in CSS and ".wf-action:hover" not in CSS


def test_entree_ne_cache_rien_apres_coup():
    # `backwards` seulement : sans animation, ou après, l'état normal s'applique.
    assert "@keyframes wf-entree" in CSS
    assert re.search(r"animation:wf-entree [^;]*backwards", CSS)
    assert not re.search(r"animation:wf-entree [^;]*\bboth\b", CSS)


# --- interdits de DESIGN.md ----------------------------------------------

@pytest.mark.parametrize("css", [CSS, CSS_SOMBRE])
def test_pas_de_texte_en_degrade(css):
    assert "background-clip:text" not in css.replace(" ", "")
    assert "-webkit-background-clip" not in css


@pytest.mark.parametrize("css", [CSS, CSS_SOMBRE])
def test_pas_de_bordure_gauche_epaisse(css):
    for m in re.finditer(r"border-left\s*:\s*([0-9.]+)px", css):
        assert float(m.group(1)) <= 1, m.group(0)


def test_plus_de_majuscules_mortes_dans_les_entetes_de_tableau():
    assert "text-transform:uppercase" not in CSS.replace(" ", "")


def test_chiffres_tabulaires_dans_les_metriques():
    assert re.search(r'\[data-testid="stMetricValue"\][^}]*tabular-nums', CSS)


def test_une_seule_elevation_pour_les_metriques():
    regle = re.search(r'\[data-testid="stMetric"\] \{([^}]*)\}', CSS).group(1)
    assert "border:none" in regle and "box-shadow" in regle
    assert re.search(r"border-radius:var\(--wf-radius\)", regle)
    assert "--wf-radius:14px" in theme._LIGHT_VARS


def test_wordmark_variante_sombre_et_signature_historique():
    assert "wf-wordmark--sombre" in theme.wordmark(sur_fond_sombre=True)
    assert "wf-wordmark--sombre" not in theme.wordmark()
    assert "font-size:2.4rem" in theme.wordmark(size=2.4)
    assert "text-align:left" in theme.wordmark(1.6, False)


def test_jauge_compacte_dans_le_bloc_invitations():
    """La jauge du bloc Invitations ne s'étire pas sur toute la largeur :
    la barre latérale porte déjà la grande."""
    assert re.search(r'\[class\*="st-key-bloc_"\]\s*\.wf-jauge:not\(\.wf-jauge--sombre\)'
                     r'\s*\{[^}]*max-width:\s*360px', CSS)


def test_pastilles_du_multiselect_texte_blanc_sur_marine():
    assert re.search(r'\[data-baseweb="tag"\]\s*\{[^}]*background:var\(--wf-accent\)', CSS)
    assert '[data-baseweb="tag"] * { color:var(--wf-on-accent) !important; }' in CSS
    assert contraste("#FFFFFF", "#172982") >= 4.5


def test_boutons_avec_aide_aussi_en_texte_blanc():
    """Un bouton avec `help=` est enveloppé dans une infobulle : aucune règle
    de bouton ne doit exiger l'enfant direct (`.stButton > button`)."""
    assert not re.search(r"\.(stButton|stDownloadButton|stFormSubmitButton) > button", CSS)
    assert '.stButton button[kind="primary"] *' in CSS
