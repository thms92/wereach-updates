# -*- coding: utf-8 -*-
"""Tableau de bord : le bloc « Vos chiffres » (période, filtres, tuiles, tableaux)."""

import sqlite3
from datetime import date, datetime, timezone

import pytest

from tests.conftest import EMAIL_DE_TEST, lancer_app, verifier_page_affichee
from utils.chiffres import Periode, texte_taux
from utils.tutoriel import ETAPES

PAGE = "📊 Dashboard"
AUJOURD_HUI = date(2026, 10, 24)


# --- aides pures ---------------------------------------------------------------

def test_periode_7_et_30_jours():
    from ui.bloc_chiffres import periode_choisie
    assert periode_choisie("7 jours", None, AUJOURD_HUI) == Periode(date(2026, 10, 18), AUJOURD_HUI)
    assert periode_choisie("30 jours", None, AUJOURD_HUI) == Periode(date(2026, 9, 25), AUJOURD_HUI)
    # Choix absent ou inconnu : la période par défaut.
    assert periode_choisie(None, None, AUJOURD_HUI) == Periode(date(2026, 9, 25), AUJOURD_HUI)


def test_plage_personnalisee():
    from ui.bloc_chiffres import periode_choisie
    choix = "Plage personnalisée"
    debut, fin = date(2026, 10, 1), date(2026, 10, 10)
    assert periode_choisie(choix, (debut, fin), AUJOURD_HUI) == Periode(debut, fin)
    # Dates inversées : remises dans l'ordre.
    assert periode_choisie(choix, (fin, debut), AUJOURD_HUI) == Periode(debut, fin)
    # Une seule date (sélection en cours) : ce jour-là.
    assert periode_choisie(choix, (debut,), AUJOURD_HUI) == Periode(debut, debut)
    assert periode_choisie(choix, debut, AUJOURD_HUI) == Periode(debut, debut)
    # Rien de choisi : les 30 derniers jours.
    assert periode_choisie(choix, (), AUJOURD_HUI) == Periode(date(2026, 9, 25), AUJOURD_HUI)


def test_texte_de_verification():
    from ui.bloc_chiffres import texte_verification
    assert texte_verification(None) == (
        "Acceptations jamais vérifiées : utilisez « Vérifier qui a accepté » "
        "dans la page Messages.")
    moment = datetime(2026, 10, 20, 7, 5, tzinfo=timezone.utc)
    local = moment.astimezone()
    assert texte_verification(moment) == (
        f"Acceptations vérifiées pour la dernière fois le {local:%d/%m} à "
        f"{local:%H:%M}, depuis la page Messages.")


def test_texte_jamais_verifiees_accorde():
    from ui.bloc_chiffres import texte_jamais_verifiees
    assert texte_jamais_verifiees(1) == "1 invitation de la période n'a jamais été vérifiée."
    assert texte_jamais_verifiees(4) == "4 invitations de la période n'ont jamais été vérifiées."


def test_etape_tutoriel_vise_le_bloc_chiffres():
    etape = _etape_tdb("Vos chiffres")
    assert ".st-key-tdb_chiffres" in etape["cible"]
    assert etape["texte"] == ("Invitations, acceptations, messages : vos chiffres sur la "
                              "période choisie, filtrables par école, entreprise et poste.")
    assert not any(e["titre"] == "Votre parcours" for e in ETAPES)


def _etape_tdb(titre):
    return next(e for e in ETAPES if e["titre"] == titre and e["page"] == PAGE)


# --- page rendue, avec une base fictive -------------------------------------------

