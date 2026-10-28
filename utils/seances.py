# -*- coding: utf-8 -*-
"""Séances courtes et pauses entre séances, pour cette personne.

Toute action LinkedIn (recherche, récolte, invitations, vérification,
messages) se fait dans une séance. Une séance s'ouvre à la première action
permise ; une action commencée moins de `SEANCE_FENETRE_MIN` minutes après
cette ouverture, tant qu'il reste des pages, en fait partie (chercher puis
inviter = une seule séance). Elle est close quand sa fenêtre est passée ou
que ses pages atteignent `MAX_PAGES_PER_SEANCE`. La séance suivante attend
`PAUSE_ENTRE_SEANCES_MIN` minutes après la fin de la dernière action, et il
n'y en a pas plus de `MAX_SEANCES_PER_DAY` par jour.

L'état vit dans `<config_dir>/seances.json` (un par personne, comme
`daily_limits.json`), en heure locale du Mac. Absent ou illisible : aucun
historique. Seule `fin_action` l'écrit, et seulement si l'action a lu au
moins une page : un refus, une session occupée ou une action qui n'a rien
ouvert ne changent rien.
"""

import json
import os
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from config import ScraperConfig

NOM_FICHIER = "seances.json"

REFUS_SEANCES = ("Vous avez fait {n} séances aujourd'hui. "
                 "Vous pourrez reprendre demain.")
REFUS_PAUSE = "Pause entre deux séances : prochaine action possible à {heure}."
REFUS_VERIFICATION = ("Vérification déjà faite aujourd'hui. "
                      "Vous pourrez la refaire demain.")


def _chemin(config_dir: str) -> str:
    return os.path.join(str(config_dir), NOM_FICHIER)


def _lire(config_dir: str) -> dict:
    """État lu et vérifié ; vide si absent ou illisible."""
    vide = {"seances": [], "verifications": []}
    try:
        with open(_chemin(config_dir), "r", encoding="utf-8") as f:
            brut = json.load(f)
        seances = [{"debut": datetime.fromisoformat(s["debut"]),
                    "fin": datetime.fromisoformat(s["fin"]),
                    "pages": int(s["pages"])}
                   for s in brut.get("seances", [])]
        verifications = [datetime.fromisoformat(v) for v in brut.get("verifications", [])]
    except Exception:
        return vide
    return {"seances": seances, "verifications": verifications}


def _ecrire(config_dir: str, etat: dict, maintenant: datetime) -> None:
    """Écrit l'état, en ne gardant que le jour en cours et la dernière séance
    (sa fin compte pour la pause, même passé minuit)."""
    seances = etat["seances"]
    gardees = [s for s in seances[:-1] if s["debut"].date() == maintenant.date()]
    gardees += seances[-1:]
    brut = {
        "seances": [{"debut": s["debut"].isoformat(), "fin": s["fin"].isoformat(),
                     "pages": s["pages"]} for s in gardees],
        "verifications": [v.isoformat() for v in etat["verifications"]
                          if v.date() == maintenant.date()],
    }
    os.makedirs(str(config_dir), exist_ok=True)
    temporaire = _chemin(config_dir) + ".tmp"
    with open(temporaire, "w", encoding="utf-8") as f:
        json.dump(brut, f)
    os.replace(temporaire, _chemin(config_dir))


def _ouverte(seance: Optional[dict], moment: datetime) -> bool:
    """La séance accueille-t-elle une action commencée à `moment` ?"""
    return (seance is not None
            and moment - seance["debut"] < timedelta(minutes=ScraperConfig.SEANCE_FENETRE_MIN)
            and seance["pages"] < ScraperConfig.MAX_PAGES_PER_SEANCE)


def _heure_minute_superieure(moment: datetime) -> str:
    """HH:MM d'un moment, arrondi à la minute suivante s'il en passe : à
    l'heure affichée, l'action est bien possible."""
    if moment.second or moment.microsecond:
        moment = moment.replace(second=0, microsecond=0) + timedelta(minutes=1)
    return moment.strftime("%H:%M")


