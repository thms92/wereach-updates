# -*- coding: utf-8 -*-
"""Choisir parmi des profils trouvés, avant d'inviter ou d'enregistrer.

Commun aux onglets « Par critères » et « Profils similaires » : un tableau
à cases, « Tout sélectionner / Tout désélectionner » et un compteur. Les
choix vivent dans `st.session_state[f"{prefixe}_choix"]` (`{url: bool}`) ;
tout est coché par défaut, sauf les profils marqués `deja` (déjà dans le
fichier), qu'on ne réinvite pas sans le vouloir.
"""

import pandas as pd
import streamlit as st

from ui.composants import pluriel


def reinitialiser_choix(prefixe: str) -> None:
    """À appeler quand une nouvelle liste arrive : les choix repartent du
    défaut, et le tableau est redessiné à neuf."""
    st.session_state[f"{prefixe}_choix"] = None
    _nouvelle_version(prefixe)


def _nouvelle_version(prefixe: str) -> None:
    cle = f"{prefixe}_version_choix"
    st.session_state[cle] = st.session_state.get(cle, 0) + 1


def _par_defaut(profil: dict) -> bool:
    return not profil.get("deja")


def choisir_profils(profils: list, prefixe: str, note: str = "") -> list:
    """Affiche le tableau de choix ; rend les profils cochés.

    `note` complète le compteur (par exemple « 11 écartés par les filtres »).
    """
    if not profils:
        return []
    cle_choix = f"{prefixe}_choix"
    if st.session_state.get(cle_choix) is None:
        st.session_state[cle_choix] = {p.get("url"): _par_defaut(p) for p in profils}
    choix = st.session_state[cle_choix]

    def _tout(valeur):
        st.session_state[cle_choix] = {p.get("url"): valeur for p in profils}
        _nouvelle_version(prefixe)

    b1, b2, b3 = st.columns([1, 1, 3], vertical_alignment="center")
    b1.button("Tout sélectionner", key=f"{prefixe}_tout", width="stretch",
              on_click=_tout, args=(True,))
    b2.button("Tout désélectionner", key=f"{prefixe}_rien", width="stretch",
              on_click=_tout, args=(False,))

    avec_deja = any(p.get("deja") for p in profils)
    lignes = []
    for p in profils:
        ligne = {
            "Choisir": bool(choix.get(p.get("url"), _par_defaut(p))),
            "Nom": p.get("nom") or "",
            "Intitulé": p.get("intitule") or "",
            "Relation": p.get("degre") or "",
            "Invitable": "Oui" if p.get("invitable") else "Non",
        }
        if avec_deja:
            ligne["Déjà au fichier"] = "Oui" if p.get("deja") else ""
        ligne["Profil"] = p.get("url") or ""
        lignes.append(ligne)
    tableau = pd.DataFrame(lignes)
    figees = [c for c in tableau.columns if c != "Choisir"]
    edite = st.data_editor(
        tableau,
        key=f"{prefixe}_tableau_{st.session_state.get(f'{prefixe}_version_choix', 0)}",
        hide_index=True, width="stretch",
        height=min(36 * (len(tableau) + 1) + 12, 760),
        disabled=figees,
        column_config={
            "Choisir": st.column_config.CheckboxColumn("Choisir", width="small"),
            "Profil": st.column_config.LinkColumn("Profil", display_text="Ouvrir", width="small"),
            "Relation": st.column_config.TextColumn(
                "Relation", width="small",
                help="2e : un contact en commun ; 3e : plus éloigné."),
            "Invitable": st.column_config.TextColumn("Invitable", width="small"),
        },
    )
    st.session_state[cle_choix] = dict(zip(edite["Profil"], edite["Choisir"]))
    choisis = [p for p in profils
               if st.session_state[cle_choix].get(p.get("url"), _par_defaut(p))]
    compteur = f"{pluriel(len(choisis), 'profil choisi', 'profils choisis')} sur {len(profils)}"
    b3.caption(f"{compteur} ({note})" if note else compteur)
    return choisis
