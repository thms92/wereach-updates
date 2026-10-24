# -*- coding: utf-8 -*-
"""Calcul des chiffres du tableau de bord (utils/chiffres.py et lignes_suivi)."""

import sqlite3
import time
from datetime import date

import pytest

from database import DatabaseManager
from utils.chiffres import (
    AUTRES, ChiffresCles, LigneTableau, Periode, chiffres_cles, filtrer,
    jour_local, options_filtres, par_categorie, par_semaine,
    periode_glissante, texte_taux,
)


@pytest.fixture
def fuseau_paris():
    """Change le fuseau du processus, puis le restaure (tzset est global)."""
    import os
    ancien = os.environ.get("TZ")
    os.environ["TZ"] = "Europe/Paris"
    time.tzset()
    yield
    if ancien is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = ancien
    time.tzset()


def _ligne(envoi="2026-10-20 10:00:00", ecole="Dauphine", entreprise="Orbique",
           poste="PM", acceptee=False, messagee=False, verifiee=False, url="u"):
    return {"url": url, "ecole": ecole, "entreprise": entreprise, "poste": poste,
            "date_envoi": envoi, "acceptee": acceptee, "messagee": messagee,
            "verifiee": verifiee}


# --- dates ------------------------------------------------------------------

def test_minuit_local_compte_le_bon_jour(fuseau_paris):
    assert jour_local("2026-10-23 22:30:00") == date(2026, 10, 24)


def test_jour_local_lit_les_formats_connus_et_rend_none_sinon(fuseau_paris):
    assert jour_local("2026-10-23T10:00:00") == date(2026, 10, 23)
    assert jour_local("2026-10-23 10:00:00.123456") == date(2026, 10, 23)
    assert jour_local("2026-10-23 10:00") == date(2026, 10, 23)
    assert jour_local("n'importe quoi") is None
    assert jour_local(None) is None
    assert jour_local("") is None


def test_periode_glissante():
    assert periode_glissante(7, date(2026, 10, 24)) == Periode(date(2026, 10, 18),
                                                              date(2026, 10, 24))


# --- taux et chiffres clés --------------------------------------------------

def test_texte_taux():
    assert texte_taux(61, 184) == "33 %"
    assert texte_taux(2, 3) == "trop peu (3)"
    assert texte_taux(0, 5) == "0 %"


def test_chiffres_cles_d_une_periode():
    lignes = [
        _ligne(acceptee=True, messagee=True), _ligne(acceptee=True),
        _ligne(verifiee=True), _ligne(), _ligne(), _ligne(),
    ]
    assert chiffres_cles(lignes) == ChiffresCles(6, 2, 1, 4, 3)


def test_chiffres_cles_sans_ligne():
    assert chiffres_cles([]) == ChiffresCles(0, 0, 0, 0, 0)


# --- filtres ----------------------------------------------------------------

def test_filtre_par_periode_exclut_les_dates_illisibles(fuseau_paris):
    lignes = [_ligne(envoi="2026-10-20 10:00:00"), _ligne(envoi="2026-09-01 10:00:00"),
              _ligne(envoi="bizarre")]
    periode = Periode(date(2026, 10, 18), date(2026, 10, 24))
    assert filtrer(lignes, periode) == [lignes[0]]
    assert filtrer(lignes, Periode(date(2020, 1, 1), date(2030, 1, 1))) == lignes[:2]


def test_filtre_ecole_retient_les_libelles_composites(fuseau_paris):
    periode = Periode(date(2026, 10, 1), date(2026, 10, 31))
    lignes = [_ligne(ecole="Dauphine / ESCP"), _ligne(ecole="ESCP"),
              _ligne(ecole="HEC"), _ligne(ecole="")]
    assert filtrer(lignes, periode, ecoles=("escp",)) == lignes[:2]
    assert filtrer(lignes, periode, ecoles=("Non renseignée",)) == [lignes[3]]
    assert filtrer(lignes, periode) == lignes


