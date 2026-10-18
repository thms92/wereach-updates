# -*- coding: utf-8 -*-
"""Page 🔍 Recherche : session LinkedIn, Candidats, Clients/Entreprises,
Profils similaires."""

from datetime import datetime

import pandas as pd
import streamlit as st

from config import ECOLES, CONCURRENTS, SECTEURS
from queue_manager import JobStatus
from scraper_v2 import LinkedInScraperV2 as _S
# Résolu à l'appel, pas à l'import : le remplacement de
# scraper_v2_sync.LinkedInScraperV2Sync (tests) reste effectif.
import scraper_v2_sync
from ui.invitations import bloc_recuperer_inviter
from utils.browsemap import filtrer_suggestions, vanity_depuis_url
from utils.search_filters import (criteres_suffisants,
                                  ecoles_sans_identifiant,
                                  parse_entreprises)

MAX_ENTREPRISES = _S.MAX_VALEURS_PAR_FACETTE


def afficher_page_recherche():
    st.title("Nouvelle recherche")

    # Compteur file d'attente pour le label de l'onglet
    qm = st.session_state.queue_manager
    nb_en_attente = sum(1 for j in qm.jobs if j.status == JobStatus.EN_ATTENTE)
    queue_tab_label = f"🔄 File d'attente ({nb_en_attente})" if nb_en_attente > 0 else "🔄 File d'attente"

    # --- Bandeau session LinkedIn (partagé, façon maquette) ---
    _ck = st.session_state.global_cookie
    if st.session_state.get("cookie_editing") or not _ck:
        with st.container(border=True):
            st.markdown("**Cookie de session LinkedIn · li_at**")
            _cin, _cbtn = st.columns([4, 1])
            _new_ck = _cin.text_input(
                "li_at", value=_ck, type="password",
                label_visibility="collapsed",
                placeholder="Colle ici la valeur du cookie li_at…",
                key="cookie_shared",
            )
            _new_ck = (_new_ck or "").strip()
            if _cbtn.button("Enregistrer", type="primary", use_container_width=True):
                if _new_ck and st.session_state.cookie_manager.validate_cookie_format(_new_ck):
                    st.session_state.cookie_manager.save_cookie(_new_ck)
                    st.session_state.global_cookie = _new_ck
                    st.session_state.cookie_editing = False
                    st.rerun()
                else:
                    st.warning("⚠️ Format de cookie suspect ou vide.")
            st.caption("Conservé de façon sécurisée — nécessaire pour lancer les recherches.")
    else:
        _masked = f"{_ck[:6]}…{_ck[-4:]}" if len(_ck) > 12 else _ck
        _bl, _br = st.columns([5, 1])
        _bl.markdown(
            '<div style="display:flex;align-items:center;gap:11px;padding:13px 15px;'
            'background:var(--wf-surface);border:1px solid var(--wf-border);'
            'border-left:3px solid var(--wf-success);border-radius:13px;box-shadow:var(--wf-shadow)">'
            '<span style="width:9px;height:9px;flex:none;border-radius:50%;background:var(--wf-success)"></span>'
            '<div style="min-width:0"><div style="font-weight:600;font-size:.85rem;color:var(--wf-text)">Session LinkedIn active</div>'
            f'<div style="font-family:JetBrains Mono,monospace;font-size:.72rem;color:var(--wf-muted)">li_at · {_masked}</div></div></div>',
            unsafe_allow_html=True,
        )
        if _br.button("Modifier", use_container_width=True):
            st.session_state.cookie_editing = True
            st.rerun()

    with st.expander("❓ Comment récupérer mon cookie LinkedIn (li_at) ?"):
        st.markdown(
            "**Sur ordinateur, dans Chrome :**\n\n"
            "1. Connecte-toi sur **linkedin.com** (assure-toi d'être bien connecté).\n"
            "2. Appuie sur **F12** (ou clic droit → **Inspecter**) pour ouvrir les outils développeur.\n"
            "3. Va dans l'onglet **Application** (si tu ne le vois pas, clique sur les `»`).\n"
            "4. À gauche : **Cookies** → **https://www.linkedin.com**.\n"
            "5. Dans la liste, trouve la ligne nommée **`li_at`**.\n"
            "6. **Double-clique sur sa valeur** (longue suite de caractères) → copie-la (**Ctrl/Cmd + C**).\n"
            "7. Reviens ici, **colle** la valeur dans le champ ci-dessus → **Enregistrer**.\n\n"
            "⚠️ **Ne partage jamais ce cookie** : il donne accès à ton compte LinkedIn. "
            "S'il expire (déconnexion), refais l'opération pour en récupérer un nouveau."
        )

    st.write("")
    tab1, tab2, tab3 = st.tabs(
        ["👤 Candidats", "🏢 Clients/Entreprises", "👥 Profils similaires"]
    )

    # TAB 1: CANDIDATS
    with tab1:
        st.header("Recherche de candidats — écoles, entreprises et secteurs")

        col1, col2 = st.columns([1, 2])

        with col1:
            cookie = st.session_state.global_cookie
            keyword = st.text_input("Mots-clés", "", placeholder="Ex : Product Manager, PM Senior")
            entreprise_libre = st.text_input(
                "Entreprises (optionnel)", "",
                placeholder="Ex : Capgemini, Accenture",
                help="Plusieurs entreprises : sépare-les par des virgules.",
            )
            concurrents = st.multiselect(
                "🎯 Cabinets concurrents (optionnel)", CONCURRENTS,
                placeholder="Choisir des cabinets…",
                help="Chasse : cible les profils actuellement dans ces cabinets.",
            )
            # Cabinets et saisie libre se cumulent — LinkedIn les combine en OU.
            entreprises = parse_entreprises(entreprise_libre, concurrents)
            if len(entreprises) > MAX_ENTREPRISES:
                st.warning(
                    f"⚠️ {len(entreprises)} entreprises sélectionnées — seules "
                    f"les {MAX_ENTREPRISES} premières seront utilisées. "
                    "Chacune demande une interrogation de LinkedIn pour être "
                    "identifiée ; au-delà, le risque de blocage augmente."
                )
            nb_profils = st.number_input("Nombre de profils", min_value=1, max_value=80, value=10)

            ile_de_france = st.toggle("🗼 Île-de-France uniquement", value=False, help="Filtre les résultats pour la région Île-de-France")

            inviter = st.toggle("Envoyer des invitations automatiquement", value=False)

            if inviter:
                reinviter_profils_scrapes = st.checkbox(
                    "Réinviter les profils déjà scrapés",
                    value=False,
                    help="Si coché, enverra des invitations même aux profils déjà présents dans votre historique"
                )

                message_personnalise = st.text_area(
                    "Message personnalisé (optionnel)",
                    placeholder="Ex: Bonjour, je serais ravi(e) de vous ajouter à mon réseau...",
                    max_chars=200,
                    help="Maximum 200 caractères. Laissez vide pour envoyer sans note."
                )
            else:
                reinviter_profils_scrapes = False
                message_personnalise = ""

        with col2:
            st.markdown("**🎓 Écoles ciblées** — optionnel, plusieurs possibles")
            ecole_noms = st.pills(
                "Écoles ciblées",
                list(ECOLES.keys()),
                selection_mode="multi",
                label_visibility="collapsed",
                key="ecoles_pills_candidat",
            )
            ecoles_selectionnees = [ECOLES[n] for n in (ecole_noms or [])]
            if ecoles_selectionnees:
                st.success(f"✅ {len(ecoles_selectionnees)} école(s) sélectionnée(s)")
                _ecartees = ecoles_sans_identifiant(ecoles_selectionnees)
                if _ecartees:
                    st.warning(
                        "⚠️ Sans identifiant LinkedIn, ces écoles ne peuvent pas "
                        f"entrer dans le filtre : **{', '.join(_ecartees)}**. "
                        "La recherche se lance quand même avec les autres."
                    )
            else:
                st.caption("Aucune école — tu peux filtrer par entreprise / cabinet / secteur à la place.")

            secteurs_noms = st.multiselect(
                "🏭 Secteurs d'activité (optionnel)",
                list(SECTEURS.keys()),
                placeholder="Choisir des secteurs…",
                help="Les secteurs se cumulent en OU, et se combinent en ET avec les écoles et entreprises.",
                key="secteurs_candidat",
            )
            secteurs_selectionnes = [SECTEURS[s] for s in secteurs_noms]

        st.markdown("---")

        col_btn1, col_btn2 = st.columns(2)

        with col_btn1:
            if st.button("🔍 Lancer le scraping", type="primary", use_container_width=True):
                if not cookie:
                    st.error("❌ Cookie manquant")
                elif not criteres_suffisants(
                    keyword, ecoles_selectionnees, entreprises, secteurs_selectionnes
                ):
                    st.error(
                        "❌ Saisis des mots-clés, ou choisis au moins un filtre. "
                        "Sans aucun critère, LinkedIn renverrait des profils au hasard."
                    )
                else:
                    with st.spinner("🚀 Scraping en cours..."):
                        scraper = scraper_v2_sync.LinkedInScraperV2Sync(use_database=True, proxy=st.session_state.get('user_proxy'), db_file=str(st.session_state.user_paths.db_file), profiles_csv=str(st.session_state.user_paths.profiles_csv), config_dir=str(st.session_state.user_paths.config_dir))

                        progress_bar = st.progress(0)
                        status_text = st.empty()

                        def update_progress(p):
                            progress_bar.progress(p)

                        def update_status(s):
                            status_text.text(s)

                        df = scraper.run_scraper(
                            cookie=cookie,
                            keyword=keyword,
                            entreprises=entreprises,
                            nb_profils=nb_profils,
                            ecoles_ids=ecoles_selectionnees,
                            secteurs_ids=secteurs_selectionnes,
                            inviter=inviter,
                            message_invitation=message_personnalise,
                            reinviter_profils_scrapes=reinviter_profils_scrapes,
                            ile_de_france=ile_de_france,
                            progress_callback=update_progress,
                            status_callback=update_status
                        )

                        if not df.empty:
                            st.success(f"✅ {len(df)} profils scrapés avec succès!")
                            st.dataframe(df, use_container_width=True)

                            # Export Excel
                            excel_data = st.session_state.export_manager.export_to_excel(df.to_dict('records'))
                            st.download_button(
                                label="📥 Télécharger Excel",
                                data=excel_data,
                                file_name=f"candidats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                        else:
                            st.warning("⚠️ Aucun profil trouvé")

                        if scraper.errors:
                            with st.expander("⚠️ Erreurs rencontrées"):
                                for err in scraper.errors:
                                    st.write(f"- {err}")

    # TAB 2: CLIENTS
    with tab2:
        st.header("Recherche clients/entreprises (sans filtre école)")

        cookie_client = st.session_state.global_cookie

        # Bouton de test de cookie (lance diagnostic_cookie.py en mode headless)
        col_test_a, col_test_b = st.columns([1, 2])
        with col_test_a:
            test_cookie_btn = st.button("🔍 Tester ce cookie", key="test_cookie_btn",
                                        help="Lance une vérification rapide pour confirmer que LinkedIn accepte le cookie")
        if test_cookie_btn:
            with st.spinner("Test du cookie en cours (10-20s)..."):
                import subprocess, sys as _sys
                try:
                    result = subprocess.run(
                        [_sys.executable, "diagnostic_cookie.py", "--headless"],
                        capture_output=True, text=True, timeout=60,
                    )
                    output = result.stdout + ("\n" + result.stderr if result.stderr else "")
                    if "✅ COOKIE VALIDE" in output:
                        st.success("✅ Cookie valide — LinkedIn accepte la session.")
                    elif "COOKIE INVALIDE" in output or "COOKIE EXPIRÉ" in output or "AUTHWALL" in output:
                        st.error("❌ Cookie expiré ou invalidé. Reconnectez-vous à LinkedIn et copiez un nouveau cookie li_at.")
                    elif "CHECKPOINT" in output:
                        st.warning("⚠️ Checkpoint LinkedIn — connectez-vous sur linkedin.com pour valider la vérification, puis recopiez le cookie.")
                    else:
                        st.warning("⚠️ Statut indéterminé — voir les détails ci-dessous.")
                    with st.expander("Détails du diagnostic"):
                        st.code(output[-3000:], language="text")
                except subprocess.TimeoutExpired:
                    st.error("⏱️ Le diagnostic a dépassé 60 secondes — réseau lent ou navigateur bloqué.")
                except Exception as e:
                    st.error(f"Erreur lors du diagnostic : {e}")

        keyword_client = st.text_input(
            "Mots-clés",
            "",
            placeholder='Ex : "Head of Data" OR CDO OR "Directeur Data"',
            key="keyword_client",
        )
        entreprise_client = st.text_input(
            "Entreprises", "",
            placeholder="Ex : Thiga, Kering",
            help="Plusieurs entreprises : sépare-les par des virgules.",
            key="entreprise_client",
        )
        # Même lecture que l'onglet Candidats : la virgule sépare deux sociétés.
        entreprises_client = parse_entreprises(entreprise_client, [])
        nb_client = st.number_input("Nombre de profils", min_value=1, max_value=80, value=10, key="nb_client")

        ile_de_france_client = st.toggle("🗼 Île-de-France uniquement", value=False, key="idf_client", help="Filtre les résultats pour la région Île-de-France")

        inviter_client = st.toggle("Envoyer des invitations automatiquement", value=False, key="inviter_client")

        if inviter_client:
            reinviter_profils_scrapes_client = st.checkbox(
                "Réinviter les profils déjà scrapés",
                value=False,
                key="reinviter_client",
                help="Si coché, enverra des invitations même aux profils déjà présents dans votre historique"
            )

            message_client = st.text_area(
                "Message personnalisé (optionnel)",
                placeholder="Message d'invitation...",
                max_chars=200,
                key="message_client"
            )
        else:
            reinviter_profils_scrapes_client = False
            message_client = ""

        if st.button("🔍 Lancer recherche clients", type="primary"):
            if not cookie_client:
                st.error("❌ Cookie manquant")
            else:
                with st.spinner("🚀 Recherche en cours..."):
                    scraper = scraper_v2_sync.LinkedInScraperV2Sync(use_database=True, proxy=st.session_state.get('user_proxy'), db_file=str(st.session_state.user_paths.db_file), profiles_csv=str(st.session_state.user_paths.profiles_csv), config_dir=str(st.session_state.user_paths.config_dir))

                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    df = scraper.run_scraper(
                        cookie=cookie_client,
                        keyword=keyword_client,
                        entreprises=entreprises_client,
                        nb_profils=nb_client,
                        ecoles_ids=[],
                        inviter=inviter_client,
                        message_invitation=message_client,
                        reinviter_profils_scrapes=reinviter_profils_scrapes_client,
                        ile_de_france=ile_de_france_client,
                        progress_callback=lambda p: progress_bar.progress(p),
                        status_callback=lambda s: status_text.text(s)
                    )

                    if not df.empty:
                        st.success(f"✅ {len(df)} profils scrapés!")
                        st.dataframe(df, use_container_width=True)

                        excel_data = st.session_state.export_manager.export_to_excel(df.to_dict('records'))
                        st.download_button(
                            label="📥 Télécharger Excel",
                            data=excel_data,
                            file_name=f"clients_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                    else:
                        st.warning(
                            "⚠️ Aucun profil trouvé — LinkedIn n'a renvoyé aucun résultat. "
                            "Cause fréquente : le filtre entreprise n'a pas pu être résolu, "
                            "et la recherche par mot-clé combinée est trop restrictive. "
                            "Essaie sans entreprise, ou consulte la page 📜 Logs pour le détail."
                        )

    # TAB 3: PROFILS SIMILAIRES
    with tab3:
        st.header("Retrouver un profil comme celui-là, ailleurs")
        st.caption(
            "Partez d'un profil qui vous a donné satisfaction : LinkedIn "
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

        if st.button("👥 Trouver des profils similaires", type="primary",
                     use_container_width=True, key="sim_btn_trouver"):
            # Un refus efface le résultat précédent : sinon la liste de
            # l'ancienne référence resterait affichée sous la nouvelle erreur.
            if (not st.session_state.global_cookie
                    or vanity_depuis_url(sim_url) is None):
                for cle in ("sim_retenues", "sim_ecartees", "sim_suggestions",
                            "sim_urls_connues", "sim_entreprise",
                            "sim_entreprise_exclue", "sim_erreurs"):
                    st.session_state.pop(cle, None)

            if not st.session_state.global_cookie:
                st.error("❌ Cookie manquant")
            elif vanity_depuis_url(sim_url) is None:
                st.error(
                    "❌ Ce lien n'est pas celui d'un profil LinkedIn — "
                    "il doit contenir « /in/ »"
                )
            else:
                scraper = scraper_v2_sync.LinkedInScraperV2Sync(use_database=True, proxy=st.session_state.get('user_proxy'), db_file=str(st.session_state.user_paths.db_file), profiles_csv=str(st.session_state.user_paths.profiles_csv), config_dir=str(st.session_state.user_paths.config_dir))

                # Un bloc d'état plutôt qu'un spinner et un texte séparés : la
                # récolte dure, et l'étape en cours doit rester lisible juste
                # sous le bouton, puis le bilan une fois fini.
                with st.status("🔄 Lecture des profils voisins...",
                               expanded=False) as sim_statut:
                    suggestions, entreprise = scraper.recolter_browsemap(
                        cookie=st.session_state.global_cookie,
                        url_reference=sim_url,
                        status_callback=lambda s: sim_statut.update(label=s),
                    )
                sim_statut.update(
                    label=f"👥 {len(suggestions)} profil(s) voisin(s) lu(s)",
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
            st.warning(f"⚠️ {erreur}")

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
                st.caption(f"Entreprise du profil de départ : **{entreprise_lue}**")
                # Le rappel s'exécute avant le rerun, donc avant que le champ
                # soit redessiné : seul endroit sûr pour écrire sa clé.
                st.button(
                    f"Écarter {entreprise_lue}",
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
                st.success(f"✅ {len(sim_retenues)} profil(s) retenu(s)")
                st.dataframe(
                    pd.DataFrame(sim_retenues).reindex(
                        # reindex et non un simple [[...]] : une clé absente
                        # ferait planter la page entière au lieu d'afficher
                        # une colonne vide.
                        columns=["nom", "degre", "intitule", "invitable", "url"]
                    ).rename(columns={
                        "nom": "Nom", "degre": "Degré", "intitule": "Intitulé",
                        "invitable": "Invitable", "url": "Lien",
                    }),
                    use_container_width=True,
                    hide_index=True,
                )
            elif not st.session_state.get("sim_erreurs"):
                # Deux vides différents : un tri qui a tout écarté (le détail
                # existe) et un panneau que LinkedIn n'a rien proposé (aucun
                # détail à montrer).
                if sim_ecartees:
                    st.info(
                        "Aucun profil retenu — tout a été écarté par les "
                        "filtres. Le détail est juste en dessous."
                    )
                else:
                    st.info(
                        "LinkedIn n'a proposé aucun profil voisin pour celui-ci "
                        "— c'est le cas d'un profil peu consulté."
                    )

            if sim_ecartees:
                with st.expander(f"🚫 {len(sim_ecartees)} profil(s) écarté(s) — pourquoi"):
                    for e in sim_ecartees:
                        st.markdown(f"- **{e.get('nom') or '(sans nom)'}** — {e['motif']}")

            if sim_retenues:
                st.markdown("---")
                st.markdown("**Étape 2 — récupérer les infos de ces profils**")
                st.caption(
                    "Chaque profil est ouvert pour en lire le poste et la "
                    "société. Cochez la case pour envoyer en même temps une "
                    "invitation."
                )
                bloc_recuperer_inviter([p["url"] for p in sim_retenues], "sim",
                                       nom_export="profils_similaires")
