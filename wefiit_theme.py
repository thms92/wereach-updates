# -*- coding: utf-8 -*-
"""Thème visuel We.Reach — CSS injecté dans Streamlit.

Tokens repris à l'identique de la maquette Claude Design (clair + sombre).

Usage :
    from wefiit_theme import inject_theme, wordmark
    inject_theme()                       # thème clair (défaut)
    inject_theme(dark=True)              # thème sombre
    st.markdown(wordmark(), unsafe_allow_html=True)   # logo « We.Reach »
"""
import streamlit as st

_FONTS = "@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');"

# Orange des accents du wordmark (identique clair/sombre)
WF_ORANGE = "#F98F03"

# Palette claire (tokens exacts de la maquette)
_LIGHT_VARS = """
  --wf-bg:#FBFBFA; --wf-surface:#FFFFFF; --wf-surface2:#F5F6F7; --wf-border:#E7E9EC;
  --wf-text:#14181C; --wf-muted:#6B7280; --wf-grid:#EEF0F2;
  --wf-accent:#172982; --wf-accent-strong:#1F2F8F; --wf-accent-tint:rgba(23,41,130,.10); --wf-on-accent:#FFFFFF;
  --wf-orange:#F98F03;
  --wf-success:#16A34A; --wf-success-tint:#E7F6EC;
  --wf-warn:#D97706; --wf-warn-tint:#FBF0DF;
  --wf-danger:#DC2626; --wf-danger-tint:#FBEAEA;
  --wf-shadow:0 1px 2px rgba(16,24,40,.04),0 1px 3px rgba(16,24,40,.05);
  --wf-shadow-lg:0 16px 44px rgba(16,24,40,.10);
"""

# Palette sombre (tokens exacts de la maquette)
_DARK_VARS = """
  --wf-bg:#0D1013; --wf-surface:#14181C; --wf-surface2:#1B2127; --wf-border:#262D34;
  --wf-text:#EAECEE; --wf-muted:#93A0A8; --wf-grid:#20272E;
  --wf-accent:#5B7CFA; --wf-accent-strong:#93A8FF; --wf-accent-tint:rgba(91,124,250,.16); --wf-on-accent:#0A1236;
  --wf-orange:#F98F03;
  --wf-success:#34D399; --wf-success-tint:rgba(52,211,153,.15);
  --wf-warn:#F5B042; --wf-warn-tint:rgba(245,176,66,.15);
  --wf-danger:#F87171; --wf-danger-tint:rgba(248,113,113,.15);
  --wf-shadow:0 1px 2px rgba(0,0,0,.4);
  --wf-shadow-lg:0 12px 40px rgba(0,0,0,.5);
"""


def wordmark(size: float = 1.9, center: bool = True) -> str:
    """Retourne le HTML du logo « We.Reach » (accents orange)."""
    align = "center" if center else "left"
    return (
        f'<div class="wf-wordmark" style="font-size:{size}rem;text-align:{align}">'
        f'We<span style="color:{WF_ORANGE}">.</span>R'
        f'<span style="color:{WF_ORANGE}">ea</span>ch</div>'
    )


