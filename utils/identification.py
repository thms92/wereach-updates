# -*- coding: utf-8 -*-
"""Identifier une entreprise suivie par la recherche d'entreprises de LinkedIn.

Le service interne qui le faisait (« typeahead ») répond 404 depuis le
2026-10-15. La page de recherche, elle, liste dix cartes : « BNP Paribas »
y côtoie Cardif, Arval, Personal Finance… On ne retient qu'un nom
**exactement** identique — sinon on demande le lien plutôt que de deviner.
"""

import urllib.parse

from utils.annuaire import normaliser_nom


def url_recherche_entreprises(nom: str) -> str:
    return ("https://www.linkedin.com/search/results/companies/?"
            + urllib.parse.urlencode({"keywords": nom}))


def choisir_entreprise(resultats, nom_suivi: str):
    """URL retenue et "", ou None et un motif complet (consigne comprise) :
    l'appelant l'affiche tel quel, sans l'analyser."""
    cible = normaliser_nom(nom_suivi)
    exacts = [r for r in resultats or [] if cible and normaliser_nom(r.get("nom", "")) == cible]
    urls = list(dict.fromkeys(r["url"] for r in exacts))
    if len(urls) == 1:
        return urls[0], ""
    if len(urls) > 1:
        return None, f"plusieurs entreprises « {nom_suivi} » sur LinkedIn : collez le lien de la bonne"
    # Coupé sur la liste et non sur le texte : un nom peut contenir « , ».
    noms = list(dict.fromkeys(r.get("nom", "") for r in resultats or [] if r.get("nom")))[:3]
    proposees = ", ".join(noms) if noms else "aucune"
    return None, (f"aucune entreprise « {nom_suivi} » sur LinkedIn (proposées : {proposees}) "
                  "— collez le lien de sa page entreprise")
