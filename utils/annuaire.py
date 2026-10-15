# -*- coding: utf-8 -*-
"""Annuaire officiel des entreprises (API Recherche d'entreprises, data.gouv).

Gratuit, sans clé, public. Il donne ce que LinkedIn ne donne pas — dirigeants,
SIREN, activité, tranche d'effectif INSEE — mais il ne sait pas *quelle*
entreprise on veut : « thiga » renvoie 14 sociétés. Il n'est donc jamais
interrogé seul ; `choisir_candidat` ne retient un résultat que s'il recoupe
la page LinkedIn (même nom, même commune de siège), et refuse de deviner
sinon.
"""

import json
import re
import unicodedata
import urllib.parse
import urllib.request

URL = "https://recherche-entreprises.api.gouv.fr/search"

# Codes INSEE de tranche d'effectif salarié.
TRANCHES_EFFECTIF = {
    "00": "0 salarié", "01": "1 à 2 salariés", "02": "3 à 5 salariés",
    "03": "6 à 9 salariés", "11": "10 à 19 salariés", "12": "20 à 49 salariés",
    "21": "50 à 99 salariés", "22": "100 à 199 salariés", "31": "200 à 249 salariés",
    "32": "250 à 499 salariés", "41": "500 à 999 salariés", "42": "1 000 à 1 999 salariés",
    "51": "2 000 à 4 999 salariés", "52": "5 000 à 9 999 salariés", "53": "10 000 salariés et plus",
}

_FORMES = {"SAS", "SASU", "SA", "SARL", "EURL", "SNC", "SCI", "SE", "SCA", "GIE"}


class AnnuaireIndisponible(Exception):
    """L'annuaire n'a pas répondu de façon exploitable."""


def _transport_http(url: str, delai: float) -> bytes:
    requete = urllib.request.Request(url, headers={"User-Agent": "We.Reach"})
    with urllib.request.urlopen(requete, timeout=delai) as reponse:
        return reponse.read()


def interroger(nom: str, transport=None, delai: float = 8.0) -> list:
    """Sociétés dont le nom ressemble à `nom` (25 au plus)."""
    url = URL + "?" + urllib.parse.urlencode({"q": nom, "per_page": 25})
    try:
        brut = (transport or _transport_http)(url, delai)
        return list(json.loads(brut).get("results") or [])
    except Exception as e:
        raise AnnuaireIndisponible(str(e)) from e


def _sans_accents(texte: str) -> str:
    decompose = unicodedata.normalize("NFKD", texte or "")
    return "".join(c for c in decompose if not unicodedata.combining(c))


def normaliser_nom(nom: str) -> str:
    """Majuscules, sans accents, sans forme juridique ni points."""
    mots = _sans_accents(nom).upper().replace(".", "").split()
    return " ".join(m for m in mots if m not in _FORMES).strip()


def _normaliser_commune(commune: str) -> str:
    c = _sans_accents(commune).upper().strip()
    # « LYON 3EME », « PARIS 9 », « MARSEILLE 1ER » : l'arrondissement ne
    # change pas la ville ; LinkedIn ne le donne jamais.
    return re.sub(r"\s+\d+\s*(E|ER|EME)?$", "", c).strip()


def commune_du_siege_linkedin(siege: str) -> str:
    """« Paris, Paris » → « PARIS » : LinkedIn écrit « ville, région »."""
    return _normaliser_commune((siege or "").split(",")[0])


def choisir_candidat(resultats, nom_linkedin: str, siege_linkedin: str):
    """(société retenue, "") ou (None, motif). Jamais de devinette."""
    commune = commune_du_siege_linkedin(siege_linkedin)
    if not commune:
        return None, "siège LinkedIn inconnu : impossible de recouper"
    cible = normaliser_nom(nom_linkedin)
    compatibles = []
    for r in resultats or []:
        if r.get("etat_administratif") != "A":
            continue
        noms = {normaliser_nom(r.get(k) or "") for k in ("nom_raison_sociale", "nom_complet", "sigle")}
        siege = r.get("siege") or {}
        if cible in noms and _normaliser_commune(siege.get("libelle_commune") or "") == commune:
            compatibles.append(r)
    if len(compatibles) == 1:
        return compatibles[0], ""
    if not compatibles:
        return None, f"aucune société « {nom_linkedin} » active avec un siège à {commune.title()}"
    return None, f"plusieurs sociétés « {nom_linkedin} » à {commune.title()} : impossible de choisir"


def _dirigeants(candidat) -> str:
    noms = []
    for d in candidat.get("dirigeants") or []:
        qualite = d.get("qualite") or ""
        # Le commissaire aux comptes contrôle, il ne dirige pas.
        if "commissaire aux comptes" in qualite.lower():
            continue
        if d.get("type_dirigeant") == "personne physique":
            nom = " ".join(x for x in ((d.get("prenoms") or "").split(" ")[0], d.get("nom") or "") if x)
        else:
            nom = d.get("denomination") or ""
        if nom:
            noms.append(f"{nom} ({qualite})" if qualite else nom)
    return " ; ".join(noms)


def fiche_depuis_annuaire(candidat: dict) -> dict:
    tranche = candidat.get("tranche_effectif_salarie")
    annee = candidat.get("annee_tranche_effectif_salarie")
    effectif = TRANCHES_EFFECTIF.get(tranche)
    effectif = f"{effectif} ({annee})" if effectif and annee else (effectif or "non employeuse ou non renseignée")
    return {
        "siren": candidat.get("siren") or "",
        "activite": candidat.get("activite_principale") or "",
        "effectif": effectif,
        "creation": candidat.get("date_creation") or "",
        "categorie": candidat.get("categorie_entreprise") or "",
        "commune": (candidat.get("siege") or {}).get("libelle_commune") or "",
        "dirigeants": _dirigeants(candidat),
    }
