# -*- coding: utf-8 -*-
"""Page 📊 Dashboard (« Tableau de bord ») : ce qui vous attend aujourd'hui.

Trois questions, dans l'ordre où on se les pose en ouvrant l'outil :
qu'est-ce que je dois faire maintenant (bloc « À faire »), combien
d'invitations me reste-t-il (la jauge du budget), où en sont mes prospects
(le parcours trouvés → invités → acceptés → message envoyé).
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd
import plotly.express as px
import streamlit as st

from ui.composants import (afficher_bandeau_contexte, afficher_carte_action,
                           afficher_entonnoir, afficher_jauge_budget, pluriel,
                           ton_budget)
from utils.budget import budget_du_jour
from wefiit_theme import PALETTE_GRAPHIQUES

# Identifiants internes des pages (voir PAGES dans app_advanced.py).
PAGE_MESSAGES = "✉️ Messages"
PAGE_RECHERCHE = "🔍 Recherche"
PAGE_VEILLE = "🏢 Veille"

# Fichier où la page Veille note la date de la visite précédente. Lu ici
# seulement : c'est la page Veille qui l'écrit quand on la consulte.
_VISITE_VEILLE = "derniere_visite_veille.txt"


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


def actions_du_jour(nb_a_messager: int, nb_en_attente: int, nb_nouveaux_veille: int,
                    budget_epuise: bool, session_active: bool
                    ) -> List[Tuple[str, str, str, str, Optional[Tuple[str, str, str]]]]:
    """Les cartes « À faire » qui s'appliquent, de la plus urgente à la moins.

    Chaque entrée : (titre, détail, ton, icône, bouton) où bouton vaut
    (libellé, clé, page cible) ou None. Liste vide = rien d'urgent.
    Pure : testée sans Streamlit.
    """
    actions = []
    if not session_active:
        actions.append((
            "Connectez votre session LinkedIn",
            "Sans elle, aucune recherche ni invitation ne peut partir. "
            "Elle se renseigne depuis la page Recherche.",
            "attention", "alerte",
            ("Aller à Recherche", "tdb_aller_recherche", PAGE_RECHERCHE),
        ))
    if nb_a_messager:
        verbe = "a accepté" if nb_a_messager < 2 else "ont accepté"
        actions.append((
            f"{pluriel(nb_a_messager, 'personne')} {verbe} votre invitation",
            "Envoyez-leur un message depuis la page Messages.",
            "accent", "message",
            ("Ouvrir Messages", "tdb_ouvrir_messages", PAGE_MESSAGES),
        ))
    if nb_nouveaux_veille:
        actions.append((
            f"{pluriel(nb_nouveaux_veille, 'nouveau contact', 'nouveaux contacts')} "
            "dans vos entreprises suivies",
            "Trouvés depuis votre dernière visite de la Veille.",
            "neutre", "veille",
            ("Ouvrir Veille", "tdb_ouvrir_veille", PAGE_VEILLE),
        ))
    if nb_en_attente:
        actions.append((
            f"{pluriel(nb_en_attente, 'invitation')} en attente de réponse",
            "Vérifiez qui a accepté depuis la page Messages.",
            "neutre", "invitation", None,
        ))
    if budget_epuise:
        actions.append((
            "Budget d'invitations du jour épuisé",
            "Les invitations reprennent demain : en attendant, préparez vos "
            "recherches ou vos messages.",
            "danger", "alerte", None,
        ))
    return actions


def _nouveaux_contacts_veille(chemins) -> int:
    """Contacts visés trouvés par la Veille depuis la dernière visite de la page.

    Lecture seule : la date de visite vient de la session si la page Veille
    a déjà été ouverte (elle y garde la visite précédente), sinon du fichier
    qu'elle tient à jour. « Autre » (hors familles visées) n'est pas compté,
    comme dans le récap de la page Veille. Toute erreur vaut 0 : cette carte
    est un rappel, pas une raison de faire tomber le tableau de bord.
    """
    try:
        from veille_store import VeilleStore
        if "veille_visite_precedente" in st.session_state:
            visite = st.session_state["veille_visite_precedente"]
        else:
            chemin = Path(chemins.config_dir) / _VISITE_VEILLE
            visite = ((chemin.read_text(encoding="utf-8").strip() or None)
                      if chemin.exists() else None)
        if visite is None:
            # Jamais ouverte : pas de « depuis votre dernière visite » à annoncer.
            return 0
        contacts = VeilleStore(str(chemins.db_file)).nouveautes_depuis(visite)["contacts"]
        return sum(1 for c in contacts if c.get("famille") != "Autre")
    except Exception:
        return 0


def _bloc_a_faire(actions) -> None:
    st.subheader("À faire")
    if not actions:
        afficher_carte_action(
            "Rien d'urgent",
            "Aucune réponse à traiter. Lancez une recherche pour trouver de "
            "nouveaux profils.",
            ton="ok", icone="ok",
        )
        return
    for titre, detail, ton, icone, bouton in actions:
        if bouton is None:
            afficher_carte_action(titre, detail, ton=ton, icone=icone)
            continue
        libelle, cle, cible = bouton
        col_carte, col_bouton = st.columns([3, 1], vertical_alignment="center")
        with col_carte:
            afficher_carte_action(titre, detail, ton=ton, icone=icone)
        with col_bouton:
            st.button(libelle, key=cle, on_click=_aller_a, args=(cible,),
                      width="stretch")


def _bloc_derniere_recherche(derniere) -> None:
    with st.container(border=True):
        if derniere:
            mots = (derniere.get("keyword") or "Sans mot-clé").replace("*", "").replace("_", " ")
            st.markdown(f"**Dernière recherche**  \n{mots}")
            st.caption(f"{date_locale(derniere.get('date'))} · "
                       f"{pluriel(int(derniere.get('nb_profils') or 0), 'profil')}")
        else:
            st.markdown("**Dernière recherche**")
            st.caption("Aucune recherche pour l'instant.")
        st.button("Nouvelle recherche", key="tdb_nouvelle_recherche",
                  icon=":material/search:", on_click=_aller_a,
                  args=(PAGE_RECHERCHE,), width="stretch")


def _bloc_ecoles(par_ecole: dict) -> None:
    """Répartition par école : secondaire, repliée.

    Gardée parce que l'équipe cible des écoles précises et veut voir où se
    concentre son fichier ; repliée parce qu'elle ne dit pas quoi faire
    aujourd'hui. Barres horizontales triées (lisibles même avec 15 écoles,
    contrairement à l'ancien camembert).
    """
    if not par_ecole:
        return
    with st.expander("Répartition par école"):
        df = (pd.DataFrame(list(par_ecole.items()), columns=["École", "Profils"])
              .sort_values("Profils", ascending=True))
        fig = px.bar(df, x="Profils", y="École", orientation="h", text="Profils",
                     color_discrete_sequence=PALETTE_GRAPHIQUES[:1])
        fig.update_traces(textposition="outside", cliponaxis=False,
                          hovertemplate="%{y} : %{x}<extra></extra>")
        fig.update_layout(
            font_family="Inter, sans-serif", showlegend=False,
            margin=dict(t=10, b=10, l=10, r=30),
            height=max(160, 34 * len(df) + 40),
            xaxis=dict(title=None, showgrid=False, showticklabels=False),
            yaxis=dict(title=None),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, width="stretch",
                        config={"displayModeBar": False})


def afficher_page_tableau_de_bord():
    st.title("Tableau de bord")

    db = st.session_state.db
    chemins = st.session_state.user_paths
    stats = db.get_statistiques()
    parcours = db.compter_parcours()
    budget = budget_du_jour(chemins.config_dir)
    session_active = bool(st.session_state.get("global_cookie"))

    afficher_bandeau_contexte("Ce qui vous attend aujourd'hui.", [
        ("Session LinkedIn active", "ok", True) if session_active
        else ("Session LinkedIn absente", "attention"),
        (f"{budget.utilisees} / {budget.plafond} invitations",
         ton_budget(budget.utilisees, budget.plafond)),
    ])

    actions = actions_du_jour(
        nb_a_messager=len(db.acceptees_non_messagees()),
        nb_en_attente=len(db.invitations_en_attente()),
        nb_nouveaux_veille=_nouveaux_contacts_veille(chemins),
        budget_epuise=budget.epuise,
        session_active=session_active,
    )

    col_gauche, col_droite = st.columns([2, 1], gap="large")
    with col_gauche:
        _bloc_a_faire(actions)
    with col_droite:
        # La jauge remplace l'ancienne métrique « n / max » : un plafond
        # n'est pas une hausse, il se lit en crans restants.
        afficher_jauge_budget(budget.utilisees, budget.plafond)
        _bloc_derniere_recherche(stats.get("derniere_recherche"))

    st.subheader("Parcours de vos prospects")
    afficher_entonnoir([
        ("Profils trouvés", parcours["trouves"]),
        ("Invités", parcours["invites"]),
        ("Acceptés", parcours["acceptes"]),
        ("Message envoyé", parcours["messages"]),
    ])
    if parcours["invites"]:
        st.caption(
            f"Taux d'acceptation : {taux_acceptation(parcours['invites'], parcours['acceptes'])}"
            " des personnes invitées. Chaque pourcentage compare une étape à la précédente."
        )
    else:
        st.caption("Aucune invitation envoyée pour l'instant : le taux d'acceptation "
                   "apparaîtra dès la première.")

    _bloc_ecoles(stats.get("par_ecole") or {})
