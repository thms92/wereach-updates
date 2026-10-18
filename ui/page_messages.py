# -*- coding: utf-8 -*-
"""Page « Messages » : acceptations d'invitation et messages de suivi.

Deux étapes : 1) vérifier qui a accepté ; 2) choisir des personnes et leur
écrire. Le moteur envoie le message tel quel, sans variable de
personnalisation : la page n'en promet donc aucune.
"""

from html import escape

import streamlit as st

# Résolu à l'appel, pas à l'import : le remplacement de
# scraper_v2_sync.LinkedInScraperV2Sync (tests) reste effectif.
import scraper_v2_sync
from ui.composants import afficher_bandeau_contexte, afficher_etat_vide, pluriel
from utils.verrou_linkedin import message_occupe

MAX_ENVOIS = 20
LIBELLE_VERIFIER = "Vérifier qui a accepté"
LIBELLE_TOUT = "Tout sélectionner"
LIBELLE_RIEN = "Tout désélectionner"


def cle_case(url: str) -> str:
    """Clé de la case à cocher d'une personne (stable : des tests s'en servent)."""
    return f"msg_{url}"


def libelle_envoi(n: int) -> str:
    return f"Envoyer à {pluriel(n, 'personne')}" if n else "Envoyer"


def raison_envoi_impossible(nb_selection: int, message: str):
    """Pourquoi le bouton d'envoi est inactif, ou None s'il est actif."""
    manque_sel, manque_msg = nb_selection == 0, not (message or "").strip()
    if manque_sel and manque_msg:
        return "Cochez au moins une personne et écrivez votre message pour pouvoir envoyer."
    if manque_sel:
        return "Cochez au moins une personne pour pouvoir envoyer."
    if manque_msg:
        return "Écrivez votre message pour pouvoir envoyer."
    return None


def _cocher_tout(urls, valeur: bool):
    for url in urls:
        st.session_state[cle_case(url)] = valeur


