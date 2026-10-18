# -*- coding: utf-8 -*-
"""Invitations : le bloc « Récupérer les infos et inviter », la jauge du
budget là où l'on invite, la confirmation avant tout envoi, et l'affichage
des résultats d'une recherche.

Le bloc est utilisé par l'onglet Profils similaires et la page Veille. Les
invitations sont rares et irréversibles : les garde-fous (interrupteur
éteint par défaut, plafond du jour vérifié avant tout envoi, récapitulatif
à confirmer) n'existent qu'ici, pour qu'aucun écran ne les oublie.
"""

import re
from datetime import datetime

import pandas as pd
import streamlit as st

# Module (et non « from … import ») : le scraper est résolu à l'appel, donc un
# remplacement de scraper_v2_sync.LinkedInScraperV2Sync (tests) reste effectif.
import scraper_v2_sync
from scraper_v2 import BUDGET_ATTEINT
from ui.composants import afficher_carte_action, afficher_jauge_budget, pluriel
from utils.budget import budget_du_jour

MESSAGE_SESSION_MANQUANTE = (
    "Session LinkedIn manquante : renseignez-la en haut de la page Recherche."
)
AIDE_MESSAGE = (
    "Facultatif, 200 caractères au plus. Laissez vide pour inviter sans note."
)
LIBELLE_CONFIRMER = "Confirmer et lancer"
LIBELLE_ANNULER = "Annuler"
PAGE_HISTORIQUE = "💾 Historique"
PAGE_MESSAGES = "✉️ Messages"

# Colonnes rendues par le moteur → libellés affichés.
_COLONNES_LIEN = ("URL du profil", "URL")
_COLONNES_INVITATION = ("Invitation envoyée", "Invitation")

_SPECIAUX_MARKDOWN = re.compile(r"([\\`*_{}\[\]()#+\-.!$~|>])")


def echapper_markdown(texte) -> str:
    """Le texte tel quel dans un libellé Markdown : un nom venu de LinkedIn
    (« *Marie* », « A_B ») ne doit ni mettre en italique ni casser la mise
    en forme."""
    return _SPECIAUX_MARKDOWN.sub(r"\\\1", str(texte or ""))


def budget():
    """Le budget d'invitations du jour de la personne connectée."""
    return budget_du_jour(st.session_state.user_paths.config_dir)


# --------------------------------------------------------- confirmation

def recap_invitations(n: int, restantes: int, message: str = "") -> str:
    """Ce qui partira, en Markdown sûr : « Jusqu'à 3 invitations partiront
    depuis votre compte LinkedIn ; il vous en restera 0 aujourd'hui. … »"""
    n = max(int(n), 0)
    reste = max(int(restantes) - n, 0)
    verbe = "partira" if n < 2 else "partiront"
    texte = (f"Jusqu'à {pluriel(n, 'invitation')} {verbe} depuis votre compte "
             f"LinkedIn ; il vous en restera {reste} aujourd'hui.")
    message = (message or "").strip()
    if message:
        texte += f" Message joint : « {echapper_markdown(message)} »"
    else:
        texte += " Sans message."
    return texte


def _empreinte(parametres: dict) -> str:
    return repr(sorted(parametres.items(), key=lambda kv: kv[0]))


def _annuler(cle: str) -> None:
    st.session_state.pop(cle, None)


def confirmation(prefixe: str, clic: bool, a_confirmer: bool,
                 parametres: dict, recap: str) -> bool:
    """Vrai quand il faut lancer maintenant.

    Sans action irréversible (`a_confirmer` faux), le clic lance tout de
    suite. Sinon le premier clic affiche le récapitulatif et seul
    « Confirmer et lancer » lance. Toute modification des paramètres depuis
    le premier clic annule la confirmation en attente : on ne confirme que
    ce que l'on a lu.
    """
    cle = f"confirmer_{prefixe}"
    empreinte = _empreinte(parametres)
    if st.session_state.get(cle) not in (None, empreinte):
        st.session_state.pop(cle, None)

    if clic:
        if not a_confirmer:
            st.session_state.pop(cle, None)
            return True
        st.session_state[cle] = empreinte

    if st.session_state.get(cle) != empreinte:
        return False

    zone = st.empty()
    with zone.container(border=True, key=f"{cle}_bloc"):
        st.markdown(recap)
        with st.container(horizontal=True):
            ok = st.button(LIBELLE_CONFIRMER, type="primary", key=f"{cle}_ok")
            st.button(LIBELLE_ANNULER, type="secondary", key=f"{cle}_annuler",
                      on_click=_annuler, args=(cle,))
    if ok:
        st.session_state.pop(cle, None)
        zone.empty()
        return True
    return False


