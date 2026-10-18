# -*- coding: utf-8 -*-
"""Page 💾 Historique : profils au fichier, filtres et export."""

from datetime import datetime

import pandas as pd
import streamlit as st

from config import ECOLES
from utils.ecoles import libelle_vise_ecole


def afficher_page_historique():
    st.title("Historique des profils")

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
            # La colonne `ecole` peut porter plusieurs écoles (« Dauphine / ESCP ») :
            # on retient le profil dès que l'école choisie figure dans le libellé.
            df = df[df['ecole'].apply(lambda lib: libelle_vise_ecole(lib, filtre_ecole))]

        if afficher_invitations:
            df = df[df['invitation_envoyee'] == 'Oui']

        st.write(f"**{len(df)} profils trouvés**")

        # Colonnes lisibles : les noms techniques de la base et l'index pandas
        # n'ont rien à faire à l'écran.
        colonnes = {
            "nom": "Nom", "poste": "Poste", "entreprise": "Entreprise",
            "ecole": "École", "localisation": "Localisation",
            "invitation_envoyee": "Invitation", "date_scraping": "Ajouté le",
            "url": "Profil",
        }
        affichage = df[[c for c in colonnes if c in df.columns]].rename(columns=colonnes)
        st.dataframe(
            affichage, hide_index=True, width="stretch",
            column_config={"Profil": st.column_config.LinkColumn("Profil", display_text="Ouvrir")},
        )

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
