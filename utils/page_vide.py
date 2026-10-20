# -*- coding: utf-8 -*-
"""Une page de résultats sans profil : absence réelle, ou lecture ratée ?

Le 15/10, une veille a rendu « 0 profils extraits » pour Amazon sans qu'on
puisse dire si LinkedIn n'avait trouvé personne ou si la page, pleine,
n'avait pas été lue. Seul le « Aucun résultat » affiché par LinkedIn prouve
une absence ; sans lui, la page est enregistrée dans logs/ pour comprendre.
Partagé par la recherche (scraper_v2) et la veille.
"""

from logger import logger
from utils.dom_selectors import DOMSelectors


async def diagnostiquer_page_vide(page, dumper, nom_fichier):
    """None si LinkedIn affiche « Aucun résultat » ; sinon où est la page.

    `dumper(html, nom_fichier=…) -> bool` enregistre le HTML (le
    `_dumper_panneau` du moteur). Le retour, « page enregistrée dans logs/ »
    ou « page non enregistrée », se glisse tel quel dans un message.
    """
    try:
        etat = await page.evaluate(DOMSelectors.etat_resultats_personnes_js()) or {}
    except Exception as e:
        logger.warning(f"⚠️ État des résultats illisible sur {getattr(page, 'url', '?')} : "
                       f"{type(e).__name__} : {e}")
        etat = {}
    if etat.get("aucunResultat"):
        return None
    enregistree = dumper(etat.get("html") or "", nom_fichier=nom_fichier)
    return "page enregistrée dans logs/" if enregistree else "page non enregistrée"
