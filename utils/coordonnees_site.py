# -*- coding: utf-8 -*-
"""Coordonnées générales d'une entreprise, lues sur son propre site.

Sans IA et sans navigateur : quelques pages (accueil, contact, mentions
légales) lues en HTTP simple, où l'on ne retient que des emails du domaine de
l'entreprise et des numéros français valides. On préfère ne rien trouver que
rapporter une adresse d'un prestataire ou un nombre qui ressemble à un
téléphone : un faux contact est pire qu'un contact absent.
"""

import html as _html
import ipaddress
import re
import urllib.parse
import urllib.request

# Pages candidates, dans l'ordre où l'on a le plus de chances d'y trouver un contact.
_CHEMINS = ("contact", "nous-contacter", "contactez-nous", "contact-us",
            "mentions-legales", "legal", "mentions-legales.html")
MAX_PAGES = 4        # pages effectivement lues
MAX_REQUETES = 6     # tentatives au total, erreurs comprises : un site lent ne doit pas bloquer
MAX_PAR_TYPE = 3

# Réseaux sociaux et hébergeurs de « page perso » : le « site web » d'une
# fiche LinkedIn y pointe parfois, mais leurs emails et téléphones ne sont pas
# ceux de l'entreprise (facebook.com serait pris pour son propre domaine).
_PLATEFORMES = (
    "facebook.com", "fb.com", "instagram.com", "linkedin.com", "twitter.com", "x.com",
    "youtube.com", "youtu.be", "linktr.ee", "sites.google.com", "wixsite.com",
    "business.site", "tiktok.com", "pinterest.com", "github.io", "weebly.com",
)


# Beaucoup de sites répondent 403 à un client qui se présente comme « We.Reach »
# (anti-robots) ; on se présente comme un navigateur de bureau courant. Ce sont
# des pages publiques lues à raison de quelques requêtes par mois.
USER_AGENT_NAVIGATEUR = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


class SiteInjoignable(Exception):
    """Aucune page du site n'a pu être lue."""


def _nu(hote: str) -> str:
    hote = (hote or "").lower()
    return hote[4:] if hote.startswith("www.") else hote


def _sous(domaine: str, ref: str) -> bool:
    """`domaine` est `ref` ou un sous-domaine de `ref` (sans liste des suffixes publics)."""
    return domaine == ref or domaine.endswith("." + ref)


def _avec_schema(site):
    """LinkedIn écrit souvent « www.exemple.fr » sans schéma : on ajoute https://.

    Seulement si cela ressemble à un nom d'hôte, pour ne pas transformer un
    texte quelconque en adresse.
    """
    s = (site or "").strip()
    if s and "://" not in s and re.match(r"(?i)[a-z0-9][a-z0-9\-]*(?:\.[a-z0-9\-]+)+(?::\d+)?(?:[/?#]|$)", s):
        return "https://" + s
    return s


def _motif_refus(site):
    """(domaine, "") ou (None, motif en clair)."""
    try:
        u = urllib.parse.urlparse(_avec_schema(site))
        hote = (u.hostname or "").lower()
    except ValueError:
        return None, "adresse de site illisible"
    if u.scheme.lower() not in ("http", "https") or not hote:
        return None, "pas d'adresse de site http(s)"
    # Un site d'entreprise est public : on ne va jamais lire le réseau local
    # (SSRF) à partir d'une valeur saisie sur une fiche.
    if hote == "localhost" or hote.endswith((".localhost", ".local", ".internal")):
        return None, "adresse locale refusée"
    try:
        ip = ipaddress.ip_address(hote)
    except ValueError:
        ip = None
    if ip is not None and (ip.is_private or ip.is_loopback or ip.is_link_local
                           or ip.is_unspecified or ip.is_reserved or ip.is_multicast):
        return None, "adresse IP privée ou locale refusée"
    if ip is None and "." not in hote:
        return None, "nom d'hôte sans domaine"
    dom = _nu(hote)
    if any(_sous(dom, p) for p in _PLATEFORMES):
        return None, "le site indiqué est une page de réseau social"
    return dom, ""


