# -*- coding: utf-8 -*-
"""Coordonnées générales d'une entreprise, lues sur son propre site.

Sans IA et sans navigateur : quelques pages (accueil, contact, mentions
légales) lues en HTTP simple, où l'on ne retient que des emails du domaine de
l'entreprise et des numéros français valides. On préfère ne rien trouver que
rapporter une adresse d'un prestataire ou un nombre qui ressemble à un
téléphone : un faux contact est pire qu'un contact absent.
"""

import html as _html
import re
import urllib.parse
import urllib.request

# Pages candidates, dans l'ordre où l'on a le plus de chances d'y trouver un contact.
_CHEMINS = ("contact", "nous-contacter", "contactez-nous", "contact-us",
            "mentions-legales", "legal", "mentions-legales.html")
MAX_PAGES = 4
MAX_PAR_TYPE = 3


class SiteInjoignable(Exception):
    """Aucune page du site n'a pu être lue."""


def _nu(hote: str) -> str:
    hote = (hote or "").lower()
    return hote[4:] if hote.startswith("www.") else hote


def domaine_de(site):
    """« https://www.exemple.fr/fr » → « exemple.fr » ; None si ce n'est pas du http(s)."""
    try:
        u = urllib.parse.urlparse((site or "").strip())
        if u.scheme.lower() not in ("http", "https") or not u.hostname:
            return None
        return _nu(u.hostname)
    except ValueError:
        return None


def pages_a_lire(site: str) -> list:
    """Accueil puis pages de contact probables, sur la même origine que `site`."""
    u = urllib.parse.urlparse(site)
    origine = f"{u.scheme}://{u.netloc}"
    return [site] + [f"{origine}/{c}" for c in _CHEMINS]


# --- Emails -----------------------------------------------------------------
# Motif volontairement conservateur : partie locale usuelle, puis un domaine à
# au moins un point. Il s'arrête de lui-même sur « ? », « " », « < » ou une
# espace, donc « mailto:a@b.fr?subject=x » donne « a@b.fr ».
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+")
_MAILTO = re.compile(r"""mailto:([^"'?\s>]+)""", re.I)
# Obfuscations triviales « nom [at] site [dot] fr » (crochets ou parenthèses
# seulement : un « at » nu dans une phrase ne doit pas devenir une arobase).
_AT = re.compile(r"\s*[\[(]\s*at\s*[\])]\s*", re.I)
_DOT = re.compile(r"\s*[\[(]\s*dot\s*[\])]\s*", re.I)
_EXT_FICHIER = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js")
_INDESIRABLES = ("example.com", "sentry", "wixpress")


def _email_valable(email: str, domaine: str) -> bool:
    if any(m in email for m in _INDESIRABLES) or email.endswith(_EXT_FICHIER):
        return False
    dom = _nu(email.rsplit("@", 1)[1])
    # Égalité ou sous-domaine, sans liste des suffixes publics : « .evil.com »
    # collé derrière le domaine ne passe pas, et « .co.uk » n'y change rien.
    return dom == domaine or dom.endswith("." + domaine)


# --- Téléphones -------------------------------------------------------------
# Numéro français : +33 / 0033 puis 9 chiffres commençant par 1-9 (le « (0) »
# est retiré avant), ou 0 puis [1-9] puis 8 chiffres. Les séparateurs sont
# espace, point ou tiret. « (?<![\d+]) » et « (?!\d) » exigent des bornes non
# numériques : un SIRET (14 chiffres), un SIREN ou un prix n'en contiennent
# pas, et « 00… » (international) ne passe pas pour un « 0[1-9] ».
_SEP = r"[\s.\-]?"
_TEL_TEXTE = re.compile(
    r"(?<![\d+])(?:(?:\+33|0033)\s*(?:\(0\))?\s*[1-9]|0[1-9])(?:" + _SEP + r"\d{2}){4}(?!\d)")


