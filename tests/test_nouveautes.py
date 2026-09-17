# -*- coding: utf-8 -*-
"""Annonce des nouveautés au lancement de l'application."""

from utils.nouveautes import (
    doit_annoncer,
    lire_sections,
    marquer_vue,
    notes_depuis,
    version_vue,
)

NOTES = """# Nouveautés

## 1.2.0
- Filtre par degré de relation

## 1.1.0
- Combiner plusieurs écoles
- Filtre par secteur

## 1.0.0
- Première version
"""


# --- Lecture du fichier ---------------------------------------------------


def test_les_sections_sont_indexees_par_version():
    assert sorted(lire_sections(NOTES)) == ["1.0.0", "1.1.0", "1.2.0"]


def test_le_corps_d_une_section_est_conserve():
    assert "Combiner plusieurs écoles" in lire_sections(NOTES)["1.1.0"]
    # ...sans déborder sur la section suivante
    assert "Première version" not in lire_sections(NOTES)["1.1.0"]


def test_un_fichier_sans_section_donne_un_index_vide():
    assert lire_sections("# Nouveautés\n\nRien pour l'instant.\n") == {}


# --- Cumul depuis la dernière version vue ---------------------------------


def test_seules_les_versions_plus_recentes_sont_retenues():
    notes = notes_depuis(NOTES, version_actuelle="1.1.0", derniere_vue="1.0.0")
    assert "Combiner plusieurs écoles" in notes
    assert "Première version" not in notes


def test_les_versions_sautees_sont_cumulees():
    # Quelqu'un qui n'a pas ouvert l'app depuis 1.0.0 et arrive en 1.2.0
    notes = notes_depuis(NOTES, version_actuelle="1.2.0", derniere_vue="1.0.0")
    assert "Filtre par degré de relation" in notes
    assert "Combiner plusieurs écoles" in notes


def test_une_version_plus_recente_que_l_actuelle_est_ignoree():
    notes = notes_depuis(NOTES, version_actuelle="1.1.0", derniere_vue="1.0.0")
    assert "Filtre par degré de relation" not in notes


def test_rien_a_annoncer_quand_on_est_a_jour():
    assert notes_depuis(NOTES, version_actuelle="1.2.0", derniere_vue="1.2.0") == ""


# --- Mémoire par utilisateur ----------------------------------------------


def test_la_version_vue_se_relit_apres_ecriture(tmp_path):
    assert version_vue(tmp_path) is None
    marquer_vue(tmp_path, "1.1.0")
    assert version_vue(tmp_path) == "1.1.0"


# --- Décision d'affichage -------------------------------------------------


def test_le_premier_lancement_n_annonce_rien_mais_memorise(tmp_path):
    # Un nouveau venu n'a que faire des nouveautés d'une version qu'il n'a
    # jamais connue — on enregistre en silence.
    assert doit_annoncer(tmp_path, "1.1.0", NOTES) is None
    assert version_vue(tmp_path) == "1.1.0"


def test_une_version_plus_ancienne_declenche_l_annonce(tmp_path):
    marquer_vue(tmp_path, "1.0.0")
    notes = doit_annoncer(tmp_path, "1.1.0", NOTES)
    assert notes is not None and "Combiner plusieurs écoles" in notes


def test_l_annonce_ne_se_repete_pas_une_fois_vue(tmp_path):
    marquer_vue(tmp_path, "1.1.0")
    assert doit_annoncer(tmp_path, "1.1.0", NOTES) is None


def test_pas_d_annonce_si_la_version_n_a_pas_de_notes(tmp_path):
    # Évite d'ouvrir une fenêtre vide sur une version publiée sans notes.
    marquer_vue(tmp_path, "1.1.0")
    assert doit_annoncer(tmp_path, "1.1.1", NOTES) is None


# --- Utilisateurs déjà installés avant que la mémoire n'existe -------------


def test_un_utilisateur_deja_installe_voit_les_nouveautes(tmp_path):
    # Pas de fichier « dernière version vue » — il n'existait pas avant cette
    # version — mais un cookie prouve que la personne utilisait déjà l'outil.
    (tmp_path / "cookie.txt").write_text("li_at=...", encoding="utf-8")

    notes = doit_annoncer(tmp_path, "1.1.0", NOTES)

    assert notes is not None and "Combiner plusieurs écoles" in notes
    # ...et seulement celles de sa version, on ne connaît pas son passé
    assert "Première version" not in notes


def test_un_nouveau_venu_ne_voit_toujours_rien(tmp_path):
    # Dossier de config vierge : personne n'a jamais utilisé l'outil ici.
    assert doit_annoncer(tmp_path, "1.1.0", NOTES) is None


def test_un_utilisateur_installe_sans_notes_pour_sa_version(tmp_path):
    (tmp_path / "cookie.txt").write_text("li_at=...", encoding="utf-8")
    assert doit_annoncer(tmp_path, "1.1.1", NOTES) is None


# --- Cohérence du fichier livré -------------------------------------------


def test_la_version_publiee_a_bien_ses_notes():
    """Publier une version sans section dans NOUVEAUTES.md est silencieux :
    l'application n'annoncerait rien à personne, sans la moindre erreur.
    C'est déjà arrivé pendant le développement de cette fonctionnalité."""
    from utils.nouveautes import charger_notes
    from version import get_version

    versions = lire_sections(charger_notes())
    assert get_version() in versions, (
        f"NOUVEAUTES.md n'a pas de section '## {get_version()}' — "
        f"sections présentes : {sorted(versions)}"
    )
    assert versions[get_version()].strip(), "la section est vide"
