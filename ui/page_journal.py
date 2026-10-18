# -*- coding: utf-8 -*-
"""Page « Journal » : ce que We.Reach a fait récemment.

La vue par défaut est une liste d'événements lisible par tous, construite à
partir du fichier journal (format de `logger.py` :
« AAAA-MM-JJ HH:MM:SS - nom - NIVEAU - message »). Le journal brut, avec
ses traces techniques, reste disponible dans un dépliant pour le support.

Les fonctions d'analyse sont pures (testables sans Streamlit).
"""

import os
import re
from collections import deque
from datetime import datetime
from typing import Dict, Iterable, List, Optional

import pandas as pd
import streamlit as st

from config import ScraperConfig
from ui.composants import afficher_bandeau_contexte, afficher_etat_vide, pluriel

# « 2026-10-18 02:26:14 - linkedin_scraper - ERROR - message »
_LIGNE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})(?:,\d+)? - (?P<nom>.*?) - "
    r"(?P<niveau>DEBUG|INFO|WARNING|ERROR|CRITICAL) - (?P<message>.*)$"
)

TYPES = {"INFO": "Information", "WARNING": "Attention",
         "ERROR": "Erreur", "CRITICAL": "Erreur"}
FILTRE_TOUT = "Tout"
FILTRE_ALERTES = "Attention et erreurs"

# Chemins de fichiers (absolus, ou relatifs avec au moins un dossier) :
# sans intérêt pour l'utilisateur, et ils exposent l'arborescence du poste.
_URL = re.compile(r"https?://\S+")
_CHEMIN_CITE = re.compile(r"(['\"])(?:[A-Za-z]:)?[/\\][^'\"]*\1")
_CHEMIN = re.compile(r"(?:[A-Za-z]:)?(?:[/\\][^\s/\\'\"«»(),]+){2,}|\b[\w.-]+/[\w./-]+\.\w+\b")
# Ce qui précède la première lettre ou le premier chiffre : émojis, flèches, puces.
_DEBUT_DECORATIF = re.compile(r"^[^\w«\"'(]+", re.UNICODE)
# Messages internes de diagnostic, sans intérêt pour l'utilisateur.
_TECHNIQUE = re.compile(r"\bdump", re.IGNORECASE)


def nettoyer_message(message: str) -> str:
    """Retire les décorations de tête (émojis, flèches) et masque les chemins."""
    texte = _URL.sub("(lien)", message or "")
    texte = _CHEMIN_CITE.sub("(fichier)", texte)
    texte = _CHEMIN.sub("(fichier)", texte)
    texte = _DEBUT_DECORATIF.sub("", texte.strip())
    texte = re.sub(r"\s{2,}", " ", texte).strip()
    return texte[:1].upper() + texte[1:] if texte else texte


def derniere_ligne_exception(trace: Iterable[str]) -> Optional[str]:
    """La ligne qui nomme l'exception à la fin d'une trace Python
    (« ValueError: … »), ou None si la suite n'est pas une trace."""
    lignes = [l.rstrip() for l in trace if l.strip()]
    if not lignes:
        return None
    for l in reversed(lignes):
        if l.startswith((" ", "\t", "Traceback", "During handling", "The above exception")):
            continue
        if set(l.strip()) <= set("^~ "):
            continue
        return l.strip()
    return None


def analyser_journal(lignes: Iterable[str]) -> List[Dict]:
    """Découpe des lignes de journal en événements, dans l'ordre du fichier.

    Chaque événement : {"date": datetime, "niveau": str, "message": str,
    "suite": [lignes de continuation]}. Les lignes de continuation (trace
    Python, message sur plusieurs lignes) s'attachent à l'événement qui les
    précède ; celles qui précèdent tout événement (début d'extrait coupé au
    milieu d'une trace) sont ignorées.
    """
    evenements: List[Dict] = []
    for brute in lignes:
        ligne = brute.rstrip("\r\n")
        m = _LIGNE.match(ligne)
        if m:
            try:
                date = datetime.strptime(m.group("date"), "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            evenements.append({"date": date, "niveau": m.group("niveau"),
                               "message": m.group("message"), "suite": []})
        elif evenements:
            evenements[-1]["suite"].append(ligne)
    return evenements


