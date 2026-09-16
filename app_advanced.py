# -*- coding: utf-8 -*-
"""
LinkedIn Scraper Advanced - Interface Streamlit améliorée
Avec dashboard, statistiques, templates, et export Excel
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os

from scraper_v2_sync import LinkedInScraperV2Sync
from config import ScraperConfig, ECOLES, CONCURRENTS, SECTEURS
from utils.search_filters import parse_entreprises
from database import DatabaseManager
from cookie_utils import CookieManager
from export_utils import ExportManager
from queue_manager import QueueManager, JobStatus
from logger import logger
from utils.user_context import resolve_user_email, user_paths_for, DEFAULT_DEV_EMAIL
from utils.proxy_store import load_proxy, save_proxy
from utils.app_auth import verify_access, access_configured, email_domain_ok, ALLOWED_DOMAIN
from wefiit_theme import inject_theme, wordmark
from version import get_version


# Configuration Streamlit
st.set_page_config(
    page_title="We.Reach",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Thème We.Reach (fond clair uniquement)
inject_theme()

def current_user_email():
    try:
        headers = dict(st.context.headers)
    except Exception:
        headers = {}
    # 1) Identité via Cloudflare Access (en-tête), si un jour en place
    email = resolve_user_email(headers, None)
    if email and email != DEFAULT_DEV_EMAIL:
        return email
    # 2) Identité via le login applicatif
    if st.session_state.get("auth_email"):
        return st.session_state["auth_email"]
    # 3) Dev local : seulement si AUCUN mot de passe d'accès n'est configuré
    if not access_configured():
        return os.getenv("DEV_USER_EMAIL") or DEFAULT_DEV_EMAIL
    # 4) Sinon : non authentifié → écran de connexion
    return None


# Initialisation
_email = current_user_email()

# Écran de connexion (mode déployé : des comptes existent et aucune identité)
if _email is None:
    st.markdown(wordmark(size=2.4), unsafe_allow_html=True)
    _c1, _c2, _c3 = st.columns([1, 2, 1])
    with _c2:
        st.subheader("🔒 Connexion")
        with st.form("login_form"):
            _em = st.text_input("Email", placeholder=f"prenom.nom@{ALLOWED_DOMAIN}")
            _pw = st.text_input("Mot de passe", type="password")
            if st.form_submit_button("Se connecter", use_container_width=True):
                if not email_domain_ok(_em):
                    st.error(f"❌ Utilise ton adresse email @{ALLOWED_DOMAIN}.")
                elif verify_access(_em, _pw):
                    st.session_state.auth_email = _em.strip().lower()
                    st.rerun()
                else:
                    st.error("❌ Email ou mot de passe incorrect.")
        st.caption(f"Réservé aux membres @{ALLOWED_DOMAIN}.")
    st.stop()

if st.session_state.get('user_email') != _email:
    # Nouvel utilisateur (ou première visite) → (ré)initialiser tout le contexte
    paths = user_paths_for(_email)
    st.session_state.user_email = _email
    st.session_state.user_paths = paths
    st.session_state.db = DatabaseManager(db_file=str(paths.db_file))
    st.session_state.cookie_manager = CookieManager(config_dir=str(paths.config_dir))
    st.session_state.export_manager = ExportManager()
    st.session_state.queue_manager = QueueManager(queue_file=str(paths.queue_file))
    st.session_state.queue_manager.charger()
    cookie_saved = st.session_state.cookie_manager.load_cookie()
    st.session_state.global_cookie = cookie_saved or ""
    st.session_state.user_proxy = load_proxy(
        str(paths.proxy_file), str(paths.key_file)
    )

# Header
st.markdown(wordmark(), unsafe_allow_html=True)

# Sidebar Navigation
st.sidebar.title("🧭 Navigation")

if st.session_state.get("auth_email"):
    st.sidebar.caption(f"👤 {st.session_state['auth_email']}")
    if st.sidebar.button("🚪 Déconnexion"):
        del st.session_state["auth_email"]
        st.rerun()

# Source de vérité du menu. tests/test_navigation.py la confronte aux
# branches `if page == …` : toute page définie doit figurer ici.
PAGES = [
    "📊 Dashboard",
    "🔍 Recherche",
    "💾 Historique",
    "✉️ Messages",
    "📜 Logs",
]

# La page courante transite par session_state : le test de fumée peut la
# fixer sans piloter le widget, qui changera de nature en Tâche 7.
_page_memorisee = st.session_state.get("page")
_index_initial = PAGES.index(_page_memorisee) if _page_memorisee in PAGES else 0
page = st.sidebar.radio("Choisir une page", PAGES, index=_index_initial)
st.session_state["page"] = page

with st.sidebar.expander("🌐 Mon proxy (recommandé)"):
    paths = st.session_state.user_paths
    cur = st.session_state.get('user_proxy') or {}
    server = st.text_input("Serveur (http://host:port)", value=cur.get("server", ""))
    p_user = st.text_input("Login proxy", value=cur.get("username", ""))
    p_pass = st.text_input("Mot de passe proxy", type="password",
                           value=cur.get("password", ""))
    if st.button("💾 Enregistrer mon proxy"):
        if server.strip():
            proxy = {"server": server.strip(),
                     "username": p_user.strip(),
                     "password": p_pass}
            save_proxy(str(paths.proxy_file), str(paths.key_file), proxy)
            st.session_state.user_proxy = proxy
            st.success("Proxy enregistré ✅")
        else:
            st.warning("Indique au moins un serveur.")

st.sidebar.divider()
st.sidebar.caption(f"We.Reach v{get_version()}")

# ==============================================
# PAGE 1: DASHBOARD
# ==============================================
if page == "📊 Dashboard":
    st.header("📊 Tableau de bord")

    # Récupérer les statistiques
    stats = st.session_state.db.get_statistiques()

    # Métriques principales
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            label="Total Profils",
            value=stats.get('total_profils', 0),
            delta=None
        )

    with col2:
        st.metric(
            label="Total Invitations",
            value=stats.get('total_invitations', 0),
            delta=None
        )

    with col3:
        st.metric(
            label="Invitations Aujourd'hui",
            value=stats.get('invitations_aujourdhui', 0),
            delta=f"Limite: {ScraperConfig.MAX_INVITATIONS_PER_DAY}"
        )

    with col4:
        taux = 0
        if stats.get('total_profils', 0) > 0:
            taux = round((stats.get('total_invitations', 0) / stats.get('total_profils', 0)) * 100, 1)
        st.metric(
            label="Taux d'invitation",
            value=f"{taux}%"
        )

    st.markdown("---")

    # Graphiques
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📚 Profils par École")
        if stats.get('par_ecole'):
            df_ecole = pd.DataFrame(
                list(stats['par_ecole'].items()),
                columns=['École', 'Nombre']
            )
            fig = px.pie(
                df_ecole,
                values='Nombre',
                names='École',
                title='Répartition par école'
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Aucune donnée disponible")

    with col2:
        st.subheader("🕐 Dernière Recherche")
        if stats.get('derniere_recherche'):
            dr = stats['derniere_recherche']
            st.write(f"**Keyword:** {dr.get('keyword', 'N/A')}")
            st.write(f"**Date:** {dr.get('date', 'N/A')}")
            st.write(f"**Profils trouvés:** {dr.get('nb_profils', 0)}")
        else:
            st.info("Aucune recherche effectuée")

    # Alertes
    st.markdown("---")
    st.subheader("⚠️ Alertes & Limites")

    invitations_today = stats.get('invitations_aujourdhui', 0)
    max_invitations = ScraperConfig.MAX_INVITATIONS_PER_DAY

    if invitations_today >= max_invitations:
        st.error(f"🚫 Limite d'invitations atteinte ({invitations_today}/{max_invitations})")
    elif invitations_today >= max_invitations * 0.8:
        st.warning(f"⚠️ Proche de la limite ({invitations_today}/{max_invitations})")
    else:
        st.success(f"✅ Marge disponible ({invitations_today}/{max_invitations})")

# ==============================================
# PAGE 2: RECHERCHE
# ==============================================
elif page == "🔍 Recherche":
    st.header("🔍 Nouvelle Recherche")

    # Compteur file d'attente pour le label de l'onglet
    qm = st.session_state.queue_manager
    nb_en_attente = sum(1 for j in qm.jobs if j.status == JobStatus.EN_ATTENTE)
    queue_tab_label = f"🔄 File d'attente ({nb_en_attente})" if nb_en_attente > 0 else "🔄 File d'attente"

    # --- Bandeau session LinkedIn (partagé, façon maquette) ---
    _ck = st.session_state.global_cookie
    if st.session_state.get("cookie_editing") or not _ck:
        with st.container(border=True):
            st.markdown("**Cookie de session LinkedIn · li_at**")
            _cin, _cbtn = st.columns([4, 1])
            _new_ck = _cin.text_input(
                "li_at", value=_ck, type="password",
                label_visibility="collapsed",
                placeholder="Colle ici la valeur du cookie li_at…",
                key="cookie_shared",
            )
            _new_ck = (_new_ck or "").strip()
            if _cbtn.button("Enregistrer", type="primary", use_container_width=True):
                if _new_ck and st.session_state.cookie_manager.validate_cookie_format(_new_ck):
                    st.session_state.cookie_manager.save_cookie(_new_ck)
                    st.session_state.global_cookie = _new_ck
                    st.session_state.cookie_editing = False
                    st.rerun()
                else:
                    st.warning("⚠️ Format de cookie suspect ou vide.")
            st.caption("Conservé de façon sécurisée — nécessaire pour lancer les recherches.")
    else:
        _masked = f"{_ck[:6]}…{_ck[-4:]}" if len(_ck) > 12 else _ck
        _bl, _br = st.columns([5, 1])
        _bl.markdown(
            '<div style="display:flex;align-items:center;gap:11px;padding:13px 15px;'
            'background:var(--wf-surface);border:1px solid var(--wf-border);'
            'border-left:3px solid var(--wf-success);border-radius:13px;box-shadow:var(--wf-shadow)">'
            '<span style="width:9px;height:9px;flex:none;border-radius:50%;background:var(--wf-success)"></span>'
            '<div style="min-width:0"><div style="font-weight:600;font-size:.85rem;color:var(--wf-text)">Session LinkedIn active</div>'
            f'<div style="font-family:JetBrains Mono,monospace;font-size:.72rem;color:var(--wf-muted)">li_at · {_masked}</div></div></div>',
            unsafe_allow_html=True,
        )
        if _br.button("Modifier", use_container_width=True):
            st.session_state.cookie_editing = True
            st.rerun()

    with st.expander("❓ Comment récupérer mon cookie LinkedIn (li_at) ?"):
        st.markdown(
            "**Sur ordinateur, dans Chrome :**\n\n"
            "1. Connecte-toi sur **linkedin.com** (assure-toi d'être bien connecté).\n"
            "2. Appuie sur **F12** (ou clic droit → **Inspecter**) pour ouvrir les outils développeur.\n"
            "3. Va dans l'onglet **Application** (si tu ne le vois pas, clique sur les `»`).\n"
            "4. À gauche : **Cookies** → **https://www.linkedin.com**.\n"
            "5. Dans la liste, trouve la ligne nommée **`li_at`**.\n"
            "6. **Double-clique sur sa valeur** (longue suite de caractères) → copie-la (**Ctrl/Cmd + C**).\n"
            "7. Reviens ici, **colle** la valeur dans le champ ci-dessus → **Enregistrer**.\n\n"
            "⚠️ **Ne partage jamais ce cookie** : il donne accès à ton compte LinkedIn. "
            "S'il expire (déconnexion), refais l'opération pour en récupérer un nouveau."
        )

    st.write("")
    tab1, tab2, tab3 = st.tabs(
        ["👤 Candidats", "🏢 Clients/Entreprises", "🔗 Par URLs"]
    )

    # TAB 1: CANDIDATS
    with tab1:
        st.subheader("Recherche de candidats — écoles, entreprises et secteurs")

        col1, col2 = st.columns([1, 2])

        with col1:
            cookie = st.session_state.global_cookie
            keyword = st.text_input("Mots-clés", "", placeholder="Ex : Product Manager, PM Senior")
            entreprise_libre = st.text_input(
                "Entreprises (optionnel)", "",
                placeholder="Ex : Capgemini, Accenture",
                help="Plusieurs entreprises : sépare-les par des virgules.",
            )
            concurrents = st.multiselect(
                "🎯 Cabinets concurrents (optionnel)", CONCURRENTS,
                help="Chasse : cible les profils actuellement dans ces cabinets.",
            )
            # Cabinets et saisie libre se cumulent — LinkedIn les combine en OU.
            entreprises = parse_entreprises(entreprise_libre, concurrents)
            nb_profils = st.number_input("Nombre de profils", min_value=1, max_value=80, value=10)

            ile_de_france = st.toggle("🗼 Île-de-France uniquement", value=False, help="Filtre les résultats pour la région Île-de-France")

            inviter = st.toggle("Envoyer des invitations automatiquement", value=False)

            if inviter:
                reinviter_profils_scrapes = st.checkbox(
                    "Réinviter les profils déjà scrapés",
                    value=False,
                    help="Si coché, enverra des invitations même aux profils déjà présents dans votre historique"
                )

                message_personnalise = st.text_area(
                    "Message personnalisé (optionnel)",
                    placeholder="Ex: Bonjour, je serais ravi(e) de vous ajouter à mon réseau...",
                    max_chars=200,
                    help="Maximum 200 caractères. Laissez vide pour envoyer sans note."
                )
            else:
                reinviter_profils_scrapes = False
                message_personnalise = ""

        with col2:
            st.markdown("**🎓 Écoles ciblées** — optionnel, plusieurs possibles")
            ecole_noms = st.pills(
                "Écoles ciblées",
                list(ECOLES.keys()),
                selection_mode="multi",
                label_visibility="collapsed",
                key="ecoles_pills_candidat",
            )
            ecoles_selectionnees = [ECOLES[n] for n in (ecole_noms or [])]
            if ecoles_selectionnees:
                st.success(f"✅ {len(ecoles_selectionnees)} école(s) sélectionnée(s)")
            else:
                st.caption("Aucune école — tu peux filtrer par entreprise / cabinet / secteur à la place.")

            secteurs_noms = st.multiselect(
                "🏭 Secteurs d'activité (optionnel)",
                list(SECTEURS.keys()),
                help="Les secteurs se cumulent en OU, et se combinent en ET avec les écoles et entreprises.",
                key="secteurs_candidat",
            )
            secteurs_selectionnes = [SECTEURS[s] for s in secteurs_noms]

        st.markdown("---")

        col_btn1, col_btn2 = st.columns(2)

        with col_btn1:
            if st.button("🔍 Lancer le scraping", type="primary", use_container_width=True):
                if not cookie:
                    st.error("❌ Cookie manquant")
                elif not ecoles_selectionnees and not entreprises and not secteurs_selectionnes:
                    st.error("❌ Choisis au moins un filtre : une école, une entreprise / un cabinet, ou un secteur.")
                else:
                    with st.spinner("🚀 Scraping en cours..."):
                        scraper = LinkedInScraperV2Sync(use_database=True, proxy=st.session_state.get('user_proxy'), db_file=str(st.session_state.user_paths.db_file), profiles_csv=str(st.session_state.user_paths.profiles_csv), config_dir=str(st.session_state.user_paths.config_dir))

                        progress_bar = st.progress(0)
                        status_text = st.empty()

                        def update_progress(p):
                            progress_bar.progress(p)

                        def update_status(s):
                            status_text.text(s)

                        df = scraper.run_scraper(
                            cookie=cookie,
                            keyword=keyword,
                            entreprises=entreprises,
                            nb_profils=nb_profils,
                            ecoles_ids=ecoles_selectionnees,
                            secteurs_ids=secteurs_selectionnes,
                            inviter=inviter,
                            message_invitation=message_personnalise,
                            reinviter_profils_scrapes=reinviter_profils_scrapes,
                            ile_de_france=ile_de_france,
                            progress_callback=update_progress,
                            status_callback=update_status
                        )

                        if not df.empty:
                            st.success(f"✅ {len(df)} profils scrapés avec succès!")
                            st.dataframe(df, use_container_width=True)

                            # Export Excel
                            excel_data = st.session_state.export_manager.export_to_excel(df.to_dict('records'))
                            st.download_button(
                                label="📥 Télécharger Excel",
                                data=excel_data,
                                file_name=f"candidats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                        else:
                            st.warning("⚠️ Aucun profil trouvé")

                        if scraper.errors:
                            with st.expander("⚠️ Erreurs rencontrées"):
                                for err in scraper.errors:
                                    st.write(f"- {err}")

    # TAB 2: CLIENTS
    with tab2:
        st.subheader("Recherche clients/entreprises (sans filtre école)")

        cookie_client = st.session_state.global_cookie

        # Bouton de test de cookie (lance diagnostic_cookie.py en mode headless)
        col_test_a, col_test_b = st.columns([1, 2])
        with col_test_a:
            test_cookie_btn = st.button("🔍 Tester ce cookie", key="test_cookie_btn",
                                        help="Lance une vérification rapide pour confirmer que LinkedIn accepte le cookie")
        if test_cookie_btn:
            with st.spinner("Test du cookie en cours (10-20s)..."):
                import subprocess, sys as _sys
                try:
                    result = subprocess.run(
                        [_sys.executable, "diagnostic_cookie.py", "--headless"],
                        capture_output=True, text=True, timeout=60,
                    )
                    output = result.stdout + ("\n" + result.stderr if result.stderr else "")
                    if "✅ COOKIE VALIDE" in output:
                        st.success("✅ Cookie valide — LinkedIn accepte la session.")
                    elif "COOKIE INVALIDE" in output or "COOKIE EXPIRÉ" in output or "AUTHWALL" in output:
                        st.error("❌ Cookie expiré ou invalidé. Reconnectez-vous à LinkedIn et copiez un nouveau cookie li_at.")
                    elif "CHECKPOINT" in output:
                        st.warning("⚠️ Checkpoint LinkedIn — connectez-vous sur linkedin.com pour valider la vérification, puis recopiez le cookie.")
                    else:
                        st.warning("⚠️ Statut indéterminé — voir les détails ci-dessous.")
                    with st.expander("Détails du diagnostic"):
                        st.code(output[-3000:], language="text")
                except subprocess.TimeoutExpired:
                    st.error("⏱️ Le diagnostic a dépassé 60 secondes — réseau lent ou navigateur bloqué.")
                except Exception as e:
                    st.error(f"Erreur lors du diagnostic : {e}")

        keyword_client = st.text_input(
            "Mots-clés",
            "",
            placeholder='Ex : "Head of Data" OR CDO OR "Directeur Data"',
            key="keyword_client",
        )
        entreprise_client = st.text_input("Entreprise", "", key="entreprise_client")
        nb_client = st.number_input("Nombre de profils", min_value=1, max_value=80, value=10, key="nb_client")

        ile_de_france_client = st.toggle("🗼 Île-de-France uniquement", value=False, key="idf_client", help="Filtre les résultats pour la région Île-de-France")

        inviter_client = st.toggle("Envoyer des invitations automatiquement", value=False, key="inviter_client")

        if inviter_client:
            reinviter_profils_scrapes_client = st.checkbox(
                "Réinviter les profils déjà scrapés",
                value=False,
                key="reinviter_client",
                help="Si coché, enverra des invitations même aux profils déjà présents dans votre historique"
            )

            message_client = st.text_area(
                "Message personnalisé (optionnel)",
                placeholder="Message d'invitation...",
                max_chars=200,
                key="message_client"
            )
        else:
            reinviter_profils_scrapes_client = False
            message_client = ""

        if st.button("🔍 Lancer recherche clients", type="primary"):
            if not cookie_client:
                st.error("❌ Cookie manquant")
            else:
                with st.spinner("🚀 Recherche en cours..."):
                    scraper = LinkedInScraperV2Sync(use_database=True, proxy=st.session_state.get('user_proxy'), db_file=str(st.session_state.user_paths.db_file), profiles_csv=str(st.session_state.user_paths.profiles_csv), config_dir=str(st.session_state.user_paths.config_dir))

                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    df = scraper.run_scraper(
                        cookie=cookie_client,
                        keyword=keyword_client,
                        entreprises=[entreprise_client],
                        nb_profils=nb_client,
                        ecoles_ids=[],
                        inviter=inviter_client,
                        message_invitation=message_client,
                        reinviter_profils_scrapes=reinviter_profils_scrapes_client,
                        ile_de_france=ile_de_france_client,
                        progress_callback=lambda p: progress_bar.progress(p),
                        status_callback=lambda s: status_text.text(s)
                    )

                    if not df.empty:
                        st.success(f"✅ {len(df)} profils scrapés!")
                        st.dataframe(df, use_container_width=True)

                        excel_data = st.session_state.export_manager.export_to_excel(df.to_dict('records'))
                        st.download_button(
                            label="📥 Télécharger Excel",
                            data=excel_data,
                            file_name=f"clients_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                    else:
                        st.warning(
                            "⚠️ Aucun profil trouvé — LinkedIn n'a renvoyé aucun résultat. "
                            "Cause fréquente : le filtre entreprise n'a pas pu être résolu, "
                            "et la recherche par mot-clé combinée est trop restrictive. "
                            "Essaie sans entreprise, ou consulte la page 📜 Logs pour le détail."
                        )

    # TAB 3: FILE D'ATTENTE
    # TAB 3: PAR URLS (ancienne page « Scraping URLs »)
    with tab3:
        st.subheader("Traiter une liste d'URLs de profils")
        st.caption("Collez des URLs LinkedIn pour récupérer le poste et la société de chaque profil.")

        col1, col2 = st.columns([2, 1])

        with col1:
            urls_input = st.text_area(
                "URLs LinkedIn (une par ligne)",
                placeholder="https://www.linkedin.com/in/jean-dupont-12345/\nhttps://www.linkedin.com/in/marie-martin-67890/",
                height=250,
                key="urls_input"
            )

        with col2:
            cookie_urls = st.text_input(
                "Cookie li_at",
                value=st.session_state.global_cookie,
                type="password",
                key="cookie_urls"
            )

            if cookie_urls != st.session_state.global_cookie:
                if st.session_state.cookie_manager.validate_cookie_format(cookie_urls):
                    st.session_state.cookie_manager.save_cookie(cookie_urls)
                    st.session_state.global_cookie = cookie_urls
                    st.success("✅ Cookie sauvegardé")

            # Compter les URLs valides
            urls_list = [u.strip() for u in urls_input.strip().split('\n') if u.strip() and '/in/' in u]
            nb_urls = len(urls_list)

            if nb_urls > 0:
                st.info(f"🔗 {nb_urls} URL(s) détectée(s)")
            else:
                st.warning("Collez des URLs LinkedIn ci-contre")

            st.markdown("---")
            st.markdown("**Options**")

            inviter_urls = st.checkbox("Envoyer des invitations", value=False, key="inviter_urls")

            if inviter_urls:
                message_urls = st.text_area(
                    "Message d'invitation",
                    placeholder="Message personnalisé...",
                    max_chars=200,
                    key="message_urls"
                )
            else:
                message_urls = ""

        st.markdown("---")

        if st.button("🚀 Lancer le scraping", type="primary", use_container_width=True, key="btn_url_scraping"):
            if not cookie_urls:
                st.error("❌ Cookie manquant")
            elif nb_urls == 0:
                st.error("❌ Aucune URL LinkedIn valide")
            else:
                with st.spinner(f"🔄 Scraping de {nb_urls} profils en cours..."):
                    scraper = LinkedInScraperV2Sync(use_database=True, proxy=st.session_state.get('user_proxy'), db_file=str(st.session_state.user_paths.db_file), profiles_csv=str(st.session_state.user_paths.profiles_csv), config_dir=str(st.session_state.user_paths.config_dir))

                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    df = scraper.run_url_scraper(
                        cookie=cookie_urls,
                        urls=urls_list,
                        inviter=inviter_urls,
                        message_invitation=message_urls,
                        progress_callback=lambda p: progress_bar.progress(min(p, 1.0)),
                        status_callback=lambda s: status_text.text(s)
                    )

                    if not df.empty:
                        st.success(f"✅ {len(df)} profils récupérés sur {nb_urls} !")
                        st.dataframe(df, use_container_width=True)

                        excel_data = st.session_state.export_manager.export_to_excel(df.to_dict('records'))
                        st.download_button(
                            label="📥 Télécharger Excel",
                            data=excel_data,
                            file_name=f"profils_urls_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )

                        csv_data = df.to_csv(index=False, sep=';', encoding='utf-8-sig')
                        st.download_button(
                            label="📥 Télécharger CSV",
                            data=csv_data,
                            file_name=f"profils_urls_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime="text/csv"
                        )
                    else:
                        st.warning("⚠️ Aucun profil récupéré")

                    if scraper.errors:
                        with st.expander(f"⚠️ Erreurs ({len(scraper.errors)})"):
                            for err in scraper.errors:
                                st.write(f"- {err}")

# ==============================================
# PAGE 5: HISTORIQUE
# ==============================================
elif page == "💾 Historique":
    st.header("💾 Historique des Profils")

    # Filtres
    col1, col2, col3 = st.columns(3)

    with col1:
        filtre_ecole = st.selectbox("Filtrer par école", ["Toutes"] + list(ECOLES.keys()))

    with col2:
        limite = st.number_input("Nombre de résultats", min_value=10, max_value=5000, value=100, step=10)

    with col3:
        afficher_invitations = st.checkbox("Seulement avec invitation", value=False)

    # Récupérer les profils
    profils = st.session_state.db.get_tous_profils(limit=limite)

    if profils:
        df = pd.DataFrame(profils)

        # Appliquer les filtres
        if filtre_ecole != "Toutes":
            df = df[df['ecole'] == filtre_ecole]

        if afficher_invitations:
            df = df[df['invitation_envoyee'] == 'Oui']

        st.write(f"**{len(df)} profils trouvés**")

        # Afficher le dataframe
        st.dataframe(df, use_container_width=True)

        # Export
        col1, col2 = st.columns(2)

        with col1:
            excel_data = st.session_state.export_manager.export_to_excel(df.to_dict('records'))
            st.download_button(
                label="📥 Télécharger Excel",
                data=excel_data,
                file_name=f"historique_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        with col2:
            csv_data = st.session_state.export_manager.export_to_csv(df.to_dict('records'))
            st.download_button(
                label="📥 Télécharger CSV",
                data=csv_data,
                file_name=f"historique_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
    else:
        st.info("Aucun profil dans l'historique")

# ==============================================
# PAGE 6: CONFIGURATION
# ==============================================
elif page == "✉️ Messages":
    st.header("✉️ Suivi & Messages")
    st.caption("Détecte qui a accepté ton invitation, puis envoie-leur un message.")

    _ckm = st.session_state.global_cookie
    if not _ckm:
        st.warning("⚠️ Renseigne d'abord ton **cookie li_at** dans la page **Recherche**.")
    else:
        _masked_m = f"{_ckm[:6]}…{_ckm[-4:]}" if len(_ckm) > 12 else _ckm
        st.markdown(
            '<div style="display:flex;align-items:center;gap:10px;padding:10px 14px;'
            'background:var(--wf-surface);border:1px solid var(--wf-border);'
            'border-left:3px solid var(--wf-success);border-radius:12px;margin-bottom:14px">'
            '<span style="width:9px;height:9px;border-radius:50%;background:var(--wf-success)"></span>'
            f'<span style="font-size:.8rem;color:var(--wf-muted)">Session LinkedIn active · li_at · {_masked_m}</span></div>',
            unsafe_allow_html=True,
        )

        def _new_scraper():
            return LinkedInScraperV2Sync(
                use_database=True, proxy=st.session_state.get('user_proxy'),
                db_file=str(st.session_state.user_paths.db_file),
                profiles_csv=str(st.session_state.user_paths.profiles_csv),
                config_dir=str(st.session_state.user_paths.config_dir),
            )

        # ── 1. Détecter les acceptations ──
        en_attente = st.session_state.db.invitations_en_attente()
        cA, cB = st.columns([3, 1])
        cA.markdown(f"**{len(en_attente)}** invitation(s) en attente à vérifier.")
        if cB.button("🔄 Vérifier qui a accepté", type="primary",
                     use_container_width=True, disabled=len(en_attente) == 0):
            with st.spinner("Vérification en cours (revisite des profils invités)…"):
                sc = _new_scraper()
                pb = st.progress(0); stt = st.empty()
                acceptees = sc.verifier_acceptations(
                    cookie=_ckm, profils=en_attente, max_check=30,
                    progress_callback=lambda p: pb.progress(p),
                    status_callback=lambda s: stt.text(s),
                )
                for a in acceptees:
                    st.session_state.db.marquer_acceptee(a["url"])
                if acceptees:
                    st.success(f"✅ {len(acceptees)} personne(s) ont accepté ton invitation !")
                else:
                    st.info("Aucune nouvelle acceptation détectée pour l'instant.")
                if sc.errors:
                    with st.expander("⚠️ Détails"):
                        for e in sc.errors:
                            st.write(f"- {e}")

        st.markdown("---")

        # ── 2. Envoyer les messages ──
        st.subheader("💬 Message aux personnes qui ont accepté")
        acc = st.session_state.db.acceptees_non_messagees()
        if not acc:
            st.info("Personne à messager pour l'instant. Lance d'abord la vérification ci-dessus.")
        else:
            message = st.text_area(
                "Modèle de message",
                placeholder="Bonjour, ravi(e) d'être en contact ! …",
                height=120,
            )
            st.caption(f"{len(acc)} personne(s) ont accepté et n'ont pas encore été messagées "
                       f"(max 20 envois par lot).")
            choix = {}
            for a in acc:
                sous = " · ".join(x for x in [a.get("poste"), a.get("entreprise")] if x)
                label = f"{a['nom']}" + (f" — {sous}" if sous else "")
                choix[a["url"]] = st.checkbox(label, key=f"msg_{a['url']}")
            sel = [a for a in acc if choix.get(a["url"])]
            if st.button(f"✉️ Envoyer les messages ({len(sel)})", type="primary",
                         disabled=(len(sel) == 0 or not message.strip())):
                with st.spinner("Envoi des messages…"):
                    sc = _new_scraper()
                    pb = st.progress(0); stt = st.empty()
                    envoyes = sc.envoyer_messages(
                        cookie=_ckm, cibles=sel, message=message, max_msg=20,
                        progress_callback=lambda p: pb.progress(p),
                        status_callback=lambda s: stt.text(s),
                    )
                    for e in envoyes:
                        st.session_state.db.marquer_messagee(e["url"])
                    st.success(f"✅ {len(envoyes)} message(s) envoyé(s).")
                    if sc.errors:
                        with st.expander("⚠️ Détails"):
                            for er in sc.errors:
                                st.write(f"- {er}")
                    st.rerun()

elif page == "📜 Logs":
    st.header("📜 Logs du scraper")
    st.caption("Journal d'exécution en temps réel — pour voir où en est un scraping ou pourquoi il s'arrête.")

    col_l1, col_l2 = st.columns([1, 3])
    with col_l1:
        nb_lignes = st.number_input("Lignes à afficher", min_value=20, max_value=2000, value=200, step=20)
        if st.button("🔄 Rafraîchir"):
            st.rerun()

    log_path = ScraperConfig.LOG_FILE
    if os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                lignes = f.readlines()
            extrait = "".join(lignes[-int(nb_lignes):])
            st.code(extrait or "(journal vide)", language="log")
            st.download_button(
                "📥 Télécharger le journal complet",
                data="".join(lignes),
                file_name="scraper.log",
                mime="text/plain"
            )
        except Exception as e:
            st.error(f"Impossible de lire le journal : {e}")
    else:
        st.info("Aucun journal pour l'instant — lance un scraping puis reviens ici.")

    st.caption("ℹ️ Le journal est partagé par l'instance (pas encore séparé par utilisateur).")

elif page == "⚙️ Configuration":
    st.header("⚙️ Configuration")

    st.subheader("🔧 Paramètres de scraping")

    col1, col2 = st.columns(2)

    with col1:
        st.write(f"**Max profils par run:** {ScraperConfig.MAX_PROFILES_PER_RUN}")
        st.write(f"**Max invitations/jour:** {ScraperConfig.MAX_INVITATIONS_PER_DAY}")
        st.write(f"**Timeout page:** {ScraperConfig.TIMEOUT_PAGE}ms")

    with col2:
        st.write(f"**Délai entre profils:** {ScraperConfig.DELAY_BETWEEN_PROFILES_MIN}-{ScraperConfig.DELAY_BETWEEN_PROFILES_MAX}ms")
        st.write(f"**Mode headless:** {ScraperConfig.HEADLESS}")
        st.write(f"**Retry attempts:** {ScraperConfig.MAX_RETRY_ATTEMPTS}")

    st.markdown("---")

    st.subheader("🏫 Écoles configurées")

    df_ecoles = pd.DataFrame(
        list(ECOLES.items()),
        columns=['École', 'ID LinkedIn']
    )
    st.dataframe(df_ecoles, use_container_width=True)

    st.markdown("---")

    st.subheader("💾 Base de données")

    _user_db = str(st.session_state.user_paths.db_file)
    if os.path.exists(_user_db):
        db_size = os.path.getsize(_user_db) / 1024
        st.success(f"✅ Base de données: {db_size:.2f} KB")
    else:
        st.warning("⚠️ Base de données non initialisée")

    if st.button("🗑️ Réinitialiser la base de données", type="secondary"):
        if st.checkbox("Je confirme vouloir supprimer toutes les données"):
            try:
                if os.path.exists(_user_db):
                    os.remove(_user_db)
                st.session_state.db = DatabaseManager(db_file=_user_db)
                st.success("✅ Base de données réinitialisée")
            except Exception as e:
                st.error(f"❌ Erreur: {e}")

# Footer
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: gray;'>LinkedIn Scraper Pro v2.0 - "
    "Développé avec ❤️ par votre équipe</div>",
    unsafe_allow_html=True
)
