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
from utils.search_filters import (criteres_suffisants,
                                  ecoles_sans_identifiant,
                                  parse_entreprises)

MAX_ENTREPRISES = _S.MAX_VALEURS_PAR_FACETTE

ONGLETS = ["Candidats", "Clients et entreprises", "Profils similaires"]


SESSION_REQUISE = "Connectez d'abord votre session LinkedIn (ci-dessus)."


def libelle_bouton_recherche(inviter: bool, jusqu_a: int = 0) -> str:
    """« Rechercher », ou « Rechercher et inviter (jusqu'à 3) » : le vrai
    nombre d'invitations qui peuvent partir."""
    if not inviter:
        return "Rechercher"
    if jusqu_a > 0:
        return f"Rechercher et inviter (jusqu'à {jusqu_a})"
    return "Rechercher et inviter"


def _bloc_invitations(nb_profils: int, cle_inviter: str, cle_reinviter: str,
                      cle_message: str):
    """L'interrupteur d'invitations, son budget et ses options, groupés.

    Rend (inviter, reinviter, message, budget ou None).
    """
    # Clé : le tutoriel pointe ce bloc (utils/tutoriel.py).
    with st.container(border=True, key=f"bloc_{cle_inviter}"):
        st.markdown("**Invitations**")
        inviter = st.toggle(
            "Envoyer des invitations", value=False, key=cle_inviter,
            help="Une invitation part vers chaque profil trouvé. L'envoi est "
                 "irréversible ; 20 par jour sont conseillés, sans blocage.",
        )
        if not inviter:
            return False, False, "", None

        b = budget()
        afficher_jauge_budget(b.utilisees, b.plafond)
        alerte = st.empty()
        st.caption(
            "Avec les invitations, le nombre de profils devient le nombre "
            "d'invitations visées : seuls les profils invités sont gardés."
        )
        reinviter = st.checkbox(
            "Réinviter les profils déjà dans votre fichier",
            value=False, key=cle_reinviter,
            help="Sinon, les profils déjà présents dans votre historique sont "
                 "passés sans invitation.",
        )
        message = st.text_area(
            "Message d'invitation (optionnel)",
            placeholder="Bonjour, je serais ravi d'échanger avec vous…",
            max_chars=200, help=AIDE_MESSAGE, key=cle_message,
        )
        depassement = message_depassement(nb_profils, b.utilisees, b.plafond)
        if depassement:
            alerte.warning(depassement)
    return inviter, reinviter, message, b


def _bouton_lancer(cle: str, inviter: bool, nb_profils: int, b) -> bool:
    """Le bouton principal d'un onglet : inactif sans session, et quand on
    invite, il annonce le nombre d'invitations qui peuvent partir."""
    jusqu_a = nb_profils if inviter else 0
    sans_session = not st.session_state.global_cookie
    clic = st.button(libelle_bouton_recherche(inviter, jusqu_a), type="primary",
                     width="stretch", key=cle, disabled=sans_session)
    if sans_session:
        st.caption(SESSION_REQUISE)
    return clic


def _recap_recherche(inviter: bool, nb_profils: int, b, message: str) -> str:
    if not inviter or b is None:
        return ""
    return recap_invitations(nb_profils, b.utilisees, b.plafond, message)


