# -*- coding: utf-8 -*-
"""Page Recherche : session LinkedIn, Candidats, Clients et entreprises,
Profils similaires."""

import pandas as pd
import streamlit as st

from config import ECOLES, CONCURRENTS, SECTEURS
from scraper_v2 import LinkedInScraperV2 as _S
# Résolu à l'appel, pas à l'import : le remplacement de
# scraper_v2_sync.LinkedInScraperV2Sync (tests) reste effectif.
import scraper_v2_sync
from ui.composants import (afficher_bandeau_contexte, afficher_jauge_budget,
                           pluriel)
from ui.invitations import (AIDE_MESSAGE, MESSAGE_SESSION_MANQUANTE,
                            afficher_resultats, bloc_recuperer_inviter, budget,
                            confirmation, echapper_markdown, recap_invitations)
from utils.browsemap import filtrer_suggestions, vanity_depuis_url
from utils.budget import message_depassement
from ui.selection import choisir_profils, reinitialiser_choix
from utils.search_filters import (criteres_suffisants,
                                  ecoles_sans_identifiant,
                                  parse_entreprises)

MAX_ENTREPRISES = _S.MAX_VALEURS_PAR_FACETTE

ONGLETS = ["Par critères", "Profils similaires"]


SESSION_REQUISE = "Connectez d'abord votre session LinkedIn (ci-dessus)."












def _nouveau_scraper():
    return scraper_v2_sync.LinkedInScraperV2Sync(use_database=True, proxy=st.session_state.get('user_proxy'), db_file=str(st.session_state.user_paths.db_file), profiles_csv=str(st.session_state.user_paths.profiles_csv), config_dir=str(st.session_state.user_paths.config_dir))


def _lancer(**parametres):
    """Lance une recherche et affiche son bilan sous le bouton."""
    scraper = _nouveau_scraper()
    progress_bar = st.progress(0)
    status_text = st.empty()
    with st.spinner(f"Recherche en cours : {pluriel(parametres['nb_profils'], 'profil')}…"):
        df = scraper.run_scraper(
            cookie=st.session_state.global_cookie,
            progress_callback=lambda p: progress_bar.progress(min(p, 1.0)),
            status_callback=lambda s: status_text.text(s),
            **parametres,
        )
    return df, scraper


def _tester_session():
    import subprocess, sys as _sys
    with st.spinner("Vérification de la session (10 à 20 secondes)…"):
        try:
            result = subprocess.run(
                [_sys.executable, "diagnostic_cookie.py", "--headless"],
                capture_output=True, text=True, timeout=60,
            )
        except subprocess.TimeoutExpired:
            st.error("La vérification a dépassé 60 secondes : réseau lent ou navigateur bloqué.")
            return
        except Exception as e:
            st.error(f"La vérification n'a pas pu se faire : {e}")
            return
    output = result.stdout + ("\n" + result.stderr if result.stderr else "")
    if "✅ COOKIE VALIDE" in output:
        st.success("Session valide : LinkedIn l'accepte.")
    elif "COOKIE INVALIDE" in output or "COOKIE EXPIRÉ" in output or "AUTHWALL" in output:
        st.error("Session expirée ou invalide. Reconnectez-vous à LinkedIn, puis "
                 "recopiez le cookie de session.")
    elif "CHECKPOINT" in output:
        st.warning("LinkedIn demande une vérification : connectez-vous sur "
                   "linkedin.com pour la valider, puis recopiez le cookie de session.")
    else:
        st.warning("Statut indéterminé : voir le détail ci-dessous.")
    with st.expander("Détail de la vérification"):
        st.code(output[-3000:], language="text")


ETAPES_SESSION = (
    "1. Dans Chrome, connectez-vous sur **linkedin.com**.\n"
    "2. Appuyez sur **F12** (ou clic droit, puis **Inspecter**) pour ouvrir les outils de développement.\n"
    "3. Ouvrez l'onglet **Application** (s'il n'apparaît pas, cliquez sur `»`).\n"
    "4. À gauche : **Cookies**, puis **https://www.linkedin.com**.\n"
    "5. Repérez le cookie de session, nommé **`li_at`** dans Chrome.\n"
    "6. **Double-cliquez sur sa valeur** (longue suite de caractères) et copiez-la (**Ctrl/Cmd + C**).\n"
    "7. **Collez** la valeur dans le champ ci-dessous, puis **Enregistrer**."
)
AVERTISSEMENT_SESSION = (
    "**Ne partagez jamais cette valeur** : elle donne accès à votre compte "
    "LinkedIn. Si elle expire (déconnexion), refaites l'opération."
)
PLACEHOLDER_SESSION = "Collez ici la valeur copiée depuis Chrome"


