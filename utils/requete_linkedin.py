# -*- coding: utf-8 -*-
"""Construction des recherches de personnes LinkedIn (adresse et mots-clés).

Logique pure, sortie de `scraper_v2.py` : aucune page, aucun réseau. La
seule dépendance extérieure, la résolution d'une entreprise en identifiant
LinkedIn, est passée en paramètre (`resoudre_urn`). `LinkedInScraperV2`
garde ses anciens noms (`_normalize_keyword`, `construire_url_recherche`…),
qui délèguent ici.
"""

import urllib.parse
from typing import Callable, List, Optional, Union

from config import ECOLES
from logger import logger
from utils.ecoles import composer_libelle
from utils.search_filters import equilibrer_parentheses

# Nombre maximum de valeurs par facette LinkedIn. Au-delà, l'URL devient
# anormalement longue — c'est un signal de détection côté LinkedIn.
MAX_VALEURS_PAR_FACETTE = 10


def as_list(valeur) -> List[str]:
    """Normalise None / str / liste en liste de chaînes non vides."""
    if valeur is None:
        return []
    if isinstance(valeur, str):
        valeur = [valeur]
    return [str(v).strip() for v in valeur if str(v).strip()]


def plafonner(valeurs: List[str], nom_facette: str) -> List[str]:
    """Limite une facette à MAX_VALEURS_PAR_FACETTE valeurs."""
    if len(valeurs) <= MAX_VALEURS_PAR_FACETTE:
        return valeurs
    logger.warning(
        f"⚠️ {len(valeurs)} {nom_facette} sélectionnées — "
        f"seules les {MAX_VALEURS_PAR_FACETTE} premières sont utilisées."
    )
    return valeurs[: MAX_VALEURS_PAR_FACETTE]


def encoder_facette(valeurs: List[str]) -> str:
    """Encode une facette LinkedIn : ["a","b"] → %5B%22a%22%2C%22b%22%5D."""
    return "%5B" + "%2C".join(f"%22{v}%22" for v in valeurs) + "%5D"


def expression_ou(noms: List[str]) -> str:
    """Construit `"A"` (une valeur) ou `("A" OR "B")` (plusieurs)."""
    cites = ['"{}"'.format(n.replace('"', '\\"')) for n in noms]
    if len(cites) == 1:
        return cites[0]
    return "(" + " OR ".join(cites) + ")"


def combiner_et(base: str, expression: str) -> str:
    """Ajoute `AND <expression>` à une requête booléenne existante.

    La base est parenthésée si elle contient déjà un OU, sinon le AND
    n'aurait pas la bonne priorité.
    """
    base = (base or "").strip()
    if not base:
        return expression
    if " OR " in base.upper():
        base = f"({base})"
    return f"{base} AND {expression}"


def nom_ecole(ecole_id: str) -> str:
    """Retrouve le nom d'une école à partir de sa valeur dans ECOLES."""
    for nom, id_ in ECOLES.items():
        if str(id_) == str(ecole_id):
            return nom
    return str(ecole_id)


def libelle_ecoles(ecoles_ids: List[str]) -> str:
    """Libellé enregistré sur chaque profil : « Dauphine / ESCP »."""
    return composer_libelle(nom_ecole(e) for e in ecoles_ids)


