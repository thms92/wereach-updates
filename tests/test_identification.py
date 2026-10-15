# -*- coding: utf-8 -*-
"""Choisir l'entreprise suivie parmi les cartes de la recherche LinkedIn.

Noms inventés. La vraie page « BNP Paribas » liste la maison mère au milieu
de ses filiales : seul un nom exactement identique est retenu, sinon on
demande le lien plutôt que de deviner.
"""

from utils.identification import choisir_entreprise, url_recherche_entreprises


def carte(nom, slug):
    return {"nom": nom, "url": f"https://www.linkedin.com/company/{slug}/"}


FILIALES = [
    carte("Orbique Assurances", "orbique-assurances"),
    carte("Orbique", "orbique"),
    carte("Groupe Orbique Leasing", "orbique-leasing"),
    carte("Orbique Immobilier", "orbique-immobilier"),
]


def test_le_nom_exact_est_retenu_parmi_les_filiales():
    assert choisir_entreprise(FILIALES, "Orbique") == ("https://www.linkedin.com/company/orbique/", "")


def test_casse_accents_et_forme_juridique_ne_comptent_pas():
    url, motif = choisir_entreprise([carte("ORBIQUE", "orbique"), carte("Orbique Studio", "orbique-studio")],
                                    "Orbiqué SAS")
    assert url == "https://www.linkedin.com/company/orbique/" and motif == ""


def test_deux_cartes_au_meme_lien_comptent_une_fois():
    url, _ = choisir_entreprise([carte("Orbique", "orbique"), carte("Orbique", "orbique")], "Orbique")
    assert url == "https://www.linkedin.com/company/orbique/"


def test_deux_entreprises_au_meme_nom_exact_ne_sont_pas_departagees():
    url, motif = choisir_entreprise([carte("Orbique", "orbique"), carte("Orbique", "orbique-fr")], "Orbique")
    assert url is None
    assert motif == "plusieurs entreprises « Orbique » sur LinkedIn : collez le lien de la bonne"


def test_aucun_nom_exact_cite_trois_propositions_au_plus():
    url, motif = choisir_entreprise([c for c in FILIALES if c["nom"] != "Orbique"]
                                    + [carte("Orbique Conseil", "orbique-conseil")], "Orbique")
    assert url is None
    assert motif == ("aucune entreprise « Orbique » sur LinkedIn "
                     "(proposées : Orbique Assurances, Groupe Orbique Leasing, Orbique Immobilier) "
                     "— collez le lien de sa page entreprise")


def test_un_nom_avec_une_virgule_reste_entier_dans_les_propositions():
    _, motif = choisir_entreprise([carte("Orbique, Conseil & Cie", "oc"), carte("Zorbique", "z"),
                                   carte("Morbique", "m"), carte("Corbique", "c")], "Orbique")
    assert "(proposées : Orbique, Conseil & Cie, Zorbique, Morbique)" in motif


def test_aucune_carte():
    assert choisir_entreprise([], "Orbique") == (
        None, "aucune entreprise « Orbique » sur LinkedIn (proposées : aucune) — collez le lien de sa page entreprise")


def test_un_nom_suivi_vide_ne_retient_rien():
    url, _ = choisir_entreprise([carte("", "orbique")], "")
    assert url is None


def test_l_adresse_de_recherche_encode_le_nom():
    assert url_recherche_entreprises("L’Orbique & Cie") == (
        "https://www.linkedin.com/search/results/companies/?keywords=L%E2%80%99Orbique+%26+Cie")
