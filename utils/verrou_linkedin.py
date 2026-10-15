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

MESSAGE_OCCUPE = ("Une autre session LinkedIn de We.Reach est en cours ({activite}) "
                  "— attendez qu'elle se termine.")


class VerrouOccupe(Exception):
    def __init__(self, activite: str):
        super().__init__(MESSAGE_OCCUPE.format(activite=activite))
        self.activite = activite


def _vivant(pid) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, TypeError):
        return False


def _occupant(chemin: Path):
    try:
        info = json.loads(chemin.read_text(encoding="utf-8"))
    except Exception:
        return None
    if time.time() - float(info.get("debut", 0)) > _DUREE_MAX or not _vivant(info.get("pid")):
        return None
    return info


@contextmanager
def session_linkedin(config_dir, activite: str):
    """Prend le verrou pour la durée du bloc ; lève `VerrouOccupe` sinon."""
    if config_dir is None:
        yield
        return
    chemin = Path(config_dir) / _NOM
    occupant = _occupant(chemin)
    if occupant:
        raise VerrouOccupe(occupant.get("activite") or "inconnue")
    chemin.parent.mkdir(parents=True, exist_ok=True)
    moi = {"pid": os.getpid(), "activite": activite, "debut": time.time()}
    chemin.write_text(json.dumps(moi), encoding="utf-8")
    try:
        yield
    finally:
        try:
            if json.loads(chemin.read_text(encoding="utf-8")).get("debut") == moi["debut"]:
                chemin.unlink()
        except Exception:
            pass