@pytest.fixture
def base(tmp_path, monkeypatch):
    """Base propre au test ; `remplir(profils)` ajoute des profils invités.

    Chaque profil : (école, entreprise, poste, acceptée, messagée, vérifiée).
    Les invitations partent « maintenant », donc dans la période par défaut.
    """
    monkeypatch.setenv("WEREACH_DATA_DIR", str(tmp_path))
    from database import DatabaseManager
    from utils.user_context import user_paths_for
    chemins = user_paths_for(EMAIL_DE_TEST)

    def remplir(profils):
        db = DatabaseManager(db_file=str(chemins.db_file))
        for i, (ecole, entreprise, poste, acceptee, messagee, verifiee) in enumerate(profils):
            url = f"https://exemple.test/in/chiffres-{i}/"
            pid = db.ajouter_profil(f"Camille Exemple{i}", poste, entreprise, ecole, url, "Ville")
            db.ajouter_invitation(pid, "Bonjour (démo)")
            if acceptee:
                db.marquer_acceptee(url)
            if messagee:
                db.marquer_messagee(url)
            if verifiee:
                db.marquer_verifiees([url])
        return chemins

    return remplir


def _principal(at):
    return " ".join(m.value for m in at.main.markdown
                    if not m.value.lstrip().startswith("<style")).replace("&#x27;", "'")


def _textes(at):
    return ([c.value for c in at.main.caption] + [i.value for i in at.main.info]
            + [_principal(at)])


def _tuiles(at):
    return {m.label: (m.value, m.delta) for m in at.main.metric}


SIX = [("École A", "Société A", "Poste A", True, True, True),
       ("École A", "Société A", "Poste A", True, False, True),
       ("École A", "Société B", "Poste B", True, False, True),
       ("École B", "Société B", "Poste B", False, False, True),
       ("École B", "Société B", "Poste B", False, False, False),
       ("École B", "Société B", "Poste B", False, False, False)]


def test_tableau_de_bord_affiche_les_cinq_tuiles(base):
    base(SIX)
    at = lancer_app(PAGE)
    verifier_page_affichee(at, PAGE)
    tuiles = _tuiles(at)
    assert list(tuiles) == ["Invitations", "Acceptées", "Taux d'acceptation",
                            "Messages envoyés", "En attente"]
    assert tuiles["Invitations"][0] == "6"
    assert tuiles["Acceptées"][0] == "3"
    assert tuiles["Taux d'acceptation"] == (texte_taux(3, 6), "3 sur 6")
    # Le « X sur Y » n'est pas une hausse : ni flèche ni couleur.
    from streamlit.proto.Metric_pb2 import Metric
    taux = next(m for m in at.main.metric if m.label == "Taux d'acceptation")
    assert taux.proto.direction == Metric.NONE and taux.proto.color == Metric.GRAY
    assert tuiles["Messages envoyés"][0] == "1"
    assert tuiles["En attente"][0] == "3"
    # Les trois tableaux, avec leurs colonnes.
    assert [s.value for s in at.main.subheader] == ["Par école", "Par entreprise", "Par poste"]
    tableaux = [d.value for d in at.main.dataframe]
    assert [list(t.columns) for t in tableaux] == [
        ["École", "Invités", "Acceptés", "Taux"],
        ["Entreprise", "Invités", "Acceptés", "Taux"],
        ["Poste", "Invités", "Acceptés", "Taux"]]
    ecoles = tableaux[0].to_dict("records")
    assert ecoles[0] == {"École": "École A", "Invités": 3, "Acceptés": 3, "Taux": "trop peu (3)"}
    # Le graphique semaine par semaine.
    assert len(at.get("plotly_chart")) == 1


def test_plus_de_parcours_ni_derniere_recherche(base):
    base(SIX)
    at = lancer_app(PAGE)
    verifier_page_affichee(at, PAGE)
    html = _principal(at)
    assert '<ol class="wf-entonnoir"' not in html
    assert "Dernière recherche" not in html
    assert "Parcours de vos prospects" not in [h.value for h in at.header]
    assert "tdb_nouvelle_recherche" not in [b.key for b in at.main.button]


