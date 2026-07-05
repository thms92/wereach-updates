# -*- coding: utf-8 -*-
"""Thème visuel WeFiiT Reach — CSS injecté dans Streamlit.

Usage :
    from wefiit_theme import inject_theme
    inject_theme()            # thème clair (défaut)
    inject_theme(dark=True)   # thème sombre
"""
import streamlit as st

_FONTS = "@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');"

_LIGHT_VARS = """
  --wf-bg:#FBFBFA; --wf-surface:#FFFFFF; --wf-surface2:#F5F6F7; --wf-border:#E7E9EC;
  --wf-text:#14181C; --wf-muted:#6B7280;
  --wf-accent:#172982; --wf-accent-strong:#1F2F8F; --wf-accent-tint:#E8EAF5; --wf-on-accent:#FFFFFF;
  --wf-success:#16A34A; --wf-warn:#D97706; --wf-danger:#DC2626;
  --wf-shadow:0 1px 2px rgba(16,24,40,.04),0 1px 3px rgba(16,24,40,.05);
"""

_DARK_VARS = """
  --wf-bg:#0D1013; --wf-surface:#14181C; --wf-surface2:#1B2026; --wf-border:#2A313A;
  --wf-text:#EAECEE; --wf-muted:#9AA4B2;
  --wf-accent:#5B7CFA; --wf-accent-strong:#7590FB; --wf-accent-tint:#1E2740; --wf-on-accent:#0D1013;
  --wf-success:#22C55E; --wf-warn:#F59E0B; --wf-danger:#EF4444;
  --wf-shadow:0 1px 2px rgba(0,0,0,.4),0 1px 3px rgba(0,0,0,.3);
"""


def inject_theme(dark: bool = False) -> None:
    """Injecte le thème WeFiiT Reach (clair par défaut)."""
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
header[data-testid="stHeader"] {{ background:transparent; height:0; }}
#MainMenu, footer {{ visibility:hidden; }}

/* Wordmark / header */
.main-header {{ font-size:1.9rem; font-weight:800; letter-spacing:-.02em; color:var(--wf-text); text-align:center; margin:.2rem 0 1.6rem; }}
.main-header .dot {{ color:var(--wf-accent); }}

/* Sidebar */
section[data-testid="stSidebar"] {{ background:var(--wf-surface) !important; border-right:1px solid var(--wf-border); }}
section[data-testid="stSidebar"] * {{ color:var(--wf-text); }}

/* Boutons */
.stButton > button {{ font-family:'Inter' !important; font-weight:600; font-size:.85rem; border-radius:11px; padding:.55rem 1.1rem; border:1px solid var(--wf-border); background:var(--wf-surface2); color:var(--wf-text); transition:filter .12s,background .12s,border-color .12s; }}
.stButton > button:hover {{ border-color:var(--wf-accent); color:var(--wf-accent-strong); }}
.stButton > button[kind="primary"] {{ background:var(--wf-accent) !important; color:var(--wf-on-accent) !important; border:none !important; font-weight:700; box-shadow:0 1px 2px rgba(23,41,130,.35); }}
.stButton > button[kind="primary"]:hover {{ filter:brightness(1.06); color:var(--wf-on-accent) !important; }}
.stDownloadButton > button {{ border-radius:11px; }}

/* Metrics (KPI) */
[data-testid="stMetric"] {{ background:var(--wf-surface); border:1px solid var(--wf-border); border-radius:16px; padding:16px 18px; box-shadow:var(--wf-shadow); }}
[data-testid="stMetricLabel"] {{ color:var(--wf-muted) !important; font-weight:600; font-size:.78rem; }}
[data-testid="stMetricValue"] {{ color:var(--wf-text) !important; font-weight:800; letter-spacing:-.02em; }}

/* Inputs & selects */
.stTextInput input, .stNumberInput input, .stTextArea textarea, [data-baseweb="select"] > div {{
  background:var(--wf-surface2) !important; border:1px solid var(--wf-border) !important; border-radius:11px !important; color:var(--wf-text) !important; font-size:.9rem; }}
.stTextInput input:focus, .stNumberInput input:focus {{ border-color:var(--wf-accent) !important; box-shadow:0 0 0 3px var(--wf-accent-tint) !important; }}
label, .stSelectbox label {{ color:var(--wf-muted) !important; font-weight:600 !important; font-size:.78rem; }}
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

/* Alertes & code */
[data-testid="stAlert"] {{ border-radius:12px; border:1px solid var(--wf-border); box-shadow:var(--wf-shadow); }}
code, pre, [data-testid="stCode"] {{ font-family:'JetBrains Mono',monospace !important; font-size:.82rem; }}
</style>
""",
        unsafe_allow_html=True,
    )