def inject_theme(dark: bool = False) -> None:
    """Injecte le thème We.Reach (clair par défaut)."""
    variables = _DARK_VARS if dark else _LIGHT_VARS
    st.markdown(
        f"""
<style>
{_FONTS}

:root {{ {variables} }}

html, body, [class*="css"], .stApp {{ font-family:'Inter',system-ui,sans-serif !important; -webkit-font-smoothing:antialiased; }}
.stApp {{ background:var(--wf-bg) !important; color:var(--wf-text); }}
.block-container {{ padding-top:2.2rem !important; padding-bottom:3rem !important; max-width:1240px; }}
h1,h2,h3 {{ color:var(--wf-text) !important; letter-spacing:-.02em; font-weight:800 !important; }}
h1 {{ font-size:1.75rem !important; }}
p, span, label, li, .stMarkdown {{ color:var(--wf-text); }}
header[data-testid="stHeader"] {{ background:transparent; height:0; }}
#MainMenu, footer {{ visibility:hidden; }}

/* Wordmark « We.Reach » */
.wf-wordmark {{ font-weight:800; letter-spacing:-.03em; color:var(--wf-text); margin:.2rem 0 1.6rem; }}

/* Sidebar */
section[data-testid="stSidebar"] {{ background:var(--wf-surface) !important; border-right:1px solid var(--wf-border); }}
section[data-testid="stSidebar"] * {{ color:var(--wf-text); }}
section[data-testid="stSidebar"] [role="radiogroup"] label {{ border-radius:11px; padding:2px 6px; }}

/* Boutons */
.stButton > button {{ font-family:'Inter' !important; font-weight:600; font-size:.85rem; border-radius:11px; padding:.55rem 1.1rem; border:1px solid var(--wf-border); background:var(--wf-surface2); color:var(--wf-text); transition:filter .12s,background .12s,border-color .12s; }}
.stButton > button:hover {{ border-color:var(--wf-accent); color:var(--wf-accent-strong); }}
.stButton > button[kind="primary"] {{ background:var(--wf-accent) !important; color:var(--wf-on-accent) !important; border:none !important; font-weight:700; box-shadow:0 1px 2px rgba(23,41,130,.35); }}
.stButton > button[kind="primary"]:hover {{ filter:brightness(1.06); color:var(--wf-on-accent) !important; }}
.stDownloadButton > button {{ border-radius:11px; }}

/* Metrics (KPI) — cartes arrondies + ombre douce */
[data-testid="stMetric"] {{ background:var(--wf-surface); border:1px solid var(--wf-border); border-radius:16px; padding:16px 18px; box-shadow:var(--wf-shadow); }}
[data-testid="stMetricLabel"] {{ color:var(--wf-muted) !important; font-weight:600; font-size:.78rem; }}
[data-testid="stMetricValue"] {{ color:var(--wf-text) !important; font-weight:800; letter-spacing:-.02em; }}
[data-testid="stMetricDelta"] {{ font-weight:600; }}

/* Inputs & selects */
.stTextInput input, .stNumberInput input, .stTextArea textarea, [data-baseweb="select"] > div {{
  background:var(--wf-surface2) !important; border:1px solid var(--wf-border) !important; border-radius:11px !important; color:var(--wf-text) !important; font-size:.9rem; }}
.stTextInput input:focus, .stNumberInput input:focus, .stTextArea textarea:focus {{ border-color:var(--wf-accent) !important; box-shadow:0 0 0 3px var(--wf-accent-tint) !important; }}
.stTextInput input::placeholder, .stTextArea textarea::placeholder {{ color:var(--wf-muted); }}
label, .stSelectbox label, .stCheckbox label {{ color:var(--wf-muted) !important; font-weight:600 !important; font-size:.78rem; }}
[data-baseweb="checkbox"] span[aria-checked="true"] {{ background:var(--wf-accent) !important; border-color:var(--wf-accent) !important; }}
[data-baseweb="toggle"] div[aria-checked="true"] {{ background:var(--wf-accent) !important; }}

/* Onglets */
.stTabs [data-baseweb="tab-list"] {{ gap:26px; border-bottom:1px solid var(--wf-border); }}
.stTabs [data-baseweb="tab"] {{ font-family:'Inter'; font-weight:600; font-size:.9rem; color:var(--wf-muted); padding:0 0 12px; background:transparent; }}
.stTabs [aria-selected="true"] {{ color:var(--wf-text) !important; }}
.stTabs [data-baseweb="tab-highlight"] {{ background:var(--wf-accent) !important; height:2px; }}

/* Tableaux */
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {{ border:1px solid var(--wf-border) !important; border-radius:16px; overflow:hidden; box-shadow:var(--wf-shadow); }}
[data-testid="stDataFrame"] [role="columnheader"], [data-testid="stDataEditor"] [role="columnheader"] {{ background:var(--wf-surface2) !important; color:var(--wf-muted) !important; font-weight:600; font-size:.72rem; text-transform:uppercase; letter-spacing:.03em; }}

/* Expander (ex. Mon proxy) */
[data-testid="stExpander"] {{ border:1px solid var(--wf-border) !important; border-radius:14px !important; background:var(--wf-surface); box-shadow:var(--wf-shadow); }}

/* Alertes & code */
[data-testid="stAlert"] {{ border-radius:12px; border:1px solid var(--wf-border); box-shadow:var(--wf-shadow); }}
code, pre, [data-testid="stCode"] {{ font-family:'JetBrains Mono',monospace !important; font-size:.82rem; }}

/* Badge / pilule utilitaire (statuts) */
.wf-badge {{ display:inline-flex; align-items:center; gap:5px; font-size:.72rem; font-weight:600; padding:3px 10px; border-radius:20px; }}
.wf-badge.ok {{ color:var(--wf-success); background:var(--wf-success-tint); }}
.wf-badge.wait {{ color:var(--wf-warn); background:var(--wf-warn-tint); }}
.wf-badge.no {{ color:var(--wf-danger); background:var(--wf-danger-tint); }}
.wf-badge.accent {{ color:var(--wf-accent-strong); background:var(--wf-accent-tint); }}
</style>
""",
        unsafe_allow_html=True,
    )
