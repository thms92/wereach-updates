# -*- coding: utf-8 -*-
"""L'annonce des nouveautés s'affiche bien dans l'application réelle.

La logique de décision est testée sans Streamlit dans test_nouveautes.py ;
ici on vérifie uniquement le câblage : la fenêtre s'ouvre quand elle doit,
et se tait le reste du temps.
"""

import pytest

from tests.conftest import chemins_de_test, lancer_app
from utils.nouveautes import marquer_vue, version_vue
from version import get_version


@pytest.fixture
def memoire_de_version():
    """Isole le fichier « dernière version vue » de l'utilisateur de test."""
    chemin = chemins_de_test().config_dir / "derniere_version_vue.txt"
    origine = chemin.read_text(encoding="utf-8") if chemin.exists() else None
    try:
        yield chemin
    finally:
        if origine is None:
            chemin.unlink(missing_ok=True)
        else:
            chemin.write_text(origine, encoding="utf-8")


def _texte_rendu(at) -> str:
    return "\n".join(m.value for m in at.markdown)


def test_la_fenetre_s_ouvre_apres_une_mise_a_jour(memoire_de_version):
    marquer_vue(memoire_de_version.parent, "0.0.1")

    at = lancer_app("📊 Dashboard")

    assert not at.exception, [str(e.value) for e in at.exception]
    assert "Vous pouvez combiner plusieurs écoles" in _texte_rendu(at)
    assert any(b.label == "J'ai compris" for b in at.button)


def test_la_fenetre_ne_reapparait_pas_au_lancement_suivant(memoire_de_version):
    marquer_vue(memoire_de_version.parent, "0.0.1")
    lancer_app("📊 Dashboard")  # premier lancement : l'annonce est consommée

    at = lancer_app("📊 Dashboard")

    assert not at.exception, [str(e.value) for e in at.exception]
    assert "Vous pouvez combiner plusieurs écoles" not in _texte_rendu(at)
    assert not any(b.label == "J'ai compris" for b in at.button)


def test_le_premier_lancement_ne_montre_rien_et_memorise(memoire_de_version):
    memoire_de_version.unlink(missing_ok=True)

    at = lancer_app("📊 Dashboard")

    assert not at.exception, [str(e.value) for e in at.exception]
    assert not any(b.label == "J'ai compris" for b in at.button)
    assert version_vue(memoire_de_version.parent) == get_version()


def test_un_collegue_deja_installe_voit_l_annonce(memoire_de_version):
    """Le cas de la publication 1.1.0 : personne n'a encore de mémoire de
    version, mais les collègues en place ont déjà leur cookie LinkedIn."""
    memoire_de_version.unlink(missing_ok=True)
    cookie = memoire_de_version.parent / "cookie.txt"
    existait = cookie.exists()
    if not existait:
        cookie.write_text("li_at=factice", encoding="utf-8")
    try:
        at = lancer_app("📊 Dashboard")

        assert not at.exception, [str(e.value) for e in at.exception]
        assert "Vous pouvez combiner plusieurs écoles" in _texte_rendu(at)
    finally:
        if not existait:
            cookie.unlink(missing_ok=True)