def test_filtre_entreprise_et_poste_acceptent_les_non_renseignes(fuseau_paris):
    periode = Periode(date(2026, 10, 1), date(2026, 10, 31))
    lignes = [_ligne(entreprise="Orbique", poste="PM"), _ligne(entreprise=" ", poste=""),
              _ligne(entreprise="Nexa", poste="CEO")]
    assert filtrer(lignes, periode, entreprises=("ORBIQUE",)) == [lignes[0]]
    assert filtrer(lignes, periode, entreprises=("Non renseignée",)) == [lignes[1]]
    assert filtrer(lignes, periode, postes=("Non renseigné",)) == [lignes[1]]
    assert filtrer(lignes, periode, entreprises=("Orbique", "Nexa"), postes=("CEO",)) \
        == [lignes[2]]


def test_options_filtres(fuseau_paris):
    lignes = [_ligne(ecole="Dauphine / ESCP", entreprise="Orbique", poste="PM"),
              _ligne(ecole="", entreprise="orbique ", poste=""),
              _ligne(ecole="ESCP", entreprise="Nexa", poste="CEO")]
    assert options_filtres(lignes) == {
        "ecole": ["Dauphine", "ESCP", "Non renseignée"],
        "entreprise": ["Nexa", "Orbique"],
        "poste": ["CEO", "Non renseigné", "PM"],
    }


# --- semaines ---------------------------------------------------------------

def test_par_semaine_inclut_les_semaines_vides(fuseau_paris):
    # 2026-10-05 est un lundi ; période du mercredi 7 au jeudi 22
    lignes = [_ligne(envoi="2026-10-07 10:00:00", acceptee=True),
              _ligne(envoi="2026-10-08 10:00:00"),
              _ligne(envoi="2026-10-21 10:00:00", acceptee=True)]
    periode = Periode(date(2026, 10, 7), date(2026, 10, 22))
    assert par_semaine(lignes, periode) == [
        (date(2026, 10, 5), 2, 1),
        (date(2026, 10, 12), 0, 0),
        (date(2026, 10, 19), 1, 1),
    ]


def test_par_semaine_utilise_le_jour_local(fuseau_paris):
    # dimanche 22 h UTC = lundi 00 h à Paris : semaine suivante
    lignes = [_ligne(envoi="2026-10-11 22:30:00")]
    periode = Periode(date(2026, 10, 5), date(2026, 10, 18))
    assert par_semaine(lignes, periode) == [(date(2026, 10, 5), 0, 0),
                                            (date(2026, 10, 12), 1, 0)]


# --- catégories -------------------------------------------------------------

def test_par_categorie_regroupe_sans_casse_et_non_renseignee():
    lignes = [_ligne(entreprise="Orbique", acceptee=True), _ligne(entreprise="orbique "),
              _ligne(entreprise="")]
    assert par_categorie(lignes, "entreprise") == [
        LigneTableau("Orbique", 2, 1), LigneTableau("Non renseignée", 1, 0)]


def test_par_categorie_ecole_compte_chaque_ecole_du_libelle():
    lignes = [_ligne(ecole="Dauphine / ESCP", acceptee=True), _ligne(ecole="escp"),
              _ligne(ecole="")]
    assert par_categorie(lignes, "ecole") == [
        LigneTableau("ESCP", 2, 1), LigneTableau("Dauphine", 1, 1),
        LigneTableau("Non renseignée", 1, 0)]


def test_par_categorie_poste_vide_se_nomme_au_masculin():
    assert par_categorie([_ligne(poste="")], "poste") == [LigneTableau("Non renseigné", 1, 0)]


def test_postes_au_dela_de_15_vont_dans_autres():
    lignes = [_ligne(poste=f"Poste {n:02d}", acceptee=(n == 17)) for n in range(18)]
    lignes += [_ligne(poste="Poste 00")]  # Poste 00 passe à 2 invitations
    resultat = par_categorie(lignes, "poste")
    assert len(resultat) == 16
    assert resultat[0] == LigneTableau("Poste 00", 2, 0)
    assert resultat[-1] == LigneTableau(AUTRES, 3, 1)  # Postes 15, 16, 17


