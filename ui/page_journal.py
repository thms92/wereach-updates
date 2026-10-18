# -*- coding: utf-8 -*-
"""Page 📜 Logs (« Journal ») : journal d'exécution du scraper."""

import os

import streamlit as st

from config import ScraperConfig


def afficher_page_journal():
    st.title("Journal d'exécution")
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
