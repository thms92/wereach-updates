# -*- coding: utf-8 -*-
"""Thème visuel We.Reach — CSS injecté dans Streamlit.

Direction : DESIGN.md (refonte du 2026-10-18). Coque marine à gauche, fond
de travail froid et clair, surfaces blanches à une seule élévation, et un
mouvement court au service de l'état (entrée de page, jauge du budget,
point « en direct »).

Usage :
    from wefiit_theme import inject_theme, wordmark
    inject_theme()                       # thème clair (défaut)
    inject_theme(dark=True)              # thème sombre
    st.markdown(wordmark(), unsafe_allow_html=True)   # logo « We.Reach »
    st.sidebar.markdown(wordmark(sur_fond_sombre=True), unsafe_allow_html=True)

Le CSS est produit par `theme_css()`, testable sans Streamlit.
"""
import streamlit as st

_FONTS = "@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');"

# Orange des accents du wordmark (identique clair/sombre)
WF_ORANGE = "#F98F03"

# Marine WEFIIT : la coque (barre latérale) et l'accent
WF_MARINE = "#172982"
WF_MARINE_PROFOND = "#101D5E"

# Palette claire. Les textes atténués et sémantiques tiennent 4.5:1 sur le
# fond (#F6F7FB) comme sur le fond des champs (#F5F6F7) :
# tests/test_theme_refonte.py le vérifie.
_LIGHT_VARS = """
  --wf-bg:#F6F7FB; --wf-surface:#FFFFFF; --wf-surface2:#F5F6F7; --wf-border:#E3E6EE; --wf-border-strong:#C9CED9;
  --wf-text:#14181C; --wf-muted:#5B6472; --wf-placeholder:#5B6472; --wf-grid:#EEF0F4; --wf-control:#858E9E;
  --wf-accent:#172982; --wf-accent-strong:#1F2F8F; --wf-accent-tint:rgba(23,41,130,.10); --wf-on-accent:#FFFFFF;
  --wf-navy:#172982; --wf-navy-deep:#101D5E; --wf-accent-vif:#3D5AFE; --wf-focus:#3D5AFE;
  --wf-orange:#F98F03; --wf-orange-text:#B45F00;
  --wf-success:#15803D; --wf-success-tint:#EDF7F0;
  --wf-warn:#B45309; --wf-warn-tint:#FDF3E6;
  --wf-danger:#B91C1C; --wf-danger-tint:#FCEDED;
  --wf-shadow:0 1px 2px rgba(16,24,40,.05),0 2px 6px rgba(16,24,40,.05);
  --wf-shadow-hover:0 2px 4px rgba(16,24,40,.06),0 10px 24px rgba(16,24,40,.09);
  --wf-shadow-lg:0 16px 44px rgba(16,24,40,.10);
  --wf-ease:cubic-bezier(.16,1,.3,1); --wf-radius:14px;
"""

# Palette sombre (variante non branchée par défaut, gardée cohérente)
_DARK_VARS = """
  --wf-bg:#0D1013; --wf-surface:#14181C; --wf-surface2:#1B2127; --wf-border:#262D34; --wf-border-strong:#3A434C;
  --wf-text:#EAECEE; --wf-muted:#A3AEB6; --wf-placeholder:#A3AEB6; --wf-grid:#20272E; --wf-control:#7D8894;
  --wf-accent:#5B7CFA; --wf-accent-strong:#93A8FF; --wf-accent-tint:rgba(91,124,250,.16); --wf-on-accent:#0A1236;
  --wf-navy:#172982; --wf-navy-deep:#101D5E; --wf-accent-vif:#7B91FF; --wf-focus:#93A8FF;
  --wf-orange:#F98F03; --wf-orange-text:#F5B042;
  --wf-success:#34D399; --wf-success-tint:rgba(52,211,153,.15);
  --wf-warn:#F5B042; --wf-warn-tint:rgba(245,176,66,.15);
  --wf-danger:#F87171; --wf-danger-tint:rgba(248,113,113,.15);
  --wf-shadow:0 1px 2px rgba(0,0,0,.4);
  --wf-shadow-hover:0 2px 4px rgba(0,0,0,.4),0 10px 24px rgba(0,0,0,.45);
  --wf-shadow-lg:0 12px 40px rgba(0,0,0,.5);
  --wf-ease:cubic-bezier(.16,1,.3,1); --wf-radius:14px;
"""

