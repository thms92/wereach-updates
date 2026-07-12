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
from config import ScraperConfig, ECOLES
from database import DatabaseManager
from cookie_utils import CookieManager
from export_utils import ExportManager
from queue_manager import QueueManager, JobStatus
from logger import logger
from utils.user_context import resolve_user_email, user_paths_for, DEFAULT_DEV_EMAIL
from utils.proxy_store import load_proxy, save_proxy
from utils.app_auth import verify_access, access_configured, email_domain_ok, ALLOWED_DOMAIN
from wefiit_theme import inject_theme, wordmark


# Configuration Streamlit
st.set_page_config(
    page_title="We.Reach",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Thème We.Reach (tokens Claude Design — clair/sombre)
inject_theme(dark=st.session_state.get("wf_dark", False))

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

# Mode sombre (thème We.Reach)
_dark = st.sidebar.toggle("🌙 Mode sombre", value=st.session_state.get("wf_dark", False))
if _dark != st.session_state.get("wf_dark", False):
    st.session_state.wf_dark = _dark
    st.rerun()

if st.session_state.get("auth_email"):
    st.sidebar.caption(f"👤 {st.session_state['auth_email']}")
    if st.sidebar.button("🚪 Déconnexion"):
        del st.session_state["auth_email"]
        st.rerun()

page = st.sidebar.radio(
    "Choisir une page",
    ["📊 Dashboard", "🔍 Recherche", "🎯 Chasse", "🔗 Scraping URLs", "📋 Templates", "💾 Historique", "📜 Logs", "⚙️ Configuration"]
)

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

    tab1, tab2, tab3 = st.tabs(["👤 Candidats", "🏢 Clients/Entreprises", queue_tab_label])

    # TAB 1: CANDIDATS
    with tab1:
        st.subheader("Recherche de candidats avec filtre école")

        col1, col2 = st.columns([1, 2])

        with col1:
            # Cookie global
            cookie = st.text_input(
                "Cookie li_at",
                value=st.session_state.global_cookie,
                type="password",
                help="Le cookie sera sauvegardé de manière sécurisée",
                key="cookie_candidats"
            )

            if cookie != st.session_state.global_cookie:
                if st.session_state.cookie_manager.validate_cookie_format(cookie):
                    st.session_state.cookie_manager.save_cookie(cookie)
                    st.session_state.global_cookie = cookie
                    st.success("✅ Cookie sauvegardé")
                else:
                    st.warning("⚠️ Format de cookie suspect")

            keyword = st.text_input("Mots-clés", "Product Manager")
            entreprise = st.text_input("Entreprise (optionnel)", "")
            nb_profils = st.number_input("Nombre de profils", min_value=1, max_value=200, value=10)

            ile_de_france = st.checkbox("🗼 Île-de-France uniquement", value=False, help="Filtre les résultats pour la région Île-de-France")

            inviter = st.checkbox("Envoyer des invitations", value=False)

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
            st.subheader("🎓 Sélectionner UNE école")

            ecoles_selectionnees = []
            cols = st.columns(4)

            for i, (nom, id_ecole) in enumerate(ECOLES.items()):
                checked = cols[i % 4].checkbox(nom, key=f"ecole_candidat_{nom}")
                if checked:
                    ecoles_selectionnees.append(id_ecole)

            if len(ecoles_selectionnees) == 1:
                st.success(f"✅ École sélectionnée")
            elif len(ecoles_selectionnees) > 1:
                st.error("❌ Sélectionnez UNE seule école")
            else:
                st.info("ℹ️ Aucune école sélectionnée")

        st.markdown("---")

        col_btn1, col_btn2 = st.columns(2)

        with col_btn1:
            if st.button("🔍 Lancer le scraping", type="primary", use_container_width=True):
                if not cookie:
                    st.error("❌ Cookie manquant")
                elif len(ecoles_selectionnees) != 1:
                    st.error("❌ Sélectionnez exactement une école")
                else:
                    with st.spinner("🚀 Scraping en cours..."):
                        scraper = LinkedInScraperV2Sync(use_database=True, proxy=st.session_state.get('user_proxy'), db_file=str(st.session_state.user_paths.db_file), profiles_csv=str(st.session_state.user_paths.profiles_csv))

                        progress_bar = st.progress(0)
                        status_text = st.empty()

                        def update_progress(p):
                            progress_bar.progress(p)

                        def update_status(s):
                            status_text.text(s)

                        df = scraper.run_scraper(
                            cookie=cookie,
                            keyword=keyword,
                            entreprise=entreprise,
                            nb_profils=nb_profils,
                            ecoles_ids=ecoles_selectionnees,
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

        cookie_client = st.text_input(
            "Cookie li_at",
            value=st.session_state.global_cookie,
            type="password",
            key="cookie_client"
        )

        # Synchroniser le cookie global
        if cookie_client != st.session_state.global_cookie:
            if st.session_state.cookie_manager.validate_cookie_format(cookie_client):
                st.session_state.cookie_manager.save_cookie(cookie_client)
                st.session_state.global_cookie = cookie_client
                st.success("✅ Cookie sauvegardé")
            else:
                st.warning("⚠️ Format de cookie suspect")

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
            '("Chief Data Officer" OR CDO OR "Head of Data" OR "Head of AI" OR "Directeur Data" OR "Responsable Data" OR "Directeur de la donnée")',
            key="keyword_client",
        )
        entreprise_client = st.text_input("Entreprise", "", key="entreprise_client")
        nb_client = st.number_input("Nombre de profils", min_value=1, max_value=200, value=10, key="nb_client")

        ile_de_france_client = st.checkbox("🗼 Île-de-France uniquement", value=False, key="idf_client", help="Filtre les résultats pour la région Île-de-France")

        inviter_client = st.checkbox("Envoyer des invitations", value=False, key="inviter_client")

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
                    scraper = LinkedInScraperV2Sync(use_database=True, proxy=st.session_state.get('user_proxy'), db_file=str(st.session_state.user_paths.db_file), profiles_csv=str(st.session_state.user_paths.profiles_csv))

                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    df = scraper.run_scraper(
                        cookie=cookie_client,
                        keyword=keyword_client,
                        entreprise=entreprise_client,
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
    with tab3:
        st.subheader("Enchaîner plusieurs entreprises automatiquement")
        st.caption("Même keyword, même config — seule l'entreprise change entre chaque job.")

        qm = st.session_state.queue_manager

        # ─── CONFIG PARTAGÉE ───
        col_q1, col_q2 = st.columns(2)

        with col_q1:
            q_cookie = st.text_input(
                "Cookie li_at",
                value=st.session_state.global_cookie,
                type="password",
                key="queue_cookie"
            )
            if q_cookie != st.session_state.global_cookie:
                if st.session_state.cookie_manager.validate_cookie_format(q_cookie):
                    st.session_state.cookie_manager.save_cookie(q_cookie)
                    st.session_state.global_cookie = q_cookie
            qm.config.cookie = q_cookie or st.session_state.global_cookie

            q_keyword = st.text_input(
                "Mots-clés",
                value=qm.config.keyword or "Product Manager",
                key="queue_keyword"
            )
            qm.config.keyword = q_keyword

            q_nb = st.number_input(
                "Profils par entreprise",
                min_value=1, max_value=200,
                value=qm.config.nb_profils_par_entreprise,
                key="queue_nb"
            )
            qm.config.nb_profils_par_entreprise = q_nb

            q_idf = st.checkbox(
                "🗼 Île-de-France uniquement",
                value=qm.config.ile_de_france,
                key="queue_idf"
            )
            qm.config.ile_de_france = q_idf

        with col_q2:
            q_inviter = st.checkbox(
                "Envoyer des invitations",
                value=qm.config.inviter,
                key="queue_inviter"
            )
            qm.config.inviter = q_inviter

            if q_inviter:
                q_reinviter = st.checkbox(
                    "Réinviter les profils déjà scrapés",
                    value=qm.config.reinviter_profils_scrapes,
                    key="queue_reinviter"
                )
                qm.config.reinviter_profils_scrapes = q_reinviter

                q_message = st.text_area(
                    "Message d'invitation",
                    value=qm.config.message_invitation,
                    max_chars=200,
                    key="queue_message"
                )
                qm.config.message_invitation = q_message

            # École optionnelle
            st.markdown("**🎓 École (optionnelle)**")
            ecoles_q = []
            cols_eq = st.columns(3)
            for i, (nom, id_ecole) in enumerate(ECOLES.items()):
                if cols_eq[i % 3].checkbox(nom, key=f"queue_ecole_{nom}"):
                    ecoles_q.append(id_ecole)
            if len(ecoles_q) > 1:
                st.error("❌ Sélectionnez UNE seule école max")
            qm.config.ecoles_ids = ecoles_q[:1]

        # Pause entre jobs
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            qm.config.pause_entre_jobs_min = st.number_input(
                "Pause min entre jobs (sec)", min_value=10, max_value=300,
                value=qm.config.pause_entre_jobs_min, key="queue_pause_min"
            )
        with col_p2:
            qm.config.pause_entre_jobs_max = st.number_input(
                "Pause max entre jobs (sec)", min_value=10, max_value=600,
                value=max(qm.config.pause_entre_jobs_max, qm.config.pause_entre_jobs_min + 10),
                key="queue_pause_max"
            )

        st.markdown("---")

        # ─── AJOUT D'ENTREPRISES ───
        col_add1, col_add2 = st.columns([3, 1])

        with col_add1:
            entreprises_input = st.text_area(
                "Entreprises (une par ligne ou séparées par des virgules)",
                placeholder="Air France\nL'Oréal\nChanel\nLVMH\nTotalEnergies",
                height=100,
                key="queue_entreprises_input"
            )

        with col_add2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("➕ Ajouter", type="primary", use_container_width=True, key="queue_add_btn"):
                if entreprises_input.strip():
                    lignes = entreprises_input.replace(",", "\n").split("\n")
                    noms = [l.strip() for l in lignes if l.strip()]
                    nb_ajoute = qm.ajouter_entreprises(noms)
                    qm.sauvegarder()
                    if nb_ajoute > 0:
                        st.success(f"✅ {nb_ajoute} entreprise(s) ajoutée(s)")
                        st.rerun()
                    else:
                        st.warning("⚠️ Déjà présentes dans la file")

            if st.button("🗑️ Vider", use_container_width=True, key="queue_clear_btn"):
                qm.vider_file()
                qm.sauvegarder()
                st.rerun()

        # ─── AFFICHAGE DE LA FILE ───
        if qm.jobs:
            st.markdown("---")
            st.markdown(f"**📋 {len(qm.jobs)} entreprise(s) dans la file :**")

            for idx, job in enumerate(qm.jobs):
                status_icons = {
                    JobStatus.EN_ATTENTE: "⏳",
                    JobStatus.EN_COURS: "🔄",
                    JobStatus.TERMINE: "✅",
                    JobStatus.ERREUR: "❌",
                    JobStatus.ANNULE: "⛔",
                }
                icon = status_icons.get(job.status, "❓")

                col_i, col_n, col_s, col_a = st.columns([0.4, 2.5, 3, 1])

                with col_i:
                    st.write(f"{icon}")

                with col_n:
                    st.write(f"**{idx + 1}. {job.entreprise}**")

                with col_s:
                    if job.status in (JobStatus.TERMINE, JobStatus.ERREUR):
                        st.caption(
                            f"👤 {job.nb_profils_trouves} · 💌 {job.nb_invitations_envoyees} · ⏱️ {job.duree_secondes}s"
                        )

                with col_a:
                    if job.status == JobStatus.EN_ATTENTE:
                        if st.button("✕", key=f"qdel_{idx}", help="Supprimer"):
                            qm.supprimer_entreprise(idx)
                            qm.sauvegarder()
                            st.rerun()

            # ─── RÉSUMÉ + ACTIONS ───
            st.markdown("---")
            resume = qm.get_resume()

            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            col_m1.metric("En attente", resume["en_attente"])
            col_m2.metric("Terminés", resume["termines"])
            col_m3.metric("Profils", resume["total_profils"])
            col_m4.metric("Invitations", resume["total_invitations"])

            col_go, col_rst = st.columns(2)

            with col_go:
                can_launch = resume["en_attente"] > 0
                if st.button(
                    f"🚀 Lancer ({resume['en_attente']} jobs)",
                    type="primary",
                    use_container_width=True,
                    disabled=not can_launch,
                    key="queue_launch_btn"
                ):
                    if not qm.config.cookie:
                        st.error("❌ Cookie non configuré")
                    else:
                        qm.sauvegarder()
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        job_info = st.empty()

                        with st.spinner("🔄 Exécution de la file d'attente..."):
                            df_total = qm.lancer_file(
                                progress_callback=lambda p: progress_bar.progress(min(p, 1.0)),
                                status_callback=lambda s: status_text.text(s),
                                job_callback=lambda idx, j: job_info.text(
                                    f"{'🔄' if j.status == JobStatus.EN_COURS else '✅' if j.status == JobStatus.TERMINE else '❌'} {j.entreprise}"
                                ),
                                proxy=st.session_state.get('user_proxy'),
                                db_file=str(st.session_state.user_paths.db_file),
                                profiles_csv=str(st.session_state.user_paths.profiles_csv)
                            )

                        qm.sauvegarder()

                        if not df_total.empty:
                            st.success(f"✅ Terminé ! {len(df_total)} profils scrapés au total")
                            st.dataframe(df_total, use_container_width=True)

                            excel_data = st.session_state.export_manager.export_to_excel(
                                df_total.to_dict('records')
                            )
                            st.download_button(
                                label="📥 Télécharger (Excel)",
                                data=excel_data,
                                file_name=f"file_attente_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                        else:
                            st.warning("⚠️ Aucun profil trouvé")

                        jobs_err = [j for j in qm.jobs if j.erreurs]
                        if jobs_err:
                            with st.expander(f"⚠️ Erreurs ({len(jobs_err)} jobs)"):
                                for j in jobs_err:
                                    st.write(f"**{j.entreprise}:** {', '.join(j.erreurs)}")

                        st.rerun()

            with col_rst:
                if st.button("🔁 Tout remettre en attente", use_container_width=True, key="queue_reset_btn"):
                    qm.reset_statuts()
                    qm.sauvegarder()
                    st.rerun()

# ==============================================
# PAGE 3: SCRAPING PAR URLs
# ==============================================
elif page == "🔗 Scraping URLs":
    st.header("🔗 Scraping par URLs de profils")
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
                scraper = LinkedInScraperV2Sync(use_database=True, proxy=st.session_state.get('user_proxy'), db_file=str(st.session_state.user_paths.db_file), profiles_csv=str(st.session_state.user_paths.profiles_csv))

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
# PAGE 4: TEMPLATES
# ==============================================
elif page == "📋 Templates":
    st.header("📋 Templates de Recherche")

    tab1, tab2 = st.tabs(["➕ Nouveau Template", "📚 Templates Sauvegardés"])

    with tab1:
        st.subheader("Créer un nouveau template")

        nom_template = st.text_input("Nom du template", placeholder="Ex: PM Tech Dauphine")
        keyword_template = st.text_input("Mots-clés", placeholder="Product Manager")
        entreprise_template = st.text_input("Entreprise", placeholder="")

        ecoles_template = st.multiselect(
            "Écoles",
            options=list(ECOLES.keys()),
            default=[]
        )

        message_template = st.text_area(
            "Message d'invitation par défaut",
            placeholder="Message personnalisé...",
            max_chars=200
        )

        nb_profils_template = st.number_input("Nombre de profils par défaut", min_value=1, max_value=200, value=10)

        if st.button("💾 Sauvegarder Template", type="primary"):
            if not nom_template:
                st.error("❌ Nom du template requis")
            else:
                ecoles_str = ",".join(ecoles_template)
                success = st.session_state.db.sauvegarder_template(
                    nom=nom_template,
                    keyword=keyword_template,
                    entreprise=entreprise_template,
                    ecoles=ecoles_str,
                    message=message_template,
                    nb_profils=nb_profils_template
                )

                if success:
                    st.success("✅ Template sauvegardé!")
                else:
                    st.error("❌ Erreur lors de la sauvegarde")

    with tab2:
        st.subheader("Templates existants")

        templates = st.session_state.db.get_templates()

        if templates:
            for template in templates:
                with st.expander(f"📄 {template['nom']}"):
                    col1, col2 = st.columns(2)

                    with col1:
                        st.write(f"**Keyword:** {template['keyword']}")
                        st.write(f"**Entreprise:** {template['entreprise'] or 'N/A'}")
                        st.write(f"**Écoles:** {template['ecoles'] or 'Aucune'}")

                    with col2:
                        st.write(f"**Nb profils:** {template['nb_profils']}")
                        st.write(f"**Créé le:** {template['date_creation']}")

                    if template['message_invitation']:
                        st.write(f"**Message:** {template['message_invitation']}")

                    if st.button(f"🚀 Utiliser ce template", key=f"use_{template['id']}"):
                        st.info("Allez dans la page Recherche pour lancer le scraping")
        else:
            st.info("Aucun template sauvegardé")

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
elif page == "🎯 Chasse":
    st.header("🎯 Chasse — recherche & invitation")
    st.caption("Recherche des prospects et, si tu coches l'option, envoie les invitations dans le même parcours.")

    cookie_chasse = st.text_input(
        "Cookie li_at", value=st.session_state.global_cookie, type="password", key="cookie_chasse"
    )
    if cookie_chasse and cookie_chasse != st.session_state.global_cookie:
        if st.session_state.cookie_manager.validate_cookie_format(cookie_chasse):
            st.session_state.cookie_manager.save_cookie(cookie_chasse)
            st.session_state.global_cookie = cookie_chasse

    col1, col2 = st.columns(2)
    with col1:
        keyword_c = st.text_input("Mots-clés", "Product Manager", key="kw_chasse")
        entreprise_c = st.text_input("Entreprise (optionnel)", "", key="ent_chasse")
    with col2:
        nb_c = st.number_input("Nombre de profils", min_value=1, max_value=200, value=10, key="nb_chasse")
        idf_c = st.checkbox("🗼 Île-de-France uniquement", value=False, key="idf_chasse")

    inviter_c = st.checkbox("📨 Envoyer des invitations pendant le scraping", value=False, key="inv_chasse")
    note_c = ""
    if inviter_c:
        if st.checkbox("Ajouter une note à l'invitation (⚠️ ~5/mois max chez LinkedIn)", key="note_chk_chasse"):
            note_c = st.text_area("Note (identique pour tous)", max_chars=280, key="note_chasse")

    if st.button("🎯 Lancer la chasse", type="primary"):
        if not st.session_state.global_cookie:
            st.error("❌ Cookie manquant")
        else:
            with st.spinner("🚀 Chasse en cours… (le navigateur va s'ouvrir)"):
                scraper = LinkedInScraperV2Sync(
                    use_database=True, proxy=st.session_state.get('user_proxy'),
                    db_file=str(st.session_state.user_paths.db_file),
                    profiles_csv=str(st.session_state.user_paths.profiles_csv),
                )
                progress = st.progress(0)
                status = st.empty()
                df_res = scraper.run_scraper(
                    cookie=st.session_state.global_cookie,
                    keyword=keyword_c,
                    entreprise=entreprise_c,
                    nb_profils=int(nb_c),
                    ecoles_ids=[],
                    inviter=inviter_c,
                    message_invitation=note_c,
                    ile_de_france=idf_c,
                    progress_callback=lambda p: progress.progress(p),
                    status_callback=lambda s: status.text(s),
                )
            if df_res is not None and not df_res.empty:
                st.success(f"✅ {len(df_res)} profil(s)" + (" — invitations envoyées" if inviter_c else ""))
                st.dataframe(df_res, use_container_width=True)
                excel = st.session_state.export_manager.export_to_excel(df_res.to_dict('records'))
                st.download_button(
                    "📥 Télécharger Excel", data=excel,
                    file_name=f"chasse_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            else:
                st.warning("Aucun profil trouvé (essaie sans entreprise ou d'autres mots-clés).")

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
