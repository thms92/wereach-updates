# -*- coding: utf-8 -*-
"""Coordonnées générales lues sur le site : aucun test ne touche le réseau."""

import io
import urllib.request

import pytest

from utils import coordonnees_site as cs


def test_domaine_de():
    assert cs.domaine_de("https://www.exemple.fr/fr") == "exemple.fr"
    assert cs.domaine_de("http://Exemple.FR") == "exemple.fr"
    assert cs.domaine_de("ftp://exemple.fr") is None
    assert cs.domaine_de("exemple.fr") == "exemple.fr"
    assert cs.domaine_de("www.exemple.fr/fr") == "exemple.fr"
    assert cs.domaine_de("pas un site") is None
    assert cs.domaine_de(None) is None
    assert cs.domaine_de("") is None


def test_pages_a_lire_meme_origine():
    pages = cs.pages_a_lire("https://www.exemple.fr/fr/accueil")
    assert pages[0] == "https://www.exemple.fr/fr/accueil"
    assert "https://www.exemple.fr/contact" in pages
    assert "https://www.exemple.fr/mentions-legales.html" in pages
    assert all(p.startswith("https://www.exemple.fr") for p in pages)


def test_emails_mailto_et_texte():
    html = ('<a href="mailto:Contact@Exemple.fr?subject=Bonjour%20vous">écrire</a>'
            "<p>ou compta@exemple.fr</p>")
    assert cs.extraire_coordonnees(html, "exemple.fr")["emails"] == ["contact@exemple.fr", "compta@exemple.fr"]


def test_email_autre_domaine_ecarte():
    html = "agence@webagency.com jean@gmail.com info@exemple.fr"
    assert cs.extraire_coordonnees(html, "exemple.fr")["emails"] == ["info@exemple.fr"]


def test_sous_domaine_accepte_mais_pas_suffixe_trompeur():
    html = "a@mail.exemple.fr b@pasexemple.fr c@exemple.fr.evil.com"
    assert cs.extraire_coordonnees(html, "exemple.fr")["emails"] == ["a@mail.exemple.fr"]


def test_faux_positifs_ecartes():
    html = ("logo@2x.png photo@exemple.fr.jpg x@exemple.fr.svg "
            "a@o1.sentry.exemple.fr b@wixpress.exemple.fr c@example.com email@domain name@ vrai@exemple.fr")
    assert cs.extraire_coordonnees(html, "exemple.fr")["emails"] == ["vrai@exemple.fr"]


def test_obfuscations_simples():
    html = "contact [at] exemple [dot] fr et info(at)exemple.fr"
    assert cs.extraire_coordonnees(html, "exemple.fr")["emails"] == ["contact@exemple.fr", "info@exemple.fr"]


def test_script_et_style_ignores():
    html = ("<script>var m='cache@exemple.fr'; var t='01 23 45 67 89'</script>"
            "<style>.a{content:'autre@exemple.fr'}</style><p>visible@exemple.fr</p>")
    r = cs.extraire_coordonnees(html, "exemple.fr")
    assert r["emails"] == ["visible@exemple.fr"]
    assert r["telephones"] == []


@pytest.mark.parametrize("texte", [
    "+33 1 23 45 67 89", "+33 (0)1 23 45 67 89", "0033 1 23 45 67 89",
    "01 23 45 67 89", "01.23.45.67.89", "01-23-45-67-89", "0123456789",
    "+33123456789",
])
def test_telephones_formats(texte):
    assert cs.extraire_coordonnees(f"<p>Tel : {texte}</p>", "exemple.fr")["telephones"] == ["+33 1 23 45 67 89"]


def test_telephone_tel_href():
    r = cs.extraire_coordonnees('<a href="tel:+33145678901">appeler</a>', "exemple.fr")
    assert r["telephones"] == ["+33 1 45 67 89 01"]
    r = cs.extraire_coordonnees('<a href="tel:+32 2 123 45 67">x</a>', "exemple.fr")
    assert r["telephones"] == ["+32 2 123 45 67"]


