# -*- coding: utf-8 -*-
"""Composant de sélection des profils trouvés (commun aux onglets)."""

from streamlit.testing.v1 import AppTest


def _app():
    import streamlit as st
    from ui.selection import choisir_profils, reinitialiser_choix
    profils = st.session_state.get("profils_test", [])
    if st.session_state.pop("nouvelle_liste", False):
        reinitialiser_choix("t")
    st.session_state["choisis_test"] = [p["url"] for p in choisir_profils(profils, "t")]


P = [{"url": f"https://www.linkedin.com/in/exemple-{i}/", "nom": f"Exemple {i}",
      "intitule": "Product Manager", "degre": "2e", "invitable": True} for i in range(3)]


def _lancer(profils, **etat):
    at = AppTest.from_function(_app)
    at.session_state["profils_test"] = profils
    for k, v in etat.items():
        at.session_state[k] = v
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


def test_tout_est_choisi_par_defaut():
    at = _lancer(P)
    assert at.session_state["choisis_test"] == [p["url"] for p in P]


def test_tout_deselectionner_puis_tout_selectionner():
    at = _lancer(P)
    at.button(key="t_rien").click().run()
    assert at.session_state["choisis_test"] == []
    at.button(key="t_tout").click().run()
    assert len(at.session_state["choisis_test"]) == 3


def test_deja_au_fichier_decoche_par_defaut():
    profils = [dict(P[0], deja=True), P[1]]
    at = _lancer(profils)
    assert at.session_state["choisis_test"] == [P[1]["url"]]


def test_une_nouvelle_liste_repart_de_zero():
    at = _lancer(P)
    at.button(key="t_rien").click().run()
    at.session_state["nouvelle_liste"] = True
    at.run()
    assert len(at.session_state["choisis_test"]) == 3


def test_champs_absents_ne_font_pas_planter():
    _lancer([{"url": "https://www.linkedin.com/in/exemple-x/"}])
