# -*- coding: utf-8 -*-
"""Adressage du panneau « Plus de profils pour vous » et filtrage de son contenu.

Tout ce qui est testé ici décide sans navigateur : c'est la couche où les
erreurs se paient en doublons dans le fichier et en profils écartés à tort.
"""

from utils.browsemap import (
    CHEMIN_PANNEAU,
    normaliser_url,
    url_panneau,
    vanity_depuis_url,
)

URL_SIMPLE = "https://www.linkedin.com/in/jean-dupont-12345/"


def test_le_vanity_est_extrait_d_une_url_simple():
    assert vanity_depuis_url(URL_SIMPLE) == "jean-dupont-12345"


def test_les_parametres_de_suivi_sont_ignores():
    # LinkedIn sert ses liens ainsi depuis le panneau : sans ça, la même
    # personne entre deux fois au fichier.
    url = URL_SIMPLE + "?miniProfileUrn=urn%3Ali%3Afsd_profile%3AACoAAA"
    assert vanity_depuis_url(url) == "jean-dupont-12345"


def test_un_sous_chemin_de_profil_est_ignore():
    url = "https://www.linkedin.com/in/jean-dupont-12345/details/experience/"
    assert vanity_depuis_url(url) == "jean-dupont-12345"


def test_la_casse_du_vanity_est_normalisee():
    assert vanity_depuis_url("https://www.linkedin.com/in/Jean-Dupont/") == "jean-dupont"


def test_une_page_entreprise_n_est_pas_un_profil():
    assert vanity_depuis_url("https://www.linkedin.com/company/thiga/") is None


def test_une_saisie_vide_n_est_pas_un_profil():
    assert vanity_depuis_url("") is None
    assert vanity_depuis_url(None) is None


def test_deux_liens_vers_la_meme_personne_donnent_la_meme_url():
    autre = "http://linkedin.com/in/JEAN-DUPONT-12345?trk=public_profile"
    assert normaliser_url(autre) == normaliser_url(URL_SIMPLE) == URL_SIMPLE


def test_l_url_du_panneau_se_construit_depuis_celle_du_profil():
    assert url_panneau(URL_SIMPLE) == URL_SIMPLE + CHEMIN_PANNEAU


def test_l_url_du_panneau_est_nulle_si_ce_n_est_pas_un_profil():
    assert url_panneau("https://www.linkedin.com/company/thiga/") is None
