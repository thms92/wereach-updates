# -*- coding: utf-8 -*-
"""Libellé d'école enregistré sur un profil.

Une recherche peut viser plusieurs écoles à la fois (pilules « Dauphine » +
« ESCP »). Chaque profil trouvé est alors enregistré avec le libellé composite
« Dauphine / ESCP » : on ignore laquelle de ces écoles il a réellement
fréquentée, et le libellé garde fidèlement ce que la recherche ciblait.

Ce module est le seul endroit qui connaît la forme de ce libellé. Ses lecteurs
— filtre de la page Historique, camembert « Répartition par école » du
Dashboard — passent par lui plutôt que de comparer la colonne `ecole` à un nom
d'école, comparaison qui ne ramenait aucun profil.
"""

from typing import Dict, Iterable, List, Tuple

SEPARATEUR = " / "


def composer_libelle(noms: Iterable[str]) -> str:
    """Assemble le libellé enregistré pour une recherche multi-écoles."""
    return SEPARATEUR.join(n for n in (str(x).strip() for x in noms) if n)


def ecoles_du_libelle(libelle: str) -> List[str]:
    """Éclate un libellé en ses écoles. Un libellé simple en rend une seule."""
    return [part.strip() for part in (libelle or "").split(SEPARATEUR) if part.strip()]


def libelle_vise_ecole(libelle: str, ecole: str) -> bool:
    """True si `ecole` fait partie du libellé.

    La comparaison est littérale, nom par nom. Surtout pas `str.contains` :
    son argument serait interprété comme une expression régulière, et des noms
    de la table ECOLES comme « Université d'Angers » ou « Ingé Epita » n'ont
    aucune raison d'être traités comme des motifs.
    """
    cible = (ecole or "").strip().casefold()
    if not cible:
        return False
    return any(nom.casefold() == cible for nom in ecoles_du_libelle(libelle))


def repartir_par_ecole(lignes: Iterable[Tuple[str, int]]) -> Dict[str, int]:
    """Convertit un comptage `(libellé, n)` en un comptage par école.

    `[("Dauphine / ESCP", 3)]` → `{"Dauphine": 3, "ESCP": 3}` : le camembert
    montre des écoles, pas des intitulés de recherche.
    """
    compte: Dict[str, int] = {}
    for libelle, nb in lignes:
        for nom in ecoles_du_libelle(libelle):
            compte[nom] = compte.get(nom, 0) + int(nb)
    return compte
