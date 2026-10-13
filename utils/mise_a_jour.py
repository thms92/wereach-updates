# -*- coding: utf-8 -*-
"""Proposer la mise à jour depuis l'application elle-même.

Jusqu'ici, la mise à jour ne se faisait qu'au démarrage du lanceur : qui ne
ferme jamais l'outil ne la recevait jamais. Une collègue est ainsi restée en
1.2.2 pendant que l'équipe passait en 1.4.5, sans que rien ne le lui signale.

L'application interroge donc le dépôt, et propose un bouton qui relance le
lanceur. Celui-ci ferme l'instance en cours (garde-fou de la 1.4.1), installe
la mise à jour et redémarre : un clic, rien d'autre à faire.
"""

import subprocess
import sys
import urllib.request
from pathlib import Path

from utils.nouveautes import cle_version

RACINE = Path(__file__).resolve().parent.parent
URL_VERSION = (
    "https://raw.githubusercontent.com/thms92/wereach-updates/main/VERSION"
)
NOM_LANCEUR = "1 - Lancer We.Reach.command"


def version_publiee(delai: float = 4.0) -> str:
    """Version servie par le dépôt, ou None si on n'a pas pu la lire.

    Silencieux à dessein : hors ligne, derrière un pare-feu d'entreprise ou
    dépôt injoignable, l'application doit fonctionner comme si de rien
    n'était.
    """
    try:
        with urllib.request.urlopen(URL_VERSION, timeout=delai) as reponse:
            return reponse.read().decode("utf-8").strip() or None
    except Exception:
        return None


def mise_a_jour_disponible(locale: str, distante: str) -> bool:
    """La version du dépôt est-elle réellement plus récente ?

    Strictement plus récente : pendant la minute ou deux où le cache de GitHub
    sert encore l'ancienne, il ne faut pas proposer une « mise à jour » qui
    ferait reculer. Et la comparaison se fait sur des nombres, sinon 1.10.0
    passerait pour plus ancienne que 1.9.0.
    """
    a, b = cle_version(locale or ""), cle_version(distante or "")
    return bool(a and b and b > a)


def chemin_lanceur() -> Path:
    """Le lanceur, voisin du dossier `app`, ou None s'il n'y en a pas.

    Absent en développement : l'application doit alors le dire plutôt que de
    prétendre savoir se relancer.
    """
    candidat = RACINE.parent / NOM_LANCEUR
    return candidat if candidat.exists() else None


def relancer() -> bool:
    """Relance l'outil par son lanceur, qui se chargera de la mise à jour.

    Lancé par `open`, donc détaché : il survit à la fermeture de l'instance
    en cours, que lui-même va provoquer.
    """
    lanceur = chemin_lanceur()
    if lanceur is None or sys.platform != "darwin":
        return False
    try:
        subprocess.Popen(["open", str(lanceur)])
        return True
    except Exception:
        return False