def domaine_de(site):
    """« https://www.exemple.fr/fr » → « exemple.fr » ; None si inutilisable.

    Inutilisable : pas du http(s), adresse locale, ou réseau social / page
    hébergée (voir `_PLATEFORMES`). Un schéma absent est complété.
    """
    return _motif_refus(site)[0]


def motif_inutilisable(site) -> str:
    """Pourquoi l'adresse ne sera jamais lue (pas du http(s), locale, réseau social) ; "" si elle peut l'être.

    Distingue un refus durable — qui ne changera qu'avec la fiche — d'une
    panne réseau passagère, pour que l'appelant ne le redise pas à chaque fois.
    """
    return _motif_refus(site)[1]


def pages_a_lire(site: str) -> list:
    """Accueil puis pages de contact probables, sur la même origine que `site`."""
    site = _avec_schema(site)
    u = urllib.parse.urlparse(site)
    origine = f"{u.scheme}://{u.netloc}"
    return [site] + [f"{origine}/{c}" for c in _CHEMINS]


# --- Emails -----------------------------------------------------------------
# Motif conservateur et BORNÉ (RFC : local 64, étiquette 63). Sans bornes, une
# longue suite de caractères sans arobase (base64, jeton) coûte un temps
# quadratique ; le lookbehind interdit de repartir au milieu d'une suite, donc
# une partie locale trop longue est refusée plutôt que tronquée. Il s'arrête de
# lui-même sur « ? », « " », « < » ou une espace : « mailto:a@b.fr?subject=x »
# donne « a@b.fr ».
_EMAIL = re.compile(
    r"(?<![A-Za-z0-9._%+\-])[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9\-]{1,63}(?:\.[A-Za-z0-9\-]{1,63}){1,7}")
_MAILTO = re.compile(r"""mailto:([^"'?\s>]+)""", re.I)
# Obfuscations triviales « nom [at] site [dot] fr » (crochets ou parenthèses
# seulement : un « at » nu dans une phrase ne doit pas devenir une arobase).
_AT = re.compile(r"\s*[\[(]\s*at\s*[\])]\s*", re.I)
_DOT = re.compile(r"\s*[\[(]\s*dot\s*[\])]\s*", re.I)
_EXT_FICHIER = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js")
# Étiquettes de sous-domaine des outils de suivi (« o1.ingest.sentry.io »). On
# compare des ÉTIQUETTES, pas des sous-chaînes : « contact@sentry-conseil.fr »
# sur son propre domaine est un vrai contact.
_ETIQUETTES_TECHNIQUES = {"sentry", "wixpress"}
# Adresses génériques d'abord : ce sont les boîtes faites pour recevoir un
# message d'inconnu, contrairement à « prenom.nom@ ».
_GENERIQUES = ("contact", "info", "infos", "hello", "bonjour", "accueil", "commercial",
               "recrutement", "rh", "jobs", "carrieres", "careers", "presse", "rgpd", "dpo",
               "secretariat", "direction", "ventes")


def _email_valable(email: str, domaine: str) -> bool:
    if email.endswith(_EXT_FICHIER):
        return False
    dom = _nu(email.rsplit("@", 1)[1])
    if dom == "example.com" or dom.endswith(".example.com"):
        return False
    # Égalité ou sous-domaine, sans liste des suffixes publics : « .evil.com »
    # collé derrière le domaine ne passe pas, et « .co.uk » n'y change rien.
    if not _sous(dom, domaine):
        return False
    prefixe = dom[: len(dom) - len(domaine)].strip(".").split(".")
    return not (set(prefixe) & _ETIQUETTES_TECHNIQUES)


