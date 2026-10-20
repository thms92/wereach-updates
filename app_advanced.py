# -*- coding: utf-8 -*-
"""
LinkedIn Scraper Advanced - Interface Streamlit améliorée
Avec dashboard, statistiques, templates, et export Excel
"""

import streamlit as st
import pandas as pd
import os
from uuid import uuid4

# Chaque page vit dans son module sous ui/ ; ce script ne garde que le
# socle commun (connexion, session, barre latérale) et l'aiguillage.
from ui.page_veille import afficher_page_veille
from ui.page_tableau_de_bord import afficher_page_tableau_de_bord
from ui.page_recherche import afficher_page_recherche
from ui.page_historique import afficher_page_historique
from ui.page_messages import afficher_page_messages
from ui.page_journal import afficher_page_journal
from config import ScraperConfig, ECOLES, EMAIL_SUPPORT
from database import DatabaseManager
from cookie_utils import CookieManager
from export_utils import ExportManager
from logger import logger
from utils.user_context import (resolve_user_email, user_paths_for,
                                DEFAULT_DEV_EMAIL, mode_admin)
from utils.proxy_store import load_proxy, save_proxy
from utils.app_auth import verify_access, access_configured, email_domain_ok, ALLOWED_DOMAIN
from wefiit_theme import (FAVICON_SVG, declarer_langue_francaise, inject_theme,
                          wordmark)
from ui.composants import afficher_jauge_budget
from utils.budget import budget_du_jour
from version import get_version
from utils.nouveautes import (charger_notes, doit_annoncer, usage_anterieur,
                              version_vue)
from utils.tutoriel import etapes_pour, marquer_vu, tutoriel_a_afficher
from ui.tutoriel import CLE_FIN, script_visite
from utils.diagnostic import lien_mailto, ouvrir_mail, rapport
from utils.mise_a_jour import (mise_a_jour_disponible, relancer,
                               version_publiee)


# Configuration Streamlit
# Icône d'onglet : la marque We.Reach en SVG (plus d'émoji). Barre latérale
# « auto » : ouverte sur ordinateur, repliée sur téléphone, où elle couvrait
# toute la page à l'ouverture.
st.set_page_config(
    page_title="We.Reach",
    page_icon=FAVICON_SVG,
    layout="wide",
    initial_sidebar_state="auto"
)

# Thème We.Reach (fond clair uniquement)
inject_theme()
declarer_langue_francaise()

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
        st.subheader("Connexion", anchor=False)
        with st.form("login_form"):
            _em = st.text_input("Email", placeholder=f"prenom.nom@{ALLOWED_DOMAIN}")
            _pw = st.text_input("Mot de passe", type="password")
            if st.form_submit_button("Se connecter", width="stretch"):
                if not email_domain_ok(_em):
                    st.error(f"Utilisez votre adresse email @{ALLOWED_DOMAIN}.")
                elif verify_access(_em, _pw):
                    st.session_state.auth_email = _em.strip().lower()
                    st.rerun()
                else:
                    st.error("Email ou mot de passe incorrect.")
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
    cookie_saved = st.session_state.cookie_manager.load_cookie()
    st.session_state.global_cookie = cookie_saved or ""
    st.session_state.user_proxy = load_proxy(
        str(paths.proxy_file), str(paths.key_file)
    )

# Le wordmark vit en tête de la barre latérale : la zone principale
# commence directement par le titre de la page.
st.sidebar.markdown(wordmark(size=1.6, center=False, sur_fond_sombre=True),
                    unsafe_allow_html=True)

# Source de vérité du menu. tests/test_navigation.py la confronte aux
# branches `if page == …` : toute page définie doit figurer ici.
PAGES = [
    "📊 Dashboard",
    "🔍 Recherche",
    "🏢 Veille",
    "✉️ Messages",
    "💾 Historique",
    "📜 Logs",
]

# Icônes vectorielles Material — st.radio ne rend que du texte, d'où les
# boutons ci-dessous (maquette validée le 2026-09-16).
ICONES_PAGES = {
    "📊 Dashboard": ":material/dashboard:",
    "🔍 Recherche": ":material/search:",
    "🏢 Veille": ":material/domain:",
    "✉️ Messages": ":material/mail:",
    "💾 Historique": ":material/database:",
    "📜 Logs": ":material/terminal:",
}

# Libellés affichés dans le menu. Les clés de PAGES restent les identifiants
# internes (session, clés de widgets, tests) : seul l'affichage change.
LIBELLES_PAGES = {
    "📊 Dashboard": "Tableau de bord",
    "🔍 Recherche": "Recherche",
    "🏢 Veille": "Veille",
    "✉️ Messages": "Messages",
    "💾 Historique": "Historique",
    "📜 Logs": "Journal",
}