def construire_url_recherche(
    keyword: str,
    entreprises: Union[str, List[str], None],
    ecoles_ids: List[str],
    ile_de_france: bool = False,
    secteurs_ids: Optional[List[str]] = None,
    *,
    resoudre_urn: Callable[[str], Optional[str]],
) -> str:
    """
    Construit l'URL de recherche LinkedIn

    Args:
        keyword: Mots-clés de recherche
        entreprises: Entreprise(s) ciblée(s) — une chaîne ou une liste
        ecoles_ids: IDs (ou noms) des écoles, tels que stockés dans ECOLES
        ile_de_france: Filtrer sur la région Île-de-France (optionnel)
        secteurs_ids: IDs numériques de secteurs LinkedIn (facette industry)

    Returns:
        URL complète de recherche

    Sémantique LinkedIn :
        Les valeurs d'une MÊME facette sont combinées en OU
        (`currentCompany=["A","B"]` = chez A ou chez B), et les facettes
        entre elles en ET (école ET entreprise ET secteur).

    Note sur les replis :
        LinkedIn attend des identifiants numériques pour `currentCompany`
        (URN entreprise) et `schoolFilter` (ID école). Quand un seul
        identifiant d'une facette manque, TOUTE la facette bascule dans la
        recherche booléenne : `(kw) AND ("A" OR "B")`. Mélanger les deux
        (`currentCompany=[urnA]` + `"B"` en mot-clé) produirait un ET et
        ne renverrait rien.
    """
    base_url = "https://www.linkedin.com/search/results/people/?"
    params = []

    # Seules les entreprises sont plafonnées, et non pour la longueur de
    # l'URL — elle fait 742 caractères avec les 38 écoles, pour une limite
    # pratique de 8 000. La vraie raison est le nombre d'appels à l'API de
    # LinkedIn : chaque entreprise non connue en déclenche un pour résoudre
    # son identifiant. Écoles et secteurs ont leurs identifiants dans
    # config.py, donc aucun appel : rien ne justifie de les tronquer.
    entreprises = plafonner(as_list(entreprises), "entreprises")
    ecoles_ids = as_list(ecoles_ids)
    # Les secteurs n'ont pas de repli booléen : un ID non numérique est
    # forcément une erreur de configuration, on l'ignore.
    secteurs_ids = [s for s in as_list(secteurs_ids) if s.isdigit()]

    # Normaliser le keyword : retirer les parenthèses englobantes inutiles
    # car LinkedIn renvoie 0 résultat quand toute la requête est entourée
    # d'une seule paire de parens (ex: `(A OR B OR C)` → 0 résultat,
    # alors que `A OR B OR C` → résultats).
    # Une parenthèse oubliée rend l'expression invalide et LinkedIn
    # répond « Aucun résultat » sans erreur — indiagnostiquable. On répare
    # avant d'envelopper quoi que ce soit, sinon on aggrave le défaut.
    keywords_combines = normalize_keyword(equilibrer_parentheses(keyword))

    # Facette entreprise : tout-ou-rien (cf. note sur les replis)
    urns = [resoudre_urn(e) for e in entreprises]
    if entreprises and all(urns):
        company_urns = urns
    else:
        company_urns = []
        if entreprises:
            keywords_combines = combiner_et(
                keywords_combines, expression_ou(entreprises)
            )

    # Facette école : même règle. Les entrées non numériques de ECOLES sont
    # des noms (ID LinkedIn pas encore connu) → repli pour toute la facette.
    # Une seule école sans identifiant faisait auparavant basculer la
    # TOTALITÉ du filtre en recherche textuelle : trois écoles obscures
    # suffisaient à ruiner une sélection de quarante. On écarte celles qui
    # n'ont pas d'identifiant et on garde le filtre précis pour les autres
    # — l'interface nomme les écartées. Le repli textuel ne subsiste que
    # si AUCUNE n'a d'identifiant, sinon il ne resterait aucun critère.
    ecoles_avec_id = [e for e in ecoles_ids if e.isdigit()]
    if ecoles_avec_id:
        ecoles_filter = ecoles_avec_id
    else:
        ecoles_filter = []
        if ecoles_ids:
            keywords_combines = combiner_et(
                keywords_combines,
                expression_ou([nom_ecole(e) for e in ecoles_ids]),
            )

    # Les replis peuvent avoir produit une requête entièrement parenthésée
    # (ex. `("A" OR "B")` quand il n'y a aucun mot-clé) → 0 résultat chez
    # LinkedIn. On repasse la normalisation après combinaison.
    keywords_combines = normalize_keyword(keywords_combines)

    if keywords_combines:
        params.append(f"keywords={urllib.parse.quote(keywords_combines)}")

    params.append("origin=FACETED_SEARCH")

    # Filtre géographique Île-de-France
    if ile_de_france:
        params.append('geoUrn=%5B%22104246759%22%5D')

    if company_urns:
        params.append(f"currentCompany={encoder_facette(company_urns)}")

    if ecoles_filter:
        params.append(f"schoolFilter={encoder_facette(ecoles_filter)}")

    if secteurs_ids:
        params.append(f"industry={encoder_facette(secteurs_ids)}")

    url = base_url + "&".join(params)
    logger.debug(f"URL construite: {url}")
    return url


def normalize_keyword(keyword: str) -> str:
    """Retire les parenthèses englobantes inutiles d'une requête keyword.

    LinkedIn n'aime pas qu'une requête entière soit entourée d'une seule
    paire de parens (`(A OR B OR C)` → 0 résultat) alors que la même
    requête sans parens englobantes (`A OR B OR C`) retourne bien des
    résultats. Cette fonction retire UNIQUEMENT les parens externes qui
    englobent toute l'expression (sans casser des sous-groupes type
    `(A OR B) AND (C OR D)`).
    """
    if not keyword:
        return keyword or ""
    kw = keyword.strip()
    while len(kw) >= 2 and kw[0] == "(" and kw[-1] == ")":
        # Vérifier que ces parens forment un seul groupe englobant
        depth = 0
        envelops_all = True
        for i, ch in enumerate(kw):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                # Si on retombe à 0 avant la fin, ce ne sont pas des
                # parens englobantes (ex: `(A) OR (B)` retombe à 0 après `(A)`)
                if depth == 0 and i < len(kw) - 1:
                    envelops_all = False
                    break
        if envelops_all and depth == 0:
            kw = kw[1:-1].strip()
        else:
            break
    return kw
