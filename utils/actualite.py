# -*- coding: utf-8 -*-
"""Actualité d'une entreprise : flux RSS public de Google News, sans clé.

Constaté le 2026-10-15 : le nom seul ramène des homonymes (« Thiga » → des
articles sans rapport) ; avec les mots des événements qui comptent et une
fenêtre d'un an, « Decathlon » ramène le rachat de 50 % de Sport 2000. Deux
filtres, donc : la requête ne demande que ces événements, et un titre n'est
gardé que s'il contient le nom de l'entreprise comme mot entier.

Le classement par mots-clés est approximatif (« recrute un biathlète »…) :
chaque titre est montré avec son lien, sa source et sa date pour que la
personne juge. Un résumé par IA pourra venir plus tard.
"""

import re
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

CATEGORIES = {
    "Rachat / fusion": ("rachat", "rachete", "acquisition", "acquiert", "fusion", "cede ",
                        "cession", "entre au capital", "prend le controle", "reprise de"),
    "Licenciements / restructuration": ("licenciement", "plan social", "pse", "suppression de postes",
                                        "suppressions de postes", "supprime", "restructuration",
                                        "redressement judiciaire", "liquidation", "plan de departs",
                                        "rupture conventionnelle collective"),
    "Levée de fonds": ("leve ", "levee de fonds", "tour de table", "financement de", "serie a", "serie b",
                       "series a", "series b"),
    "Nomination": ("nomme", "nouveau directeur", "nouvelle directrice", "nouveau pdg", "nouveau ceo",
                   "prend la tete"),
}
_MOTS_REQUETE = ("rachat", "acquisition", "fusion", "licenciement", '"plan social"', "restructuration",
                 '"levée de fonds"', "lève", "nomme")
_MAX = 20


class ActualiteIndisponible(Exception):
    """Google News n'a pas répondu de façon exploitable."""


def _plat(texte: str) -> str:
    decompose = unicodedata.normalize("NFKD", texte or "")
    return "".join(c for c in decompose if not unicodedata.combining(c)).lower()


def url_flux(nom: str) -> str:
    q = f'"{nom}" (' + " OR ".join(_MOTS_REQUETE) + ") when:1y"
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": q, "hl": "fr", "gl": "FR", "ceid": "FR:fr"})


def categorie_du_titre(titre: str):
    plat = _plat(titre) + " "
    for categorie, mots in CATEGORIES.items():
        if any(re.search(r"\b" + re.escape(m.strip()) + (r"\b" if not m.endswith(" ") else r"\s"), plat)
               for m in mots):
            return categorie
    return None


def _contient_le_nom(titre: str, nom: str) -> bool:
    return re.search(r"(?<!\w)" + re.escape(_plat(nom).strip()) + r"(?!\w)", _plat(titre)) is not None


def lire_flux(xml: bytes, nom: str) -> list:
    racine = ET.fromstring(xml)
    articles, vus = [], set()
    for it in racine.iter("item"):
        brut = (it.findtext("title") or "").strip()
        source = (it.findtext("source") or "").strip()
        titre = brut[: -len(" - " + source)] if source and brut.endswith(" - " + source) else brut
        if not titre or titre.lower() in vus or not _contient_le_nom(titre, nom):
            continue
        categorie = categorie_du_titre(titre)
        if categorie is None:
            continue
        try:
            publie = parsedate_to_datetime(it.findtext("pubDate") or "").date().isoformat()
        except Exception:
            publie = ""
        vus.add(titre.lower())
        articles.append({"titre": titre, "lien": (it.findtext("link") or "").strip(), "source": source,
                         "publie_le": publie, "categorie": categorie})
    articles.sort(key=lambda a: a["publie_le"], reverse=True)
    return articles[:_MAX]


def _transport_http(url: str, delai: float) -> bytes:
    requete = urllib.request.Request(url, headers={"User-Agent": "We.Reach"})
    with urllib.request.urlopen(requete, timeout=delai) as reponse:
        return reponse.read()


def interroger(nom: str, transport=None, delai: float = 8.0) -> list:
    try:
        return lire_flux((transport or _transport_http)(url_flux(nom), delai), nom)
    except Exception as e:
        raise ActualiteIndisponible(str(e)) from e