_page_memorisee = st.session_state.get("page")
if _page_memorisee not in PAGES:
    st.session_state["page"] = PAGES[0]

# Les boutons vivent dans un conteneur identifie : le theme s'y accroche pour
# resserrer l'espacement et aligner les libelles a gauche, sans toucher aux
# autres boutons de la barre laterale.
with st.sidebar.container(key="nav_menu"):
    for _libelle in PAGES:
        _actif = st.session_state["page"] == _libelle
        if st.button(
            LIBELLES_PAGES[_libelle],
            icon=ICONES_PAGES[_libelle],
            key=f"nav_{_libelle}",
            type="primary" if _actif else "secondary",
            width="stretch",
        ):
            st.session_state["page"] = _libelle
            st.rerun()

page = st.session_state["page"]

# Le geste signature (DESIGN.md) : le budget d'invitations du jour, sous le
# menu, sur toutes les pages. Lu dans le compteur du moteur, celui qui bloque.
# Réservée ici, redessinée en fin de script : la barre latérale est écrite
# AVANT la page, et une recherche lancée depuis la page laissait la jauge sur
# l'ancien compte. Un premier dessin tout de suite garde la jauge visible si
# la page s'arrête en chemin (st.stop, erreur).
_jauge = st.sidebar.empty()


def _dessiner_jauge() -> None:
    _budget = budget_du_jour(st.session_state.user_paths.config_dir)
    afficher_jauge_budget(_budget.utilisees, _budget.plafond, sur_fond_sombre=True,
                          conteneur=_jauge)


_dessiner_jauge()

# Streamlit abandonne l'état d'un widget dès qu'un rerun ne le dessine pas, et
# les pages sont ici des branches d'un même script : aller sur Historique puis
# revenir vidait les filtres de « Profils similaires » alors que la liste
# trouvée, elle, restait en session — et réapparaissaient alors en silence les
# gens encore chez l'entreprise de référence. Se réaffecter la valeur à chaque
# rerun la retient. Pas sim_inviter ni sim_message : repartir décoché est voulu.
for _cle_filtre in ("sim_entreprise_exclue", "sim_mot", "sim_invitables"):
    if _cle_filtre in st.session_state:
        st.session_state[_cle_filtre] = st.session_state[_cle_filtre]

# Reglages techniques : masques pour l'equipe. Le proxy n'a pas de sens
# quand chacun scrape depuis son propre Mac, et Reglages contient un
# bouton qui efface toute la base. Deposer un fichier `admin` dans le
# dossier de l'application les fait reapparaitre.
if mode_admin():
    with st.sidebar.expander("Mon proxy (recommandé)", icon=":material/vpn_lock:"):
        paths = st.session_state.user_paths
        cur = st.session_state.get('user_proxy') or {}
        server = st.text_input("Serveur (http://host:port)", value=cur.get("server", ""))
        p_user = st.text_input("Login proxy", value=cur.get("username", ""))
        p_pass = st.text_input("Mot de passe proxy", type="password",
                               value=cur.get("password", ""))
        if st.button("Enregistrer mon proxy", icon=":material/save:"):
            if server.strip():
                proxy = {"server": server.strip(),
                         "username": p_user.strip(),
                         "password": p_pass}
                save_proxy(str(paths.proxy_file), str(paths.key_file), proxy)
                st.session_state.user_proxy = proxy
                st.success("Proxy enregistré.")
            else:
                st.warning("Indiquez au moins un serveur.")

    with st.sidebar.expander("Réglages", icon=":material/settings:"):
        st.markdown("**Paramètres de recherche**")
        _ms = lambda v: f"{v / 1000:g} s".replace(".", ",")
        st.markdown(
            f"- Profils au plus par recherche : {ScraperConfig.MAX_PROFILES_PER_RUN}\n"
            f"- Invitations au plus par jour : {ScraperConfig.MAX_INVITATIONS_PER_DAY}\n"
            f"- Attente maximale d'une page : {_ms(ScraperConfig.TIMEOUT_PAGE)}\n"
            f"- Pause entre deux profils : {_ms(ScraperConfig.DELAY_BETWEEN_PROFILES_MIN)}"
            f" à {_ms(ScraperConfig.DELAY_BETWEEN_PROFILES_MAX)}\n"
            f"- Navigateur invisible : {'oui' if ScraperConfig.HEADLESS else 'non'}\n"
            f"- Nouvelles tentatives en cas d'échec : {ScraperConfig.MAX_RETRY_ATTEMPTS}"
        )

        st.markdown("---")

        st.markdown("**Écoles configurées**")

        df_ecoles = pd.DataFrame(
            list(ECOLES.items()),
            columns=['École', 'ID LinkedIn']
        )
        st.dataframe(df_ecoles, width="stretch")

        st.markdown("---")

        st.markdown("**Base de données**")

        _user_db = str(st.session_state.user_paths.db_file)
        if os.path.exists(_user_db):
            db_size = os.path.getsize(_user_db) / 1024
            st.caption(f"Taille : {db_size:.0f} Ko".replace(".", ","))
        else:
            st.caption("Base de données pas encore créée.")

        # La case d'abord, le bouton ensuite : cochée dans un rendu, elle
        # déverrouille le bouton au rendu suivant. L'inverse (case affichée
        # après le clic) ne pouvait jamais être cochée à temps.
        # Le rappel décoche la case : le bouton ne reste pas armé après usage.
        def _reinitialiser_base(chemin=_user_db):
            st.session_state["confirm_reset_db"] = False
            try:
                if os.path.exists(chemin):
                    os.remove(chemin)
                st.session_state.db = DatabaseManager(db_file=chemin)
                st.session_state["_reset_db_resultat"] = ("ok", "Base de données réinitialisée.")
            except Exception as e:
                st.session_state["_reset_db_resultat"] = ("erreur", f"Réinitialisation impossible : {e}")

        _confirme = st.checkbox("Je confirme vouloir supprimer toutes les données",
                                key="confirm_reset_db")
        st.button("Réinitialiser la base de données", type="secondary",
                  icon=":material/delete_forever:", disabled=not _confirme,
                  on_click=_reinitialiser_base)
        _resultat = st.session_state.pop("_reset_db_resultat", None)
        if _resultat:
            (st.success if _resultat[0] == "ok" else st.error)(_resultat[1])

