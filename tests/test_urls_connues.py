# -*- coding: utf-8 -*-
"""L'ensemble des URLs déjà au fichier, pour le filtre des profils voisins.

`profil_existe()` ne suffit pas : il compare des URLs brutes, et la base
contient les liens tels qu'ils ont été copiés. La comparaison se fait sur des
formes canoniques, des deux côtés — ce qui suppose de lire celles stockées.
"""

import sqlite3

from database import DatabaseManager


def base_jetable(tmp_path):
    return DatabaseManager(db_file=str(tmp_path / "test.db"))


def test_une_base_vide_ne_connait_aucune_url(tmp_path):
    assert base_jetable(tmp_path).urls_connues() == set()


def test_les_urls_ajoutees_sont_connues(tmp_path):
    db = base_jetable(tmp_path)
    db.ajouter_profil("Jean Dupont", "PM", "Thiga", "Dauphine",
                      "https://www.linkedin.com/in/jean-dupont/")
    db.ajouter_profil("Marie Martin", "Dev", "Kering", "ESCP",
                      "https://www.linkedin.com/in/marie-martin/")

    assert db.urls_connues() == {
        "https://www.linkedin.com/in/jean-dupont/",
        "https://www.linkedin.com/in/marie-martin/",
    }


def test_les_urls_sont_rendues_telles_qu_elles_sont_stockees(tmp_path):
    # La normalisation appartient à utils.browsemap, pas à la base : celle-ci
    # dit ce qu'elle contient, sans l'interpréter.
    db = base_jetable(tmp_path)
    brute = "http://LINKEDIN.com/in/Jean-Dupont?trk=x"
    db.ajouter_profil("Jean", "PM", "Thiga", "", brute)

    assert db.urls_connues() == {brute}


def test_un_echec_de_lecture_ne_rend_pas_None(tmp_path, monkeypatch):
    # Les méthodes de cette classe avalent leurs exceptions. Celle-ci doit
    # alors rendre un ensemble vide : l'appelant fait `url in connues`.
    # La base est créée normalement, puis la connexion échoue : c'est bien la
    # branche d'exception qui est exercée.
    db = base_jetable(tmp_path)

    def connexion_impossible(*args, **kwargs):
        raise sqlite3.OperationalError("base illisible")

    monkeypatch.setattr("database.sqlite3.connect", connexion_impossible)

    assert db.urls_connues() == set()
