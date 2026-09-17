# -*- coding: utf-8 -*-
"""Un libellé d'école composite ne doit casser aucun de ses consommateurs.

Une recherche visant plusieurs écoles (pilules « Dauphine » + « ESCP »)
enregistre chaque profil avec `ecole = "Dauphine / ESCP"` : le libellé garde
fidèlement ce que la recherche ciblait, puisqu'on ignore laquelle de ces écoles
le profil a réellement fréquentée.

Les deux lecteurs de cette colonne doivent le comprendre : le filtre de la page
Historique et le camembert « Répartition par école » du Dashboard.
"""

from pathlib import Path

import pytest

from database import DatabaseManager
from scraper_v2 import LinkedInScraperV2
from tests.conftest import chemins_de_test, lancer_app, verifier_page_affichee
from utils.ecoles import composer_libelle, ecoles_du_libelle, libelle_vise_ecole

LIBELLE_COMPOSITE = "Dauphine / ESCP"


def _semer_profils(db_file: str, nb: int = 3, ecole: str = LIBELLE_COMPOSITE):
    """Repart d'une base vide et y écrit `nb` profils portant `ecole`."""
    Path(db_file).unlink(missing_ok=True)
    db = DatabaseManager(db_file=db_file)
    for i in range(nb):
        db.ajouter_profil(
            nom=f"Profil {i}",
            poste="Product Manager",
            entreprise="Thiga",
            ecole=ecole,
            url=f"https://www.linkedin.com/in/profil-test-{i}/",
        )
    return db


@pytest.fixture
def base_semee(tmp_path):
    return _semer_profils(str(tmp_path / "profiles.db"))


# --- Dashboard : agrégation par école ------------------------------------


def test_le_dashboard_compte_chaque_ecole_du_libelle_composite(base_semee):
    # Attendu : trois profils comptés pour Dauphine ET pour ESCP,
    # et surtout aucune catégorie « Dauphine / ESCP » dans le camembert.
    stats = base_semee.get_statistiques()
    assert stats["par_ecole"] == {"Dauphine": 3, "ESCP": 3}


def test_le_dashboard_compte_toujours_une_ecole_seule(tmp_path):
    db = _semer_profils(str(tmp_path / "profiles.db"), nb=2, ecole="Dauphine")
    assert db.get_statistiques()["par_ecole"] == {"Dauphine": 2}


# --- Historique : filtre par école ---------------------------------------


def _nb_profils_affiches(at) -> int:
    """Le compteur « N profils trouvés » affiché par la page Historique."""
    for bloc in at.main.markdown:
        if bloc.value.endswith("profils trouvés**"):
            return int(bloc.value.strip("*").split()[0])
    raise AssertionError("compteur « N profils trouvés » absent de la page")


def _filtrer_historique(ecole: str):
    """Rend la page Historique et y applique le filtre d'école demandé."""
    at = lancer_app("💾 Historique")
    verifier_page_affichee(at, "💾 Historique")

    filtre = [s for s in at.selectbox if s.label == "Filtrer par école"][0]
    filtre.set_value(ecole)
    at.run()

    assert not at.exception, [str(e.value) for e in at.exception]
    return at


@pytest.mark.parametrize("ecole", ["Dauphine", "ESCP"])
def test_le_filtre_historique_retrouve_une_ecole_du_libelle_composite(ecole):
    _semer_profils(str(chemins_de_test().db_file))

    at = _filtrer_historique(ecole)

    assert _nb_profils_affiches(at) == 3
    assert len(at.main.dataframe[0].value) == 3


def test_le_filtre_historique_ecarte_une_ecole_absente_du_libelle():
    _semer_profils(str(chemins_de_test().db_file))

    at = _filtrer_historique("HEC")

    assert _nb_profils_affiches(at) == 0


def test_le_filtre_historique_traite_les_noms_a_risque_litteralement():
    # « Université d'Angers » ne doit pas être interprété comme un motif
    # d'expression régulière par le filtre.
    _semer_profils(str(chemins_de_test().db_file), ecole="Université d'Angers / ESCP")

    at = _filtrer_historique("Université d'Angers")

    assert _nb_profils_affiches(at) == 3


# --- Le libellé : écrit par le scraper, relu par les deux pages ----------


def test_le_scraper_compose_le_libelle_des_ecoles_ciblees():
    # 15092700 = Dauphine et 308907 = ESCP dans config.ECOLES
    assert LinkedInScraperV2._libelle_ecoles(["15092700", "308907"]) == LIBELLE_COMPOSITE


def test_le_libelle_ecrit_est_relu_ecole_par_ecole():
    assert ecoles_du_libelle(composer_libelle(["Dauphine", "ESCP"])) == ["Dauphine", "ESCP"]


def test_un_libelle_simple_ne_designe_qu_une_ecole():
    assert ecoles_du_libelle("Dauphine") == ["Dauphine"]
    assert libelle_vise_ecole("Dauphine", "Dauphine") is True
    assert libelle_vise_ecole("Dauphine", "ESCP") is False


def test_un_libelle_ou_un_filtre_vide_ne_vise_aucune_ecole():
    assert ecoles_du_libelle("") == []
    assert libelle_vise_ecole("", "Dauphine") is False
    assert libelle_vise_ecole(LIBELLE_COMPOSITE, "") is False


def test_le_nom_d_ecole_n_est_pas_traite_comme_une_expression_reguliere():
    assert libelle_vise_ecole(LIBELLE_COMPOSITE, "D.uphine") is False
    assert libelle_vise_ecole(LIBELLE_COMPOSITE, "Dauphine|ESCP") is False
    assert libelle_vise_ecole("Université d'Angers / ESCP", "Université d'Angers") is True