def _classer_emails(emails):
    """Adresses génériques d'abord, ordre d'apparition conservé sinon."""
    return sorted(emails, key=lambda e: e.split("@")[0] not in _GENERIQUES)


# --- Téléphones -------------------------------------------------------------
# Numéro français : +33 / 0033 puis 9 chiffres commençant par 1-9 (le « (0) »
# est retiré avant), ou 0 puis [1-9] puis 8 chiffres, ou numéro vert 0800 123
# 456 (écrit 4-3-3). Séparateurs : espace, point ou tiret, jamais un saut de
# ligne (deux blocs voisins ne forment pas un numéro). « (?<![\d+]) » et
# « (?!\d) » exigent des bornes non numériques : un SIRET (14 chiffres), un
# SIREN ou un prix n'en contiennent pas, et « 00… » (international) ne passe
# pas pour un « 0[1-9] ».
_E = r"[ \t\u00a0]"
_SEP = r"[ \t\u00a0.\-]?"
_TEL_TEXTE = re.compile(
    r"(?<![\d+])(?:(?:\+33|0033)" + _E + r"*(?:\(0\))?" + _E + r"*[1-9]|0[1-9])(?:" + _SEP + r"\d{2}){4}(?!\d)"
    r"|(?<![\d+])0" + _E + r"?8\d{2}" + _SEP + r"\d{3}" + _SEP + r"\d{3}(?!\d)")
_TEL_HREF = re.compile(r"""href\s*=\s*(?:"\s*tel:([^"]*)"|'\s*tel:([^']*)'|tel:([^\s>]+))""", re.I)
_ETRANGER = re.compile(r"\+[\d\s().\-]{8,20}")
# Signature d'un prestataire : son téléphone n'est pas celui de l'entreprise.
_CREDIT = re.compile(
    r"(?:réalis|conçu|concu|développ|developp|créé|cree|propuls|design)\w*\s+(?:par|by)\b|\bagence\b",
    re.I)


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
    """Numéro d'un lien tel: ; un numéro étranger (+…) est gardé, espacé proprement."""
    v = urllib.parse.unquote(valeur).strip()
    fr = _normaliser_fr(v)
    if fr:
        return fr
    # Un numéro étranger n'est gardé que s'il est entièrement fait de chiffres et
    # de séparateurs (8 à 15 chiffres) ; « (0) » est un artifice d'écriture
    # (« +44 (0)20… ») qui fausserait le numéro international.
    v = v.replace("(0)", "")
    if _ETRANGER.fullmatch(v) and 8 <= len(re.sub(r"\D", "", v)) <= 15:
        return re.sub(r"\s+", " ", re.sub(r"[.\-()]", " ", v)).strip()
    return None


def _zones_credit(texte: str):
    """Intervalles (début, fin) où un numéro est celui d'un prestataire.

    Du repère (« réalisé par », « agence »…) jusqu'à 80 caractères plus loin ou
    la fin du bloc. Limite connue : on ne voit que ce que la page dit ; un
    crédit sans ces mots, ou un numéro de `tel:` placé dans un pied de page de
    prestataire, n'est pas reconnu. Le repère « agence » écarte aussi, par
    prudence, « notre agence de Lyon : 04… » (un contact manquant vaut mieux
    qu'un contact faux).
    """
    zones = []
    for m in _CREDIT.finditer(texte):
        fin_bloc = texte.find("\n", m.end())
        fin_bloc = len(texte) if fin_bloc == -1 else fin_bloc
        zones.append((m.start(), min(m.end() + 80, fin_bloc)))
    return zones


def _unique(valeurs):
    vus = []
    for v in valeurs:
        if v and v not in vus:
            vus.append(v)
    return vus[:MAX_PAR_TYPE]


