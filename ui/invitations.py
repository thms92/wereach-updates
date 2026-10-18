# -*- coding: utf-8 -*-
"""Invitations : le bloc « Récupérer les infos et inviter », la jauge du
budget là où l'on invite, et l'affichage des résultats d'une recherche.

Le bloc est utilisé par l'onglet Profils similaires et la page Veille. Les
invitations sont rares et irréversibles : les garde-fous (case décochée par
défaut, plafond du jour vérifié avant tout envoi) n'existent qu'ici, pour
qu'aucun écran ne les oublie.
"""

from datetime import datetime

import pandas as pd
import streamlit as st

# Module (et non « from … import ») : le scraper est résolu à l'appel, donc un
# remplacement de scraper_v2_sync.LinkedInScraperV2Sync (tests) reste effectif.
import scraper_v2_sync
from ui.composants import afficher_jauge_budget, pluriel
from utils.budget import budget_du_jour

MESSAGE_SESSION_MANQUANTE = (
    "Session LinkedIn manquante : renseignez-la en haut de la page Recherche."
)
AIDE_MESSAGE = (
    "Facultatif, 200 caractères au plus. Laissez vide pour inviter sans note."
)

# Colonnes rendues par le moteur → libellés affichés.
_COLONNES_LIEN = ("URL du profil", "URL")
_COLONNES_INVITATION = ("Invitation envoyée", "Invitation")


def budget():
    """Le budget d'invitations du jour de la personne connectée."""
    return budget_du_jour(st.session_state.user_paths.config_dir)


def nombre_invitations(df: pd.DataFrame):
    """Invitations envoyées lors du passage, ou None si le tableau ne le dit pas."""
    for col in _COLONNES_INVITATION:
        if col in df.columns:
            return int((df[col].astype(str) == "Oui").sum())
    return None


def resume_resultats(df: pd.DataFrame, inviter: bool) -> str:
    """« 12 profils trouvés, 8 invitations envoyées. Suivez les réponses dans Messages. »"""
    texte = pluriel(len(df), "profil trouvé", "profils trouvés")
    invitations = nombre_invitations(df) if inviter else None
    if invitations is not None:
        texte += ", " + pluriel(invitations, "invitation envoyée", "invitations envoyées")
    texte += "."
    if invitations:
        texte += " Suivez les réponses dans Messages."
    return texte


def afficher_resultats(df: pd.DataFrame, inviter: bool, nom_export: str,
                       prefixe: str, erreurs=()) -> None:
    """Bilan, tableau lisible, exports et incidents d'un passage."""
    if df is not None and not df.empty:
        st.success(resume_resultats(df, inviter))

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
        st.dataframe(affiche, use_container_width=True, hide_index=True,
                     column_config=config)

        c1, c2 = st.columns(2)
        c1.download_button(
            label="Télécharger (Excel)",
            data=st.session_state.export_manager.export_to_excel(df.to_dict('records')),
            file_name=f"{nom_export}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{prefixe}_dl_excel", use_container_width=True,
        )
        c2.download_button(
            label="Télécharger (CSV)",
            data=df.to_csv(index=False, sep=';', encoding='utf-8-sig'),
            file_name=f"{nom_export}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            key=f"{prefixe}_dl_csv", use_container_width=True,
        )

    erreurs = list(erreurs or [])
    if erreurs:
        with st.expander(f"Incidents pendant la recherche ({len(erreurs)})"):
            for err in erreurs:
                st.write(f"- {err}")


def bloc_recuperer_inviter(urls, prefixe: str, libelle_bouton: str = None,
                          nom_export: str = "profils_similaires") -> None:
    st.session_state.setdefault(f"{prefixe}_inviter", False)
    message = ""
    with st.container(border=True):
        st.markdown("**Invitations**")
        inviter = st.checkbox(
            "Envoyer des invitations", key=f"{prefixe}_inviter",
            help="Une invitation par profil retenu. L'envoi est irréversible.",
        )
        if inviter:
            b = budget()
            afficher_jauge_budget(b.utilisees, b.plafond)
            if b.epuise:
                st.error(
                    "Budget du jour épuisé : les invitations reprennent demain. "
                    "Décochez la case pour récupérer les infos sans inviter."
                )
            elif len(urls) > b.restantes:
                st.error(
                    f"{pluriel(len(urls), 'profil retenu', 'profils retenus')} pour "
                    f"{pluriel(b.restantes, 'invitation restante', 'invitations restantes')} "
                    "aujourd'hui : rien ne partira. Resserrez la liste avec les "
                    "filtres, ou décochez la case."
                )
            message = st.text_area(
                "Message d'invitation",
                placeholder="Bonjour, je serais ravi d'échanger avec vous…",
                max_chars=200,
                help=AIDE_MESSAGE,
                key=f"{prefixe}_message",
            )

    if libelle_bouton is None:
        libelle_bouton = "Récupérer les infos et inviter" if inviter else "Récupérer les infos"

    if st.button(libelle_bouton, type="primary",
                 use_container_width=True, key=f"{prefixe}_btn_recuperer"):
        if not st.session_state.global_cookie:
            st.error(MESSAGE_SESSION_MANQUANTE)
            return
        scraper = scraper_v2_sync.LinkedInScraperV2Sync(use_database=True, proxy=st.session_state.get('user_proxy'), db_file=str(st.session_state.user_paths.db_file), profiles_csv=str(st.session_state.user_paths.profiles_csv), config_dir=str(st.session_state.user_paths.config_dir))

        # Le plafond du jour est contrôlé ici, avant tout lancement, par le
        # compteur du moteur lui-même : la chaîne partagée ne vérifie
        # qu'« au moins une restante » à l'entrée et s'arrêterait au milieu
        # de la liste, après avoir ouvert Chrome.
        restantes = None
        if inviter:
            restantes = scraper.scraper.human.daily_limits.remaining_invitations()

        if restantes is not None and len(urls) > restantes:
            st.error(
                f"Il ne reste que {pluriel(restantes, 'invitation')} aujourd'hui "
                f"pour {pluriel(len(urls), 'profil retenu', 'profils retenus')}. "
                "Décochez « Envoyer des invitations », ou resserrez la liste "
                "avec les filtres."
            )
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