with st.sidebar.expander("Signaler un problème", icon=":material/bug_report:"):
    st.caption(
        "Nous ouvrons un mail déjà rédigé avec ce qui sert au diagnostic. "
        "Vous voyez tout avant d'envoyer, et rien ne part sans vous."
    )
    _diagnostic = st.cache_data(ttl=120)(rapport)()
    _lien = lien_mailto(EMAIL_SUPPORT, _diagnostic)
    if st.button("Préparer le mail", width="stretch", type="primary",
                 icon=":material/mail:"):
        if ouvrir_mail(_lien):
            st.success("Votre logiciel de messagerie s'ouvre avec le mail déjà rédigé.")
        else:
            st.warning("Impossible d'ouvrir la messagerie : copiez le texte ci-dessous.")
    st.code(_diagnostic)

# Pied de barre latérale, discret : compte connecté, version, vérification
# des mises à jour, déconnexion.
st.sidebar.divider()
if st.session_state.get("auth_email"):
    st.sidebar.caption(st.session_state["auth_email"])
st.sidebar.caption(f"We.Reach {get_version()}")

# La verification est mise en cache 10 minutes pour ne pas solliciter le depot
# a chaque clic. Ce bouton la force, pour qui vient d'etre prevenu qu'une
# version est sortie et ne veut pas attendre.
# Cache court : des rendus rapproches ne sollicitent pas le depot, mais le
# fragment qui surveille en arriere-plan obtient une valeur fraiche.
_verifier_version = st.cache_data(ttl=60, show_spinner=False)(version_publiee)

if st.sidebar.button("Vérifier les mises à jour", key="btn_verif_maj",
                     type="tertiary", icon=":material/refresh:"):
    _verifier_version.clear()
    st.session_state["_maj_verifiee"] = True
    st.rerun()

if st.session_state.pop("_maj_verifiee", False):
    if not mise_a_jour_disponible(get_version(), _verifier_version()):
        st.sidebar.success("Vous avez la dernière version.")

def _relancer_tutoriel():
    st.session_state["tutoriel_id"] = uuid4().hex


def _tutoriel_termine():
    # Appelé par le clic JavaScript sur le bouton caché, en fin de visite
    # (Terminer ou Passer) : le tutoriel ne revient plus de lui-même.
    st.session_state.pop("tutoriel_id", None)
    st.session_state["_tutoriel_fini"] = True
    marquer_vu(st.session_state.user_paths.config_dir)


st.sidebar.button("Revoir le tutoriel", key="btn_tutoriel", type="tertiary",
                  icon=":material/school:", on_click=_relancer_tutoriel)
# Invisible (thème) : seul le script de visite le clique.
st.sidebar.button("Tutoriel terminé", key=CLE_FIN, on_click=_tutoriel_termine)

