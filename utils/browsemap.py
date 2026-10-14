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
import urllib.parse

# Le segment qui suit /in/ : on s'arrête au premier /, ? ou #, ce qui écarte
# d'un coup les paramètres de suivi et les sous-pages (/details/experience/).
_MOTIF_VANITY = re.compile(r"linkedin\.com/in/([^/?#]+)", re.I)

CHEMIN_PANNEAU = "overlay/browsemap-recommendations/"


def vanity_depuis_url(url):
    """Identifiant du profil dans son URL, ou None si ce n'est pas un profil.

    Rendu décodé et en minuscules : c'est la clé qui reconnaît une même
    personne sous ses différentes écritures. LinkedIn traite ces
    identifiants sans égard à la casse, et sert les vanity accentués
    encodés (« c%C3%A9line ») là où la personne colle « céline » — sans
    décodage, ce seraient deux clés. On décode avant de minusculer : sur
    « %C3%89 », minusculer l'encodage ne toucherait pas le « É ».
    """
    correspondance = _MOTIF_VANITY.search(url or "")
    if not correspondance:
        return None
    return urllib.parse.unquote(correspondance.group(1)).strip().lower() or None


def normaliser_url(url):
    """URL canonique du profil, ou None. C'est la clé de comparaison.

    Le panneau sert ses liens avec des paramètres de suivi. Sans forme
    canonique, le filtre « déjà dans ton fichier » ne reconnaît pas quelqu'un
    qui y est déjà, et la personne ressort une seconde fois.

    Le vanity y est ré-encodé, pas laissé accentué : c'est la forme que
    LinkedIn sert lui-même dans ses liens, que tout navigateur ouvre, et
    qui passe telle quelle dans un CSV, un Excel ou la base. Décoder puis
    ré-encoder rend la même URL pour les deux écritures, jusqu'à la casse
    des chiffres hexadécimaux.
    """
    vanity = vanity_depuis_url(url)
    if vanity is None:
        return None
    return f"https://www.linkedin.com/in/{urllib.parse.quote(vanity, safe='')}/"


def url_panneau(url):
    """URL du panneau « Plus de profils pour vous » de ce profil, ou None.

    Ce n'est PAS une adresse où se rendre : chargée directement, elle
    redirige vers le profil nu (constaté au premier essai réel). C'est la
    cible du lien « Tout afficher » de la section du profil, sur lequel on
    clique pour ouvrir le panneau — la récolte s'en sert pour le trouver.
    """
    canonique = normaliser_url(url)
    return None if canonique is None else canonique + CHEMIN_PANNEAU


MOTIF_URL_ILLISIBLE = "lien de profil illisible"
MOTIF_PREMIER_DEGRE = "déjà dans ton réseau (1er degré)"
MOTIF_DEJA_AU_FICHIER = "déjà dans ton fichier"
MOTIF_NON_INVITABLE = "non invitable (« Suivre » seulement)"


def filtrer_suggestions(suggestions, urls_en_base=(), entreprise_reference=None,
                        invitables_seulement=False, mot_intitule=None):
    """Trie les entrées du panneau en (retenues, écartées).

    Chaque écartée porte son motif, affiché à l'écran : une liste qui se vide
    doit dire pourquoi, sinon elle passe pour un profil sans voisins — c'est
    précisément le défaut corrigé en 1.4.7, sous une autre forme.

    L'ordre des exclusions n'est pas indifférent. On écarte d'abord sur ce qui
    est certain — lien illisible, réseau, fichier —, ensuite sur ce qui est
    approximatif — l'entreprise, lue dans un intitulé écrit à la main —, enfin
    sur le choix de la personne. Le motif affiché est donc toujours le plus sûr
    des motifs applicables.
    """
    connues = {normaliser_url(u) for u in (urls_en_base or ())}
    connues.discard(None)

    entreprise = (entreprise_reference or "").strip().lower()
    mot = (mot_intitule or "").strip().lower()

    retenues, ecartees = [], []

    for entree in suggestions or ():
        canonique = normaliser_url(entree.get("url"))
        intitule = (entree.get("intitule") or "").lower()

        if canonique is None:
            motif = MOTIF_URL_ILLISIBLE
        elif (entree.get("degre") or "").strip() == "1er":
            motif = MOTIF_PREMIER_DEGRE
        elif canonique in connues:
            motif = MOTIF_DEJA_AU_FICHIER
        elif entreprise and entreprise in intitule:
            # Best effort assumé : qui ne mentionne pas son employeur dans son
            # intitulé passera le filtre. Le tableau de l'étape 2 affiche la
            # société lue sur la page de profil, où on le verra.
            motif = f"encore chez {entreprise_reference.strip()}"
        elif invitables_seulement and not entree.get("invitable"):
            motif = MOTIF_NON_INVITABLE
        elif mot and mot not in intitule:
            motif = f"l'intitulé ne contient pas « {mot_intitule.strip()} »"
        else:
            retenues.append(dict(entree, url=canonique))
            continue

        ecartees.append(dict(entree, motif=motif))

    return retenues, ecartees
