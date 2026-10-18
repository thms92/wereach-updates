# -*- coding: utf-8 -*-
"""Page « Historique » : profils enregistrés, recherche, filtres et export."""

from datetime import datetime, timedelta
from typing import Iterable, Optional

import pandas as pd
import streamlit as st

from config import ECOLES
from ui.composants import afficher_bandeau_contexte, afficher_etat_vide, pluriel
from utils.ecoles import libelle_vise_ecole

PERIODES = {"Tout": None, "7 derniers jours": 7, "30 derniers jours": 30}

# Colonnes lisibles : les noms techniques de la base et l'index pandas
# n'ont rien à faire à l'écran.
COLONNES = {
    "nom": "Nom", "poste": "Poste", "entreprise": "Entreprise",
    "ecole": "École", "localisation": "Localisation",
    "invitation_envoyee": "Invitation", "date_scraping": "Ajouté le",
    "url": "Profil",
}
_CHAMPS_RECHERCHE = ("nom", "poste", "entreprise", "ecole", "localisation")


def filtrer_profils(df: pd.DataFrame, recherche: str = "",
                    ecoles: Iterable[str] = (), periode: str = "Tout",
                    seulement_invites: bool = False,
                    maintenant: Optional[datetime] = None) -> pd.DataFrame:
    """Filtre côté client : texte libre (nom, poste, entreprise, école,
    lieu ; insensible à la casse), écoles (une suffit), période d'ajout."""
    if df.empty:
        return df
    masque = pd.Series(True, index=df.index)

    texte = (recherche or "").strip().casefold()
    if texte:
        champs = [c for c in _CHAMPS_RECHERCHE if c in df.columns]
        botte = df[champs].fillna("").astype(str).agg(" ".join, axis=1).str.casefold()
        for mot in texte.split():
            masque &= botte.str.contains(mot, regex=False)

    ecoles = list(ecoles or [])
    if ecoles and "ecole" in df.columns:
        # La colonne `ecole` peut porter plusieurs écoles (« Dauphine / ESCP ») :
        # on retient le profil dès qu'une école choisie figure dans le libellé.
        masque &= df["ecole"].apply(
            lambda lib: isinstance(lib, str) and any(libelle_vise_ecole(lib, e) for e in ecoles))

    jours = PERIODES.get(periode)
    if jours and "date_scraping" in df.columns:
        limite = (maintenant or datetime.now()) - timedelta(days=jours)
        dates = pd.to_datetime(df["date_scraping"], errors="coerce")
        masque &= dates >= limite

    if seulement_invites and "invitation_envoyee" in df.columns:
        masque &= df["invitation_envoyee"] == "Oui"

    return df[masque]


def afficher_page_historique():
    st.title("Historique des profils")

    limite = st.session_state.get("hist_limite", 1000)
    profils = st.session_state.db.get_tous_profils(limit=limite)
    try:
        total = int(st.session_state.db.get_statistiques().get("total_profils", len(profils)))
    except Exception:
        total = len(profils)
    afficher_bandeau_contexte(
        "Tous les profils trouvés par vos recherches, du plus récent au plus ancien.",
        [(pluriel(max(total, len(profils)), "profil"), "neutre")],
    )

    if not profils:
        afficher_etat_vide(
            "Aucun profil pour l'instant.",
            "Les profils trouvés depuis la page Recherche sont enregistrés ici "
            "automatiquement.",
        )
        return

    recherche = st.text_input(
        "Rechercher", placeholder="Rechercher un nom, un poste, une entreprise…",
        key="hist_recherche", label_visibility="collapsed",
        icon=":material/search:",
    )
    col1, col2, col3, col4 = st.columns([3, 1.6, 1.4, 1.6], vertical_alignment="bottom")
    with col1:
        ecoles = st.multiselect("École", list(ECOLES.keys()),
                                placeholder="Choisir des écoles…", key="hist_ecoles")
    with col2:
        periode = st.selectbox("Période", list(PERIODES), key="hist_periode")
    with col3:
        st.number_input("Profils chargés", min_value=10, max_value=5000, value=1000,
                        step=100, key="hist_limite",
                        help="Les plus récents d'abord. Augmentez pour remonter plus loin.")
    with col4:
        seulement_invites = st.checkbox("Seulement les invités", key="hist_invites")

    df = filtrer_profils(pd.DataFrame(profils), recherche, ecoles, periode, seulement_invites)

    st.caption(pluriel(len(df), "profil trouvé", "profils trouvés"))

    if df.empty:
        afficher_etat_vide(
            "Aucun profil ne correspond.",
            "Essayez un autre mot, retirez une école ou élargissez la période.",
        )
        return

    affichage = df[[c for c in COLONNES if c in df.columns]].rename(columns=COLONNES)
    if "Ajouté le" in affichage.columns:
        affichage["Ajouté le"] = pd.to_datetime(affichage["Ajouté le"], errors="coerce")
    # Le plus utile d'abord : à 1440 px, seule la localisation peut être coupée.
    ordre = ["Nom", "Poste", "Entreprise", "École", "Ajouté le", "Profil",
             "Invitation", "Localisation"]
    affichage = affichage[[c for c in ordre if c in affichage.columns]]
    st.dataframe(
        affichage, hide_index=True, width="stretch",
        height=min(38 + 35 * len(affichage), 600),
        column_config={
            "Nom": st.column_config.TextColumn("Nom", width=160),
            "Poste": st.column_config.TextColumn("Poste", width=240),
            "Entreprise": st.column_config.TextColumn("Entreprise", width=170),
            "École": st.column_config.TextColumn("École", width=130),
            "Ajouté le": st.column_config.DatetimeColumn("Ajouté le", format="DD/MM/YYYY",
                                                         width=100),
            "Profil": st.column_config.LinkColumn("Profil", display_text="Ouvrir", width=65),
            "Invitation": st.column_config.TextColumn("Invitation", width=80),
            "Localisation": st.column_config.TextColumn("Localisation", width=170),
        },
    )

    # Export : ce qui est affiché, filtres compris.
    horodatage = datetime.now().strftime('%Y%m%d_%H%M%S')
    lignes = df.to_dict('records')
    with st.container(horizontal=True, gap="small"):
        st.download_button(
            label="Télécharger en Excel",
            data=st.session_state.export_manager.export_to_excel(lignes),
            file_name=f"historique_{horodatage}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            icon=":material/download:",
        )
        st.download_button(
            label="Télécharger en CSV",
            data=st.session_state.export_manager.export_to_csv(lignes),
            file_name=f"historique_{horodatage}.csv",
            mime="text/csv",
            icon=":material/download:",
        )