if st.session_state.get("auth_email"):
    if st.sidebar.button("Déconnexion", type="tertiary", icon=":material/logout:"):
        del st.session_state["auth_email"]
        st.rerun()


# --- Annonce des nouveautés -----------------------------------------------
# Une seule fois par version et par personne. La décision (et la mémoire de
# ce qui a déjà été vu) est dans utils/nouveautes.py, testée sans Streamlit.
@st.dialog(f"Nouveautés de la version {get_version()}", width="large")
def _annoncer_nouveautes(notes: str):
    st.markdown(notes)
    if st.button("J'ai compris", type="primary", width="stretch"):
        st.rerun()


_config_dir = st.session_state.user_paths.config_dir
# Lu AVANT doit_annoncer, qui mémorise la version : sinon un nouveau venu
# passerait pour quelqu'un de mis à jour dès son premier rendu.
if "tutoriel_maj" not in st.session_state:
    st.session_state["tutoriel_maj"] = (usage_anterieur(_config_dir)
                                        or version_vue(_config_dir) is not None)

# Tutoriel : au premier lancement et après la mise à jour qui l'apporte, tant
# qu'il n'a été ni terminé ni passé ; ou sur demande (« Revoir le
# tutoriel »). Il remplace alors la fenêtre des nouveautés : jamais les deux.
if tutoriel_a_afficher(_config_dir) or "tutoriel_id" in st.session_state:
    if "tutoriel_id" not in st.session_state:
        st.session_state["tutoriel_id"] = uuid4().hex
    st.html(script_visite(etapes_pour(st.session_state["tutoriel_maj"]),
                          st.session_state["tutoriel_id"]),
            unsafe_allow_javascript=True)
elif not st.session_state.get("_tutoriel_fini"):
    # Seulement hors visite : doit_annoncer mémorise la version, et des
    # nouveautés marquées vues pendant le tutoriel seraient perdues. Juste
    # après la fin du tutoriel, rien ne s'ouvre : elles attendront le
    # lancement suivant (« jamais deux choses au même démarrage »).
    _notes_a_annoncer = doit_annoncer(_config_dir, get_version(), charger_notes())
    if _notes_a_annoncer:
        _annoncer_nouveautes(_notes_a_annoncer)

# --- Bandeau de mise a jour ------------------------------------------------
# La mise a jour ne se faisait qu'au demarrage du lanceur : qui ne ferme
# jamais l'outil ne la recevait jamais. On la signale donc ici, sur toutes les
# pages. Le bouton relance le lanceur, qui ferme l'instance en cours et
# installe la nouvelle version. L'appel reseau est silencieux : hors ligne,
# rien ne s'affiche et l'application fonctionne normalement.
# Fragment : il se ré-exécute tout seul toutes les 5 minutes, sans que la
# personne ait à cliquer où que ce soit. Sans ça, la vérification ne se faisait
# qu'au moment d'une interaction — quelqu'un qui laisse We.Reach ouvert sans y
# toucher pouvait ne jamais être prévenu, ce qui s'est produit en réel.
@st.fragment(run_every="5m")
def _bandeau_mise_a_jour():
    distante = _verifier_version()
    if not mise_a_jour_disponible(get_version(), distante):
        return
    col_msg, col_btn = st.columns([3, 1], vertical_alignment="center")
    with col_msg:
        st.warning(
            f"**Une nouvelle version est disponible ({distante}).** "
            f"Vous utilisez la {get_version()}."
        )
    with col_btn:
        if st.button("Mettre à jour maintenant", type="primary",
                     width="stretch", key="btn_maj"):
            if relancer():
                st.info("We.Reach redémarre avec la nouvelle version…")
            else:
                st.error(
                    "Fermez puis rouvrez We.Reach pour installer la mise à jour."
                )


_bandeau_mise_a_jour()

# ==============================================
# PAGES : chacune vit dans son module sous ui/
# ==============================================
if page == "📊 Dashboard":
    afficher_page_tableau_de_bord()

elif page == "🔍 Recherche":
    afficher_page_recherche()

elif page == "💾 Historique":
    afficher_page_historique()

elif page == "🏢 Veille":
    afficher_page_veille()

elif page == "✉️ Messages":
    afficher_page_messages()

elif page == "📜 Logs":
    afficher_page_journal()

# Après la page : le compteur a pu bouger (recherche, invitations envoyées).
_dessiner_jauge()

# Pas de pied de page : le nom et la version vivent dans la barre latérale.
# L'ancien (« LinkedIn Scraper Pro v2.0 ») contredisait « We.Reach v1.5.x ».
