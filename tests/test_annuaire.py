# -*- coding: utf-8 -*-
"""Annuaire officiel : interrogé, puis recoupé avec LinkedIn — jamais seul.

La recherche « thiga » renvoie 14 sociétés dont une exploitation agricole
des Ardennes : sans recoupement, la fiche d'un cabinet de conseil parisien
afficherait les gérants d'une ferme. Données inventées ci-dessous, même
structure que les vraies réponses.
"""

import json

import pytest

from utils.annuaire import (
    AnnuaireIndisponible, choisir_candidat, commune_du_siege_linkedin,
    fiche_depuis_annuaire, interroger, normaliser_nom,
)


def societe(siren, nom, commune, etat="A", dirigeants=None, **autres):
    base = {
        "siren": siren, "nom_complet": nom, "nom_raison_sociale": nom, "sigle": None,
        "activite_principale": "70.22Z", "tranche_effectif_salarie": "22",
        "annee_tranche_effectif_salarie": "2024", "date_creation": "2014-04-28",
        "etat_administratif": etat, "categorie_entreprise": "PME",
        "siege": {"libelle_commune": commune, "code_postal": "75009"},
        "dirigeants": dirigeants or [],
    }
    base.update(autres)
    return base


HOMONYMES = [
    societe("111111111", "ORBIQUE", "CORNY-MACHEROMENIL"),
    societe("222222222", "ORBIQUE", "MARENNES-HIERS-BROUAGE"),
    societe("333333333", "ORBIQUE", "PARIS"),
    societe("444444444", "ORBIQUE IMMOBILIER", "PARIS"),
]


def test_la_commune_du_siege_linkedin():
    assert commune_du_siege_linkedin("Paris, Paris") == "PARIS"
    assert commune_du_siege_linkedin("Saint-Étienne, Auvergne-Rhône-Alpes") == "SAINT-ETIENNE"
    assert commune_du_siege_linkedin("") == ""


def test_le_nom_est_normalise_sans_forme_juridique():
    assert normaliser_nom("Orbique SAS") == normaliser_nom("ORBIQUE") == "ORBIQUE"
    assert normaliser_nom("Café & Cie S.A.") == "CAFE & CIE"


def test_l_homonyme_est_leve_par_la_commune():
    candidat, motif = choisir_candidat(HOMONYMES, "Orbique", "Paris, Paris")
    assert candidat["siren"] == "333333333"
    assert motif == ""


def test_un_nom_qui_ne_fait_que_commencer_pareil_n_est_pas_retenu():
    candidat, _ = choisir_candidat([HOMONYMES[3]], "Orbique", "Paris, Paris")
    assert candidat is None


def test_aucune_commune_compatible():
    candidat, motif = choisir_candidat(HOMONYMES[:2], "Orbique", "Lyon, Auvergne-Rhône-Alpes")
    assert candidat is None and "aucune" in motif


def test_plusieurs_candidats_compatibles():
    doublon = HOMONYMES + [societe("555555555", "ORBIQUE", "PARIS")]
    candidat, motif = choisir_candidat(doublon, "Orbique", "Paris, Paris")
    assert candidat is None and "plusieurs" in motif


def test_sans_siege_linkedin_on_ne_devine_pas():
    candidat, motif = choisir_candidat(HOMONYMES, "Orbique", "")
    assert candidat is None and "siège" in motif


def test_une_societe_cessee_est_ignoree():
    candidat, _ = choisir_candidat([societe("333333333", "ORBIQUE", "PARIS", etat="C")], "Orbique", "Paris, Paris")
    assert candidat is None


def test_un_arrondissement_ne_bloque_pas_le_recoupement():
    candidat, _ = choisir_candidat([societe("666666666", "ORBIQUE", "LYON 3EME")], "Orbique", "Lyon, Auvergne-Rhône-Alpes")
    assert candidat["siren"] == "666666666"


def test_la_fiche_annuaire():
    dirigeants = [
        {"type_dirigeant": "personne physique", "nom": "EXEMPLE", "prenoms": "Jeanne", "qualite": "Présidente"},
        {"type_dirigeant": "personne morale", "denomination": "HOLDING FICTIVE", "siren": "999999999", "qualite": "Président de SAS"},
        {"type_dirigeant": "personne morale", "denomination": "CABINET AUDIT", "siren": "888888888", "qualite": "Commissaire aux comptes titulaire"},
    ]
    fiche = fiche_depuis_annuaire(societe("333333333", "ORBIQUE", "PARIS", dirigeants=dirigeants))
    assert fiche == {
        "siren": "333333333",
        "activite": "70.22Z",
        "effectif": "100 à 199 salariés (2024)",
        "creation": "2014-04-28",
        "categorie": "PME",
        "commune": "PARIS",
        "dirigeants": "Jeanne EXEMPLE (Présidente) ; HOLDING FICTIVE (Président de SAS)",
    }


def test_une_tranche_inconnue_ou_non_employeuse():
    assert fiche_depuis_annuaire(societe("1", "X", "PARIS", tranche_effectif_salarie="NN"))["effectif"] == "non employeuse ou non renseignée"


def test_interroger_lit_les_resultats():
    def transport(url, delai):
        assert url.startswith("https://recherche-entreprises.api.gouv.fr/search?")
        assert "q=Orbique" in url and "per_page=25" in url
        return json.dumps({"results": HOMONYMES, "total_results": 4}).encode()
    assert [r["siren"] for r in interroger("Orbique", transport=transport)] == [
        "111111111", "222222222", "333333333", "444444444"
    ]


@pytest.mark.parametrize("panne", [OSError("réseau"), ValueError("pas du json")])
def test_une_panne_de_l_annuaire_est_signalee(panne):
    def transport(url, delai):
        raise panne
    with pytest.raises(AnnuaireIndisponible):
        interroger("Orbique", transport=transport)


def test_un_json_illisible_est_signale():
    with pytest.raises(AnnuaireIndisponible):
        interroger("Orbique", transport=lambda url, delai: b"<html>")
