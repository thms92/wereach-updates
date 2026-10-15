# -*- coding: utf-8 -*-
"""« Récupérer les infos et inviter » : un seul bloc pour tout l'outil.

Utilisé par l'onglet Profils similaires et la page Veille. Les invitations
sont rares et irréversibles : les garde-fous (case décochée par défaut,
plafond du jour vérifié avant tout envoi) n'existent qu'ici, pour qu'aucun
écran ne les oublie.
"""

from datetime import datetime

import streamlit as st

# Module (et non « from … import ») : le scraper est résolu à l'appel, donc un
# remplacement de scraper_v2_sync.LinkedInScraperV2Sync (tests) reste effectif.
import scraper_v2_sync


def bloc_recuperer_inviter(urls, prefixe: str, libelle_bouton: str = "🚀 Récupérer les infos") -> None:
    st.markdown("**Étape 2 — récupérer les infos de ces profils**")
    st.caption(
        "Chaque profil est ouvert pour en lire le poste et la "
        "société. Cochez la case pour envoyer en même temps une "
        "invitation."
    )

    st.session_state.setdefault(f"{prefixe}_inviter", False)
    inviter = st.checkbox(
        "Envoyer des invitations", key=f"{prefixe}_inviter"
    )
    if inviter:
        message = st.text_area(
            "Message d'invitation",
            placeholder="Message personnalisé...",
            max_chars=200,
            key=f"{prefixe}_message",
        )
    else:
        message = ""

    if st.button(libelle_bouton, type="primary",
                 use_container_width=True, key=f"{prefixe}_btn_recuperer"):
        if not st.session_state.global_cookie:
            st.error("❌ Cookie manquant")
        else:
            scraper = scraper_v2_sync.LinkedInScraperV2Sync(use_database=True, proxy=st.session_state.get('user_proxy'), db_file=str(st.session_state.user_paths.db_file), profiles_csv=str(st.session_state.user_paths.profiles_csv), config_dir=str(st.session_state.user_paths.config_dir))

            # Le plafond du jour est contrôlé ici, avant tout
            # lancement : la chaîne partagée ne vérifie qu'« au
            # moins une restante » à l'entrée et s'arrêterait au
            # milieu de la liste, après avoir ouvert Chrome.
            restantes = None
            if inviter:
                restantes = (
                    scraper.scraper.human.daily_limits
                    .remaining_invitations()
                )

            if restantes is not None and len(urls) > restantes:
                st.error(
                    f"❌ Il ne reste que {restantes} invitation(s) "
                    f"aujourd'hui pour {len(urls)} profil(s) "
                    f"retenu(s). Décochez « Envoyer des "
                    f"invitations », ou resserrez la liste avec "
                    f"les filtres."
                )
            else:
                progress_bar = st.progress(0)
                status_text = st.empty()

                with st.spinner(f"🔄 {len(urls)} profils en cours..."):
                    df = scraper.run_url_scraper(
                        cookie=st.session_state.global_cookie,
                        urls=urls,
                        inviter=inviter,
                        message_invitation=message,
                        progress_callback=lambda p: progress_bar.progress(min(p, 1.0)),
                        status_callback=lambda s: status_text.text(s),
                    )

                if not df.empty:
                    st.success(f"✅ {len(df)} profils récupérés sur {len(urls)} !")
                    st.dataframe(df, use_container_width=True)

                    excel_data = st.session_state.export_manager.export_to_excel(df.to_dict('records'))
                    st.download_button(
                        label="📥 Télécharger Excel",
                        data=excel_data,
                        file_name=f"profils_similaires_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"{prefixe}_dl_excel",
                    )

                    csv_data = df.to_csv(index=False, sep=';', encoding='utf-8-sig')
                    st.download_button(
                        label="📥 Télécharger CSV",
                        data=csv_data,
                        file_name=f"profils_similaires_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        key=f"{prefixe}_dl_csv",
                    )
                else:
                    st.warning("⚠️ Aucun profil récupéré")

                if scraper.errors:
                    with st.expander(f"⚠️ Erreurs ({len(scraper.errors)})"):
                        for err in scraper.errors:
                            st.write(f"- {err}")
