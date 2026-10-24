# -*- coding: utf-8 -*-
"""Calcul des chiffres du tableau de bord (pur : ni Streamlit ni base).

Les lignes viennent de `DatabaseManager.lignes_suivi()` : une par profil
invité. Une période regroupe les invitations *envoyées* dans la période
(jour local de la première invitation) ; acceptées, messages, en attente et
taux portent sur ces mêmes profils.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from utils.ecoles import ecoles_du_libelle

SEUIL_TAUX = 5       # en dessous, un taux ne veut rien dire
LIMITE_POSTES = 15   # postes affichés avant la ligne « Autres »
AUTRES = "Autres"

_VIDE_ECOLE = "Non renseignée"
_VIDE_ENTREPRISE = "Non renseignée"
_VIDE_POSTE = "Non renseigné"
_VIDES = {"ecole": _VIDE_ECOLE, "entreprise": _VIDE_ENTREPRISE, "poste": _VIDE_POSTE}

# Mêmes formats que `date_locale` de la page du tableau de bord.
_FORMATS_DATE = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S",
                 "%Y-%m-%d %H:%M")


@dataclass(frozen=True)
class Periode:
    """Jours locaux, bornes incluses."""
    debut: date
    fin: date


@dataclass(frozen=True)
class ChiffresCles:
    invitations: int
    acceptees: int
    messages: int
    en_attente: int
    jamais_verifiees: int


@dataclass(frozen=True)
class LigneTableau:
    libelle: str
    invites: int
    acceptes: int


def periode_glissante(jours: int, aujourd_hui: date) -> Periode:
    """Aujourd'hui et les `jours - 1` jours d'avant."""
    return Periode(aujourd_hui - timedelta(days=jours - 1), aujourd_hui)


def jour_local(brut) -> Optional[date]:
    """Horodatage SQLite (UTC) → jour local ; `None` si illisible."""
    texte = str(brut or "").strip()
    for motif in _FORMATS_DATE:
        try:
            moment = datetime.strptime(texte, motif)
        except ValueError:
            continue
        return moment.replace(tzinfo=timezone.utc).astimezone().date()
    return None


def _cle(valeur: str) -> str:
    """Clé de regroupement : sans casse ni espaces en trop."""
    return " ".join((valeur or "").split()).casefold()


def _valeurs(ligne: Dict, cle: str) -> List[str]:
    """Valeurs d'une ligne pour un filtre ; une école composite en donne plusieurs."""
    brut = ligne.get(cle) or ""
    if cle == "ecole":
        valeurs = ecoles_du_libelle(brut)
    else:
        valeurs = [" ".join(brut.split())] if brut.strip() else []
    return valeurs or [_VIDES[cle]]


def filtrer(lignes: Iterable[Dict], periode: Periode, ecoles: Sequence[str] = (),
            entreprises: Sequence[str] = (), postes: Sequence[str] = ()) -> List[Dict]:
    """Lignes envoyées dans la période et retenues par les filtres (vides = tout).

    Une ligne à la date illisible n'appartient à aucune période.
    """
    voulus = {"ecole": {_cle(v) for v in ecoles},
              "entreprise": {_cle(v) for v in entreprises},
              "poste": {_cle(v) for v in postes}}
    retenues = []
    for ligne in lignes:
        jour = jour_local(ligne.get("date_envoi"))
        if jour is None or not periode.debut <= jour <= periode.fin:
            continue
        if all(not attendus or attendus & {_cle(v) for v in _valeurs(ligne, cle)}
               for cle, attendus in voulus.items()):
            retenues.append(ligne)
    return retenues


def chiffres_cles(lignes: Sequence[Dict]) -> ChiffresCles:
    """`jamais_verifiees` : en attente et jamais passées par la vérification."""
    acceptees = sum(1 for l in lignes if l["acceptee"])
    attente = [l for l in lignes if not l["acceptee"]]
    return ChiffresCles(
        invitations=len(lignes),
        acceptees=acceptees,
        messages=sum(1 for l in lignes if l["acceptee"] and l["messagee"]),
        en_attente=len(attente),
        jamais_verifiees=sum(1 for l in attente if not l["verifiee"]),
    )


def texte_taux(acceptes: int, invites: int) -> str:
    """« 33 % » (espace fine insécable) ; « trop peu (n) » sous le seuil."""
    if invites < SEUIL_TAUX:
        return f"trop peu ({invites})"
    return f"{round(acceptes * 100 / invites)} %"


def _lundi(jour: date) -> date:
    return jour - timedelta(days=jour.weekday())


def par_semaine(lignes: Iterable[Dict], periode: Periode) -> List[Tuple[date, int, int]]:
    """(lundi, invitations, acceptées) pour chaque semaine touchée par la période."""
    semaines: Dict[date, List[int]] = {}
    lundi = _lundi(periode.debut)
    while lundi <= periode.fin:
        semaines[lundi] = [0, 0]
        lundi += timedelta(days=7)
    for ligne in lignes:
        jour = jour_local(ligne.get("date_envoi"))
        if jour is None or not periode.debut <= jour <= periode.fin:
            continue
        compte = semaines[_lundi(jour)]
        compte[0] += 1
        compte[1] += 1 if ligne["acceptee"] else 0
    return [(lundi, inv, acc) for lundi, (inv, acc) in semaines.items()]


def par_categorie(lignes: Iterable[Dict], cle: str) -> List[LigneTableau]:
    """Invitations et acceptations par école, entreprise ou poste.

    Triées par invitations décroissantes puis libellé. Les postes au-delà des
    `LIMITE_POSTES` premiers sont additionnés dans une ligne « Autres ».
    """
    groupes: Dict[str, List] = {}  # clé → [libellé affiché, invités, acceptés]
    for ligne in lignes:
        for valeur in _sans_doublon(_valeurs(ligne, cle)):
            groupe = groupes.setdefault(_cle(valeur), [valeur, 0, 0])
            groupe[1] += 1
            groupe[2] += 1 if ligne["acceptee"] else 0
    tableau = sorted((LigneTableau(*g) for g in groupes.values()),
                     key=lambda l: (-l.invites, l.libelle.casefold()))
    if cle == "poste" and len(tableau) > LIMITE_POSTES:
        reste = tableau[LIMITE_POSTES:]
        tableau = tableau[:LIMITE_POSTES] + [
            LigneTableau(AUTRES, sum(l.invites for l in reste),
                         sum(l.acceptes for l in reste))]
    return tableau


def _sans_doublon(valeurs: List[str]) -> List[str]:
    """Valeurs sans doublon (à la casse près), ordre conservé : un profil compte
    une fois par école même si le libellé la répète."""
    vues, resultat = set(), []
    for v in valeurs:
        if _cle(v) not in vues:
            vues.add(_cle(v))
            resultat.append(v)
    return resultat


def options_filtres(lignes: Iterable[Dict]) -> Dict[str, List[str]]:
    """Valeurs proposées par filtre, triées ; les vides sous leur libellé."""
    lignes = list(lignes)
    options = {}
    for cle in ("ecole", "entreprise", "poste"):
        uniques: Dict[str, str] = {}
        for ligne in lignes:
            for valeur in _valeurs(ligne, cle):
                uniques.setdefault(_cle(valeur), valeur)
        options[cle] = sorted(uniques.values(), key=str.casefold)
    return options