def evenement_lisible(ev: Dict) -> Optional[Dict]:
    """Ligne du tableau « Heure / Type / Événement », ou None si l'événement
    n'est pas destiné à l'utilisateur (détail de diagnostic, DEBUG)."""
    type_ = TYPES.get(ev["niveau"])
    if type_ is None or _TECHNIQUE.search(ev["message"]):
        return None
    texte = nettoyer_message(ev["message"])
    exception = derniere_ligne_exception(ev["suite"]) if any(
        l.startswith("Traceback") for l in ev["suite"]) else None
    if exception:
        detail = f"Erreur technique : {nettoyer_message(exception)}"
        texte = f"{texte.rstrip(' .:')}. {detail}" if texte else detail
    if not texte:
        return None
    return {"Heure": ev["date"].strftime("%d/%m %H:%M:%S"), "Type": type_,
            "Événement": texte}


def evenements_lisibles(lignes: Iterable[str], filtre: str = FILTRE_TOUT) -> List[Dict]:
    """Les événements utiles, du plus récent au plus ancien."""
    lus = []
    for ev in analyser_journal(lignes):
        ligne = evenement_lisible(ev)
        if ligne is None:
            continue
        if filtre == FILTRE_ALERTES and ligne["Type"] == "Information":
            continue
        lus.append(ligne)
    lus.reverse()
    return lus


def _dernieres_lignes(chemin: str, n: int) -> List[str]:
    with open(chemin, "r", encoding="utf-8", errors="replace") as f:
        return list(deque(f, maxlen=n))


def afficher_page_journal():
    st.title("Journal d'exécution")
    afficher_bandeau_contexte("Ce que We.Reach a fait récemment.")

    col_filtre, col_nb, col_btn = st.columns([3, 2, 1], vertical_alignment="bottom")
    with col_filtre:
        filtre = st.segmented_control(
            "Afficher", [FILTRE_TOUT, FILTRE_ALERTES], default=FILTRE_TOUT,
            key="journal_filtre",
        ) or FILTRE_TOUT
    with col_nb:
        nb_lignes = st.number_input("Lignes du journal à parcourir", min_value=20,
                                    max_value=5000, value=200, step=20)
    with col_btn:
        if st.button("Actualiser", icon=":material/refresh:", width="stretch"):
            st.rerun()

    log_path = ScraperConfig.LOG_FILE
    if not os.path.exists(log_path):
        afficher_etat_vide(
            "Rien à afficher pour l'instant",
            "Les recherches, invitations et messages lancés depuis We.Reach "
            "apparaîtront ici au fil de l'eau.",
        )
        return

    try:
        lignes = _dernieres_lignes(log_path, int(nb_lignes))
    except OSError as e:
        st.error(f"Impossible de lire le journal : {e}")
        return

    evenements = evenements_lisibles(lignes, filtre)
    if evenements:
        st.caption(pluriel(len(evenements), "événement") + ", du plus récent au plus ancien.")
        st.dataframe(
            pd.DataFrame(evenements, columns=["Heure", "Type", "Événement"]),
            hide_index=True, width="stretch",
            height=min(38 + 35 * len(evenements), 560),
            column_config={
                "Heure": st.column_config.TextColumn("Heure", width=130),
                "Type": st.column_config.TextColumn("Type", width=110),
                "Événement": st.column_config.TextColumn("Événement", width="large"),
            },
        )
    elif filtre == FILTRE_ALERTES:
        afficher_etat_vide(
            "Aucune alerte récente",
            "Rien ne s'est mal passé dans la période parcourue. "
            "Augmentez le nombre de lignes pour remonter plus loin.",
        )
    else:
        afficher_etat_vide(
            "Aucun événement récent",
            "Augmentez le nombre de lignes pour remonter plus loin, "
            "ou lancez une recherche pour voir son déroulement ici.",
        )

    with st.expander("Détail technique (pour le support)"):
        st.caption("Le journal brut, tel que l'enregistre We.Reach. "
                   "Utile si le support vous le demande.")
        st.code("".join(lignes) or "(journal vide)", language="log", height=480)
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                complet = f.read()
        except OSError:
            complet = "".join(lignes)
        st.download_button(
            "Télécharger le journal complet", data=complet,
            file_name="journal-we-reach.log", mime="text/plain",
            icon=":material/download:",
        )
        st.caption("Le journal est commun à tous les utilisateurs de cette installation.")
