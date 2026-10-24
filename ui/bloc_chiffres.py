# -*- coding: utf-8 -*-
"""Tableau de bord : le bloc « Vos chiffres ».

Les invitations envoyées sur une période (7 jours, 30 jours ou une plage
choisie), filtrables par école, entreprise et poste : cinq tuiles, la date de
la dernière vérification des acceptations, un graphique semaine par semaine
et trois tableaux. Les calculs vivent dans `utils/chiffres.py` ; ce module ne
fait que choisir la période et afficher.
"""

from datetime import date, datetime
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ui.composants import _nombre, afficher_etat_vide, pluriel
from utils.chiffres import (Periode, chiffres_cles, filtrer, options_filtres,
                            par_categorie, par_semaine, periode_glissante,
                            texte_taux)
from utils.verification import derniere_verification
from wefiit_theme import PALETTE_GRAPHIQUES

PERIODE_7, PERIODE_30, PERIODE_PLAGE = "7 jours", "30 jours", "Plage personnalisée"
ORANGE_ACCEPTEES = "#F98F03"

# (clé de la ligne, clé du widget, libellé du filtre et première colonne)
_CATEGORIES = (("ecole", "tdb_f_ecole", "École"),
               ("entreprise", "tdb_f_entreprise", "Entreprise"),
               ("poste", "tdb_f_poste", "Poste"))
_TITRES_TABLEAUX = {"ecole": "Par école", "entreprise": "Par entreprise",
                    "poste": "Par poste"}


def periode_choisie(choix: Optional[str], plage, aujourd_hui: date) -> Periode:
    """Choix de période (+ valeur du sélecteur de dates) → `Periode`.

    Pendant qu'on choisit une plage, le sélecteur ne rend qu'une date : on
    prend ce jour-là. Des dates inversées sont remises dans l'ordre. Un
    choix absent ou une plage vide donnent les 30 derniers jours.
    Pure : testée sans Streamlit.
    """
    if choix == PERIODE_7:
        return periode_glissante(7, aujourd_hui)
    if choix == PERIODE_PLAGE:
        dates = [plage] if isinstance(plage, date) else [d for d in (plage or ()) if d]
        if dates:
            return Periode(min(dates[:2]), max(dates[:2]))
    return periode_glissante(30, aujourd_hui)


def texte_verification(moment: Optional[datetime]) -> str:
    """Quand les acceptations ont été vérifiées pour la dernière fois (heure locale)."""
    if moment is None:
        return ("Acceptations jamais vérifiées : utilisez « Vérifier qui a accepté » "
                "dans la page Messages.")
    local = moment.astimezone()
    return (f"Acceptations vérifiées pour la dernière fois le {local:%d/%m} à "
            f"{local:%H:%M}, depuis la page Messages.")


def texte_jamais_verifiees(n: int) -> str:
    verbe = "n'a jamais été vérifiée" if n < 2 else "n'ont jamais été vérifiées"
    return f"{pluriel(n, 'invitation')} de la période {verbe}."


def _filtres(lignes, aujourd_hui: date):
    """La ligne de filtres ; rend (période, {clé: valeurs choisies})."""
    options = options_filtres(lignes)
    col_periode, *cols = st.columns([2.2, 1, 1, 1], vertical_alignment="top")
    with col_periode:
        choix = st.segmented_control(
            "Période", [PERIODE_7, PERIODE_30, PERIODE_PLAGE], default=PERIODE_30,
            required=True, key="tdb_periode")
        plage = None
        if choix == PERIODE_PLAGE:
            # Valeur par défaut seulement à la création : la donner alors que
            # la clé existe déjà fait afficher un avertissement à Streamlit.
            defaut = {} if "tdb_plage" in st.session_state else {
                "value": (periode_glissante(30, aujourd_hui).debut, aujourd_hui)}
            plage = st.date_input("Dates", key="tdb_plage", format="DD/MM/YYYY",
                                  max_value=aujourd_hui, **defaut)
    choisis = {}
    for col, (cle, cle_widget, libelle) in zip(cols, _CATEGORIES):
        with col:
            choisis[cle] = st.multiselect(libelle, options[cle], key=cle_widget,
                                          placeholder="Choisir…")
    return periode_choisie(choix, plage, aujourd_hui), choisis


