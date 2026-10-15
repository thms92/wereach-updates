# -*- coding: utf-8 -*-
"""Une seule session LinkedIn de We.Reach à la fois, par utilisateur.

La veille du matin et une recherche lancée à la main ouvriraient deux
fenêtres Chrome sur le même compte : c'est le comportement qui fait repérer
un compte. Le verrou est un petit fichier dans le dossier de config de la
personne ; il porte le pid et l'heure, pour qu'un verrou laissé par un
processus mort, ou vieux de plus de trois heures, ne bloque personne.
"""

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path

_NOM = "session_linkedin.lock"
_DUREE_MAX = 3 * 3600
# Un verrou vide plus jeune que ça est en train d'être écrit, pas abandonné.
_DELAI_ECRITURE = 10

MESSAGE_OCCUPE = ("Une autre session LinkedIn de We.Reach est en cours ({activite}) "
                  "— attendez qu'elle se termine.")


class VerrouOccupe(Exception):
    def __init__(self, activite: str):
        super().__init__(MESSAGE_OCCUPE.format(activite=activite))
        self.activite = activite


def message_occupe(erreurs):
    """Le message « session occupée » parmi `erreurs`, ou None.

    Les enveloppes synchrones du scraper rangent le refus parmi leurs
    erreurs et rendent une liste vide : l'appelant doit le dire en clair
    plutôt qu'afficher « 0 envoyé » ou « aucune acceptation ».
    """
    debut = MESSAGE_OCCUPE.split("{activite}")[0]
    return next((str(e) for e in erreurs or () if str(e).startswith(debut)), None)


def _vivant(pid) -> bool:
    try:
        pid = int(pid)
    except (ValueError, TypeError):
        return False
    # os.kill(0, …) vise le groupe de processus, os.kill(-1, …) tous les
    # processus : l'appel « réussirait » sans rien dire du propriétaire.
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except PermissionError:
        # Le processus existe, il appartient seulement à un autre compte.
        return True
    except (OSError, OverflowError):
        return False
    return True


def _occupant(chemin: Path):
    """Le propriétaire vivant du verrou, ou None si le verrou est à reprendre."""
    try:
        brut = chemin.read_text(encoding="utf-8")
        if not brut and time.time() - chemin.stat().st_mtime < _DELAI_ECRITURE:
            # Créé à l'instant, pas encore écrit par son propriétaire.
            return {"activite": "inconnue"}
        info = json.loads(brut)
    except Exception:
        return None
    if time.time() - float(info.get("debut", 0)) > _DUREE_MAX or not _vivant(info.get("pid")):
        return None
    return info


def _creer(chemin: Path, moi: dict) -> bool:
    """Crée le verrou d'un seul geste ; False s'il existe déjà.

    O_EXCL : entre « personne ne le tient » et « je le prends », un autre
    processus (la veille lancée par le réveil) ne peut pas se glisser.
    """
    try:
        fd = os.open(str(chemin), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(json.dumps(moi))
    return True


@contextmanager
def session_linkedin(config_dir, activite: str):
    """Prend le verrou pour la durée du bloc ; lève `VerrouOccupe` sinon."""
    if config_dir is None:
        yield
        return
    chemin = Path(config_dir) / _NOM
    chemin.parent.mkdir(parents=True, exist_ok=True)
    moi = {"pid": os.getpid(), "activite": activite, "debut": time.time()}
    if not _creer(chemin, moi):
        occupant = _occupant(chemin)
        if occupant:
            raise VerrouOccupe(occupant.get("activite") or "inconnue")
        # Verrou mort ou illisible : on l'efface et on retente une seule fois.
        # Si un autre l'a repris entre-temps, c'est lui qui l'a.
        try:
            chemin.unlink()
        except FileNotFoundError:
            pass
        if not _creer(chemin, moi):
            occupant = _occupant(chemin) or {}
            raise VerrouOccupe(occupant.get("activite") or "inconnue")
    try:
        yield
    finally:
        try:
            if json.loads(chemin.read_text(encoding="utf-8")).get("debut") == moi["debut"]:
                chemin.unlink()
        except Exception:
            pass
