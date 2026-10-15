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
            "sentry@exemple.fr wixpress@exemple.fr email@domain name@ vrai@exemple.fr")
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


@pytest.mark.parametrize("site", [None, "", "ftp://exemple.fr", "exemple.fr"])
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
    assert vu == {"ua": "We.Reach", "timeout": 3.0}


def test_lire_site_avec_transport_par_defaut(monkeypatch):
    def faux_urlopen(requete, timeout=None):
        return _FausseReponse("<p>contact@exemple.fr 01 23 45 67 89 é</p>".encode("utf-8"), requete.full_url)

    monkeypatch.setattr(urllib.request, "urlopen", faux_urlopen)
    r = cs.lire_site("https://exemple.fr")
    assert r["emails"] == ["contact@exemple.fr"] and r["telephones"] == ["+33 1 23 45 67 89"]
