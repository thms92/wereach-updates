# -*- coding: utf-8 -*-
"""Dernière vérification des acceptations, pour cette personne.

Le moment est gardé dans `<config_dir>/derniere_verification.json`
(un par personne, comme `daily_limits.json`), en ISO 8601 avec fuseau.
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional

NOM_FICHIER = "derniere_verification.json"


def _chemin(config_dir: str) -> str:
    return os.path.join(str(config_dir), NOM_FICHIER)


def enregistrer_verification(config_dir: str,
                             moment: Optional[datetime] = None) -> None:
    """Note que les acceptations viennent d'être vérifiées (maintenant, en UTC,
    sauf `moment` donné)."""
    if moment is None:
        moment = datetime.now(timezone.utc)
    os.makedirs(str(config_dir), exist_ok=True)
    with open(_chemin(config_dir), "w", encoding="utf-8") as f:
        json.dump({"moment": moment.isoformat()}, f)


def derniere_verification(config_dir: str) -> Optional[datetime]:
    """Moment de la dernière vérification, ou None si absent ou illisible."""
    try:
        with open(_chemin(config_dir), "r", encoding="utf-8") as f:
            return datetime.fromisoformat(json.load(f)["moment"])
    except Exception:
        return None
