# -*- coding: utf-8 -*-
"""Profils voisins d'un profil de référence : adressage et filtrage.

LinkedIn entretient pour chaque profil une liste de profils voisins — le
panneau « Plus de profils pour vous » — fondée sur la co-consultation : les
gens qui ont regardé ce profil ont aussi regardé ceux-là. C'est un signal
qu'on ne saurait pas reconstruire, puisqu'il repose sur des parcours de
navigation que LinkedIn seul observe.

Ce module ne connaît ni Playwright, ni Streamlit, ni la base : il adresse le
panneau et trie son contenu. Tout s'y teste sans navigateur.
"""

import re

# Le segment qui suit /in/ : on s'arrête au premier /, ? ou #, ce qui écarte
# d'un coup les paramètres de suivi et les sous-pages (/details/experience/).
_MOTIF_VANITY = re.compile(r"linkedin\.com/in/([^/?#]+)", re.I)

CHEMIN_PANNEAU = "overlay/browsemap-recommendations/"


def vanity_depuis_url(url):
    """Identifiant du profil dans son URL, ou None si ce n'est pas un profil.

    Minuscule à dessein : LinkedIn traite ces identifiants sans égard à la
    casse, et deux écritures du même profil doivent se reconnaître.
    """
    correspondance = _MOTIF_VANITY.search(url or "")
    if not correspondance:
        return None
    return correspondance.group(1).strip().lower() or None


def normaliser_url(url):
    """URL canonique du profil, ou None. C'est la clé de comparaison.

    Le panneau sert ses liens avec des paramètres de suivi. Sans forme
    canonique, le filtre « déjà dans ton fichier » ne reconnaît pas quelqu'un
    qui y est déjà, et la personne ressort une seconde fois.
    """
    vanity = vanity_depuis_url(url)
    if vanity is None:
        return None
    return f"https://www.linkedin.com/in/{vanity}/"


def url_panneau(url):
    """URL du panneau « Plus de profils pour vous » de ce profil, ou None.

    Le panneau est directement adressable : pas de clic à simuler, pas de
    menu à déplier.
    """
    canonique = normaliser_url(url)
    return None if canonique is None else canonique + CHEMIN_PANNEAU