# Sur la coque marine, les mêmes tokens prennent leur valeur « sur fond
# sombre » : chaque règle écrite avec var(--wf-…) devient lisible dans la
# barre latérale sans règle dédiée. Le blanc y joue le rôle de l'accent.
_VARS_SUR_SOMBRE = """
  --wf-text:#FFFFFF; --wf-muted:#C9CEE6; --wf-placeholder:#C9CEE6; --wf-control:#C9CEE6;
  --wf-surface:rgba(255,255,255,.06); --wf-surface2:rgba(255,255,255,.08);
  --wf-border:rgba(255,255,255,.18); --wf-border-strong:rgba(255,255,255,.32);
  --wf-accent:#FFFFFF; --wf-accent-strong:#FFFFFF; --wf-accent-tint:rgba(255,255,255,.14); --wf-on-accent:#172982;
  --wf-accent-vif:#FFFFFF; --wf-focus:#FFFFFF; --wf-orange-text:#FBC56B;
  --wf-success:#86EFAC; --wf-success-tint:rgba(134,239,172,.14);
  --wf-warn:#FCD34D; --wf-warn-tint:rgba(252,211,77,.14);
  --wf-danger:#FCA5A5; --wf-danger-tint:rgba(252,165,165,.16);
  --wf-shadow:none; --wf-shadow-hover:none;
"""

# Couleurs des graphiques : l'accent d'abord, puis des teintes de la même
# famille et l'orange du wordmark — jamais la palette par défaut de Plotly,
# dont le rouge vif se lit comme une alerte.
PALETTE_GRAPHIQUES = ["#172982", "#5B7CFA", "#F98F03", "#93A8FF", "#1F2F8F",
                      "#FBC56B", "#6B7280", "#C7D2FE"]

# Coloration du code (st.code, page Journal). Streamlit colore avec Prism et
# ses teintes par défaut passent sous 4.5:1 sur fond clair. Toutes celles-ci
# tiennent 4.5:1 sur FOND_CODE (vérifié par les tests).
FOND_CODE = "#FFFFFF"
COULEURS_CODE = {
    "comment": "#5B6472", "prolog": "#5B6472", "doctype": "#5B6472", "cdata": "#5B6472",
    "punctuation": "#3F4752", "operator": "#3F4752",
    "keyword": "#172982", "atrule": "#172982", "tag": "#172982", "property": "#172982",
    "builtin": "#1F2F8F", "class-name": "#1F2F8F", "function": "#3D5AFE",
    "string": "#15803D", "char": "#15803D", "attr-value": "#15803D", "selector": "#15803D",
    "inserted": "#15803D", "regex": "#15803D", "url": "#15803D",
    "number": "#B45F00", "boolean": "#B45F00", "symbol": "#B45F00", "attr-name": "#B45F00",
    "constant": "#B91C1C", "deleted": "#B91C1C", "important": "#B45309",
    "variable": "#14181C", "entity": "#14181C",
}


def declarer_langue_francaise() -> None:
    """Passe `<html lang>` en français.

    Streamlit sert la page en `lang="en"` et n'offre aucun réglage : un
    lecteur d'écran prononce alors tout le texte français avec des règles
    anglaises. Le script s'exécute dans la page (pas dans une iframe).
    """
    st.html("<script>document.documentElement.lang='fr';</script>",
            unsafe_allow_javascript=True)


def wordmark(size: float = 1.9, center: bool = True,
             sur_fond_sombre: bool = False) -> str:
    """Retourne le HTML du logo « We.Reach » (accents orange).

    `sur_fond_sombre=True` : lettres blanches, pour la coque marine.
    """
    align = "center" if center else "left"
    classes = "wf-wordmark wf-wordmark--sombre" if sur_fond_sombre else "wf-wordmark"
    return (
        f'<div class="{classes}" style="font-size:{size}rem;text-align:{align}">'
        f'We<span style="color:{WF_ORANGE}">.</span>R'
        f'<span style="color:{WF_ORANGE}">ea</span>ch</div>'
    )


def _css_code() -> str:
    """Teintes Prism lisibles, dans la zone principale seulement."""
    portee = '[data-testid="stMain"] [data-testid="stCode"]'
    regles = [
        f'{portee} pre {{ background:{FOND_CODE} !important; '
        'box-shadow:inset 0 0 0 1px var(--wf-border); border-radius:12px; }',
        f'{portee} code {{ color:var(--wf-text); }}',
    ]
    for jeton, couleur in COULEURS_CODE.items():
        regles.append(f'{portee} .token.{jeton} {{ color:{couleur} !important; '
                      'background:none !important; }')
    return "\n".join(regles)


