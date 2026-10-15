# -*- coding: utf-8 -*-
"""Règles de la veille : ce qu'on cherche, comment on classe, ce qu'on lit.

Tout ici décide sans navigateur ni réseau. Une erreur dans ces règles se
paie en pages LinkedIn gaspillées ou en contacts mal rangés.
"""

import pytest

from utils.veille_regles import (
    FAMILLES, PAGES_PAR_JOUR_DEFAUT, ReglagesVeille, charger_reglages,
    expression_mots_cles, famille_de_l_intitule, fiche_depuis_apropos,
    ordre_du_lot, sauver_reglages, signature_familles, url_recherche_personnes,
)


def test_les_trois_familles_existent():
    assert set(FAMILLES) == {"Product", "Data", "IA"}


def test_l_expression_n_est_pas_entierement_parenthesee():
    # LinkedIn renvoie 0 résultat pour « ("a" OR "b") » : constaté en 2026.
    expr = expression_mots_cles(["Product"], [])
    assert not (expr.startswith("(") and expr.endswith(")"))
    assert '"product manager"' in expr.lower()
    assert " OR " in expr


def test_l_expression_combine_familles_et_intitules_libres_sans_doublon():
    expr = expression_mots_cles(["Product", "Data"], ["Product Manager", "Growth Lead"])
    termes = [t.strip().strip('"').lower() for t in expr.split(" OR ")]
    assert "growth lead" in termes
    assert "data scientist" in termes
    assert termes.count("product manager") == 1


def test_une_expression_vide_leve():
    with pytest.raises(ValueError):
        expression_mots_cles([], [])


def test_l_url_de_recherche_filtre_sur_l_entreprise_et_pagine():
    url = url_recherche_personnes("4998677", '"a" OR "b"', 2)
    assert url.startswith("https://www.linkedin.com/search/results/people/?")
    assert "currentCompany=%5B%224998677%22%5D" in url
    assert "page=2" in url
    assert "keywords=" in url


def test_l_url_refuse_un_identifiant_vide_ou_non_numerique():
    # Sans filtre entreprise, la recherche renverrait tout LinkedIn.
    for mauvais in ("", None, "thiga", "12a"):
        with pytest.raises(ValueError):
            url_recherche_personnes(mauvais, '"a"', 1)


@pytest.mark.parametrize("intitule,famille", [
    ("Senior Product Manager @Acme", "Product"),
    ("Head of Data & Analytics", "Data"),
    ("Machine Learning Engineer", "IA"),
    ("Responsable IA générative", "IA"),
    ("Directeur commercial", "Autre"),
])
def test_un_intitule_est_range_dans_sa_famille(intitule, famille):
    assert famille_de_l_intitule(intitule, ["Product", "Data", "IA"], []) == famille


def test_une_famille_non_cochee_n_est_pas_attribuee():
    assert famille_de_l_intitule("Data Scientist", ["Product"], []) == "Autre"


def test_un_intitule_libre_range_dans_sa_propre_categorie():
    assert famille_de_l_intitule("Growth Lead Europe", ["Product"], ["Growth Lead"]) == "Growth Lead"


def test_la_signature_change_quand_les_familles_changent():
    assert signature_familles(["Product"], []) != signature_familles(["Product", "Data"], [])
    assert signature_familles(["Data", "Product"], []) == signature_familles(["Product", "Data"], [])


def test_la_fiche_se_lit_dans_les_champs_a_propos():
    champs = {
        "Site web": ["https://www.exemple.co"],
        "Téléphone": ["+33 1 00 00 00 00", "Le numéro de téléphone est le +33 1 00 00 00 00"],
        "Secteur": ["Services et conseil aux entreprises"],
        "Taille de l’entreprise": ["201-500 employés", "198 membres associés"],
        "Siège social": ["Paris, Paris"],
        "Fondée en": ["2014"],
        "Spécialisations": ["Product Management, Discovery"],
        "Page vérifiée": ["1 juin 2024"],
    }
    assert fiche_depuis_apropos(champs) == {
        "site": "https://www.exemple.co",
        "telephone": "+33 1 00 00 00 00",
        "secteur": "Services et conseil aux entreprises",
        "taille": "201-500 employés",
        "membres": "198",
        "siege": "Paris, Paris",
        "fondee": "2014",
        "specialisations": "Product Management, Discovery",
    }


