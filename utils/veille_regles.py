# -*- coding: utf-8 -*-
"""Règles de la veille entreprises : quoi chercher, comment ranger, quoi lire.

Module pur (hors lecture/écriture du petit fichier de réglages) : aucune
dépendance à Playwright, Streamlit ni SQLite. Toute décision de la veille
qui peut se tester sans navigateur vit ici.
"""

import json
import unicodedata
import urllib.parse
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Intitulés cherchés par famille. Ils servent deux fois : dans la recherche
# LinkedIn (mots-clés en OU) et pour ranger chaque contact trouvé.
FAMILLES = {
    "Product": ("product manager", "product owner", "head of product",
                "vp product", "chief product officer", "product director",
                "directeur produit", "responsable produit"),
    "Data": ("data scientist", "data engineer", "data analyst",
             "head of data", "chief data officer", "data manager",
             "responsable data"),
    "IA": ("machine learning", "ml engineer", "ai engineer", "head of ai",
           "intelligence artificielle", "responsable ia", "mlops",
           "ia générative", "generative ai"),
}

PAGES_PAR_JOUR_DEFAUT = 20
PAGES_MIN = 5
PAGES_MAX = 40
# Au-delà, une seule grande entreprise mangerait le budget du matin.
PAGES_MAX_PAR_ENTREPRISE = 2
# Une fiche ne change pas chaque matin ; chaque relecture coûte une page.
RELECTURE_FICHE_JOURS = 30

_FICHIER_REGLAGES = "reglages_veille.json"

# Libellés des <dt> de la page « À propos », apostrophes normalisées.
_CHAMPS_APROPOS = {
    "site web": "site",
    "telephone": "telephone",
    "secteur": "secteur",
    "taille de l'entreprise": "taille",
    "siege social": "siege",
    "fondee en": "fondee",
    "specialisations": "specialisations",
}


def _sans_accents(texte: str) -> str:
    decompose = unicodedata.normalize("NFKD", texte or "")
    return "".join(c for c in decompose if not unicodedata.combining(c))


def _cle(libelle: str) -> str:
    return _sans_accents(libelle).replace("’", "'").strip().lower()


def _termes(familles, intitules_libres):
    vus, termes = set(), []
    for terme in [t for f in familles for t in FAMILLES.get(f, ())] + list(intitules_libres or []):
        cle = terme.strip().lower()
        if cle and cle not in vus:
            vus.add(cle)
            termes.append(terme.strip())
    return termes


def expression_mots_cles(familles, intitules_libres) -> str:
    """`"a" OR "b" OR …` — sans parenthèses englobantes.

    LinkedIn renvoie zéro résultat pour une requête entièrement entre
    parenthèses : constaté, et corrigé ailleurs par `_normalize_keyword`.
    """
    termes = _termes(familles, intitules_libres)
    if not termes:
        raise ValueError("aucun intitulé à chercher : cochez au moins une famille")
    return " OR ".join('"{}"'.format(t.replace('"', "")) for t in termes)


def url_recherche_personnes(company_id, expression: str, page: int) -> str:
    """Recherche de personnes chez une entreprise, page `page`.

    Refuse un identifiant absent ou non numérique : sans le filtre
    `currentCompany`, la recherche porterait sur tout LinkedIn et la veille
    rangerait des inconnus dans la fiche de l'entreprise.
    """
    if not company_id or not str(company_id).isdigit():
        raise ValueError(f"identifiant d'entreprise invalide : {company_id!r}")
    facette = urllib.parse.quote(f'["{company_id}"]', safe="")
    mots = urllib.parse.quote(expression, safe="")
    return ("https://www.linkedin.com/search/results/people/?"
            f"currentCompany={facette}&keywords={mots}"
            f"&origin=FACETED_SEARCH&page={int(page)}")


def famille_de_l_intitule(intitule: str, familles, intitules_libres) -> str:
    """La famille cochée dont un terme apparaît dans l'intitulé, sinon « Autre ».

    Les intitulés libres forment chacun leur propre catégorie : c'est ce que
    la personne a demandé explicitement, on ne le noie pas dans une famille.
    """
    bas = _sans_accents(intitule or "").lower()
    for libre in intitules_libres or []:
        if _sans_accents(libre).lower().strip() and _sans_accents(libre).lower().strip() in bas:
            return libre.strip()
    for famille in familles:
        for terme in FAMILLES.get(famille, ()):
            if _sans_accents(terme).lower() in bas:
                return famille
    return "Autre"