def _quitter_edition() -> None:
    st.session_state.cookie_editing = False


def _champ_session(ck: str, annulable: bool) -> None:
    """Le champ de saisie, Enregistrer et, en modification, Annuler."""
    _cin, _cbtn = st.columns([4, 1], vertical_alignment="bottom")
    _new_ck = _cin.text_input(
        "Session LinkedIn", value=ck, type="password",
        label_visibility="collapsed",
        placeholder=PLACEHOLDER_SESSION,
        key="cookie_shared",
    )
    _new_ck = (_new_ck or "").strip()
    enregistrer = _cbtn.button("Enregistrer", type="primary", width="stretch",
                               key="cookie_enregistrer")
    if annulable:
        st.button("Annuler", key="cookie_annuler", on_click=_quitter_edition)
    if enregistrer:
        if _new_ck and st.session_state.cookie_manager.validate_cookie_format(_new_ck):
            st.session_state.cookie_manager.save_cookie(_new_ck)
            st.session_state.global_cookie = _new_ck
            st.session_state.cookie_editing = False
            st.session_state.session_a_tester = True
            st.rerun()
        else:
            st.warning("Valeur vide ou au format inattendu : vérifiez la copie.")


def _premiere_connexion() -> None:
    """Aucune session : l'étape unique, dépliée, avec le champ sur place."""
    with st.container(border=True, key="premiere_connexion"):
        st.header("Première connexion à LinkedIn", anchor=False)
        st.markdown(
            "We.Reach agit depuis votre compte LinkedIn. Pour cela, il lui faut "
            "votre session : une valeur à copier depuis Chrome, **une seule "
            "fois**. Elle est ensuite conservée de façon sécurisée."
        )
        st.markdown(ETAPES_SESSION)
        _champ_session("", annulable=False)
        st.caption(AVERTISSEMENT_SESSION.replace("**", ""))


def _session_linkedin(ck: str) -> None:
    if not ck:
        _premiere_connexion()
        return

    if st.session_state.get("cookie_editing"):
        with st.container(border=True, key="session_edition"):
            st.markdown("**Session LinkedIn**")
            _champ_session(ck, annulable=True)
            st.caption("Conservée de façon sécurisée, nécessaire pour lancer les recherches.")
        return

    a_tester = st.session_state.get("session_a_tester")
    masque = f"{ck[:6]}…{ck[-4:]}" if len(ck) > 12 else "…"
    with st.container(border=True, horizontal=True, vertical_alignment="center",
                      key="session_ligne"):
        st.markdown(
            '<div style="min-width:0"><div style="font-weight:600;color:var(--wf-text)">'
            'Session LinkedIn</div><div style="font-family:\'JetBrains Mono\',monospace;'
            f'font-size:.75rem;color:var(--wf-muted)">{masque}</div></div>',
            unsafe_allow_html=True, width="stretch",
        )
        tester = st.button("Tester la session" if a_tester else "Tester",
                           key="test_cookie_btn",
                           type="primary" if a_tester else "secondary",
                           help="Vérifie que LinkedIn accepte encore la session.")
        if st.button("Modifier", key="cookie_modifier"):
            st.session_state.cookie_editing = True
            st.session_state.pop("session_a_tester", None)
            st.rerun()
    if a_tester and not tester:
        st.caption("Session enregistrée. Testez-la une fois : la vérification "
                   "prend 10 à 20 secondes.")
    if tester:
        st.session_state.pop("session_a_tester", None)
        _tester_session()