def _tuiles(chiffres) -> None:
    colonnes = st.columns(5)
    tuiles = (
        ("Invitations", _nombre(chiffres.invitations), None),
        ("Acceptées", _nombre(chiffres.acceptees), None),
        ("Taux d'acceptation", texte_taux(chiffres.acceptees, chiffres.invitations),
         f"{_nombre(chiffres.acceptees)} sur {_nombre(chiffres.invitations)}"),
        ("Messages envoyés", _nombre(chiffres.messages), None),
        ("En attente", _nombre(chiffres.en_attente), None),
    )
    for col, (libelle, valeur, dessous) in zip(colonnes, tuiles):
        # Le « X sur Y » passe par le delta, neutralisé (ni flèche ni couleur).
        col.metric(libelle, valeur, dessous, delta_color="off", delta_arrow="off",
                   height="stretch")


def _graphique(lignes, periode: Periode) -> None:
    semaines = par_semaine(lignes, periode)
    etiquettes = [f"S{lundi.isocalendar()[1]}" for lundi, _, _ in semaines]
    dates = [f"semaine du {lundi:%d/%m}" for lundi, _, _ in semaines]
    fig = go.Figure()
    for nom, valeurs, couleur in (
            ("Invitations", [inv for _, inv, _ in semaines], PALETTE_GRAPHIQUES[0]),
            ("Acceptées", [acc for _, _, acc in semaines], ORANGE_ACCEPTEES)):
        fig.add_bar(name=nom, x=etiquettes, y=valeurs, marker_color=couleur,
                    customdata=dates,
                    hovertemplate=f"%{{x}} (%{{customdata}}) : %{{y}} {nom.lower()}<extra></extra>")
    fig.update_layout(
        barmode="group", bargap=0.35, bargroupgap=0.08,
        font_family="Inter, sans-serif", height=260,
        margin=dict(t=30, b=10, l=10, r=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None),
        xaxis=dict(title=None, showgrid=False, type="category"),
        yaxis=dict(title=None, rangemode="tozero", tickformat="d",
                   gridcolor="rgba(127,127,127,0.15)"),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def _tableau(lignes, cle: str, libelle: str) -> None:
    st.subheader(_TITRES_TABLEAUX[cle], anchor=False)
    df = pd.DataFrame(
        [{libelle: l.libelle, "Invités": l.invites, "Acceptés": l.acceptes,
          "Taux": texte_taux(l.acceptes, l.invites)} for l in par_categorie(lignes, cle)],
        columns=[libelle, "Invités", "Acceptés", "Taux"])
    st.dataframe(df, hide_index=True, width="stretch",
                 column_config={libelle: st.column_config.TextColumn(width="large")})


def afficher_bloc_chiffres(db, config_dir: str,
                           aujourd_hui: Optional[date] = None) -> None:
    aujourd_hui = aujourd_hui or date.today()
    with st.container(key="tdb_chiffres"):
        st.header("Vos chiffres", anchor=False)
        lignes = db.lignes_suivi()
        if not lignes:
            # Un mur de zéros n'apprend rien : on dit comment le remplir.
            afficher_etat_vide(
                "Lancez votre première recherche",
                "Vos chiffres s'afficheront ici dès vos premières invitations.",
                etapes=("Connecter la session LinkedIn",
                        "Lancer une recherche",
                        "Suivre les réponses dans Messages"),
            )
            return

        periode, choisis = _filtres(lignes, aujourd_hui)
        retenues = filtrer(lignes, periode, ecoles=choisis["ecole"],
                           entreprises=choisis["entreprise"], postes=choisis["poste"])
        if not retenues:
            st.info("Aucune invitation sur cette période avec ces filtres.")
            return

        chiffres = chiffres_cles(retenues)
        _tuiles(chiffres)
        verification = texte_verification(derniere_verification(config_dir))
        if chiffres.jamais_verifiees:
            verification += " " + texte_jamais_verifiees(chiffres.jamais_verifiees)
        st.caption(verification)

        _graphique(retenues, periode)
        for cle, _, libelle in _CATEGORIES:
            _tableau(retenues, cle, libelle)
