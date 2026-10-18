# -*- coding: utf-8 -*-
"""Page ✉️ Messages : acceptations d'invitation et messages de suivi."""

import streamlit as st

# Résolu à l'appel, pas à l'import : le remplacement de
# scraper_v2_sync.LinkedInScraperV2Sync (tests) reste effectif.
import scraper_v2_sync
from utils.verrou_linkedin import message_occupe


def afficher_page_messages():
    st.title("Suivi et messages")
    st.caption("Détecte qui a accepté ton invitation, puis envoie-leur un message.")

    _ckm = st.session_state.global_cookie
    if not _ckm:
        st.warning("⚠️ Renseigne d'abord ton **cookie li_at** dans la page **Recherche**.")
    else:
        _masked_m = f"{_ckm[:6]}…{_ckm[-4:]}" if len(_ckm) > 12 else _ckm
        st.markdown(
            '<div style="display:flex;align-items:center;gap:10px;padding:10px 14px;'
            'background:var(--wf-surface);border:1px solid var(--wf-border);'
            'border-left:3px solid var(--wf-success);border-radius:12px;margin-bottom:14px">'
            '<span style="width:9px;height:9px;border-radius:50%;background:var(--wf-success)"></span>'
            f'<span style="font-size:.8rem;color:var(--wf-muted)">Session LinkedIn active · li_at · {_masked_m}</span></div>',
            unsafe_allow_html=True,
        )

        def _new_scraper():
            return scraper_v2_sync.LinkedInScraperV2Sync(
                use_database=True, proxy=st.session_state.get('user_proxy'),
                db_file=str(st.session_state.user_paths.db_file),
                profiles_csv=str(st.session_state.user_paths.profiles_csv),
                config_dir=str(st.session_state.user_paths.config_dir),
            )

        # ── 1. Détecter les acceptations ──
        en_attente = st.session_state.db.invitations_en_attente()
        cA, cB = st.columns([3, 1])
        cA.markdown(f"**{len(en_attente)}** invitation(s) en attente à vérifier.")
        if cB.button("🔄 Vérifier qui a accepté", type="primary",
                     use_container_width=True, disabled=len(en_attente) == 0):
            with st.spinner("Vérification en cours (revisite des profils invités)…"):
                sc = _new_scraper()
                pb = st.progress(0); stt = st.empty()
                acceptees = sc.verifier_acceptations(
                    cookie=_ckm, profils=en_attente, max_check=30,
                    progress_callback=lambda p: pb.progress(p),
                    status_callback=lambda s: stt.text(s),
                )
                for a in acceptees:
                    st.session_state.db.marquer_acceptee(a["url"])
                # Session occupée : rien n'a été vérifié, ce n'est pas « aucune acceptation ».
                occupe = message_occupe(sc.errors)
                if occupe:
                    st.error(f"❌ {occupe}")
                elif acceptees:
                    st.success(f"✅ {len(acceptees)} personne(s) ont accepté ton invitation !")
                else:
                    st.info("Aucune nouvelle acceptation détectée pour l'instant.")
                if sc.errors and not occupe:
                    with st.expander("⚠️ Détails"):
                        for e in sc.errors:
                            st.write(f"- {e}")

        st.markdown("---")

        # ── 2. Envoyer les messages ──
        st.header("Message aux personnes qui ont accepté")
        acc = st.session_state.db.acceptees_non_messagees()
        if not acc:
            st.info("Personne à messager pour l'instant. Lance d'abord la vérification ci-dessus.")
        else:
            message = st.text_area(
                "Modèle de message",
                placeholder="Bonjour, ravi(e) d'être en contact ! …",
                height=120,
            )
            st.caption(f"{len(acc)} personne(s) ont accepté et n'ont pas encore été messagées "
                       f"(max 20 envois par lot).")
            choix = {}
            for a in acc:
                sous = " · ".join(x for x in [a.get("poste"), a.get("entreprise")] if x)
                label = f"{a['nom']}" + (f" — {sous}" if sous else "")
                choix[a["url"]] = st.checkbox(label, key=f"msg_{a['url']}")
            sel = [a for a in acc if choix.get(a["url"])]
            if st.button(f"✉️ Envoyer les messages ({len(sel)})", type="primary",
                         disabled=(len(sel) == 0 or not message.strip())):
                with st.spinner("Envoi des messages…"):
                    sc = _new_scraper()
                    pb = st.progress(0); stt = st.empty()
                    envoyes = sc.envoyer_messages(
                        cookie=_ckm, cibles=sel, message=message, max_msg=20,
                        progress_callback=lambda p: pb.progress(p),
                        status_callback=lambda s: stt.text(s),
                    )
                    for e in envoyes:
                        st.session_state.db.marquer_messagee(e["url"])
                    # Session occupée : rien n'est parti ; le dire, et ne pas
                    # relancer la page, qui effacerait l'explication.
                    occupe = message_occupe(sc.errors)
                    if occupe:
                        st.error(f"❌ {occupe}")
                    else:
                        st.success(f"✅ {len(envoyes)} message(s) envoyé(s).")
                        if sc.errors:
                            with st.expander("⚠️ Détails"):
                                for er in sc.errors:
                                    st.write(f"- {er}")
                        st.rerun()