# -------------------------------------------------------------- résultats

def nombre_invitations(df: pd.DataFrame):
    """Invitations envoyées lors du passage, ou None si le tableau ne le dit pas."""
    for col in _COLONNES_INVITATION:
        if col in df.columns:
            return int((df[col].astype(str) == "Oui").sum())
    return None


def resume_resultats(df: pd.DataFrame, inviter: bool) -> str:
    """« 12 profils trouvés · 3 invitations envoyées »"""
    texte = pluriel(len(df), "profil trouvé", "profils trouvés")
    invitations = nombre_invitations(df) if inviter else None
    if invitations is not None:
        texte += " · " + pluriel(invitations, "invitation envoyée", "invitations envoyées")
    return texte


def _aller_a(page: str) -> None:
    st.session_state["page"] = page


def afficher_resultats(df: pd.DataFrame, inviter: bool, nom_export: str,
                       prefixe: str, erreurs=()) -> None:
    """Bilan et suite, tableau lisible, exports et incidents d'un passage."""
    erreurs = list(erreurs or [])
    budget_atteint = BUDGET_ATTEINT in erreurs
    erreurs = [e for e in erreurs if e != BUDGET_ATTEINT]

    if df is not None and not df.empty:
        invitations = nombre_invitations(df) if inviter else None
        with st.container(border=True, key=f"{prefixe}_bilan"):
            afficher_carte_action(
                resume_resultats(df, inviter),
                ("Les profils sont enregistrés dans l'Historique. Les "
                 "acceptations se suivent dans Messages.") if invitations
                else "Les profils sont enregistrés dans l'Historique.",
                ton="ok", icone="ok",
            )
            with st.container(horizontal=True):
                st.button("Voir dans l'Historique", key=f"{prefixe}_vers_historique",
                          icon=":material/database:", on_click=_aller_a,
                          args=(PAGE_HISTORIQUE,))
                if invitations:
                    st.button("Suivre dans Messages", key=f"{prefixe}_vers_messages",
                              icon=":material/mail:", on_click=_aller_a,
                              args=(PAGE_MESSAGES,))

        affiche = df.copy()
        if "Date" in affiche.columns:
            dates = pd.to_datetime(affiche["Date"], errors="coerce")
            affiche["Date"] = dates.dt.strftime("%d/%m/%Y %H:%M").fillna(affiche["Date"])
        config = {}
        for col in _COLONNES_LIEN:
            if col in affiche.columns:
                config[col] = st.column_config.LinkColumn("Profil", display_text="Ouvrir")
        if "Invitation" in affiche.columns:
            config["Invitation"] = st.column_config.TextColumn("Invitation envoyée")
        st.dataframe(affiche, width="stretch", hide_index=True,
                     column_config=config)

        # on_click="ignore" : télécharger ne relance pas la page, sinon les
        # résultats, rendus seulement après le lancement, disparaîtraient.
        c1, c2 = st.columns(2)
        c1.download_button(
            label="Télécharger (Excel)",
            data=st.session_state.export_manager.export_to_excel(df.to_dict('records')),
            file_name=f"{nom_export}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{prefixe}_dl_excel", width="stretch", on_click="ignore",
        )
        c2.download_button(
            label="Télécharger (CSV)",
            data=df.to_csv(index=False, sep=';', encoding='utf-8-sig'),
            file_name=f"{nom_export}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            key=f"{prefixe}_dl_csv", width="stretch", on_click="ignore",
        )

    # Le moteur s'arrête de lui-même au plafond du jour : c'est une issue
    # normale, pas un incident.
    if budget_atteint:
        st.info(BUDGET_ATTEINT)
    if erreurs:
        with st.expander(f"Incidents pendant la recherche ({len(erreurs)})"):
            for err in erreurs:
                st.write(f"- {err}")


# ------------------------------------------------ récupérer et inviter

