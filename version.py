# -*- coding: utf-8 -*-
"""Version de We.Reach — lue depuis le fichier VERSION (source unique)."""
import os


def get_version() -> str:
    """Retourne la version courante (contenu du fichier VERSION), ou '?'."""
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION")
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip() or "?"
    except Exception:
        return "?"


__version__ = get_version()
