# -*- coding: utf-8 -*-
"""Page 📊 Dashboard (« Tableau de bord ») : ce qui vous attend aujourd'hui.

Trois questions, dans l'ordre où on se les pose en ouvrant l'outil :
qu'est-ce que je dois faire maintenant (bloc « À faire »), combien
d'invitations me reste-t-il (la puce du bandeau ; la jauge, elle, vit dans la
barre latérale), et que donnent mes invitations (bloc « Vos chiffres »,
ui/bloc_chiffres.py : période, filtres, tuiles, semaines, tableaux).
"""

from datetime import datetime, timezone
from typing import List, Optional, Tuple

import streamlit as st

from ui.bloc_chiffres import afficher_bloc_chiffres
from ui.composants import (afficher_bandeau_contexte, afficher_carte_action,
                           pluriel, texte_budget, ton_budget)
from utils.budget import budget_du_jour

# Identifiants internes des pages (voir PAGES dans app_advanced.py).
PAGE_MESSAGES = "✉️ Messages"
PAGE_RECHERCHE = "🔍 Recherche"



def _aller_a(page: str) -> None:
    """Rappel de bouton : change de page avant le rerun qui suit le clic."""
    st.session_state["page"] = page


def date_locale(brut) -> str:
    """Horodatage SQLite (UTC, « AAAA-MM-JJ HH:MM:SS ») → « jj/mm/aaaa hh:mm » local.

    `CURRENT_TIMESTAMP` de SQLite est en UTC : affiché tel quel, une
    recherche lancée à 10 h à Paris apparaîtrait à 8 h. Une valeur illisible
    est rendue telle quelle plutôt que de faire tomber la page.
    """
    if not brut:
        return "—"
    texte = str(brut).strip()
    for motif in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S",
                  "%Y-%m-%d %H:%M"):
        try:
            moment = datetime.strptime(texte, motif)
        except ValueError:
            continue
        return moment.replace(tzinfo=timezone.utc).astimezone().strftime("%d/%m/%Y %H:%M")
    return texte[:16]


def taux_acceptation(invites: int, acceptes: int) -> str:
    """« 42 % » des invités ont accepté ; « — » tant que personne n'est invité."""
    if invites <= 0:
        return "—"
    return f"{round(acceptes * 100 / invites)}\u202f%"


# Icône de la carte « ont accepté » : la seule mise en vedette (pic de réussite).
ICONE_REUSSITE = "accepte"
# Le bouton de cette action est LE bouton principal de l'écran au premier
# lancement : sans session, rien d'autre ne peut se faire.
CLE_CONNEXION = "tdb_aller_recherche"


def actions_du_jour(nb_a_messager: int, nb_en_attente: int,
                    session_active: bool,
                    budget_utilisees: int = 0, budget_plafond: int = 0,
                    ) -> List[Tuple[str, str, str, str, Optional[Tuple[str, str, str]]]]:
    """Les cartes « À faire » qui s'appliquent, la réussite d'abord.

    Chaque entrée : (titre, détail, ton, icône, bouton) où bouton vaut
    (libellé, clé, page cible) ou None. Liste vide = rien d'urgent.
    Des personnes qui ont accepté passent en tête : c'est le moment que
    l'outil sert à produire. `budget_utilisees`/`budget_plafond` donnent
    l'alerte « il vous reste N invitations » dès 80 % consommés.
    Pure : testée sans Streamlit.
    """
    actions = []
    if nb_a_messager:
        verbe = "a accepté" if nb_a_messager < 2 else "ont accepté"
        actions.append((
            f"{pluriel(nb_a_messager, 'personne')} {verbe} votre invitation",
            "Envoyez-leur un message depuis la page Messages.",
            "ok", ICONE_REUSSITE,
            ("Ouvrir Messages", "tdb_ouvrir_messages", PAGE_MESSAGES),
        ))
    if not session_active:
        actions.append((
            "Connectez votre session LinkedIn",
            "Sans elle, aucune recherche ni invitation ne peut partir. "
            "Elle se renseigne depuis la page Recherche.",
            "attention", "alerte",
            ("Connecter la session LinkedIn", CLE_CONNEXION, PAGE_RECHERCHE),
        ))
    if nb_en_attente:
        actions.append((
            f"{pluriel(nb_en_attente, 'invitation')} en attente de réponse",
            "Vérifiez qui a accepté depuis la page Messages.",
            "neutre", "invitation", None,
        ))
    if budget_plafond > 0 and budget_utilisees >= budget_plafond:
        # Limite conseillée, pas bloquante : on informe, on n'interdit pas.
        actions.append((
            f"Limite conseillée de {budget_plafond} invitations atteinte",
            "Vous pouvez continuer à inviter : rien n'est bloqué, mais au-delà "
            "le risque de restriction de votre compte LinkedIn augmente.",
            "attention", "alerte", None,
        ))
    elif budget_plafond > 0 and ton_budget(budget_utilisees, budget_plafond) == "attention":
        restantes = budget_plafond - budget_utilisees
        actions.append((
            f"Plus que {pluriel(restantes, 'invitation')} avant la limite conseillée",
            "Gardez-les pour les profils les plus prometteurs ; le compteur "
            "repart à zéro demain.",
            "attention", "invitation", None,
        ))
    return actions


def _bloc_a_faire(actions) -> None:
    st.header("À faire", anchor=False)
    if not actions:
        afficher_carte_action(
            "Rien d'urgent",
            "Aucune réponse à traiter. Lancez une recherche pour trouver de "
            "nouveaux profils.",
            ton="ok", icone="ok",
        )
        return
    for titre, detail, ton, icone, bouton in actions:
        vedette = icone == ICONE_REUSSITE
        if bouton is None:
            afficher_carte_action(titre, detail, ton=ton, icone=icone, vedette=vedette)
            continue
        libelle, cle, cible = bouton
        # Le bouton vit DANS la carte, sous le texte (le thème stylise les
        # conteneurs `wf_carte_…`) : en colonne étroite à droite, « Ouvrir
        # Messages » passait sur deux lignes à 1440 px.
        with st.container(key=f"wf_carte_{cle}"):
            afficher_carte_action(titre, detail, ton=ton, icone=icone, vedette=vedette)
            st.button(libelle, key=cle, on_click=_aller_a, args=(cible,),
                      type="primary" if cle == CLE_CONNEXION else "secondary",
                      width="content")


def afficher_page_tableau_de_bord():
    st.title("Tableau de bord", anchor=False)

    db = st.session_state.db
    chemins = st.session_state.user_paths
    budget = budget_du_jour(chemins.config_dir)
    session_active = bool(st.session_state.get("global_cookie"))

    afficher_bandeau_contexte("Ce qui vous attend aujourd'hui.", [
        ("Session LinkedIn active", "ok", True) if session_active
        else ("Session LinkedIn absente", "attention"),
        (texte_budget(budget.utilisees, budget.plafond),
         ton_budget(budget.utilisees, budget.plafond)),
    ])

    actions = actions_du_jour(
        nb_a_messager=len(db.acceptees_non_messagees()),
        nb_en_attente=len(db.invitations_en_attente()),
        session_active=session_active,
        budget_utilisees=budget.utilisees,
        budget_plafond=budget.plafond,
    )

    _bloc_a_faire(actions)

    afficher_bloc_chiffres(db, str(chemins.config_dir))
