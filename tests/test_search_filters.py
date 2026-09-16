# -*- coding: utf-8 -*-
"""Assemblage de la liste d'entreprises saisie dans l'UI."""

from utils.search_filters import parse_entreprises


def test_le_texte_libre_est_decoupe_sur_les_virgules():
    assert parse_entreprises("Capgemini, Accenture , Thiga", []) == [
        "Capgemini", "Accenture", "Thiga"
    ]


def test_le_parenthetique_des_concurrents_est_retire():
    # "AKKODIS (ex- AKKA & Modis)" → on ne garde que le nom cherchable
    assert parse_entreprises("", ["AKKODIS (ex- AKKA & Modis)"]) == ["AKKODIS"]


def test_concurrents_et_texte_libre_fusionnent():
    assert parse_entreprises("Thiga", ["Capgemini"]) == ["Capgemini", "Thiga"]


def test_les_doublons_sont_supprimes_sans_tenir_compte_de_la_casse():
    assert parse_entreprises("capgemini, Thiga", ["Capgemini"]) == [
        "Capgemini", "Thiga"
    ]


def test_une_saisie_vide_donne_une_liste_vide():
    assert parse_entreprises("  ,  ", []) == []


def test_une_saisie_absente_donne_une_liste_vide():
    assert parse_entreprises(None, None) == []
