# -*- coding: utf-8 -*-
"""Branchement du tutoriel dans l'application réelle."""

import re

import pytest

from tests.conftest import chemins_de_test, lancer_app
from utils.nouveautes import marquer_vue
from utils.tutoriel import FICHIER_VU, marquer_vu, tutoriel_a_afficher

PAGE = "📊 Dashboard"


@pytest.fixture
def config():
    """Isole les marqueurs « tutoriel vu » et « version vue » du test."""
    dossier = chemins_de_test().config_dir
    fichiers = [dossier / FICHIER_VU, dossier / "derniere_version_vue.txt"]
    origines = {f: (f.read_text(encoding="utf-8") if f.exists() else None) for f in fichiers}
    for f in fichiers:
        f.unlink(missing_ok=True)
    try:
        yield dossier
    finally:
        for f, contenu in origines.items():
            if contenu is None:
                f.unlink(missing_ok=True)
            else:
                f.write_text(contenu, encoding="utf-8")


def _scripts(at):
    return [e.proto.body for e in at.get("html") if "__wrTour" in e.proto.body]


def _identifiant(at):
    return re.search(r'var ID = "([0-9a-f]+)"', _scripts(at)[0]).group(1)


def test_premier_lancement_injecte_la_visite(config):
    at = lancer_app(PAGE)
    assert not at.exception
    assert len(_scripts(at)) == 1


def test_la_visite_remplace_la_fenetre_nouveautes(config):
    marquer_vue(config, "0.0.1")
    at = lancer_app(PAGE)
    assert _scripts(at)
    assert not any(b.label == "J'ai compris" for b in at.button)


def test_le_bouton_cache_marque_vu(config):
    at = lancer_app(PAGE)
    at.button(key="tutoriel_fini").click().run()
    assert not tutoriel_a_afficher(config)
    assert not _scripts(at)
    assert not _scripts(lancer_app(PAGE))


def test_revoir_le_tutoriel_relance_avec_un_nouvel_identifiant(config):
    marquer_vu(config)
    at = lancer_app(PAGE)
    assert not _scripts(at)
    at.button(key="btn_tutoriel").click().run()
    premier = _identifiant(at)
    at.button(key="btn_tutoriel").click().run()
    assert _identifiant(at) != premier


def test_un_rerun_garde_le_meme_identifiant(config):
    at = lancer_app(PAGE)
    premier = _identifiant(at)
    at.run()
    assert _identifiant(at) == premier


def test_la_version_n_est_pas_consommee_pendant_la_visite(config):
    # Revue finale : doit_annoncer mémorisait la version pendant que le
    # tutoriel la remplaçait, et ses nouveautés étaient perdues.
    from utils.nouveautes import version_vue
    marquer_vue(config, "0.0.1")
    lancer_app(PAGE)
    assert version_vue(config) == "0.0.1"


def test_pas_de_fenetre_nouveautes_juste_apres_la_fin_du_tutoriel(config):
    marquer_vue(config, "0.0.1")
    at = lancer_app(PAGE)
    at.button(key="tutoriel_fini").click().run()
    assert not any(b.label == "J'ai compris" for b in at.button)
