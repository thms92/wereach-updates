# -*- coding: utf-8 -*-
"""Proposer la mise à jour depuis l'application elle-même.

Jusqu'ici, la mise à jour ne se faisait qu'au démarrage du lanceur. Qui ne
ferme jamais l'outil ne la reçoit jamais : une collègue est restée bloquée en
1.2.2 pendant que l'équipe passait en 1.4.5.
"""

from pathlib import Path

from utils.mise_a_jour import (
    chemin_lanceur,
    mise_a_jour_disponible,
    relancer,
    version_publiee,
)


# --- Comparaison des versions ---------------------------------------------


def test_une_version_plus_recente_est_detectee():
    assert mise_a_jour_disponible("1.2.2", "1.4.5")


def test_la_meme_version_ne_declenche_rien():
    assert not mise_a_jour_disponible("1.4.5", "1.4.5")


def test_on_ne_propose_pas_de_revenir_en_arriere():
    # Pendant la minute ou deux ou le cache de GitHub sert encore l'ancienne
    # version, l'app ne doit pas proposer une « mise a jour » regressive.
    assert not mise_a_jour_disponible("1.4.5", "1.4.4")


def test_les_numeros_sont_compares_en_nombres_pas_en_texte():
    # "1.10.0" < "1.9.0" en comparaison de chaines : le piege classique.
    assert mise_a_jour_disponible("1.9.0", "1.10.0")
    assert not mise_a_jour_disponible("1.10.0", "1.9.0")


def test_une_version_illisible_ne_declenche_rien():
    assert not mise_a_jour_disponible("1.4.5", "")
    assert not mise_a_jour_disponible("1.4.5", None)


# --- Interrogation du dépôt ------------------------------------------------


def test_un_depot_injoignable_reste_silencieux(monkeypatch):
    # Hors ligne, l'app doit fonctionner normalement sans rien afficher.
    def boum(*a, **k):
        raise OSError("pas de reseau")

    monkeypatch.setattr("urllib.request.urlopen", boum)
    assert version_publiee() is None


# --- Relance ---------------------------------------------------------------


def test_le_lanceur_est_trouve_a_cote_du_dossier_app(tmp_path, monkeypatch):
    app = tmp_path / "We.Reach" / "app"
    app.mkdir(parents=True)
    lanceur = tmp_path / "We.Reach" / "1 - Lancer We.Reach.command"
    lanceur.write_text("#!/bin/bash\n", encoding="utf-8")
    monkeypatch.setattr("utils.mise_a_jour.RACINE", app)

    assert chemin_lanceur() == lanceur


def test_sans_lanceur_on_ne_pretend_pas_pouvoir_relancer(tmp_path, monkeypatch):
    # En developpement il n'y a pas de lanceur : l'app doit le dire plutot
    # que d'echouer silencieusement.
    monkeypatch.setattr("utils.mise_a_jour.RACINE", tmp_path)
    assert chemin_lanceur() is None
    assert relancer() is False


def test_la_relance_passe_par_le_lanceur(tmp_path, monkeypatch):
    app = tmp_path / "We.Reach" / "app"
    app.mkdir(parents=True)
    lanceur = tmp_path / "We.Reach" / "1 - Lancer We.Reach.command"
    lanceur.write_text("#!/bin/bash\n", encoding="utf-8")
    monkeypatch.setattr("utils.mise_a_jour.RACINE", app)
    monkeypatch.setattr("sys.platform", "darwin")

    appels = []
    monkeypatch.setattr("subprocess.Popen", lambda cmd, **k: appels.append(cmd))

    assert relancer() is True
    assert appels == [["open", str(lanceur)]]


# --- Bandeau dans l'application --------------------------------------------


def test_le_bandeau_apparait_quand_une_version_plus_recente_existe(monkeypatch):
    import utils.mise_a_jour as m
    from tests.conftest import lancer_app

    monkeypatch.setattr(m, "version_publiee", lambda *a, **k: "99.0.0")
    at = lancer_app("📊 Dashboard")

    assert not at.exception, [str(e.value) for e in at.exception]
    assert any("nouvelle version est disponible" in w.value for w in at.warning)
    assert any(b.label == "Mettre à jour maintenant" for b in at.button)


def test_aucun_bandeau_quand_on_est_a_jour(monkeypatch):
    import utils.mise_a_jour as m
    from tests.conftest import lancer_app
    from version import get_version

    monkeypatch.setattr(m, "version_publiee", lambda *a, **k: get_version())
    at = lancer_app("📊 Dashboard")

    assert not any("nouvelle version" in w.value for w in at.warning)
    assert not any(b.label == "Mettre à jour maintenant" for b in at.button)


def test_hors_ligne_rien_ne_s_affiche(monkeypatch):
    import utils.mise_a_jour as m
    from tests.conftest import lancer_app

    monkeypatch.setattr(m, "version_publiee", lambda *a, **k: None)
    at = lancer_app("📊 Dashboard")

    assert not at.exception, [str(e.value) for e in at.exception]
    assert not any(b.label == "Mettre à jour maintenant" for b in at.button)