def _normaliser_fr(brut: str):
    """Chiffres français → « +33 1 23 45 67 89 », ou None si ce n'est pas valide."""
    chiffres = re.sub(r"\D", "", brut.replace("(0)", ""))
    if chiffres.startswith("0033"):
        chiffres = chiffres[4:]
    elif brut.strip().startswith("+33"):
        chiffres = chiffres[2:]
    elif chiffres.startswith("0"):
        chiffres = chiffres[1:]
    else:
        return None
    if not re.fullmatch(r"[1-9]\d{8}", chiffres):
        return None
    return "+33 {} {} {} {} {}".format(chiffres[0], *(chiffres[i:i + 2] for i in range(1, 9, 2)))


def _telephone_href(valeur: str):
    """Numéro d'un lien tel: ; un numéro étranger (+…) est gardé tel quel, espacé proprement."""
    v = urllib.parse.unquote(valeur).strip()
    fr = _normaliser_fr(v)
    if fr:
        return fr
    if v.startswith("+"):
        v = re.sub(r"\s+", " ", re.sub(r"[.\-()]", " ", v)).strip()
        if len(re.sub(r"\D", "", v)) >= 8:
            return v
    return None


def _unique(valeurs):
    vus = []
    for v in valeurs:
        if v and v not in vus:
            vus.append(v)
    return vus[:MAX_PAR_TYPE]


def extraire_coordonnees(html: str, domaine: str) -> dict:
    """Emails du domaine et téléphones d'une page : dédoublonnés, 3 au plus chacun."""
    # Le contenu des scripts et feuilles de style est du code, pas du contact.
    html = re.sub(r"(?is)<(script|style)\b.*?</\1\s*>", " ", html or "")
    emails = []
    for m in _MAILTO.finditer(html):
        emails += _EMAIL.findall(urllib.parse.unquote(_html.unescape(m.group(1))))
    texte = _html.unescape(re.sub(r"(?s)<[^>]*>", " ", html))
    texte = _DOT.sub(".", _AT.sub("@", texte))
    emails += _EMAIL.findall(texte)
    emails = [e.lower() for e in emails]

    tels = [_telephone_href(m.group(1)) for m in re.finditer(r"""tel:([^"'>]+)""", html, re.I)]
    tels += [_normaliser_fr(m.group(0)) for m in _TEL_TEXTE.finditer(texte)]
    return {"emails": _unique(e for e in emails if _email_valable(e, domaine)),
            "telephones": _unique(tels)}


# --- Lecture HTTP -----------------------------------------------------------
def _transport_http(url: str, delai: float, taille_max: int = 1_500_000):
    """(url finale, octets) ; la lecture est plafonnée pour ne pas avaler un fichier géant."""
    requete = urllib.request.Request(url, headers={"User-Agent": "We.Reach"})
    with urllib.request.urlopen(requete, timeout=delai) as reponse:
        return reponse.geturl(), reponse.read(taille_max)


def lire_site(site, transport=None, delai: float = 6.0, taille_max: int = 1_500_000) -> dict:
    """Coordonnées générales du site, en s'arrêtant dès un email ET un téléphone.

    Le domaine de référence est celui du site donné par LinkedIn. Si l'accueil
    redirige ailleurs (site racheté, page de l'agence), on ne l'adopte pas :
    ce serait accepter les emails d'un tiers comme étant ceux de l'entreprise.
    """
    domaine = domaine_de(site)
    if not domaine:
        raise SiteInjoignable("pas d'adresse de site http(s)")
    transport = transport or (lambda u, d: _transport_http(u, d, taille_max))
    emails, tels, lues, erreur = [], [], [], None
    for url in pages_a_lire(site):
        if len(lues) >= MAX_PAGES or (emails and tels):
            break
        try:
            _finale, brut = transport(url, delai)
        except Exception as e:  # une page en erreur est sautée, pas fatale
            erreur = e
            continue
        lues.append(url)
        trouve = extraire_coordonnees(brut[:taille_max].decode("utf-8", errors="replace"), domaine)
        emails = _unique(emails + trouve["emails"])
        tels = _unique(tels + trouve["telephones"])
    if not lues:
        raise SiteInjoignable(str(erreur) if erreur else "aucune page lue")
    return {"emails": emails, "telephones": tels, "pages_lues": lues}