def afficher_page_messages():
    st.title("Suivi et messages")

    db = st.session_state.db
    en_attente = db.invitations_en_attente()
    acc = db.acceptees_non_messagees()
    _ckm = st.session_state.global_cookie

    puces = [
        (pluriel(len(en_attente), "invitation en attente", "invitations en attente"), "neutre"),
        (pluriel(len(acc), "personne à contacter", "personnes à contacter"),
         "accent" if acc else "neutre"),
    ]
    if _ckm:
        puces.append(("Session LinkedIn active", "ok", True))
    afficher_bandeau_contexte(
        "Relancez les personnes qui ont accepté votre invitation.", puces)

    if not _ckm:
        st.warning("Connectez d'abord votre **session LinkedIn** depuis la page **Recherche** : "
                   "elle est nécessaire pour vérifier les acceptations et envoyer des messages.")
        return

    def _new_scraper():
        return scraper_v2_sync.LinkedInScraperV2Sync(
            use_database=True, proxy=st.session_state.get('user_proxy'),
            db_file=str(st.session_state.user_paths.db_file),
            profiles_csv=str(st.session_state.user_paths.profiles_csv),
            config_dir=str(st.session_state.user_paths.config_dir),
        )

    # ── Étape 1 : détecter les acceptations ──
    st.subheader("1. Vérifier qui a accepté")
    if en_attente:
        cA, cB = st.columns([3, 1], vertical_alignment="center")
        cA.markdown(
            f"{pluriel(len(en_attente), 'invitation')} en attente de réponse. "
            "We.Reach revisite les profils invités pour repérer ceux qui ont accepté "
            "(30 au plus par vérification)."
        )
        lancer = cB.button(LIBELLE_VERIFIER, type="primary", width="stretch",
                           icon=":material/how_to_reg:")
    else:
        afficher_etat_vide(
            "Aucune invitation en attente.",
            "Les personnes que vous invitez depuis Recherche ou Veille apparaîtront ici.",
        )
        # Inactif, et visiblement inactif : un bouton principal désactivé
        # garde la couleur d'accent du thème.
        lancer = st.button(LIBELLE_VERIFIER, type="secondary", disabled=True,
                           icon=":material/how_to_reg:")

    if lancer:
        with st.spinner("Vérification en cours : We.Reach revisite les profils invités…"):
            sc = _new_scraper()
            pb = st.progress(0); stt = st.empty()
            acceptees = sc.verifier_acceptations(
                cookie=_ckm, profils=en_attente, max_check=30,
                progress_callback=lambda p: pb.progress(p),
                status_callback=lambda s: stt.text(s),
            )
            for a in acceptees:
                db.marquer_acceptee(a["url"])
            # Session occupée : rien n'a été vérifié, ce n'est pas « aucune acceptation ».
            occupe = message_occupe(sc.errors)
            if occupe:
                st.error(occupe)
            elif acceptees:
                n = len(acceptees)
                verbe = "a accepté" if n < 2 else "ont accepté"
                st.success(f"{pluriel(n, 'personne')} {verbe} votre invitation.")
                acc = db.acceptees_non_messagees()
            else:
                st.info("Aucune nouvelle acceptation pour l'instant. Réessayez dans quelques jours.")
            if sc.errors and not occupe:
                with st.expander("Détails"):
                    for e in sc.errors:
                        st.write(f"- {e}")

    st.divider()

    # ── Étape 2 : écrire aux personnes qui ont accepté ──
    st.subheader("2. Écrire aux personnes qui ont accepté")
    if not acc:
        afficher_etat_vide(
            "Personne à contacter pour l'instant.",
            "Les personnes qui acceptent votre invitation apparaîtront ici "
            "après la vérification de l'étape 1.",
        )
        return

    urls = [a["url"] for a in acc]
    col_info, col_tout, col_rien = st.columns([4, 1.4, 1.6], vertical_alignment="center")
    col_info.markdown(
        f"{pluriel(len(acc), 'personne a', 'personnes ont')} accepté et "
        f"{'n’a' if len(acc) < 2 else 'n’ont'} pas encore reçu de message."
    )
    col_tout.button(LIBELLE_TOUT, key="msg_tout", width="stretch",
                    on_click=_cocher_tout, args=(urls, True))
    col_rien.button(LIBELLE_RIEN, key="msg_rien", width="stretch",
                    on_click=_cocher_tout, args=(urls, False))

    choix = {}
    with st.container(border=True):
        for a in acc:
            sous = " · ".join(x for x in [a.get("poste"), a.get("entreprise")] if x)
            label = f"**{a['nom']}**" + (f" — {sous}" if sous else "")
            choix[a["url"]] = st.checkbox(label, key=cle_case(a["url"]))
    sel = [a for a in acc if choix.get(a["url"])]

    message = st.text_area(
        "Votre message",
        key="msg_modele",
        placeholder="Bonjour, merci d'avoir accepté mon invitation. …",
        height=140,
        help=("Le même texte est envoyé à chaque personne cochée, tel quel : "
              "aucun prénom ni autre information n'est inséré automatiquement. "
              "Écrivez-le pour qu'il convienne à tous."),
    )

    if message.strip():
        st.caption("Aperçu, tel que chaque personne le recevra")
        st.markdown(
            '<div style="white-space:pre-wrap;padding:12px 14px;border:1px solid var(--wf-border);'
            'border-radius:12px;background:var(--wf-surface);color:var(--wf-text);'
            f'font-size:.95rem;line-height:1.5">{escape(message)}</div>',
            unsafe_allow_html=True,
        )

    raison = raison_envoi_impossible(len(sel), message)
    if len(sel) > MAX_ENVOIS:
        st.warning(f"{MAX_ENVOIS} envois au plus par lot : seules les {MAX_ENVOIS} premières "
                   "personnes cochées recevront le message. Relancez ensuite pour les suivantes.")
    envoyer = st.button(
        libelle_envoi(min(len(sel), MAX_ENVOIS)),
        type="secondary" if raison else "primary",
        disabled=raison is not None, icon=":material/send:", key="msg_envoyer",
    )
    if raison:
        st.caption(raison)

    if envoyer:
        with st.spinner("Envoi des messages…"):
            sc = _new_scraper()
            pb = st.progress(0); stt = st.empty()
            envoyes = sc.envoyer_messages(
                cookie=_ckm, cibles=sel, message=message, max_msg=MAX_ENVOIS,
                progress_callback=lambda p: pb.progress(p),
                status_callback=lambda s: stt.text(s),
            )
            for e in envoyes:
                db.marquer_messagee(e["url"])
            # Session occupée : rien n'est parti ; le dire, et ne pas
            # relancer la page, qui effacerait l'explication.
            occupe = message_occupe(sc.errors)
            if occupe:
                st.error(occupe)
            else:
                n = len(envoyes)
                st.success(f"{pluriel(n, 'message envoyé', 'messages envoyés')}.")
                if sc.errors:
                    with st.expander("Détails"):
                        for er in sc.errors:
                            st.write(f"- {er}")
                st.rerun()