def _nouveau_scraper():
    return scraper_v2_sync.LinkedInScraperV2Sync(use_database=True, proxy=st.session_state.get('user_proxy'), db_file=str(st.session_state.user_paths.db_file), profiles_csv=str(st.session_state.user_paths.profiles_csv), config_dir=str(st.session_state.user_paths.config_dir))


def _refus_plafond(restantes: int, n: int) -> str:
    return (
        f"Il ne reste que {pluriel(restantes, 'invitation')} aujourd'hui "
        f"pour {pluriel(n, 'profil retenu', 'profils retenus')}. "
        "Désactivez « Envoyer des invitations », ou resserrez la liste "
        "avec les filtres."
    )


def bloc_recuperer_inviter(urls, prefixe: str, libelle_bouton: str = None,
                          nom_export: str = "profils_similaires") -> None:
    st.session_state.setdefault(f"{prefixe}_inviter", False)
    message = ""
    b = None
    with st.container(border=True):
        st.markdown("**Invitations**")
        inviter = st.toggle(
            "Envoyer des invitations", key=f"{prefixe}_inviter",
            help="Une invitation par profil retenu. L'envoi est irréversible.",
        )
        if inviter:
            b = budget()
            afficher_jauge_budget(b.utilisees, b.plafond)
            if b.epuise:
                st.error(
                    "Budget du jour épuisé : les invitations reprennent demain. "
                    "Désactivez les invitations pour récupérer les infos sans inviter."
                )
            elif len(urls) > b.restantes:
                st.error(
                    f"{pluriel(len(urls), 'profil retenu', 'profils retenus')} pour "
                    f"{pluriel(b.restantes, 'invitation restante', 'invitations restantes')} "
                    "aujourd'hui : rien ne partira. Resserrez la liste avec les "
                    "filtres, ou désactivez les invitations."
                )
            message = st.text_area(
                "Message d'invitation",
                placeholder="Bonjour, je serais ravi d'échanger avec vous…",
                max_chars=200,
                help=AIDE_MESSAGE,
                key=f"{prefixe}_message",
            )

    if inviter:
        libelle = "Récupérer les infos et inviter"
        if b is not None and 0 < len(urls) <= b.restantes:
            libelle += f" (jusqu'à {len(urls)})"
    else:
        libelle = libelle_bouton or "Récupérer les infos"

    clic = st.button(libelle, type="primary",
                     width="stretch", key=f"{prefixe}_btn_recuperer")

    # Le plafond du jour est contrôlé avant tout lancement, par le compteur
    # du moteur lui-même : la chaîne partagée ne vérifie qu'« au moins une
    # restante » à l'entrée et s'arrêterait au milieu de la liste, après
    # avoir ouvert Chrome. Contrôlé au premier clic (rien à confirmer si
    # rien ne peut partir) puis de nouveau au lancement.
    restantes = None
    if clic:
        if not st.session_state.global_cookie:
            st.error(MESSAGE_SESSION_MANQUANTE)
            return
        if inviter:
            restantes = _nouveau_scraper().scraper.human.daily_limits.remaining_invitations()
            if len(urls) > restantes:
                st.error(_refus_plafond(restantes, len(urls)))
                st.session_state.pop(f"confirmer_{prefixe}", None)
                return
            st.session_state[f"confirmer_{prefixe}_restantes"] = restantes

    recap = recap_invitations(
        len(urls),
        st.session_state.get(f"confirmer_{prefixe}_restantes",
                             b.restantes if b is not None else 0),
        message,
    )
    parametres = {"urls": tuple(urls), "inviter": inviter, "message": message}
    if not confirmation(prefixe, clic, inviter, parametres, recap):
        return

    scraper = _nouveau_scraper()
    if inviter:
        restantes = scraper.scraper.human.daily_limits.remaining_invitations()
        if len(urls) > restantes:
            st.error(_refus_plafond(restantes, len(urls)))
            return

    progress_bar = st.progress(0)
    status_text = st.empty()
    with st.spinner(f"Récupération en cours : {pluriel(len(urls), 'profil')}…"):
        df = scraper.run_url_scraper(
            cookie=st.session_state.global_cookie,
            urls=urls,
            inviter=inviter,
            message_invitation=message,
            progress_callback=lambda p: progress_bar.progress(min(p, 1.0)),
            status_callback=lambda s: status_text.text(s),
        )

    if df.empty:
        st.warning("Aucun profil récupéré.")
    afficher_resultats(df, inviter, nom_export, prefixe, scraper.errors)