def debut_action(config_dir: str, maintenant: datetime) -> Tuple[Optional[str], int]:
    """(refus, pages restantes dans la séance) pour une action qui commence.

    Ne change rien à l'état : c'est `fin_action` qui ouvre ou complète la
    séance. Refus : 4 séances déjà ouvertes aujourd'hui, ou pause pas encore
    écoulée ; le texte dit pourquoi et quand.
    """
    plafond = ScraperConfig.MAX_PAGES_PER_SEANCE
    if config_dir is None:
        return None, plafond
    seances = _lire(config_dir)["seances"]
    derniere = seances[-1] if seances else None
    if _ouverte(derniere, maintenant):
        return None, plafond - derniere["pages"]

    du_jour = [s for s in seances if s["debut"].date() == maintenant.date()]
    if len(du_jour) >= ScraperConfig.MAX_SEANCES_PER_DAY:
        return REFUS_SEANCES.format(n=len(du_jour)), 0
    if derniere is not None:
        reprise = derniere["fin"] + timedelta(minutes=ScraperConfig.PAUSE_ENTRE_SEANCES_MIN)
        if maintenant < reprise:
            return REFUS_PAUSE.format(heure=_heure_minute_superieure(reprise)), 0
    return None, plafond


def fin_action(config_dir: str, maintenant: datetime, pages: int,
               debut: Optional[datetime] = None) -> None:
    """Ajoute les `pages` de l'action finie à sa séance et note l'heure de fin.

    `debut` : moment où l'action a commencé (par défaut `maintenant`). Une
    action commencée dans une séance ouverte en fait partie, même si elle
    finit après la fenêtre ; sinon elle ouvre une séance à `debut`. Sans
    aucune page lue, rien ne change.
    """
    if config_dir is None or pages <= 0:
        return
    debut = debut or maintenant
    etat = _lire(config_dir)
    seances = etat["seances"]
    if seances and _ouverte(seances[-1], debut):
        seances[-1]["pages"] += pages
        seances[-1]["fin"] = maintenant
    else:
        seances.append({"debut": debut, "fin": maintenant, "pages": pages})
    _ecrire(config_dir, etat, maintenant)


def verification_permise(config_dir: str, maintenant: datetime) -> Optional[str]:
    """None si une vérification des acceptations est encore permise
    aujourd'hui, sinon le refus."""
    if config_dir is None:
        return None
    faites = [v for v in _lire(config_dir)["verifications"] if v.date() == maintenant.date()]
    if len(faites) >= ScraperConfig.MAX_VERIFICATIONS_PAR_JOUR:
        return REFUS_VERIFICATION
    return None


def noter_verification(config_dir: str, maintenant: datetime) -> None:
    """Note une vérification des acceptations faite à `maintenant`."""
    if config_dir is None:
        return
    etat = _lire(config_dir)
    etat["verifications"].append(maintenant)
    _ecrire(config_dir, etat, maintenant)


def message_refus(erreurs: Optional[List]) -> Optional[str]:
    """Le refus de séance (pause, séances du jour, vérification) parmi
    `erreurs`, ou None.

    Le wrapper synchrone range le refus parmi ses erreurs et rend un
    résultat vide : l'appelant doit le dire en clair plutôt qu'afficher
    « 0 résultat » ou « aucune acceptation ».
    """
    def _est_refus(texte: str) -> bool:
        return any(texte.startswith(avant) and texte.endswith(apres)
                   for avant, _, apres in (REFUS_SEANCES.partition("{n}"),
                                           REFUS_PAUSE.partition("{heure}"),
                                           REFUS_VERIFICATION.partition("\0")))
    return next((str(e) for e in erreurs or () if _est_refus(str(e))), None)