def signature_familles(familles, intitules_libres) -> str:
    """Empreinte des critères : si elle change, le curseur repart de zéro."""
    return "|".join(sorted(f.lower() for f in familles)) + "#" + \
        "|".join(sorted(t.strip().lower() for t in intitules_libres or []))


def fiche_depuis_apropos(champs: dict) -> dict:
    """Champs de la page « À propos » → fiche à plat.

    Prend la première valeur de chaque rubrique ; la taille est accompagnée
    d'une seconde ligne « N membres associés », gardée à part.
    """
    fiche = {}
    for libelle, valeurs in (champs or {}).items():
        cle = _CHAMPS_APROPOS.get(_cle(libelle))
        if not cle or not valeurs:
            continue
        fiche[cle] = valeurs[0].strip()
        if cle == "taille":
            for v in valeurs[1:]:
                chiffres = "".join(c for c in v.split("membres")[0] if c.isdigit())
                if "membres" in v and chiffres:
                    fiche["membres"] = chiffres
    return fiche


@dataclass
class ReglagesVeille:
    familles: list = field(default_factory=lambda: ["Product", "Data", "IA"])
    intitules_libres: list = field(default_factory=list)
    pages_par_jour: int = PAGES_PAR_JOUR_DEFAUT


def charger_reglages(config_dir) -> ReglagesVeille:
    """Réglages de la personne, ou les défauts si absents ou illisibles."""
    try:
        brut = json.loads((Path(config_dir) / _FICHIER_REGLAGES).read_text(encoding="utf-8"))
        r = ReglagesVeille(
            familles=[f for f in brut.get("familles", []) if f in FAMILLES],
            intitules_libres=[str(t) for t in brut.get("intitules_libres", []) if str(t).strip()],
            pages_par_jour=int(brut.get("pages_par_jour", PAGES_PAR_JOUR_DEFAUT)),
        )
    except Exception:
        return ReglagesVeille()
    r.pages_par_jour = max(PAGES_MIN, min(PAGES_MAX, r.pages_par_jour))
    return r


def sauver_reglages(config_dir, reglages: ReglagesVeille) -> None:
    dossier = Path(config_dir)
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / _FICHIER_REGLAGES).write_text(
        json.dumps(asdict(reglages), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def resume_fiche(fiche: dict, contacts: list, actualites: list, depuis) -> str:
    """La fiche en une ligne : ce qu'on lit avant de décider d'ouvrir le reste.

    Actualité : la plus récente seulement — c'est un signal, pas une revue de
    presse. Contacts : les familles « Autre » ne comptent pas, ce ne sont pas
    les postes visés.
    """
    morceaux = [fiche[c]["valeur"] for c in ("linkedin.taille", "linkedin.secteur") if c in fiche]
    if "linkedin.siege" in fiche:
        morceaux.append(fiche["linkedin.siege"]["valeur"].split(",")[0].strip())
    if "annuaire.effectif" in fiche:
        morceaux.append(fiche["annuaire.effectif"]["valeur"])
    if not morceaux:
        morceaux.append("Fiche pas encore remplie")
    if actualites:
        a = max(actualites, key=lambda x: x.get("publie_le") or "")
        j = (a.get("publie_le") or "")[:10]
        date_fr = f"{j[8:10]}/{j[5:7]}/{j[:4]}" if len(j) == 10 else j
        morceaux.append(f"📰 {a['categorie']} : {a['titre']} ({date_fr})")
    else:
        morceaux.append("aucune actualité")
    vises = [c for c in contacts if c.get("famille") != "Autre"]
    if vises:
        nouveaux = sum(1 for c in vises if depuis and (c.get("decouvert_le") or "") > depuis)
        texte = f"{len(vises)} contact{'s' if len(vises) > 1 else ''} Product/Data/IA"
        if nouveaux:
            texte += f", dont {nouveaux} nouveau{'x' if nouveaux > 1 else ''}"
        morceaux.append(texte)
    else:
        morceaux.append("aucun contact Product/Data/IA")
    return " · ".join(morceaux)


def ordre_du_lot(entreprises: list) -> list:
    """Les entreprises à passer, les plus en retard d'abord.

    Une entreprise « non identifiée » n'est reprise que si on lui a collé un
    lien : la rechercher encore par son nom referait la même erreur.
    """
    candidates = [
        e for e in entreprises
        if e.get("etat") != "non_identifiee" or e.get("url_linkedin")
    ]
    return sorted(candidates, key=lambda e: (e.get("derniere_veille") is not None,
                                             e.get("derniere_veille") or ""))