def test_telephone_faux_positifs():
    html = ("SIRET 12345678901234 SIREN 123456789 date 2026-10-15 prix 1234567890123 "
            "00 12 34 56 78 numero 0023456789")
    assert cs.extraire_coordonnees(html, "exemple.fr")["telephones"] == []


def test_doublons_ordre_et_plafond():
    html = ("<p>01 23 45 67 89 / 01.23.45.67.89 / 02 11 22 33 44 / 03 11 22 33 44 / 04 11 22 33 44</p>"
            "a@exemple.fr b@exemple.fr a@exemple.fr c@exemple.fr d@exemple.fr")
    r = cs.extraire_coordonnees(html, "exemple.fr")
    assert r["telephones"] == ["+33 1 23 45 67 89", "+33 2 11 22 33 44", "+33 3 11 22 33 44"]
    assert r["emails"] == ["a@exemple.fr", "b@exemple.fr", "c@exemple.fr"]


def _transport(pages, appels=None):
    def t(url, delai):
        if appels is not None:
            appels.append(url)
        if url not in pages:
            raise OSError("404")
        v = pages[url]
        return v if isinstance(v, tuple) else (url, v.encode())
    return t


def test_lire_site_arret_des_que_email_et_telephone():
    appels = []
    pages = {
        "https://exemple.fr": "<p>info@exemple.fr</p>",
        "https://exemple.fr/contact": "<p>01 23 45 67 89</p>",
        "https://exemple.fr/nous-contacter": "<p>autre@exemple.fr</p>",
    }
    r = cs.lire_site("https://exemple.fr", transport=_transport(pages, appels))
    assert r["emails"] == ["info@exemple.fr"] and r["telephones"] == ["+33 1 23 45 67 89"]
    assert r["pages_lues"] == ["https://exemple.fr", "https://exemple.fr/contact"]
    assert "https://exemple.fr/nous-contacter" not in appels


def test_lire_site_page_en_erreur_sautee():
    pages = {"https://exemple.fr": "rien", "https://exemple.fr/contactez-nous": "x@exemple.fr 0123456789"}
    r = cs.lire_site("https://exemple.fr", transport=_transport(pages))
    assert r["emails"] == ["x@exemple.fr"]
    assert r["pages_lues"] == ["https://exemple.fr", "https://exemple.fr/contactez-nous"]


def test_lire_site_quatre_pages_au_plus():
    appels = []
    pages = {u: "vide" for u in cs.pages_a_lire("https://exemple.fr")}
    r = cs.lire_site("https://exemple.fr", transport=_transport(pages, appels))
    assert len(r["pages_lues"]) == 4 and len(appels) == 4
    assert r["emails"] == [] and r["telephones"] == []


def test_lire_site_tout_en_erreur():
    with pytest.raises(cs.SiteInjoignable):
        cs.lire_site("https://exemple.fr", transport=_transport({}))


@pytest.mark.parametrize("site", [None, "", "ftp://exemple.fr"])
def test_lire_site_sans_site_valide(site):
    with pytest.raises(cs.SiteInjoignable):
        cs.lire_site(site, transport=_transport({}))


def test_redirection_vers_autre_domaine_garde_le_domaine_linkedin():
    pages = {"https://exemple.fr": ("https://autre.com/", b"info@autre.com info@exemple.fr")}
    r = cs.lire_site("https://exemple.fr", transport=_transport(pages))
    assert r["emails"] == ["info@exemple.fr"]


