# -*- coding: utf-8 -*-
"""Reconnaître une page d'alerte LinkedIn après une navigation.

Le 26/10, LinkedIn a affiché une page d'avertissement
(/checkpoint/challenge/…, « Nous avons remarqué une activité inhabituelle
sur votre compte »). Fonction pure, sans Playwright : l'appelant lui donne
l'URL, le texte visible et le statut HTTP de la page.
"""

from typing import Optional
from urllib.parse import urlparse

CHEMINS_ALERTE = ("/checkpoint/", "/challenge/")
CHEMINS_SESSION = ("/authwall", "/uas/login", "/login")
CHEMINS_TRAVAIL = ("/in/", "/search/", "/feed/", "/mynetwork/", "/company/", "/school/")

# Comparés en minuscules : « restreint » seul n'en fait pas partie, il
# apparaît sur de simples profils.
TEXTES_ALERTE = (
    "activité inhabituelle",
    "unusual activity",
    "vérifions qu'il s'agit bien de vous",
    "let's do a quick security check",
    "votre compte a été restreint",
    "your account has been restricted",
)

STATUTS_ALERTE = (429, 999)


def _commence_par(chemin: str, prefixes) -> bool:
    """Le chemin (sans requête) commence par l'un des préfixes, segment entier :
    « /login » vaut /login et /login/…, pas /loginov/."""
    chemin = chemin.lower()
    if not chemin.endswith("/"):
        chemin += "/"
    return any(chemin.startswith(p.rstrip("/") + "/") for p in prefixes)


def nature_page(url: str, texte: Optional[str] = None,
                statut: Optional[int] = None) -> Optional[str]:
    """"alerte" (avertissement LinkedIn), "session" (connexion à refaire) ou None.

    L'alerte passe avant la session. Le texte n'est lu que hors des pages de
    travail (profil, recherche, fil…), où il peut citer ces mots sans alerte.
    """
    chemin = urlparse(url or "").path or "/"
    if statut in STATUTS_ALERTE or _commence_par(chemin, CHEMINS_ALERTE):
        return "alerte"
    if _commence_par(chemin, CHEMINS_SESSION):
        return "session"
    if texte and not _commence_par(chemin, CHEMINS_TRAVAIL):
        bas = texte.lower().replace("’", "'")
        if any(t in bas for t in TEXTES_ALERTE):
            return "alerte"
    return None
