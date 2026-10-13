# -*- coding: utf-8 -*-
"""Assemblage des filtres de recherche saisis dans l'interface."""

from typing import List, Optional


def _nom_cherchable(entreprise: str) -> str:
    """Retire le parenthétique explicatif d'un nom de cabinet.

    « AKKODIS (ex- AKKA & Modis) » → « AKKODIS » : seule la raison sociale
    courte est utilisable comme filtre LinkedIn.
    """
    return entreprise.split("(")[0].strip()


def parse_entreprises(
    texte_libre: Optional[str], concurrents: Optional[List[str]]
) -> List[str]:
    """Fusionne les cabinets sélectionnés et les entreprises saisies à la main.

    Le texte libre accepte plusieurs noms séparés par des virgules. Les
    doublons sont supprimés sans tenir compte de la casse, la première
    occurrence gagne (les cabinets sélectionnés passent en premier).
    """
    noms = [_nom_cherchable(c) for c in (concurrents or [])]
    noms += [part.strip() for part in (texte_libre or "").split(",")]

    resultat: List[str] = []
    vus = set()
    for nom in noms:
        if not nom or nom.lower() in vus:
            continue
        vus.add(nom.lower())
        resultat.append(nom)
    return resultat


def criteres_suffisants(
    mots_cles: Optional[str],
    ecoles: Optional[List[str]],
    entreprises: Optional[List[str]],
    secteurs: Optional[List[str]],
) -> bool:
    """Y a-t-il de quoi lancer une recherche ?

    L'onglet Candidats exigeait auparavant un filtre (école, entreprise ou
    secteur), ce que l'onglet Clients/Entreprises n'a jamais demandé. Une
    recherche par mots-clés seuls est pourtant légitime.

    Reste un garde-fou : sans aucun critère, LinkedIn renverrait une liste de
    profils au hasard, et le quota quotidien d'invitations y passerait sur un
    simple clic malheureux.
    """
    return bool((mots_cles or "").strip() or ecoles or entreprises or secteurs)