class _FausseReponse(io.BytesIO):
    def __init__(self, donnees, url, charset=None):
        super().__init__(donnees)
        self._url = url
        self.headers = type("H", (), {"get_content_charset": lambda s: charset})()

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def test_transport_par_defaut_plafonne_et_signe(monkeypatch):
    vu = {}

    def faux_urlopen(requete, timeout=None):
        vu["ua"] = requete.get_header("User-agent")
        vu["timeout"] = timeout
        return _FausseReponse(b"a" * 1000 + b"\xe9", "https://exemple.fr/final")

    monkeypatch.setattr(urllib.request, "urlopen", faux_urlopen)
    url, brut = cs._transport_http("https://exemple.fr", 3.0, taille_max=100)
    assert url == "https://exemple.fr/final"
    assert len(brut) == 100
    # Un navigateur courant, pas « We.Reach » : beaucoup de sites répondent 403 à ce dernier.
    assert vu == {"ua": cs.USER_AGENT_NAVIGATEUR, "timeout": 3.0}
    assert cs.USER_AGENT_NAVIGATEUR.startswith("Mozilla/5.0") and "Chrome/" in cs.USER_AGENT_NAVIGATEUR


def test_lire_site_avec_transport_par_defaut(monkeypatch):
    def faux_urlopen(requete, timeout=None):
        return _FausseReponse("<p>contact@exemple.fr 01 23 45 67 89 é</p>".encode("utf-8"), requete.full_url)

    monkeypatch.setattr(urllib.request, "urlopen", faux_urlopen)
    r = cs.lire_site("https://exemple.fr")
    assert r["emails"] == ["contact@exemple.fr"] and r["telephones"] == ["+33 1 23 45 67 89"]


def test_tel_seulement_dans_href_et_sans_debris():
    html = "<p>Tel: +33 1 23 45 67 89 \u2014 Fax: +33 1 98 76 54 32</p>"
    r = cs.extraire_coordonnees(html, "exemple.fr")
    assert r["telephones"] == ["+33 1 23 45 67 89", "+33 1 98 76 54 32"]
    r = cs.extraire_coordonnees("<p>Hotel: +33 1 23 45 67 89</p>", "exemple.fr")
    assert r["telephones"] == ["+33 1 23 45 67 89"]
    r = cs.extraire_coordonnees("<p>Tel: +41 22 123 45 67</p>", "exemple.fr")
    assert r["telephones"] == []


def test_tel_href_etranger_borne():
    assert cs.extraire_coordonnees("<a href='tel:+44 (0)20 7946 0958'>x</a>", "e.fr")["telephones"] == ["+44 20 7946 0958"]
    assert cs.extraire_coordonnees('<a href="tel:+41 22 123 45 67">x</a>', "e.fr")["telephones"] == ["+41 22 123 45 67"]
    assert cs.extraire_coordonnees('<a href="tel:+12">x</a>', "e.fr")["telephones"] == []
    assert cs.extraire_coordonnees('<a href="tel:+1234567890123456789">x</a>', "e.fr")["telephones"] == []
    assert cs.extraire_coordonnees('<a href=tel:0123456789>x</a>', "e.fr")["telephones"] == ["+33 1 23 45 67 89"]


def test_regex_email_bornee_pas_quadratique():
    import time
    t = time.perf_counter()
    r = cs.extraire_coordonnees("a" * 100_000 + " " + "a." * 50_000 + "@", "exemple.fr")
    assert time.perf_counter() - t < 1
    assert r["emails"] == []


def test_partie_locale_trop_longue_refusee():
    assert cs.extraire_coordonnees("a" * 70 + "@exemple.fr", "exemple.fr")["emails"] == []


def test_telephone_ignore_hors_domaine_final():
    pages = {"https://exemple.fr": ("https://autre.com/", b"info@exemple.fr 01 23 45 67 89")}
    r = cs.lire_site("https://exemple.fr", transport=_transport(pages))
    assert r["emails"] == ["info@exemple.fr"] and r["telephones"] == []
    pages = {"https://exemple.fr": ("https://www.exemple.fr/fr", b"01 23 45 67 89")}
    assert cs.lire_site("https://exemple.fr", transport=_transport(pages))["telephones"] == ["+33 1 23 45 67 89"]