def test_quinze_postes_pile_n_ont_pas_de_ligne_autres():
    lignes = [_ligne(poste=f"Poste {n:02d}") for n in range(15)]
    assert len(par_categorie(lignes, "poste")) == 15
    assert all(l.libelle != AUTRES for l in par_categorie(lignes, "poste"))


def test_les_autres_categories_ne_sont_pas_tronquees():
    lignes = [_ligne(entreprise=f"E{n:02d}") for n in range(20)]
    assert len(par_categorie(lignes, "entreprise")) == 20


# --- lignes_suivi -----------------------------------------------------------

def _base(tmp_path):
    db = DatabaseManager(db_file=str(tmp_path / "c.db"))
    return db, sqlite3.connect(db.db_file)


def test_lignes_suivi_compte_un_profil_invite_deux_fois_une_fois(tmp_path):
    db, con = _base(tmp_path)
    con.execute("INSERT INTO profiles (id, nom, poste, entreprise, ecole, url) "
                "VALUES (1, 'Ana', 'PM', 'Orbique', 'Dauphine', 'u1')")
    con.execute("INSERT INTO profiles (id, nom, url) VALUES (2, 'Bob', 'u2')")
    con.execute("INSERT INTO profiles (id, nom, url) VALUES (3, 'Zoé', 'u3')")
    con.executemany(
        "INSERT INTO invitations (profile_id, date_envoi, statut, date_acceptation, "
        "date_message, date_verification) VALUES (?, ?, ?, ?, ?, ?)",
        [(1, "2026-10-02 08:00:00", "envoyee", None, None, None),
         (1, "2026-10-09 08:00:00", "acceptee", "2026-10-10 08:00:00",
          "2026-10-11 08:00:00", "2026-10-10 09:00:00"),
         (2, "2026-10-03 08:00:00", "envoyee", None, None, None)])
    con.commit(); con.close()
    lignes = {l["url"]: l for l in db.lignes_suivi()}
    assert set(lignes) == {"u1", "u2"}  # u3 n'a jamais été invité
    assert lignes["u1"] == {"url": "u1", "ecole": "Dauphine", "entreprise": "Orbique",
                            "poste": "PM", "date_envoi": "2026-10-02 08:00:00",
                            "acceptee": True, "messagee": True, "verifiee": True}
    assert lignes["u2"]["acceptee"] is False and lignes["u2"]["ecole"] == ""
    assert lignes["u2"]["messagee"] is False and lignes["u2"]["verifiee"] is False


def test_lignes_suivi_base_ancienne(tmp_path):
    chemin = tmp_path / "vieille.db"
    con = sqlite3.connect(chemin)
    con.execute("CREATE TABLE profiles (id INTEGER PRIMARY KEY, nom TEXT, poste TEXT, "
                "entreprise TEXT, ecole TEXT, url TEXT)")
    con.execute("CREATE TABLE invitations (id INTEGER PRIMARY KEY, profile_id INTEGER, "
                "date_envoi TIMESTAMP, statut TEXT, date_acceptation TIMESTAMP)")
    con.execute("INSERT INTO profiles VALUES (1, 'Ana', 'PM', 'Orbique', 'HEC', 'u1')")
    con.execute("INSERT INTO invitations VALUES (1, 1, '2026-10-02 08:00:00', 'acceptee', "
                "'2026-10-03 08:00:00')")
    con.commit(); con.close()
    db = DatabaseManager.__new__(DatabaseManager)  # sans init_database : base laissée telle quelle
    db.db_file = str(chemin)
    assert db.lignes_suivi() == [{"url": "u1", "ecole": "HEC", "entreprise": "Orbique",
                                  "poste": "PM", "date_envoi": "2026-10-02 08:00:00",
                                  "acceptee": True, "messagee": False, "verifiee": False}]


def test_lignes_suivi_erreur_rend_une_liste_vide(tmp_path):
    db = DatabaseManager.__new__(DatabaseManager)
    db.db_file = str(tmp_path / "vide.db")  # aucune table
    assert db.lignes_suivi() == []