def test_taux_sous_le_seuil_affiche_trop_peu(base):
    base(SIX[:3])
    at = lancer_app(PAGE)
    verifier_page_affichee(at, PAGE)
    tuiles = _tuiles(at)
    assert tuiles["Taux d'acceptation"] == ("trop peu (3)", "3 sur 3")
    # Les nombres bruts restent visibles.
    assert tuiles["Invitations"][0] == "3" and tuiles["Acceptées"][0] == "3"


def test_filtre_sans_resultat_dit_pourquoi(base):
    base(SIX)
    at = lancer_app(PAGE)
    at.multiselect(key="tdb_f_ecole").set_value(["École A"])
    at.multiselect(key="tdb_f_poste").set_value(["Poste A"])
    at.multiselect(key="tdb_f_entreprise").set_value(["Société B"]).run()
    verifier_page_affichee(at, PAGE)
    assert any("Aucune invitation sur cette période avec ces filtres." in t for t in _textes(at))
    assert not list(at.main.metric)


def test_les_filtres_s_appliquent_aux_tuiles(base):
    base(SIX)
    at = lancer_app(PAGE)
    at.multiselect(key="tdb_f_ecole").set_value(["École B"]).run()
    verifier_page_affichee(at, PAGE)
    assert _tuiles(at)["Invitations"][0] == "3"
    assert _tuiles(at)["Acceptées"][0] == "0"


def test_plage_a_une_seule_date(base):
    base(SIX)
    at = lancer_app(PAGE)
    at.session_state["tdb_periode"] = "Plage personnalisée"
    at.session_state["tdb_plage"] = (date.today(),)
    at.run()
    verifier_page_affichee(at, PAGE)
    assert _tuiles(at)["Invitations"][0] == "6"


def test_jamais_verifiees_signalees(base):
    base(SIX)
    at = lancer_app(PAGE)
    verifier_page_affichee(at, PAGE)
    textes = " ".join(_textes(at))
    assert "2 invitations de la période n'ont jamais été vérifiées." in textes
    assert "Acceptations jamais vérifiées" in textes


def test_derniere_verification_affichee(base):
    chemins = base(SIX[:4])
    from utils.verification import enregistrer_verification
    moment = datetime(2026, 10, 20, 7, 5, tzinfo=timezone.utc)
    enregistrer_verification(str(chemins.config_dir), moment)
    at = lancer_app(PAGE)
    verifier_page_affichee(at, PAGE)
    local = moment.astimezone()
    textes = " ".join(_textes(at))
    assert (f"Acceptations vérifiées pour la dernière fois le {local:%d/%m} à "
            f"{local:%H:%M}, depuis la page Messages.") in textes
    assert "jamais été vérifié" not in textes


def test_base_sans_invitation_etat_vide(base):
    base([])
    at = lancer_app(PAGE)
    verifier_page_affichee(at, PAGE)
    html = _principal(at)
    assert '<div class="wf-vide">' in html
    assert not list(at.main.metric)
    assert "tdb_periode" not in at.session_state


def _figure(monkeypatch, periode):
    import ui.bloc_chiffres as bc
    figures = []
    monkeypatch.setattr(bc.st, "plotly_chart", lambda fig, **k: figures.append(fig))
    bc._graphique([], periode)
    return figures[0]


def test_graphique_sur_plus_d_un_an_des_semaines_distinctes(monkeypatch):
    fig = _figure(monkeypatch, Periode(date(2025, 10, 1), AUJOURD_HUI))
    x = list(fig.data[0].x)
    # S40 2025 et S40 2026 ne se confondent plus sur l'axe.
    assert len(x) == len(set(x))
    etiquettes = list(fig.layout.xaxis.ticktext)
    assert etiquettes[0] == "S40 2025" and etiquettes[-1] == "S43 2026"


def test_graphique_dans_une_annee_etiquettes_sans_annee(monkeypatch):
    fig = _figure(monkeypatch, Periode(date(2026, 9, 25), AUJOURD_HUI))
    assert list(fig.layout.xaxis.ticktext) == ["S39", "S40", "S41", "S42", "S43"]