def test_l_apostrophe_droite_est_aussi_reconnue():
    assert fiche_depuis_apropos({"Taille de l'entreprise": ["11-50 employés"]}) == {
        "taille": "11-50 employés"
    }


def test_des_champs_vides_donnent_une_fiche_vide():
    assert fiche_depuis_apropos({}) == {}


def test_les_reglages_par_defaut(tmp_path):
    r = charger_reglages(tmp_path)
    assert r.familles == ["Product", "Data", "IA"]
    assert r.intitules_libres == []
    assert r.pages_par_jour == PAGES_PAR_JOUR_DEFAUT == 20


def test_les_reglages_survivent_a_un_aller_retour(tmp_path):
    sauver_reglages(tmp_path, ReglagesVeille(["Data"], ["Growth Lead"], 12))
    assert charger_reglages(tmp_path) == ReglagesVeille(["Data"], ["Growth Lead"], 12)


def test_un_budget_hors_bornes_est_ramene_dans_les_bornes(tmp_path):
    sauver_reglages(tmp_path, ReglagesVeille(["Data"], [], 500))
    assert charger_reglages(tmp_path).pages_par_jour == 40


def test_un_fichier_de_reglages_corrompu_donne_les_defauts(tmp_path):
    (tmp_path / "reglages_veille.json").write_text("{pas du json", encoding="utf-8")
    assert charger_reglages(tmp_path).pages_par_jour == 20


def test_le_lot_commence_par_les_jamais_passees_puis_les_plus_anciennes():
    entreprises = [
        {"id": 1, "etat": "identifiee", "url_linkedin": "u", "derniere_veille": "2026-10-10"},
        {"id": 2, "etat": "a_identifier", "url_linkedin": None, "derniere_veille": None},
        {"id": 3, "etat": "identifiee", "url_linkedin": "u", "derniere_veille": "2026-10-01"},
        {"id": 4, "etat": "non_identifiee", "url_linkedin": None, "derniere_veille": "2026-09-01"},
    ]
    assert [e["id"] for e in ordre_du_lot(entreprises)] == [2, 3, 1]


def test_une_entreprise_non_identifiee_avec_un_lien_colle_revient_dans_le_lot():
    entreprises = [{"id": 4, "etat": "non_identifiee", "url_linkedin": "https://www.linkedin.com/company/x/", "derniere_veille": None}]
    assert [e["id"] for e in ordre_du_lot(entreprises)] == [4]


# --- En-tête « en un coup d'œil » ------------------------------------------

from utils.veille_regles import resume_fiche

FICHE = {
    "linkedin.taille": {"valeur": "201-500 employés"}, "linkedin.secteur": {"valeur": "Conseil"},
    "linkedin.siege": {"valeur": "Paris, Paris"}, "annuaire.effectif": {"valeur": "100 à 199 salariés (2024)"},
}
CONTACTS = [{"famille": "Product", "decouvert_le": "2026-10-01"}, {"famille": "Data", "decouvert_le": "2026-10-15T08:00:00"},
            {"famille": "Autre", "decouvert_le": "2026-10-15T08:00:00"}]
ACTUS = [{"categorie": "Rachat / fusion", "titre": "Orbique rachète Zéphyr", "publie_le": "2026-08-31"},
         {"categorie": "Nomination", "titre": "Orbique nomme une DG", "publie_le": "2026-06-01"}]


def test_l_en_tete_resume_la_fiche_en_une_ligne():
    assert resume_fiche(FICHE, CONTACTS, ACTUS, "2026-10-10") == (
        "201-500 employés · Conseil · Paris · 100 à 199 salariés (2024) · "
        "📰 Rachat / fusion : Orbique rachète Zéphyr (31/08/2026) · "
        "2 contacts Product/Data/IA, dont 1 nouveau"
    )


def test_l_en_tete_d_une_fiche_vide():
    assert resume_fiche({}, [], [], None) == "Fiche pas encore remplie · aucune actualité · aucun contact Product/Data/IA"