def extraire_coordonnees(html: str, domaine: str, avec_telephones: bool = True) -> dict:
    """Emails du domaine et téléphones d'une page : dédoublonnés, 3 au plus chacun.

    `avec_telephones=False` pour une page lue après une redirection hors du
    domaine : ses emails sont filtrés par domaine, mais un numéro n'a pas de
    domaine pour prouver qu'il appartient à l'entreprise.
    """
    # Le contenu des scripts et feuilles de style est du code, pas du contact.
    # Une balise jamais fermée est coupée jusqu'à la fin du document.
    html = re.sub(r"(?is)<(script|style)\b.*?(?:</\1\s*>|\Z)", " ", html or "")
    emails = []
    for m in _MAILTO.finditer(html):
        emails += _EMAIL.findall(urllib.parse.unquote(_html.unescape(m.group(1))))
    # Les balises de bloc deviennent des sauts de ligne : ils délimitent « un
    # même bloc de texte » pour la détection des crédits.
    texte = re.sub(r"(?is)</?(?:p|div|li|ul|ol|br|tr|td|th|table|h[1-6]|section|footer|header|article)\b[^>]*>", "\n", html)
    texte = _html.unescape(re.sub(r"(?s)<[^>]*>", " ", texte))
    texte = _DOT.sub(".", _AT.sub("@", texte))
    emails += _EMAIL.findall(texte)
    emails = _classer_emails([e.lower() for e in emails if _email_valable(e.lower(), domaine)])

    tels = []
    if avec_telephones:
        for m in _TEL_HREF.finditer(html):
            tels.append(_telephone_href(next(g for g in m.groups() if g is not None)))
        zones = _zones_credit(texte)
        tels += [_normaliser_fr(m.group(0)) for m in _TEL_TEXTE.finditer(texte)
                 if not any(a <= m.start() < b for a, b in zones)]
    return {"emails": _unique(emails), "telephones": _unique(tels)}


# --- Lecture HTTP -----------------------------------------------------------
def _transport_http(url: str, delai: float, taille_max: int = 1_500_000):
    """(url finale, octets) ; la lecture est plafonnée pour ne pas avaler un fichier géant."""
    requete = urllib.request.Request(url, headers={"User-Agent": USER_AGENT_NAVIGATEUR})
    with urllib.request.urlopen(requete, timeout=delai) as reponse:
        return reponse.geturl(), reponse.read(taille_max)


def lire_site(site, transport=None, delai: float = 6.0, taille_max: int = 1_500_000) -> dict:
    """Coordonnées générales du site, en s'arrêtant dès un email ET un téléphone.

    Le domaine de référence est celui du site donné par LinkedIn. Si l'accueil
    redirige ailleurs (site racheté, page de l'agence), on ne l'adopte pas :
    ce serait accepter les emails d'un tiers comme étant ceux de l'entreprise.
    Pour la même raison, les téléphones d'une page dont l'adresse FINALE n'est
    pas sur ce domaine sont ignorés.
    """
    domaine, motif = _motif_refus(site)
    if not domaine:
        raise SiteInjoignable(motif)
    transport = transport or (lambda u, d: _transport_http(u, d, taille_max))
    emails, tels, lues, tentatives, erreur = [], [], [], 0, None
    for url in pages_a_lire(site):
        if len(lues) >= MAX_PAGES or tentatives >= MAX_REQUETES or (emails and tels):
            break
        tentatives += 1
        try:
            finale, brut = transport(url, delai)
        except Exception as e:  # une page en erreur est sautée, pas fatale
            erreur = e
            continue
        lues.append(url)
        domaine_final = domaine_de(finale)
        trouve = extraire_coordonnees(
            brut[:taille_max].decode("utf-8", errors="replace"), domaine,
            avec_telephones=bool(domaine_final and _sous(domaine_final, domaine)))
        emails = _unique(_classer_emails(emails + trouve["emails"]))
        tels = _unique(tels + trouve["telephones"])
    if not lues:
        raise SiteInjoignable(str(erreur) if erreur else "aucune page lue")
    return {"emails": emails, "telephones": tels, "pages_lues": lues}