def _refus_lancement(inviter: bool, b):
    """Pourquoi le clic ne peut rien lancer, ou None."""
    if not st.session_state.global_cookie:
        return MESSAGE_SESSION_MANQUANTE
    return None


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
    tab1, tab2, tab3 = st.tabs(ONGLETS)

    # TAB 1: CANDIDATS
    with tab1:
        st.caption("Ciblez par mots-clés, entreprises, écoles ou secteurs : au moins un critère suffit.")

        col1, col2 = st.columns([1, 2], gap="large")

        with col1:
            st.markdown("**Qui**")
            keyword = st.text_input("Mots-clés", "", placeholder="Ex : Product Manager, PM Senior")

            st.markdown("**Où**")
            entreprise_libre = st.text_input(
                "Entreprises (optionnel)", "",
                placeholder="Ex : Capgemini, Accenture",
                help="Plusieurs entreprises : séparez-les par des virgules.",
            )
            concurrents = st.multiselect(
                "Cabinets concurrents (optionnel)", CONCURRENTS,
                placeholder="Choisir des cabinets…",
                help="Chasse : cible les profils actuellement dans ces cabinets.",
            )
            # Cabinets et saisie libre se cumulent — LinkedIn les combine en OU.
            entreprises = parse_entreprises(entreprise_libre, concurrents)
            if len(entreprises) > MAX_ENTREPRISES:
                st.warning(
                    f"{len(entreprises)} entreprises sélectionnées : seules "
                    f"les {MAX_ENTREPRISES} premières seront utilisées. "
                    "Chacune demande une interrogation de LinkedIn pour être "
                    "identifiée ; au-delà, le risque de blocage augmente."
                )
            ile_de_france = st.toggle("Île-de-France uniquement", value=False,
                                      help="Ne garde que les profils situés en Île-de-France.")

            st.markdown("**Combien**")
            nb_profils = st.number_input("Nombre de profils", min_value=1, max_value=80, value=10)

        with col2:
            st.markdown("**Formation et secteur**")
            ecole_noms = st.multiselect(
                "Écoles ciblées (optionnel)",
                list(ECOLES.keys()),
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
                "Secteurs d'activité (optionnel)",
                list(SECTEURS.keys()),
                placeholder="Choisir des secteurs…",
                help="Les secteurs se cumulent en OU, et se combinent en ET avec les écoles et entreprises.",
                key="secteurs_candidat",
            )
            secteurs_selectionnes = [SECTEURS[s] for s in secteurs_noms]

        inviter, reinviter_profils_scrapes, message_personnalise, b_cand = _bloc_invitations(
            nb_profils, "inviter_candidat", "reinviter_candidat", "message_candidat")

        clic = _bouton_lancer("btn_rechercher_candidats", inviter, nb_profils, b_cand)
        if clic:
            refus = _refus_lancement(inviter, b_cand)
            if refus is None and not criteres_suffisants(
                keyword, ecoles_selectionnees, entreprises, secteurs_selectionnes
            ):
                refus = ("Saisissez des mots-clés, ou choisissez au moins un filtre. "
                         "Sans aucun critère, LinkedIn renverrait des profils au hasard.")
            if refus:
                st.error(refus)
                st.session_state.pop("confirmer_candidats", None)
                clic = False
        parametres = dict(
            keyword=keyword,
            entreprises=entreprises,
            nb_profils=nb_profils,
            ecoles_ids=ecoles_selectionnees,
            secteurs_ids=secteurs_selectionnes,
            inviter=inviter,
            message_invitation=message_personnalise,
            reinviter_profils_scrapes=reinviter_profils_scrapes,
            ile_de_france=ile_de_france,
        )
        if confirmation("candidats", clic, inviter, parametres,
                        _recap_recherche(inviter, nb_profils, b_cand, message_personnalise)):
            df, scraper = _lancer(**parametres)
            if df.empty:
                st.warning("Aucun profil trouvé.")
            afficher_resultats(df, inviter, "candidats", "candidats", scraper.errors)

    # TAB 2: CLIENTS
    with tab2:
        st.caption("Décideurs et contacts en entreprise, sans filtre école.")

        col1, col2 = st.columns(2, gap="large")
        with col1:
            st.markdown("**Qui**")
            keyword_client = st.text_input(
                "Mots-clés",
                "",
                placeholder='Ex : "Head of Data" OR CDO OR "Directeur Data"',
                key="keyword_client",
            )
            st.markdown("**Combien**")
            nb_client = st.number_input("Nombre de profils", min_value=1, max_value=80, value=10, key="nb_client")
        with col2:
            st.markdown("**Où**")
            entreprise_client = st.text_input(
                "Entreprises", "",
                placeholder="Ex : Thiga, Kering",
                help="Plusieurs entreprises : séparez-les par des virgules.",
                key="entreprise_client",
            )
            # Même lecture que l'onglet Candidats : la virgule sépare deux sociétés.
            entreprises_client = parse_entreprises(entreprise_client, [])
            ile_de_france_client = st.toggle(
                "Île-de-France uniquement", value=False, key="idf_client",
                help="Ne garde que les profils situés en Île-de-France.")

        inviter_client, reinviter_profils_scrapes_client, message_client, b_cli = _bloc_invitations(
            nb_client, "inviter_client", "reinviter_client", "message_client")

        clic = _bouton_lancer("btn_rechercher_clients", inviter_client, nb_client, b_cli)
        if clic:
            refus = _refus_lancement(inviter_client, b_cli)
            if refus:
                st.error(refus)
                st.session_state.pop("confirmer_clients", None)
                clic = False
        parametres = dict(
            keyword=keyword_client,
            entreprises=entreprises_client,
            nb_profils=nb_client,
            ecoles_ids=[],
            inviter=inviter_client,
            message_invitation=message_client,
            reinviter_profils_scrapes=reinviter_profils_scrapes_client,
            ile_de_france=ile_de_france_client,
        )
        if confirmation("clients", clic, inviter_client, parametres,
                        _recap_recherche(inviter_client, nb_client, b_cli, message_client)):
            df, scraper = _lancer(**parametres)
            if df.empty:
                st.warning(
                    "Aucun profil trouvé : LinkedIn n'a renvoyé aucun résultat. "
                    "Cause fréquente : le filtre entreprise n'a pas pu être "
                    "identifié, et combiné aux mots-clés il devient trop "
                    "restrictif. Essayez sans entreprise, ou consultez le "
                    "Journal pour le détail."
                )
            afficher_resultats(df, inviter_client, "clients", "clients", scraper.errors)

    # TAB 3: PROFILS SIMILAIRES
    with tab3:
        st.caption(
            "Retrouvez un profil comme celui-là, ailleurs. Partez d'un profil qui vous a donné satisfaction : LinkedIn "
            "propose lui-même les profils que les mêmes personnes consultent. "
            "Les gens déjà dans votre réseau ou déjà dans votre fichier sont "
            "écartés."
        )

        col1, col2 = st.columns([2, 1])

        with col1:
            sim_url = st.text_input(
                "Lien du profil de référence",
                placeholder="https://www.linkedin.com/in/jean-dupont-12345/",
                key="sim_url",
                help="Le profil de quelqu'un que vous avez déjà placé, par exemple.",
            )

        with col2:
            # Valeur initiale posée en session plutôt que par value= : la
            # réaffectation qui retient les filtres d'une page à l'autre
            # (en tête de script) écrit aussi cette clé, et Streamlit avertit
            # quand un widget reçoit les deux.
            st.session_state.setdefault("sim_invitables", False)
            sim_invitables = st.checkbox(
                "Seulement les profils invitables",
                key="sim_invitables",
                help="Écarte ceux qui ne proposent que « Suivre » : ils ne "
                     "peuvent pas recevoir d'invitation.",
            )
            sim_mot = st.text_input(
                "Mot attendu dans l'intitulé (optionnel)",
                placeholder="Product",
                key="sim_mot",
                help="Pour resserrer si la liste part dans une direction qui "
                     "ne vous intéresse pas.",
            )

        _sans_session = not st.session_state.global_cookie
        _sim_clic = st.button("Rechercher des profils similaires", type="primary",
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
                            "sim_entreprise_exclue", "sim_erreurs"):
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

                # Un bloc d'état plutôt qu'un spinner et un texte séparés : la
                # récolte dure, et l'étape en cours doit rester lisible juste
                # sous le bouton, puis le bilan une fois fini.
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

                # Les URLs du fichier servent de filtre, comparées sous forme
                # canonique des deux côtés — la base contient les liens tels
                # qu'ils ont été copiés. Lues une fois ici : le filtre est
                # rejoué à chaque rerun, on n'interroge pas la base à chaque
                # frappe dans un champ.
                st.session_state["sim_urls_connues"] = list(
                    scraper.db.urls_connues() if scraper.use_database else ()
                )

                # Les suggestions brutes restent en session : les filtres de
                # l'écran (entreprise, invitables, mot) les rejouent sans
                # relancer une récolte de plusieurs minutes.
                st.session_state["sim_suggestions"] = suggestions
                st.session_state["sim_entreprise"] = entreprise
                # Vide : par défaut rien n'est écarté hors fichier et 1er
                # degré. L'entreprise lue n'est que proposée sous le champ.
                st.session_state["sim_entreprise_exclue"] = ""
                st.session_state["sim_erreurs"] = list(scraper.errors)
                # Une nouvelle liste ne démarre jamais avec les invitations
                # cochées : l'envoi est irréversible et le quota rare.
                st.session_state.pop("sim_inviter", None)
                st.session_state.pop("sim_message", None)

        # Juste sous le bouton, avant tout le reste : au premier essai réel,
        # rendus sous le champ entreprise et le tableau, ils sont passés
        # inaperçus — dont celui qui disait que la liste était partielle.
        for erreur in st.session_state.get("sim_erreurs") or []:
            st.warning(erreur)

        sim_suggestions = st.session_state.get("sim_suggestions")

        if sim_suggestions is not None:
            st.text_input(
                "Entreprise à écarter",
                key="sim_entreprise_exclue",
                help="Les profils dont l'intitulé mentionne encore cette "
                     "entreprise sont écartés : on cherche le même profil "
                     "ailleurs.",
            )
            entreprise_lue = st.session_state.get("sim_entreprise")
            if entreprise_lue:
                st.caption(f"Entreprise du profil de départ : **{echapper_markdown(entreprise_lue)}**")
                # Le rappel s'exécute avant le rerun, donc avant que le champ
                # soit redessiné : seul endroit sûr pour écrire sa clé.
                st.button(
                    f"Écarter {echapper_markdown(entreprise_lue)}",
                    key="sim_btn_ecarter_ref",
                    on_click=lambda: st.session_state.__setitem__(
                        "sim_entreprise_exclue", entreprise_lue),
                )
            else:
                st.caption(
                    "L'entreprise du profil de départ n'a pas pu être lue : "
                    "saisissez-la ci-dessus pour écarter ceux qui y travaillent "
                    "encore."
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
        else:
            st.session_state.pop("sim_retenues", None)
            st.session_state.pop("sim_ecartees", None)

        sim_retenues = st.session_state.get("sim_retenues")
        sim_ecartees = st.session_state.get("sim_ecartees") or []

        if sim_retenues is not None:
            if sim_retenues:
                st.success(pluriel(len(sim_retenues), "profil retenu", "profils retenus"))
                st.dataframe(
                    pd.DataFrame(sim_retenues).reindex(
                        # reindex et non un simple [[...]] : une clé absente
                        # ferait planter la page entière au lieu d'afficher
                        # une colonne vide.
                        columns=["nom", "degre", "intitule", "invitable", "url"]
                    ).rename(columns={
                        "nom": "Nom", "degre": "Relation", "intitule": "Intitulé",
                        "invitable": "Invitable", "url": "Lien",
                    }),
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "Lien": st.column_config.LinkColumn("Profil", display_text="Ouvrir"),
                        "Relation": st.column_config.TextColumn(
                            "Relation", help="2e : un contact en commun ; 3e : plus éloigné."),
                    },
                )
            elif not st.session_state.get("sim_erreurs"):
                # Deux vides différents : un tri qui a tout écarté (le détail
                # existe) et un panneau que LinkedIn n'a rien proposé (aucun
                # détail à montrer).
                if sim_ecartees:
                    st.info(
                        "Aucun profil retenu : tout a été écarté par les "
                        "filtres. Le détail est juste en dessous."
                    )
                else:
                    st.info(
                        "LinkedIn n'a proposé aucun profil voisin pour celui-ci : "
                        "c'est le cas d'un profil peu consulté."
                    )

            if sim_ecartees:
                with st.expander(f"{pluriel(len(sim_ecartees), 'profil écarté', 'profils écartés')} : pourquoi"):
                    for e in sim_ecartees:
                        st.markdown(f"- **{echapper_markdown(e.get('nom') or 'Sans nom')}** : "
                                    f"{e['motif']}")

            if sim_retenues:
                st.divider()
                st.markdown("**Étape 2 : récupérer les infos de ces profils**")
                st.caption(
                    "Chaque profil est ouvert pour en lire le poste et la "
                    "société. Activez les invitations pour en envoyer une en "
                    "même temps."
                )
                bloc_recuperer_inviter([p["url"] for p in sim_retenues], "sim",
                                       nom_export="profils_similaires")
