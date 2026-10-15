# -*- coding: utf-8 -*-
"""Page Veille : liste suivie, lancement, récap, fiche.

Le moteur est remplacé : aucune session LinkedIn ne s'ouvre. La base est
celle de l'utilisateur de test, isolée par conftest.
"""

import pytest

import veille
from tests.conftest import chemins_de_test, lancer_app, verifier_page_affichee
from veille import RapportPassage
from veille_store import VeilleStore

PAGE = "🏢 Veille"


@pytest.fixture
def store():
    s = VeilleStore(str(chemins_de_test().db_file))
    for e in s.entreprises():
        s.retirer_entreprise(e["id"])
    return s
# (retirer_entreprise supprime aussi fiche, contacts et actualités)


@pytest.fixture
def moteur_espion(monkeypatch):
    appels = []

    def faux(chemins, cookie, proxy=None, status=None):
        appels.append(cookie)
        return RapportPassage(debut="2026-10-15T08:00:00", fin="2026-10-15T08:10:00",
                              entreprises=["Orbique"], pages=3, cause="budget",
                              erreurs=["Orbique : annuaire officiel injoignable"], nouveaux_contacts=2)

    monkeypatch.setattr(veille, "lancer_passage", faux)
    return appels


def _page():
    at = lancer_app(PAGE)
    verifier_page_affichee(at, PAGE)
    return at


def _bouton(at, libelle):
    return [b for b in at.button if b.label == libelle][0]


def test_la_page_est_au_menu():
    _page()


def test_ajouter_une_entreprise_par_son_lien(store):
    at = _page()
    at.text_input(key="veille_lien").set_value("https://www.linkedin.com/company/orbique/")
    _bouton(at, "Ajouter").click()
    at.run()
    assert [e["url_linkedin"] for e in store.entreprises()] == ["https://www.linkedin.com/company/orbique/"]


def test_un_lien_qui_n_est_pas_une_page_entreprise_est_refuse(store):
    at = _page()
    at.text_input(key="veille_lien").set_value("https://www.linkedin.com/in/jeanne/")
    _bouton(at, "Ajouter").click()
    at.run()
    assert store.entreprises() == []
    assert any("/company/" in e.value for e in at.error)


def test_lancer_la_veille_affiche_le_rapport(store, moteur_espion):
    store.ajouter_entreprise("Orbique", "2026-10-14")
    at = _page()
    at.session_state["global_cookie"] = "COOKIE-DE-TEST"
    _bouton(at, "🏢 Lancer la veille").click()
    at.run()
    assert moteur_espion == ["COOKIE-DE-TEST"]
    textes = " ".join(m.value for m in list(at.markdown) + list(at.warning) + list(at.info) + list(at.success))
    assert "budget" in textes.lower()
    assert "annuaire officiel injoignable" in textes


def test_sans_cookie_la_veille_ne_part_pas(store, moteur_espion):
    store.ajouter_entreprise("Orbique", "2026-10-14")
    at = _page()
    at.session_state["global_cookie"] = ""
    _bouton(at, "🏢 Lancer la veille").click()
    at.run()
    assert moteur_espion == []
    assert any("Cookie" in e.value for e in at.error)


def test_le_recap_montre_les_nouveaux_contacts(store):
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    store.relier_contact(i, {"nom": "Jeanne Exemple", "poste": "Product Manager",
                             "url": "https://www.linkedin.com/in/jeanne-exemple/", "connexions": "2e"},
                         "Product", "2999-01-01T08:00:00", set())
    at = _page()
    tableaux = [d.value for d in at.dataframe]
    assert any("Jeanne Exemple" in df.to_string() for df in tableaux)


def test_le_recap_montre_les_actualites(store):
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    store.enregistrer_actualites(i, [{"titre": "Orbique rachète Zéphyr", "lien": "https://n/1", "source": "Les Échos",
                                      "publie_le": "2026-08-31", "categorie": "Rachat / fusion"}], "2999-01-01T08:00:00")
    at = _page()
    assert any("Orbique rachète Zéphyr" in m.value for m in at.markdown)


def test_la_fiche_s_ouvre_sur_le_coup_d_oeil(store):
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    store.enregistrer_fiche(i, {"taille": "201-500 employés", "secteur": "Conseil"}, "linkedin", "2026-10-14")
    at = _page()
    assert any(m.value.startswith("**En un coup d'œil** — 201-500 employés · Conseil") for m in at.markdown)


def test_le_recap_vide_le_dit(store):
    at = _page()
    assert any("Rien de nouveau" in i.value for i in at.info)


def test_les_reglages_se_sauvent(store):
    from utils.veille_regles import charger_reglages
    at = _page()
    at.number_input(key="veille_pages").set_value(12)
    _bouton(at, "Enregistrer les réglages").click()
    at.run()
    assert charger_reglages(chemins_de_test().config_dir).pages_par_jour == 12


def test_un_arret_de_securite_est_explique(store, monkeypatch):
    def faux(chemins, cookie, proxy=None, status=None):
        return RapportPassage(debut="2026-10-15T08:00:00", fin="2026-10-15T08:01:00",
                              entreprises=[], pages=1, cause="securite")

    monkeypatch.setattr(veille, "lancer_passage", faux)
    store.ajouter_entreprise("Orbique", "2026-10-14")
    at = _page()
    at.session_state["global_cookie"] = "COOKIE-DE-TEST"
    _bouton(at, "🏢 Lancer la veille").click()
    at.run()
    assert any("activité inhabituelle" in w.value for w in at.warning)


def test_un_lien_sans_nom_d_entreprise_est_refuse(store):
    at = _page()
    at.text_input(key="veille_lien").set_value("https://www.linkedin.com/company/-/")
    _bouton(at, "Ajouter").click()
    at.run()
    assert store.entreprises() == []
    assert at.error


def test_ajouter_une_selection_vide_est_refuse(store):
    at = _page()
    _bouton(at, "Ajouter la sélection").click()
    at.run()
    assert store.entreprises() == []
    assert at.error


def test_un_annuaire_non_rapproche_est_dit_et_ses_anciennes_valeurs_cachees(store):
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    store.enregistrer_fiche(i, {"effectif": "50 à 99 salariés", "rapprochement": "rapprochée"}, "annuaire",
                            "2026-09-01")
    store.enregistrer_fiche(i, {"rapprochement": "plusieurs sociétés homonymes"}, "annuaire", "2026-10-14")
    at = _page()
    assert any("non rapprochée" in c.value and "plusieurs sociétés homonymes" in c.value for c in at.caption)
    fiche = [d.value for d in at.dataframe if "Source" in d.value.columns][0]
    assert "50 à 99 salariés" not in fiche.to_string()
    assert list(fiche.loc[fiche["Valeur"] == "plusieurs sociétés homonymes", "Source"]) == ["Annuaire officiel"]


def test_aucun_widget_n_a_a_la_fois_une_valeur_par_defaut_et_une_valeur_en_session(store):
    import logging

    messages = []

    class Collecteur(logging.Handler):
        def emit(self, record):
            messages.append(record.getMessage())

    journal = logging.getLogger("streamlit.elements.lib.policies")
    collecteur = Collecteur(level=logging.WARNING)
    journal.addHandler(collecteur)
    try:
        at = _page()
        at.number_input(key="veille_pages").set_value(15)
        _bouton(at, "Enregistrer les réglages").click()
        at.run()
        at.session_state["page"] = "💾 Historique"
        at.run()
        at.session_state["page"] = PAGE
        at.run()
    finally:
        journal.removeHandler(collecteur)
    assert not at.exception
    assert not any("default value" in m for m in messages), messages
