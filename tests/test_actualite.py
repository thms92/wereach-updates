# -*- coding: utf-8 -*-
"""Actualité d'une entreprise par Google News : rachat, licenciements, levée.

Constaté le 2026-10-15 : un nom seul ramène des homonymes ; avec les mots des
événements et une fenêtre d'un an, les vrais signaux sortent (« Decathlon » →
rachat de 50 % de Sport 2000). Flux inventé ci-dessous, même structure RSS.
"""

import urllib.parse

import pytest

from utils.actualite import (
    ActualiteIndisponible, categorie_du_titre, interroger, lire_flux, url_flux,
)


def item(titre, source="Les Échos", date="Mon, 31 Aug 2026 07:00:00 GMT", lien="https://news.example/a"):
    return (f"<item><title>{titre} - {source}</title><link>{lien}</link>"
            f"<pubDate>{date}</pubDate><source url=\"https://x\">{source}</source></item>")


def flux(*items):
    return ("<?xml version=\"1.0\" encoding=\"UTF-8\"?><rss version=\"2.0\"><channel><title>G</title>"
            + "".join(items) + "</channel></rss>").encode("utf-8")


def test_l_url_ne_demande_que_les_evenements_de_l_annee():
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url_flux("Orbique")).query)
    assert url_flux("Orbique").startswith("https://news.google.com/rss/search?")
    assert q["q"][0].startswith('"Orbique" (') and q["q"][0].endswith(") when:1y")
    assert "licenciement" in q["q"][0] and '"plan social"' in q["q"][0]
    assert q["hl"] == ["fr"] and q["gl"] == ["FR"]


@pytest.mark.parametrize("titre,categorie", [
    ("Orbique rachète 50 % de Zéphyr", "Rachat / fusion"),
    ("Zéphyr annonce l'acquisition d'Orbique", "Rachat / fusion"),
    ("Orbique prépare un plan social", "Licenciements / restructuration"),
    ("Orbique : 200 suppressions de postes", "Licenciements / restructuration"),
    ("Orbique lève 12 millions d'euros", "Levée de fonds"),
    ("Orbique nomme une nouvelle directrice générale", "Nomination"),
    ("Orbique ouvre un magasin à Lyon", None),
])
def test_la_categorie_d_un_titre(titre, categorie):
    assert categorie_du_titre(titre) == categorie


def test_le_flux_est_lu_trie_et_nettoye():
    articles = lire_flux(flux(
        item("Orbique lève 12 M€", source="Maddyness", date="Mon, 01 Jun 2026 07:00:00 GMT", lien="https://n/1"),
        item("Orbique rachète Zéphyr", source="Les Échos", date="Mon, 31 Aug 2026 07:00:00 GMT", lien="https://n/2"),
    ), "Orbique")
    assert articles == [
        {"titre": "Orbique rachète Zéphyr", "lien": "https://n/2", "source": "Les Échos",
         "publie_le": "2026-08-31", "categorie": "Rachat / fusion"},
        {"titre": "Orbique lève 12 M€", "lien": "https://n/1", "source": "Maddyness",
         "publie_le": "2026-06-01", "categorie": "Levée de fonds"},
    ]


def test_un_titre_sans_le_nom_de_l_entreprise_est_ecarte():
    # Le cas « Thiga » : la requête ramène des homonymes et des articles voisins.
    assert lire_flux(flux(item("Thi*ga : un chanteur lève les foules")), "Thiga") == []


def test_le_nom_doit_etre_un_mot_entier():
    assert lire_flux(flux(item("Orbiquement parlant, la fusion avance")), "Orbique") == []


def test_le_nom_est_reconnu_sans_tenir_compte_des_accents_ni_de_la_casse():
    assert len(lire_flux(flux(item("ÉLAN rachète un concurrent")), "Élan")) == 1


def test_un_titre_sans_evenement_est_ecarte():
    assert lire_flux(flux(item("Orbique ouvre un magasin")), "Orbique") == []


def test_les_doublons_de_titre_sont_fusionnes():
    a = item("Orbique rachète Zéphyr", source="Les Échos", lien="https://n/1")
    b = item("Orbique rachète Zéphyr", source="Les Échos", lien="https://n/2")
    assert len(lire_flux(flux(a, b), "Orbique")) == 1


def test_un_flux_vide_ne_rend_rien():
    assert lire_flux(flux(), "Orbique") == []


def test_interroger_et_ses_pannes():
    assert interroger("Orbique", transport=lambda url, delai: flux(item("Orbique rachète Zéphyr")))[0]["categorie"] == "Rachat / fusion"
    with pytest.raises(ActualiteIndisponible):
        interroger("Orbique", transport=lambda url, delai: (_ for _ in ()).throw(OSError("réseau")))
    with pytest.raises(ActualiteIndisponible):
        interroger("Orbique", transport=lambda url, delai: b"<html>pas du rss")


# --- Correctifs du premier tour de relecture ---------------------------------

@pytest.mark.parametrize("titre,categorie", [
    ("Decathlon : 200 licenciements à Lille", "Licenciements / restructuration"),
    ("Marie Dupont nommée directrice générale de Thiga", "Nomination"),
    ("La levée de 5 M€ de Thiga", "Levée de fonds"),
    ("Thiga fusionne avec Y", "Rachat / fusion"),
    ("Restructurations chez Thiga", "Licenciements / restructuration"),
    ("Thiga acquisitions", "Rachat / fusion"),
    ("Thiga s'offre la start-up X", "Rachat / fusion"),
    ("Thiga met la main sur X", "Rachat / fusion"),
    ("Thiga se sépare de 50 salariés", "Licenciements / restructuration"),
    ("Nomination d'un nouveau CTO chez Thiga", "Nomination"),
    ("Thiga s’offre la start-up X", "Rachat / fusion"),   # apostrophe typographique
    # Faux positifs écartés : débuts de mots volontairement bornés.
    ("L'élève de Thiga", None),
    ("Le cèdre de Thiga", None),
    ("Thiga acquitté en appel", None),
])
def test_le_francais_courant_est_classe(titre, categorie):
    assert categorie_du_titre(titre) == categorie


def test_l_apostrophe_typographique_n_empeche_pas_de_reconnaitre_le_nom():
    xml = (b"<rss><channel><item><title>L\xe2\x80\x99Or\xc3\xa9al rach\xc3\xa8te Aesop</title>"
           b"<link>u</link></item></channel></rss>")
    assert len(lire_flux(xml, "L'Or\u00e9al")) == 1
