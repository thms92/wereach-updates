# -*- coding: utf-8 -*-
"""Acceptations lues dans deux listes LinkedIn, pas profil par profil.

La liste des invitations envoyées et celle des relations (triées par ajout
récent) montrent beaucoup de personnes par page : deux ou trois pages
suffisent là où la visite de chaque profil en coûtait une par personne.

Structure relevée en réel le 2026-10-28 (compte de Thomas, lecture seule) :
chaque liste est un unique conteneur `data-component-type="LazyColumn"` qui
se remplit au défilement ; chaque carte y porte le lien /in/ de la personne
(deux fois pour une relation). Le total s'affiche hors du conteneur :
« Personnes (18) » sur les envoyées, « 20 relations » sur les relations.
Les noms de classes sont générés par LinkedIn et changent : on ne s'y fie
pas. Seuls les liens /in/ À L'INTÉRIEUR du conteneur comptent, pour qu'une
suggestion affichée à côté ne passe jamais pour une relation.

Ce module ne connaît ni Playwright, ni la base : tout s'y teste sans
navigateur.
"""

import re
import urllib.parse
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import List, Optional

URL_INVITATIONS_ENVOYEES = "https://www.linkedin.com/mynetwork/invitation-manager/sent/"
URL_RELATIONS = "https://www.linkedin.com/mynetwork/invite-connect/connections/"

# Pages chargées pour lire les listes : les envoyées, les relations, et une
# page suivante si l'une des deux en propose une. Défiler ne charge pas de
# page ; une nouvelle adresse, si.
MAX_PAGES_LISTES = 3
# Défilements par page au plus, et défilements sans nouvelle carte avant
# d'arrêter (la liste est alors entièrement chargée).
MAX_DEFILEMENTS_LISTE = 12
DEFILEMENTS_SANS_NOUVEAU = 2

# Total annoncé par LinkedIn, pris à sa première occurrence dans la page.
# Séparateur de milliers (espace, insécable, point, virgule) par groupes de
# trois seulement : un autre nombre placé juste avant ne s'y colle pas.
_NOMBRE = r"(\d{1,3}(?:[\s.,]\d{3})+|\d+)"
MOTIF_TOTAL_ENVOYEES = re.compile(r"(?:Personnes|People)\s*\(\s*" + _NOMBRE + r"\s*\)", re.I)
MOTIF_TOTAL_RELATIONS = re.compile(r"\b" + _NOMBRE + r"\s*(?:relations?|connections?)\b", re.I)

LIBELLE_LISTE_ILLISIBLE = "Liste LinkedIn illisible : vérification faite profil par profil."

_MOTIF_SLUG = re.compile(r"/in/([^/?#]+)", re.I)
_LIBELLES_SUIVANT = ("suivant", "page suivante", "next")
_VIDES = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
          "meta", "source", "track", "wbr"}


def slug_profil(url) -> Optional[str]:
    """Identifiant du profil après /in/, décodé et en minuscules, ou None.

    Sans requête ni « / » final : c'est la clé qui reconnaît une même
    personne dans la base et dans les listes."""
    m = _MOTIF_SLUG.search(urllib.parse.urlparse(url or "").path or "")
    if not m:
        return None
    return urllib.parse.unquote(m.group(1)).strip().lower() or None


def est_urn(slug: Optional[str]) -> bool:
    """/in/ACoAA… : identifiant interne, que les listes n'affichent pas
    dans leurs liens de profil. Une telle adresse ne s'y retrouve jamais."""
    return bool(slug) and slug.startswith("acoaa")


@dataclass
class ListeLue:
    """Ce qu'une liste montre : les personnes lues, dans l'ordre, sans
    doublon, et le total que LinkedIn annonce."""
    slugs: List[str] = field(default_factory=list)
    annonce: Optional[int] = None
    suivante: Optional[str] = None

    @property
    def complete(self) -> bool:
        """Toutes les personnes annoncées ont été lues."""
        return self.annonce is not None and len(self.slugs) == self.annonce

    def fusionner(self, autre: "ListeLue") -> "ListeLue":
        """Ajoute les personnes d'une lecture suivante (défilement, page
        suivante). Une liste qui décharge ses premières cartes en défilant
        ne fait donc perdre personne."""
        vus = set(self.slugs)
        slugs = self.slugs + [s for s in autre.slugs if s not in vus]
        annonce = self.annonce if self.annonce is not None else autre.annonce
        return ListeLue(slugs, annonce, autre.suivante)