def test_telephone_dans_un_credit_ignore():
    html = ("<footer><p>Site réalisé par Webcom 04 11 22 33 44</p>"
            "<p>Standard 01 23 45 67 89</p><p>Agence Pixel : 05 11 22 33 44</p></footer>")
    assert cs.extraire_coordonnees(html, "exemple.fr")["telephones"] == ["+33 1 23 45 67 89"]
    html = "<p>Développé par Pixel</p><p>01 23 45 67 89</p>"
    assert cs.extraire_coordonnees(html, "exemple.fr")["telephones"] == ["+33 1 23 45 67 89"]


@pytest.mark.parametrize("site", [
    "https://www.facebook.com/exemple", "https://fr.linkedin.com/company/x", "https://instagram.com/x",
    "https://x.com/exemple", "https://linktr.ee/exemple", "https://sites.google.com/view/x",
    "https://exemple.wixsite.com/site", "https://exemple.business.site", "https://youtube.com/@x",
])
def test_plateformes_refusees(site):
    assert cs.domaine_de(site) is None
    with pytest.raises(cs.SiteInjoignable, match="réseau social"):
        cs.lire_site(site, transport=_transport({}))


def test_domaine_au_nom_proche_d_une_plateforme_accepte():
    assert cs.domaine_de("https://monfacebook.com") == "monfacebook.com"


def test_domaine_sentry_conseil_garde():
    assert cs.extraire_coordonnees("contact@sentry-conseil.fr", "sentry-conseil.fr")["emails"] == ["contact@sentry-conseil.fr"]


def test_plafond_de_requetes_erreurs_comprises():
    appels = []
    with pytest.raises(cs.SiteInjoignable):
        cs.lire_site("https://exemple.fr", transport=_transport({}, appels))
    assert len(appels) == cs.MAX_REQUETES == 6


def test_script_non_ferme_coupe_jusqu_a_la_fin():
    html = "<p>vrai@exemple.fr</p><script>var a = 'cache@exemple.fr'; 01 23 45 67 89"
    r = cs.extraire_coordonnees(html, "exemple.fr")
    assert r["emails"] == ["vrai@exemple.fr"] and r["telephones"] == []


@pytest.mark.parametrize("texte", ["0800 123 456", "0 800 123 456", "0800.123.456", "08 00 12 34 56"])
def test_numero_vert(texte):
    assert cs.extraire_coordonnees(f"<p>{texte}</p>", "exemple.fr")["telephones"] == ["+33 8 00 12 34 56"]


def test_emails_generiques_d_abord():
    html = "jean.dupont@exemple.fr marie@exemple.fr contact@exemple.fr rh@exemple.fr"
    assert cs.extraire_coordonnees(html, "exemple.fr")["emails"] == [
        "contact@exemple.fr", "rh@exemple.fr", "jean.dupont@exemple.fr"]


@pytest.mark.parametrize("site", ["http://localhost/", "http://127.0.0.1", "http://192.168.1.10/x",
                                  "http://169.254.169.254/", "http://0.0.0.0", "http://10.0.0.5", "http://intranet/"])
def test_hotes_locaux_refuses(site):
    assert cs.domaine_de(site) is None
    with pytest.raises(cs.SiteInjoignable):
        cs.lire_site(site, transport=_transport({}))


def test_un_refus_durable_est_distingue_d_une_panne():
    from utils.coordonnees_site import motif_inutilisable
    assert motif_inutilisable("https://www.facebook.com/orbique") == "le site indiqué est une page de réseau social"
    assert motif_inutilisable("http://192.168.1.10/") == "adresse IP privée ou locale refusée"
    assert motif_inutilisable("ftp://orbique.example") == "pas d'adresse de site http(s)"
    assert motif_inutilisable("www.orbique.example") == ""