def afficher_page_recherche():
    st.title("Nouvelle recherche", anchor=False)

    ck = st.session_state.global_cookie
    # Les invitations du jour sont sous le menu, sur toutes les pages, et dans le
    # bloc Invitations dès qu'on invite : pas de troisième rappel ici.
    puce_session = (("Session LinkedIn active", "ok", True) if ck
                    else ("Session LinkedIn à renseigner", "attention"))
    afficher_bandeau_contexte(
        "Trouvez des profils et invitez-les, en suivant la limite conseillée d'invitations du jour.",
        puces=[puce_session],
    )

    _session_linkedin(ck)

    if ck:
        with st.expander("Comment récupérer votre session LinkedIn ?"):
            st.markdown(ETAPES_SESSION.replace(
                "dans le champ ci-dessous", "dans le champ de la session (bouton **Modifier**)")
                + "\n\n" + AVERTISSEMENT_SESSION)

    st.write("")
    tab1, tab3 = st.tabs(ONGLETS)

    # TAB 1: PAR CRITÈRES (fusion de Candidats et Clients, 2026-10-21)
    # Trois temps, comme Profils similaires : chercher sans inviter, choisir
    # parmi les profils trouvés, puis inviter les seuls profils choisis.
    with tab1:
        st.subheader("1. Critères", anchor=False)
        st.caption("Au moins un critère : des mots-clés, une entreprise, une école ou un secteur.")
        col1, col2 = st.columns(2, gap="large")
        with col1:
            keyword = st.text_input(
                "Mots-clés (qui)", "", key="crit_mots",
                placeholder="Ex : Product Manager, Head of Data",
                help='Plusieurs intitulés : séparez-les par OR, et mettez une '
                     'expression entre guillemets, par exemple "Head of Data" OR CDO.',
            )
            nb_profils = st.number_input("Nombre de profils (combien)", min_value=1,
                                         max_value=80, value=10, key="crit_nb")
        with col2:
            entreprise_libre = st.text_input(
                "Entreprises (où)", "", key="crit_entreprises",
                placeholder="Ex : Capgemini, Thiga",
                help="Plusieurs entreprises : séparez-les par des virgules.",
            )
            concurrents = st.multiselect(
                "Cabinets concurrents", CONCURRENTS, key="crit_cabinets",
                placeholder="Choisir des cabinets…",
                help="Chasse : cible les profils actuellement dans ces cabinets.",
            )
            ile_de_france = st.toggle("Île-de-France uniquement", value=False, key="crit_idf",
                                      help="Ne garde que les profils situés en Île-de-France.")
        # Cabinets et saisie libre se cumulent — LinkedIn les combine en OU.
        entreprises = parse_entreprises(entreprise_libre, concurrents)
        if len(entreprises) > MAX_ENTREPRISES:
            st.warning(
                f"{len(entreprises)} entreprises sélectionnées : seules "
                f"les {MAX_ENTREPRISES} premières seront utilisées. "
                "Chacune demande une interrogation de LinkedIn pour être "
                "identifiée ; au-delà, le risque de blocage augmente."
            )

        avances = bool(st.session_state.get("ecoles_pills_candidat")
                       or st.session_state.get("secteurs_candidat"))
        with st.expander("Filtres avancés : écoles et secteurs", expanded=avances):
            ecole_noms = st.multiselect(
                "Écoles ciblées", list(ECOLES.keys()),
                placeholder="Choisir des écoles…",
                help="Plusieurs écoles possibles : elles se cumulent en OU.",
                key="ecoles_pills_candidat",
            )
            ecoles_selectionnees = [ECOLES[n] for n in (ecole_noms or [])]
            if ecoles_selectionnees:
                _ecartees = ecoles_sans_identifiant(ecoles_selectionnees)
                if _ecartees:
                    st.warning(
                        "Sans identifiant LinkedIn, ces écoles ne peuvent pas "
                        f"entrer dans le filtre : **{', '.join(_ecartees)}**. "
                        "La recherche se lance quand même avec les autres."
                    )
            secteurs_noms = st.multiselect(
                "Secteurs d'activité", list(SECTEURS.keys()),
                placeholder="Choisir des secteurs…",
                help="Les secteurs se cumulent en OU, et se combinent en ET avec les écoles et entreprises.",
                key="secteurs_candidat",
            )
            secteurs_selectionnes = [SECTEURS[s] for s in secteurs_noms]

        sans_session = not st.session_state.global_cookie
        clic = st.button("Rechercher", type="primary", width="stretch",
                         key="btn_rechercher", disabled=sans_session)
        if sans_session:
            st.caption(SESSION_REQUISE)
        if clic:
            if not criteres_suffisants(keyword, ecoles_selectionnees, entreprises,
                                       secteurs_selectionnes):
                st.error("Saisissez des mots-clés, ou choisissez au moins un filtre. "
                         "Sans aucun critère, LinkedIn renverrait des profils au hasard.")
            else:
                df, scraper = _lancer(
                    keyword=keyword, entreprises=entreprises, nb_profils=nb_profils,
                    ecoles_ids=ecoles_selectionnees, secteurs_ids=secteurs_selectionnes,
                    inviter=False, message_invitation="", reinviter_profils_scrapes=False,
                    ile_de_france=ile_de_france,
                )
                st.session_state["crit_profils"] = [{
                    "url": r.get("URL du profil") or "",
                    "nom": r.get("Nom") or "",
                    "intitule": " · ".join(x for x in (r.get("Poste"), r.get("Entreprise")) if x),
                    "invitable": True,
                } for r in (df.to_dict("records") if df is not None and not df.empty else [])
                    if r.get("URL du profil")]
                st.session_state["crit_erreurs"] = list(scraper.errors)
                reinitialiser_choix("crit")
                st.session_state.pop("crit_message", None)

        profils = st.session_state.get("crit_profils")
        for erreur in st.session_state.get("crit_erreurs") or []:
            st.warning(erreur)
        if profils is not None:
            st.subheader("2. Choisir les profils", anchor=False)
            if not profils:
                st.info(
                    "Aucun nouveau profil trouvé. Les profils déjà dans votre fichier "
                    "sont écartés ; essayez d'élargir les critères, ou sans entreprise "
                    "si elle n'a pas pu être identifiée (détail dans le Journal)."
                )
            else:
                st.caption("Les profils trouvés sont enregistrés dans l'Historique. "
                           "Décochez ceux que vous ne voulez pas inviter.")
                choisis = choisir_profils(profils, "crit")
                st.subheader("3. Inviter", anchor=False)
                if not choisis:
                    st.caption("Cochez au moins un profil dans le tableau ci-dessus.")
                else:
                    bloc_recuperer_inviter([p["url"] for p in choisis], "crit",
                                           nom_export="recherche", inviter_seulement=True)

    # TAB 3: PROFILS SIMILAIRES
    # Trois temps, nommés : partir d'un profil, choisir parmi ses voisins,
    # puis inviter ou enregistrer les seuls profils choisis (refonte du
    # 2026-10-21 : filtres regroupés, une case par profil).
    with tab3:
        st.caption(
            "Partez d'un profil qui vous a donné satisfaction : LinkedIn propose "
            "lui-même les profils que les mêmes personnes consultent. Vous "
            "choisissez ensuite qui inviter."
        )

        st.subheader("1. Profil de départ", anchor=False)
        sim_url = st.text_input(
            "Lien du profil de référence",
            placeholder="https://www.linkedin.com/in/jean-dupont-12345/",
            key="sim_url",
            help="Le profil de quelqu'un que vous avez déjà placé, par exemple.",
        )

        _sans_session = not st.session_state.global_cookie
        _sim_clic = st.button("Trouver les profils similaires", type="primary",
                              width="stretch", key="sim_btn_trouver",
                              disabled=_sans_session)
        if _sans_session:
            st.caption(SESSION_REQUISE)
        if _sim_clic:
            # Un refus efface le résultat précédent : sinon la liste de
            # l'ancienne référence resterait affichée sous la nouvelle erreur.
            if (not st.session_state.global_cookie
                    or vanity_depuis_url(sim_url) is None):
                for cle in ("sim_retenues", "sim_ecartees", "sim_suggestions",
                            "sim_urls_connues", "sim_entreprise",
                            "sim_entreprise_exclue", "sim_erreurs", "sim_choix"):
                    st.session_state.pop(cle, None)

            if not st.session_state.global_cookie:
                st.error(MESSAGE_SESSION_MANQUANTE)
            elif vanity_depuis_url(sim_url) is None:
                st.error(
                    "Ce lien n'est pas celui d'un profil LinkedIn : "
                    "il doit contenir « /in/ »."
                )
            else:
                scraper = _nouveau_scraper()
                with st.status("Lecture des profils voisins…",
                               expanded=False) as sim_statut:
                    suggestions, entreprise = scraper.recolter_browsemap(
                        cookie=st.session_state.global_cookie,
                        url_reference=sim_url,
                        status_callback=lambda s: sim_statut.update(label=s),
                    )
                sim_statut.update(
                    label=pluriel(len(suggestions), "profil voisin lu", "profils voisins lus"),
                    state="complete" if suggestions else "error",
                )
                # Lues une fois ici : les filtres sont rejoués à chaque
                # rerun sans réinterroger la base ni LinkedIn.
                st.session_state["sim_urls_connues"] = list(
                    scraper.db.urls_connues() if scraper.use_database else ()
                )
                st.session_state["sim_suggestions"] = suggestions
                st.session_state["sim_entreprise"] = entreprise
                # Par défaut, on écarte ceux qui travaillent encore chez
                # l'entreprise du profil de départ : on cherche le même profil
                # ailleurs. Le champ reste modifiable (vide = ne rien écarter).
                st.session_state["sim_entreprise_exclue"] = entreprise or ""
                st.session_state["sim_erreurs"] = list(scraper.errors)
                # Nouvelle liste : tout est choisi (on décoche ceux qu'on ne
                # veut pas), invitations désactivées.
                reinitialiser_choix("sim")
                st.session_state.pop("sim_inviter", None)
                st.session_state.pop("sim_message", None)

        for erreur in st.session_state.get("sim_erreurs") or []:
            st.warning(erreur)

        sim_suggestions = st.session_state.get("sim_suggestions")
        if sim_suggestions is None:
            st.session_state.pop("sim_retenues", None)
            st.session_state.pop("sim_ecartees", None)
        else:
            st.subheader("2. Choisir les profils", anchor=False)
            # Valeurs initiales posées en session plutôt que par value= : la
            # réaffectation qui retient les filtres d'une page à l'autre (en
            # tête de app_advanced) écrit aussi ces clés.
            st.session_state.setdefault("sim_invitables", False)
            f1, f2, f3 = st.columns([1.2, 1, 1], vertical_alignment="bottom")
            f1.text_input(
                "Écarter ceux qui travaillent encore chez",
                key="sim_entreprise_exclue",
                placeholder="Nom de l'entreprise",
                help="Rempli avec l'entreprise du profil de départ. Videz-le "
                     "pour garder tout le monde.",
            )
            sim_mot = f2.text_input(
                "Mot attendu dans l'intitulé",
                placeholder="Product",
                key="sim_mot",
                help="Pour resserrer la liste sur un métier.",
            )
            sim_invitables = f3.checkbox(
                "Seulement les profils invitables",
                key="sim_invitables",
                help="Écarte ceux qui ne proposent que « Suivre ».",
            )

            retenues, ecartees = filtrer_suggestions(
                sim_suggestions,
                urls_en_base=st.session_state.get("sim_urls_connues") or (),
                entreprise_reference=st.session_state.get("sim_entreprise_exclue"),
                invitables_seulement=sim_invitables,
                mot_intitule=sim_mot,
            )
            st.session_state["sim_retenues"] = retenues
            st.session_state["sim_ecartees"] = ecartees

            if retenues:
                choisis = choisir_profils(
                    retenues, "sim",
                    note=f"{pluriel(len(ecartees), 'écarté', 'écartés')} par les filtres")
            elif not st.session_state.get("sim_erreurs"):
                if ecartees:
                    st.info("Aucun profil retenu : tout a été écarté par les filtres. "
                            "Le détail est juste en dessous.")
                else:
                    st.info("LinkedIn n'a proposé aucun profil voisin pour celui-ci : "
                            "c'est le cas d'un profil peu consulté.")
                choisis = []
            else:
                choisis = []

            if ecartees:
                with st.expander(f"{pluriel(len(ecartees), 'profil écarté', 'profils écartés')} : pourquoi"):
                    for e in ecartees:
                        st.markdown(f"- **{echapper_markdown(e.get('nom') or 'Sans nom')}** : "
                                    f"{e['motif']}")

            if retenues:
                st.subheader("3. Inviter ou enregistrer", anchor=False)
                if not choisis:
                    st.caption("Cochez au moins un profil dans le tableau ci-dessus.")
                else:
                    st.caption(
                        "Chaque profil choisi est ouvert sur LinkedIn pour enregistrer "
                        "son poste et sa société dans l'Historique. Activez les "
                        "invitations pour leur en envoyer une en même temps."
                    )
                    bloc_recuperer_inviter([p["url"] for p in choisis], "sim",
                                           nom_export="profils_similaires")