class _Lecteur(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.profondeur = 0          # > 0 : à l'intérieur du conteneur
        self.conteneur_vu = False
        self.hrefs: List[str] = []
        self.texte: List[str] = []
        self.suivante: Optional[str] = None
        self._ignore = 0             # dans <script> ou <style>

    def handle_starttag(self, tag, attrs):
        if tag in _VIDES:
            return
        a = dict(attrs)
        if tag in ("script", "style"):
            self._ignore += 1
        if self.profondeur:
            self.profondeur += 1
        elif a.get("data-component-type") == "LazyColumn" and not self.conteneur_vu:
            self.conteneur_vu = True
            self.profondeur = 1
        if tag == "a" and a.get("href"):
            href = a["href"]
            if self.profondeur and "/in/" in href:
                self.hrefs.append(href)
            libelle = (a.get("aria-label") or "").strip().lower()
            if self.suivante is None and ((a.get("rel") or "").lower() == "next"
                                          or libelle.startswith(_LIBELLES_SUIVANT)):
                self.suivante = href

    def handle_endtag(self, tag):
        if tag in _VIDES:
            return
        if tag in ("script", "style") and self._ignore:
            self._ignore -= 1
        if self.profondeur:
            self.profondeur -= 1

    def handle_data(self, data):
        if not self._ignore:
            self.texte.append(data)


def _nombre(brut: str) -> Optional[int]:
    chiffres = re.sub(r"\D", "", brut or "")
    return int(chiffres) if chiffres else None


def lire_liste(html: str, url_page: str, motif_total) -> Optional[ListeLue]:
    """Personnes et total d'une liste, ou None si la page ne se lit pas
    comme une liste (conteneur ou total introuvable). Une liste vide
    annoncée « (0) » se lit, même sans conteneur."""
    lecteur = _Lecteur()
    try:
        lecteur.feed(html or "")
        lecteur.close()
    except Exception:
        return None
    m = motif_total.search(" ".join(lecteur.texte))
    annonce = _nombre(m.group(1)) if m else None
    if annonce is None or (not lecteur.conteneur_vu and annonce != 0):
        return None
    slugs, vus = [], set()
    for href in lecteur.hrefs:
        slug = slug_profil(urllib.parse.urljoin(url_page, href))
        if slug and slug not in vus:
            vus.add(slug)
            slugs.append(slug)
    suivante = urllib.parse.urljoin(url_page, lecteur.suivante) if lecteur.suivante else None
    if suivante and slug_profil(suivante):
        suivante = None
    return ListeLue(slugs, annonce, suivante)


@dataclass
class Classement:
    """Le sort de chaque invitation en attente après lecture des listes."""
    acceptees: list = field(default_factory=list)     # dans les relations
    en_attente: list = field(default_factory=list)    # dans les envoyées
    absentes: list = field(default_factory=list)      # retirée
    restants: list = field(default_factory=list)      # statut non établi

    @property
    def verifiees(self) -> List[str]:
        return [p.get("url") for p in self.acceptees + self.en_attente + self.absentes]


def classer(profils, envoyees: Optional[ListeLue],
            relations: Optional[ListeLue]) -> Classement:
    """Range chaque invitation en attente selon les deux listes (None =
    liste illisible).

    Dans les relations : acceptée. Dans les envoyées : toujours en attente.
    Dans aucune des deux alors que les DEUX listes ont été lues en entier :
    retirée, pas acceptée. Une liste de relations lue en partie ne suffit
    pas : quelqu'un qui a accepté avant la partie lue n'y figure pas, et
    serait classé non accepté à chaque passage. Sinon, ou pour une adresse
    /in/ACoAA… : non établi, à vérifier sur le profil."""
    res = Classement()
    dans_relations = set(relations.slugs) if relations else set()
    dans_envoyees = set(envoyees.slugs) if envoyees else set()
    deux_listes_lues = bool(envoyees and envoyees.complete and relations and relations.complete)
    for prof in profils:
        slug = slug_profil(prof.get("url"))
        if not slug or est_urn(slug):
            res.restants.append(prof)
        elif slug in dans_relations:
            res.acceptees.append(prof)
        elif slug in dans_envoyees:
            res.en_attente.append(prof)
        elif deux_listes_lues:
            res.absentes.append(prof)
        else:
            res.restants.append(prof)
    return res
