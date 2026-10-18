# -*- coding: utf-8 -*-
"""Page 📊 Dashboard (« Tableau de bord ») : chiffres clés, graphiques, alertes."""

import pandas as pd
import plotly.express as px
import streamlit as st

from config import ScraperConfig
from wefiit_theme import PALETTE_GRAPHIQUES


def afficher_page_tableau_de_bord():
    st.title("Tableau de bord")

    # Récupérer les statistiques
    stats = st.session_state.db.get_statistiques()

    # Métriques principales
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            label="Profils au fichier",
            value=stats.get('total_profils', 0),
            delta=None
        )

    with col2:
        st.metric(
            label="Invitations envoyées",
            value=stats.get('total_invitations', 0),
            delta=None
        )

    with col3:
        # Un plafond n'est pas une hausse : affiché « n / max » plutôt qu'en
        # delta, que Streamlit dessine en flèche verte montante.
        st.metric(
            label="Invitations aujourd'hui",
            value=f"{stats.get('invitations_aujourdhui', 0)} / {ScraperConfig.MAX_INVITATIONS_PER_DAY}",
            help="Plafond quotidien de sécurité pour votre compte LinkedIn.",
        )

    with col4:
        taux = 0
        if stats.get('total_profils', 0) > 0:
            taux = round((stats.get('total_invitations', 0) / stats.get('total_profils', 0)) * 100, 1)
        st.metric(
            label="Taux d'invitation",
            value=f"{taux:.1f} %".replace(".", ",")
        )

    st.markdown("---")

    # Graphiques
    col1, col2 = st.columns(2)

    with col1:
        st.header("Profils par école")
        if stats.get('par_ecole'):
            df_ecole = pd.DataFrame(
                list(stats['par_ecole'].items()),
                columns=['École', 'Nombre']
            )
            # Couleurs de la marque, pas la palette par défaut de Plotly.
            fig = px.pie(
                df_ecole,
                values='Nombre',
                names='École',
                color_discrete_sequence=PALETTE_GRAPHIQUES,
            )
            fig.update_layout(font_family="Inter, sans-serif",
                              margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Aucune donnée disponible")

    with col2:
        st.header("Dernière recherche")
        if stats.get('derniere_recherche'):
            dr = stats['derniere_recherche']
            st.write(f"**Mots-clés :** {dr.get('keyword') or '—'}")
            st.write(f"**Date :** {str(dr.get('date') or '—')[:16]}")
            st.write(f"**Profils trouvés :** {dr.get('nb_profils', 0)}")
        else:
            st.info("Aucune recherche effectuée")

    # Alertes
    st.markdown("---")
    st.header("Alertes et limites")

    invitations_today = stats.get('invitations_aujourdhui', 0)
    max_invitations = ScraperConfig.MAX_INVITATIONS_PER_DAY

    if invitations_today >= max_invitations:
        st.error(f"🚫 Limite d'invitations atteinte ({invitations_today}/{max_invitations})")
    elif invitations_today >= max_invitations * 0.8:
        st.warning(f"⚠️ Proche de la limite ({invitations_today}/{max_invitations})")
    else:
        st.success(f"✅ Marge disponible ({invitations_today}/{max_invitations})")