# Gabarit CSS : chaîne brute (pas de f-string, les accolades restent
# lisibles). __VARS__, __SOMBRE__ et __CODE__ sont remplacés à l'injection.
_CSS = r"""
:root { __VARS__ }

html, body, [class*="css"], .stApp { font-family:'Inter',system-ui,sans-serif !important; -webkit-font-smoothing:antialiased; }
.stApp { background:var(--wf-bg) !important; color:var(--wf-text); }
.block-container { padding-top:2.2rem !important; padding-bottom:3rem !important; max-width:1240px; }
::selection { background:rgba(61,90,254,.20); }

/* Titres (DESIGN.md) : h1 1.75rem/800, h2 1.25rem/700, h3 1.05rem/700 */
h1,h2,h3 { color:var(--wf-text) !important; letter-spacing:-.02em; }
h1 { font-size:1.75rem !important; font-weight:800 !important; letter-spacing:-.025em; }
h2 { font-size:1.25rem !important; font-weight:700 !important; letter-spacing:-.015em; }
h3 { font-size:1.05rem !important; font-weight:700 !important; letter-spacing:-.01em; }
p, span, label, li, .stMarkdown { color:var(--wf-text); }
.stMarkdown [data-testid="stMarkdownContainer"] p, .stMarkdown [data-testid="stMarkdownContainer"] li { font-size:.95rem; }
header[data-testid="stHeader"] { background:transparent; height:0; }
#MainMenu, footer { visibility:hidden; }

/* Wordmark « We.Reach » */
.wf-wordmark { font-weight:800; letter-spacing:-.03em; color:var(--wf-text); margin:.2rem 0 1.6rem; }
.wf-wordmark--sombre { color:#FFFFFF !important; }

/* ---------- Coque : barre latérale marine ---------- */
section[data-testid="stSidebar"], .wf-sur-sombre { __SOMBRE__ }
section[data-testid="stSidebar"] {
  background:linear-gradient(180deg,#172982 0%,#172982 55%,#101D5E 100%) !important;
  border-right:none !important;
}
[data-testid="stSidebarContent"], [data-testid="stSidebarHeader"] { background:transparent !important; }
section[data-testid="stSidebar"] * { color:var(--wf-text); }
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] * { color:var(--wf-muted) !important; }
section[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] button,
section[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] svg { color:#FFFFFF !important; fill:currentColor; }
section[data-testid="stSidebar"] hr { border-color:var(--wf-border) !important; background:var(--wf-border) !important; }
section[data-testid="stSidebar"] [data-testid="stExpander"] details { border-color:var(--wf-border) !important; }
section[data-testid="stSidebar"] [data-testid="stExpander"] summary:hover { background:rgba(255,255,255,.06); }
section[data-testid="stSidebar"] [data-testid="stExpander"] summary svg { color:#FFFFFF; fill:currentColor; }
section[data-testid="stSidebar"] [data-testid="stCode"] pre { background:rgba(0,0,0,.20) !important; }
section[data-testid="stSidebar"] [data-testid="stCode"] code,
section[data-testid="stSidebar"] [data-testid="stCode"] .token { color:#E6E9F5 !important; }
section[data-testid="stSidebar"] [data-testid="stAlert"] > div { background:rgba(255,255,255,.10) !important; }
/* Boutons primaires de la barre : blancs à texte marine, sans règle dédiée —
   --wf-accent y vaut #FFFFFF et --wf-on-accent la marine. */

/* Menu : items transparents, survol voilé, item actif en pilule blanche
   translucide. Portée : le conteneur `nav_menu` seulement (Streamlit pose
   `st-key-<clé>` sur le conteneur d'un widget doté d'une clé). */
.st-key-nav_menu { gap:2px !important; }
/* Les libellés étaient centrés : Streamlit intercale un div interne qui
   recentre, il faut aligner le bouton ET ce div. */
section[data-testid="stSidebar"] .st-key-nav_menu .stButton > button {
  justify-content:flex-start !important; border:none !important; background:transparent !important;
  box-shadow:none !important; transform:none !important;
  font-weight:500 !important; border-radius:10px !important; padding:9px 12px !important;
  color:rgba(255,255,255,.86) !important;
}
section[data-testid="stSidebar"] .st-key-nav_menu .stButton > button * { color:inherit !important; }
section[data-testid="stSidebar"] .st-key-nav_menu .stButton > button > div { justify-content:flex-start !important; width:100% !important; }
section[data-testid="stSidebar"] .st-key-nav_menu .stButton > button:hover { background:rgba(255,255,255,.08) !important; color:#FFFFFF !important; }
/* Item actif : le fond va sur le BOUTON SEUL (deux couches translucides
   dessinaient un rectangle autour du texte). */
section[data-testid="stSidebar"] .st-key-nav_menu .stButton > button[kind="primary"] { background:rgba(255,255,255,.14) !important; }
section[data-testid="stSidebar"] .st-key-nav_menu .stButton > button[kind="primary"],
section[data-testid="stSidebar"] .st-key-nav_menu .stButton > button[kind="primary"] * { color:#FFFFFF !important; font-weight:700 !important; }

/* ---------- Boutons ---------- */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {
  font-family:'Inter' !important; font-weight:600; font-size:.875rem; border-radius:10px; padding:.55rem 1.1rem;
  transition:transform .15s var(--wf-ease), box-shadow .15s var(--wf-ease), background-color .15s, border-color .15s, color .15s;
}
.stButton > button[kind="secondary"], .stDownloadButton > button[kind="secondary"], .stFormSubmitButton > button[kind="secondary"] {
  border:1px solid var(--wf-border); background:var(--wf-surface); color:var(--wf-text);
}
.stButton > button[kind="secondary"]:hover, .stDownloadButton > button[kind="secondary"]:hover, .stFormSubmitButton > button[kind="secondary"]:hover {
  border-color:var(--wf-accent); color:var(--wf-accent-strong); transform:translateY(-2px); box-shadow:var(--wf-shadow-hover);
}
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {
  background:var(--wf-accent) !important; color:var(--wf-on-accent) !important; border:none !important; font-weight:700;
  box-shadow:0 1px 2px rgba(23,41,130,.30);
}
.stButton > button[kind="primary"]:hover, .stDownloadButton > button[kind="primary"]:hover, .stFormSubmitButton > button[kind="primary"]:hover {
  background:var(--wf-accent-strong) !important; transform:translateY(-2px); box-shadow:0 8px 20px rgba(23,41,130,.28);
}
.stButton > button:active, .stDownloadButton > button:active, .stFormSubmitButton > button:active { transform:translateY(0); }
.stButton > button:disabled, .stDownloadButton > button:disabled, .stFormSubmitButton > button:disabled { transform:none !important; box-shadow:none !important; }
/* Le texte interne hérite de la couleur du bouton — sinon la règle globale
   'span/p {color:var(--wf-text)}' rend le libellé illisible sur le bleu. */
.stButton > button *, .stDownloadButton > button *, .stFormSubmitButton > button * { color:inherit !important; }
.stButton > button[kind="primary"] *, .stFormSubmitButton > button[kind="primary"] * { color:var(--wf-on-accent) !important; }
/* Désactivé : il doit se lire comme indisponible. Le bleu plein d'un bouton
   principal désactivé passait pour cliquable (critique du 2026-10-18). */
.stButton > button:disabled, .stDownloadButton > button:disabled, .stFormSubmitButton > button:disabled,
.stButton > button:disabled *, .stDownloadButton > button:disabled *, .stFormSubmitButton > button:disabled * {
  background:var(--wf-surface2) !important; color:var(--wf-muted) !important; cursor:not-allowed;
}
.stButton > button:disabled, .stDownloadButton > button:disabled, .stFormSubmitButton > button:disabled {
  border:1px dashed var(--wf-border-strong) !important; opacity:1 !important;
}

/* ---------- Focus clavier visible ---------- */
/* Filet de sécurité : tout bouton (copie du code, repli de la barre…) */
button:focus-visible, summary:focus-visible, [data-testid="stCode"] :focus-visible { outline:2px solid var(--wf-focus) !important; outline-offset:2px; }
.stButton > button:focus-visible, .stDownloadButton > button:focus-visible, .stFormSubmitButton > button:focus-visible,
[data-testid="stPills"] button:focus-visible, [data-testid="stButtonGroup"] button:focus-visible,
.stTabs [data-baseweb="tab"]:focus-visible, [data-testid="stExpander"] summary:focus-visible,
[data-testid="stLinkButton"] a:focus-visible, a:focus-visible {
  outline:2px solid var(--wf-focus) !important; outline-offset:2px !important;
}
section[data-testid="stSidebar"] .st-key-nav_menu .stButton > button:focus-visible { outline:2px solid #FFFFFF !important; outline-offset:2px !important; }
.stTextInput input:focus-visible, .stNumberInput input:focus-visible, .stTextArea textarea:focus-visible,
[data-baseweb="select"] input:focus-visible { outline:none; }
[data-baseweb="input"]:focus-within, [data-baseweb="textarea"]:focus-within, [data-baseweb="select"] > div:focus-within {
  outline:2px solid var(--wf-focus) !important; outline-offset:1px; border-radius:11px;
}
[data-baseweb="checkbox"]:has(input:focus-visible), [data-baseweb="radio"]:has(input:focus-visible) {
  outline:2px solid var(--wf-focus); outline-offset:2px; border-radius:6px;
}

/* ---------- Métriques : une seule élévation ---------- */
[data-testid="stMetric"] {
  background:var(--wf-surface); border:none; border-radius:var(--wf-radius); padding:16px 18px; box-shadow:var(--wf-shadow);
  transition:transform .15s var(--wf-ease), box-shadow .15s var(--wf-ease);
}
[data-testid="stMetric"]:hover { transform:translateY(-2px); box-shadow:var(--wf-shadow-hover); }
[data-testid="stMetricLabel"] { color:var(--wf-muted) !important; font-weight:600; font-size:.8rem; }
[data-testid="stMetricValue"] { color:var(--wf-text) !important; font-weight:800; letter-spacing:-.02em; font-variant-numeric:tabular-nums; }
[data-testid="stMetricDelta"] { font-weight:600; font-variant-numeric:tabular-nums; }
[data-testid="stMetricValue"] * { font-size:inherit !important; font-weight:inherit !important; color:inherit !important; letter-spacing:inherit; }

/* ---------- Champs ---------- */
.stTextInput input, .stNumberInput input, .stTextArea textarea, [data-baseweb="select"] > div {
  background:var(--wf-surface2) !important; border:1px solid var(--wf-border) !important; border-radius:11px !important;
  color:var(--wf-text) !important; font-size:.9rem; caret-color:var(--wf-accent-vif); }
.stTextInput input:focus, .stNumberInput input:focus, .stTextArea textarea:focus { border-color:var(--wf-accent) !important; }
.stTextInput input::placeholder, .stTextArea textarea::placeholder, .stNumberInput input::placeholder {
  color:var(--wf-placeholder) !important; opacity:1 !important; -webkit-text-fill-color:var(--wf-placeholder) !important; }
[data-baseweb="select"] [data-baseweb="select"] div[aria-hidden], [data-baseweb="select"] div[class*="placeholder"] { color:var(--wf-placeholder) !important; }
label, .stSelectbox label, .stCheckbox label { color:var(--wf-muted) !important; font-weight:600 !important; font-size:.8rem; }
/* Libellés des champs : 0.82rem/600, couleur du texte (la règle `p` du corps ne doit pas les grossir). */
[data-testid="stWidgetLabel"] p { font-size:.82rem !important; font-weight:600 !important; color:var(--wf-text) !important; }
[data-baseweb="checkbox"] span[aria-checked="true"] { background:var(--wf-accent) !important; border-color:var(--wf-accent) !important; }
[data-baseweb="toggle"] div[aria-checked="true"] { background:var(--wf-accent) !important; }
/* Cases et interrupteurs éteints : contour à 3:1 (ils se perdaient sur le fond). */
[data-testid="stCheckbox"] label[data-baseweb="checkbox"]:has(input[aria-checked="false"]) > span:first-child { border-color:var(--wf-control) !important; }
[data-testid="stCheckbox"] label[data-baseweb="checkbox"]:has(input[aria-checked="false"]) > div:first-child { background:var(--wf-control) !important; }
/* Champ numérique : un seul cadre autour du nombre et des boutons − + */
[data-testid="stNumberInputContainer"] { background:var(--wf-surface2) !important; border:1px solid var(--wf-border) !important; border-radius:11px !important; overflow:hidden; }
[data-testid="stNumberInputContainer"] input { border:none !important; border-radius:0 !important; }
[data-testid="stNumberInputContainer"] [data-baseweb="input"] { border:none !important; background:transparent !important; }
[data-testid="stNumberInputContainer"] button { background:transparent !important; color:var(--wf-text) !important; }
[data-testid="stNumberInputContainer"] button:hover { background:var(--wf-accent-tint) !important; }
[data-testid="stNumberInputContainer"]:focus-within { outline:2px solid var(--wf-focus) !important; outline-offset:1px; }
[data-testid="stNumberInputContainer"] [data-baseweb="input"]:focus-within { outline:none !important; }

/* ---------- Onglets ---------- */
.stTabs [data-baseweb="tab-list"] { gap:26px; border-bottom:1px solid var(--wf-border); }
.stTabs [data-baseweb="tab"] { font-family:'Inter'; font-weight:600; font-size:.9rem; color:var(--wf-muted); padding:0 0 12px; background:transparent; border-radius:6px 6px 0 0; transition:color .15s; }
.stTabs [data-baseweb="tab"] p { color:inherit !important; font-size:.9rem !important; }
.stTabs [data-baseweb="tab"]:hover { color:var(--wf-text); }
.stTabs [aria-selected="true"] { color:var(--wf-text) !important; }
.stTabs [data-baseweb="tab-highlight"] { background:var(--wf-accent) !important; height:2px; }

/* ---------- Tableaux, volets, alertes : une seule élévation (bordure) ---------- */
[data-testid="stDataFrame"], [data-testid="stDataEditor"] { border:1px solid var(--wf-border) !important; border-radius:var(--wf-radius); overflow:hidden; font-variant-numeric:tabular-nums; }
[data-testid="stExpander"] details { border:1px solid var(--wf-border) !important; border-radius:var(--wf-radius) !important; background:var(--wf-surface); }
[data-testid="stAlert"] { border-radius:12px; }
code, pre, [data-testid="stCode"] { font-family:'JetBrains Mono',monospace !important; font-size:.82rem; }
__CODE__

/* Puces « École ciblée » (st.pills) — plus d'air + alignement soigné */
[data-testid="stPills"] { margin-top:4px; }
[data-testid="stPills"] [role="group"],
[data-testid="stButtonGroup"] > div,
[data-testid="stButtonGroup"] {
  display:flex !important; flex-wrap:wrap !important;
  gap:10px 10px !important; row-gap:12px !important; align-items:center;
}
[data-testid="stPills"] button,
[data-testid="stButtonGroup"] button {
  border-radius:20px !important; padding:7px 16px !important; margin:0 !important;
  line-height:1.2; font-weight:600 !important; white-space:nowrap;
}

/* Chips du multiselect : sans ça le libellé héritait de la règle globale
   `span {color:var(--wf-text)}` et devenait illisible sur le fond accent.
   Le libellé n'est plus tronqué : la pilule s'adapte au texte. */
[data-testid="stMultiSelect"] [data-baseweb="select"] > div { flex-wrap:wrap !important; height:auto !important; }
[data-baseweb="tag"] {
  background:var(--wf-accent-tint) !important; border:1px solid var(--wf-accent) !important;
  border-radius:20px !important; max-width:none !important; height:auto !important;
  padding:3px 6px 3px 10px !important; margin:3px 4px 3px 0 !important;
}
[data-baseweb="tag"], [data-baseweb="tag"] * { color:var(--wf-accent-strong) !important; }
[data-baseweb="tag"] svg { fill:currentColor !important; }
[data-baseweb="tag"] span {
  max-width:none !important; overflow:visible !important; text-overflow:clip !important;
  white-space:normal !important; font-size:.8rem; font-weight:600;
}

/* Badge utilitaire (ancien, conservé) */
.wf-badge { display:inline-flex; align-items:center; gap:5px; font-size:.72rem; font-weight:600; padding:3px 10px; border-radius:20px; }
.wf-badge.ok { color:var(--wf-success); background:var(--wf-success-tint); }
.wf-badge.wait { color:var(--wf-warn); background:var(--wf-warn-tint); }
.wf-badge.no { color:var(--wf-danger); background:var(--wf-danger-tint); }
.wf-badge.accent { color:var(--wf-accent-strong); background:var(--wf-accent-tint); }

/* ---------- Composants (ui/composants.py) ---------- */
.wf-sr { position:absolute !important; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }

/* Bandeau de contexte sous le titre de page */
.wf-bandeau { display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:10px 20px; margin:-.35rem 0 .9rem; }
.wf-bandeau__texte { margin:0; color:var(--wf-muted); font-size:.95rem; line-height:1.5; max-width:68ch; }
.wf-bandeau__puces { display:flex; flex-wrap:wrap; gap:8px; }

/* Puce d'état */
.wf-puce { display:inline-flex; align-items:center; gap:7px; font-size:.78rem; font-weight:600; line-height:1; padding:6px 11px; border-radius:999px; white-space:nowrap; font-variant-numeric:tabular-nums; color:var(--wf-muted); background:var(--wf-surface); box-shadow:inset 0 0 0 1px var(--wf-border); }
.wf-puce * { color:inherit; }
.wf-puce--ok { color:var(--wf-success); background:var(--wf-success-tint); box-shadow:none; }
.wf-puce--attention { color:var(--wf-warn); background:var(--wf-warn-tint); box-shadow:none; }
.wf-puce--danger { color:var(--wf-danger); background:var(--wf-danger-tint); box-shadow:none; }
.wf-puce--accent { color:var(--wf-accent-strong); background:var(--wf-accent-tint); box-shadow:none; }
.wf-puce__point { width:7px; height:7px; border-radius:50%; background:currentColor; flex:none; }

/* Point « en direct » */
.wf-direct { position:relative; display:inline-block; width:8px; height:8px; border-radius:50%; background:var(--wf-success); flex:none; }
.wf-puce .wf-direct { background:currentColor; width:7px; height:7px; }
.wf-direct::after { content:""; position:absolute; inset:0; border-radius:50%; background:inherit; animation:wf-pouls 1.8s var(--wf-ease) infinite; }
@keyframes wf-pouls { 0% { transform:scale(1); opacity:.6; } 100% { transform:scale(2.8); opacity:0; } }

/* Jauge du budget : le geste signature */
.wf-jauge { --wf-j-reste:var(--wf-accent-vif); --wf-j-utilise:var(--wf-orange); display:grid; gap:8px; padding:14px 16px 16px; border-radius:var(--wf-radius); background:var(--wf-surface); box-shadow:var(--wf-shadow); margin-bottom:.5rem; }
.wf-jauge * { color:inherit; }
.wf-jauge--sombre { --wf-j-reste:#FFFFFF; background:rgba(255,255,255,.07); box-shadow:none; }
.wf-jauge__tete { display:flex; flex-wrap:wrap; justify-content:space-between; align-items:baseline; gap:2px 8px; font-size:.78rem; font-weight:600; color:var(--wf-muted); font-variant-numeric:tabular-nums; }
.wf-jauge__libelle { color:var(--wf-text); font-weight:700; white-space:nowrap; }
.wf-jauge__compte { white-space:nowrap; }
.wf-jauge__compte { color:var(--wf-muted); }
.wf-jauge__valeur { color:var(--wf-text); font-size:.9rem; font-weight:600; line-height:1.15; }
.wf-jauge__nombre { font-size:1.65rem; font-weight:800; letter-spacing:-.02em; font-variant-numeric:tabular-nums; margin-right:2px; }
.wf-jauge--attention .wf-jauge__valeur { color:var(--wf-warn); }
.wf-jauge--danger .wf-jauge__valeur { color:var(--wf-danger); }
.wf-jauge__crans { display:grid; grid-template-columns:repeat(var(--wf-crans,20),minmax(0,1fr)); gap:3px; height:14px; }
.wf-cran { display:block; border-radius:3px; background:var(--wf-j-reste); transform-origin:50% 100%; animation:wf-cran .42s var(--wf-ease) backwards; animation-delay:calc(var(--i,0) * 18ms); }
.wf-cran--utilise { background:var(--wf-j-utilise); }
.wf-jauge__note { font-size:.8rem; font-weight:600; color:var(--wf-danger); }
@keyframes wf-cran { from { transform:scaleY(.15); opacity:.25; } }

/* Entonnoir du parcours */
ol.wf-entonnoir { list-style:none !important; margin:0 0 1rem !important; padding:16px 4px !important; display:grid !important; width:100%; grid-template-columns:repeat(var(--wf-etapes,4),minmax(0,1fr)); background:var(--wf-surface); border-radius:var(--wf-radius); box-shadow:var(--wf-shadow); }
.wf-entonnoir__etape { margin:0 !important; padding:0 16px !important; display:grid !important; list-style:none !important; gap:6px; align-content:start; min-width:0; }
.wf-entonnoir__etape + .wf-entonnoir__etape { border-left:1px solid var(--wf-border); }
.wf-entonnoir__tete { display:flex; justify-content:space-between; align-items:baseline; gap:8px; }
.wf-entonnoir__libelle { font-size:.8rem; font-weight:600; color:var(--wf-muted); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.wf-entonnoir__taux { font-size:.75rem; font-weight:700; color:var(--wf-accent-strong); font-variant-numeric:tabular-nums; white-space:nowrap; }
.wf-entonnoir__taux--vide { color:var(--wf-muted); }
.wf-entonnoir__nombre { font-size:1.6rem; font-weight:800; letter-spacing:-.02em; color:var(--wf-text); font-variant-numeric:tabular-nums; line-height:1.1; }
.wf-entonnoir__barre { height:6px; border-radius:3px; background:var(--wf-grid); overflow:hidden; }
.wf-entonnoir__barre > span { display:block; height:100%; border-radius:3px; background:var(--wf-accent-vif); transform-origin:0 50%; animation:wf-barre .5s var(--wf-ease) backwards; animation-delay:calc(var(--i,0) * 60ms); }
.wf-entonnoir__etape:last-child .wf-entonnoir__barre > span { background:var(--wf-orange); }
@keyframes wf-barre { from { transform:scaleX(0); } }
@media (max-width: 720px) {
  ol.wf-entonnoir { grid-template-columns:1fr !important; gap:14px; }
  .wf-entonnoir__etape + .wf-entonnoir__etape { border-left:none; }
}

/* Carte « À faire » */
.wf-action { display:flex; align-items:center; gap:14px; padding:12px 16px; border-radius:var(--wf-radius); background:var(--wf-surface); box-shadow:var(--wf-shadow); margin-bottom:8px; transition:transform .15s var(--wf-ease), box-shadow .15s var(--wf-ease); }
.wf-action:hover { transform:translateY(-2px); box-shadow:var(--wf-shadow-hover); }
.wf-action__icone { width:34px; height:34px; flex:none; display:grid; place-items:center; border-radius:10px; color:var(--wf-muted); background:var(--wf-surface2); }
.wf-action__icone svg { width:18px; height:18px; }
.wf-action--ok .wf-action__icone { color:var(--wf-success); background:var(--wf-success-tint); }
.wf-action--attention .wf-action__icone { color:var(--wf-warn); background:var(--wf-warn-tint); }
.wf-action--danger .wf-action__icone { color:var(--wf-danger); background:var(--wf-danger-tint); }
.wf-action--accent .wf-action__icone { color:var(--wf-accent); background:var(--wf-accent-tint); }
.wf-action__corps { min-width:0; }
.wf-action__titre { font-weight:700; font-size:.92rem; color:var(--wf-text); }
.wf-action__detail { font-size:.84rem; color:var(--wf-muted); margin-top:2px; }

/* État vide qui explique */
.wf-vide { display:flex; gap:14px; align-items:flex-start; padding:20px 22px; border-radius:var(--wf-radius); border:1px dashed var(--wf-border-strong); background:transparent; margin-bottom:1rem; }
.wf-vide__icone { width:36px; height:36px; flex:none; display:grid; place-items:center; border-radius:10px; color:var(--wf-accent); background:var(--wf-accent-tint); }
.wf-vide__icone svg { width:18px; height:18px; }
.wf-vide__titre { font-weight:700; font-size:.98rem; color:var(--wf-text); }
.wf-vide__texte { margin:.25rem 0 0; font-size:.9rem; color:var(--wf-muted); line-height:1.5; max-width:65ch; }

/* ---------- Mouvement ---------- */
/* Entrée du contenu de page : fondu + montée de 8px, une fois par montage.
   `backwards` et non `both` : après l'animation, l'élément revient à ses
   styles normaux, et le voile « périmé » de Streamlit pendant un rerun
   (opacité réduite) continue de s'appliquer. Sans animation, rien n'est
   caché : l'état par défaut est visible. */
@keyframes wf-entree { from { opacity:0; transform:translateY(8px); } }
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] > * { animation:wf-entree .22s var(--wf-ease) backwards; }
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] > :nth-child(2) { animation-delay:40ms; }
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] > :nth-child(3) { animation-delay:80ms; }
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] > :nth-child(4) { animation-delay:120ms; }
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] > :nth-child(5) { animation-delay:160ms; }
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] > :nth-child(6) { animation-delay:200ms; }
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] > :nth-child(7) { animation-delay:240ms; }
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] > :nth-child(n+8) { animation-delay:280ms; }
/* Cartes de métriques côte à côte : décalage de 40ms de colonne en colonne */
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] [data-testid="stMetric"] { animation:wf-entree .22s var(--wf-ease) backwards; }
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(2) [data-testid="stMetric"] { animation-delay:40ms; }
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(3) [data-testid="stMetric"] { animation-delay:80ms; }
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(4) [data-testid="stMetric"] { animation-delay:120ms; }
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(n+5) [data-testid="stMetric"] { animation-delay:160ms; }

/* Mouvement réduit : ni translation, ni pulsation, ni remplissage animé. */
@media (prefers-reduced-motion: reduce) {
  [data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] > *,
  [data-testid="stMetric"], .wf-cran, .wf-entonnoir__barre > span, .wf-direct::after { animation:none !important; }
  .wf-direct::after { display:none; }
  .stButton > button, .stDownloadButton > button, .stFormSubmitButton > button,
  [data-testid="stMetric"], .wf-action { transition:background-color .15s, border-color .15s, color .15s !important; }
  .stButton > button:hover, .stDownloadButton > button:hover, .stFormSubmitButton > button:hover,
  [data-testid="stMetric"]:hover, .wf-action:hover { transform:none !important; }
}
"""


def theme_css(dark: bool = False) -> str:
    """Retourne la feuille de style complète (sans la balise <style>)."""
    variables = _DARK_VARS if dark else _LIGHT_VARS
    return (_FONTS + "\n" + _CSS
            .replace("__VARS__", variables)
            .replace("__SOMBRE__", _VARS_SUR_SOMBRE)
            .replace("__CODE__", _css_code()))


def inject_theme(dark: bool = False) -> None:
    """Injecte le thème We.Reach (clair par défaut)."""
    st.markdown(f"<style>\n{theme_css(dark)}\n</style>", unsafe_allow_html=True)
