# -*- coding: utf-8 -*-
"""Refonte de la page Veille : une vue par métier, retrait confirmé, mots clairs.

Le moteur n'est jamais appelé : la base est celle de l'utilisateur de test.
"""

import re

import pytest

from tests.conftest import chemins_de_test, lancer_app, verifier_page_affichee
from veille_store import VeilleStore

PAGE = "🏢 Veille"
CIBLES = "Product / Data / IA"


@pytest.fixture
def store():
    s = VeilleStore(str(chemins_de_test().db_file))
    for e in s.entreprises():
        s.retirer_entreprise(e["id"])
    return s


def _page():
    at = lancer_app(PAGE)
    verifier_page_affichee(at, PAGE)
    return at


def _textes(at):
    return " ".join(e.value for e in list(at.markdown) + list(at.warning) + list(at.info) + list(at.success)
                    + list(at.caption) + list(at.error) + list(at.subheader))


def _bouton(at, libelle):
    return [b for b in at.button if b.label == libelle][0]


def test_quatre_onglets_un_par_metier(store):
    at = _page()
    assert [t.label for t in at.tabs] == ["Nouveautés", "Mes entreprises", "Fiche entreprise", "Réglages"]
    assert [t.value for t in at.title] == ["Veille entreprises"]


def test_le_bandeau_dit_ce_que_fait_la_veille_et_son_etat(store):
    store.ajouter_entreprise("Orbique", "2026-10-14")
    store.ajouter_entreprise("Zéphyr", "2026-10-14")
    store.enregistrer_passage("2026-10-15T08:00:00", "2026-10-15T08:12:00", ["Orbique"], 3, "termine", [])
    at = _page()
    bandeau = [m.value for m in at.markdown if 'class="wf-bandeau"' in m.value][0]
    assert "repère les personnes Product, Data et IA" in bandeau
    assert "2 entreprises suivies" in bandeau
    assert "Dernier passage : 15/10/2026 08:12" in bandeau
    assert re.search(r"\d+ restantes? sur \d+", bandeau)


def test_le_bandeau_sans_passage_ni_entreprise(store, monkeypatch):
    # La base de test garde les passages des autres tests : on simule une veille jamais lancée.
    monkeypatch.setattr(VeilleStore, "dernier_passage", lambda self: None)
    at = _page()
    bandeau = [m.value for m in at.markdown if 'class="wf-bandeau"' in m.value][0]
    assert "0 entreprise suivie" in bandeau and "Veille jamais lancée" in bandeau


def test_sans_entreprise_l_etat_vide_apprend_quoi_faire(store):
    at = _page()
    assert "Ajoutez des entreprises dans l&#x27;onglet Mes entreprises, puis lancez la veille." in _textes(at) \
        or "Ajoutez des entreprises dans l'onglet Mes entreprises, puis lancez la veille." in _textes(at)
    assert _bouton(at, "Lancer la veille").disabled


def test_entreprises_sans_resultat_sur_une_ligne_d_information(store):
    store.ajouter_entreprise("Orbique", "2026-10-14")
    store.enregistrer_passage("2026-10-15T08:00:00", "2026-10-15T08:12:00", ["Orbique", "Zéphyr"], 4, "termine",
                              [f"Orbique : aucun profil {CIBLES} trouvé.", f"Zéphyr : aucun profil {CIBLES} trouvé."])
    at = _page()
    assert not at.warning and not at.success
    [resume] = [i.value for i in at.info if "Passage du" in i.value]
    assert "Aucun profil Product, Data ou IA trouvé chez : Orbique, Zéphyr." in resume


def test_un_passage_propre_est_un_seul_message_ok(store):
    store.ajouter_entreprise("Orbique", "2026-10-14")
    store.enregistrer_passage("2026-10-15T08:00:00", "2026-10-15T08:12:00", ["Orbique"], 1, "termine", [])
    at = _page()
    assert [s.value for s in at.success if "Passage du" in s.value]
    assert "1 entreprise : Orbique, 1 page LinkedIn." in _textes(at)
    assert not at.warning


def test_retirer_demande_confirmation(store):
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    store.relier_contact(i, {"nom": "Jeanne Exemple", "poste": "Product Manager",
                             "url": "https://www.linkedin.com/in/jeanne-exemple/"}, "Product", "2026-10-14", set())
    store.relier_contact(i, {"nom": "Paul Exemple", "poste": "Head of Data",
                             "url": "https://www.linkedin.com/in/paul-exemple/"}, "Data", "2026-10-14", set())
    at = _page()
    at.selectbox(key="veille_fiche").set_value("Orbique")
    at.selectbox(key="veille_retirer").set_value("Orbique")
    at.run()
    assert any("Retirer Orbique supprimera sa fiche et ses 2 contacts de la veille" in w.value for w in at.warning)
    bouton = at.button(key="veille_btn_retirer")
    assert bouton.disabled
    bouton.click()
    at.run()
    assert [e["nom"] for e in store.entreprises()] == ["Orbique"]
    at.checkbox(key=f"veille_retirer_confirme_{i}").check()
    at.run()
    assert not at.button(key="veille_btn_retirer").disabled
    at.button(key="veille_btn_retirer").click()
    at.run()
    assert not at.exception
    assert store.entreprises() == []


def test_une_ligne_du_tableau_ouvre_sa_fiche(monkeypatch):
    import ui.page_veille as page

    class FauxSt:
        session_state = {"veille_tableau_entreprises": {"selection": {"rows": [1], "columns": []}},
                         "_veille_noms_tableau": ["Orbique", "Zéphyr"]}

    monkeypatch.setattr(page, "st", FauxSt)
    page._ouvrir_fiche_selectionnee()
    assert FauxSt.session_state["veille_fiche"] == "Zéphyr"
    assert FauxSt.session_state["veille_onglet"] == "Fiche entreprise"


def test_le_tableau_des_entreprises_se_selectionne(store):
    store.ajouter_entreprise("Orbique", "2026-10-14")
    at = _page()
    [tableau] = [d for d in at.dataframe if "Entreprise" in d.value.columns and "État" in d.value.columns]
    assert tableau.proto.selection_mode  # sélection d'une ligne active
    assert "15/10" not in tableau.value.to_string() and "jamais" in tableau.value.to_string()


def test_la_description_generique_de_linkedin_est_masquee(store):
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    store.enregistrer_fiche(i, {"description": "Partagez votre profil en toute confidentialité avec nos "
                                               "recruteurs.", "taille": "11-50 employés"}, "linkedin", "2026-10-14")
    at = _page()
    textes = _textes(at) + " ".join(d.value.to_string() for d in at.dataframe)
    assert "Partagez votre profil" not in textes
    assert "Description non disponible" in textes


def test_une_vraie_description_est_montree(store):
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    store.enregistrer_fiche(i, {"description": "Cabinet de conseil en stratégie."}, "linkedin", "2026-10-14")
    at = _page()
    assert any(c.value == "Cabinet de conseil en stratégie." for c in at.caption)


def test_une_seule_table_pour_la_fiche_et_ses_coordonnees(store):
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    store.enregistrer_fiche(i, {"taille": "201-500 employés", "telephone": "+33 1 23 45 67 89"},
                            "linkedin", "2026-10-14T08:00:00")
    store.marquer_lecture(i, "linkedin", "2026-10-14T08:00:00")
    at = _page()
    fiches = [d.value for d in at.dataframe if "Source" in d.value.columns]
    assert len(fiches) == 1
    assert {"Taille", "Téléphone (LinkedIn)"} <= set(fiches[0]["Information"])


def test_donnees_legales_au_lieu_de_rapprochement(store):
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    store.enregistrer_fiche(i, {"siren": "333333333", "rapprochement": "rapprochée"}, "annuaire", "2026-10-14")
    at = _page()
    [fiche] = [d.value for d in at.dataframe if "Source" in d.value.columns]
    lignes = dict(zip(fiche["Information"], fiche["Valeur"]))
    assert lignes["Données légales (annuaire des entreprises)"] == "vérifiées"
    assert "rapproch" not in (_textes(at) + fiche.to_string()).lower()


@pytest.mark.parametrize("contact, attendu", [
    ({"degre": "1er"}, "1er niveau"), ({"degre": "· 2e"}, "2e niveau"), ({"degre": "3rd"}, "3e niveau"),
    ({"degre": "2e", "en_relation": True}, "1er niveau (invitation acceptée)"), ({}, "inconnue"),
])
def test_la_relation_est_dite_en_niveaux(contact, attendu):
    from ui.page_veille import _relation_lisible
    assert _relation_lisible(contact) == attendu


def test_l_ecran_dit_relation_et_dates_francaises(store):
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    store.relier_contact(i, {"nom": "Jeanne Exemple", "poste": "Product Manager",
                             "url": "https://www.linkedin.com/in/jeanne-exemple/", "connexions": "2e"},
                         "Product", "2026-10-14T08:00:00", set())
    at = _page()
    [t] = [d.value for d in at.dataframe if "Relation" in d.value.columns and "Inviter" not in d.value.columns]
    assert "Degré" not in t.columns
    assert list(t["Relation"]) == ["2e niveau"] and list(t["Trouvé le"]) == ["14/10/2026"]


def test_ni_jargon_ni_emoji_ni_pluriel_bricole(store):
    store.ajouter_entreprise("Orbique", "2026-10-14")
    store.enregistrer_passage("2026-10-15T08:00:00", "2026-10-15T08:12:00", ["Orbique"], 7, "budget", [])
    at = _page()
    libelles = [b.label for b in at.button] + [e.label for e in at.expander] + [t.label for t in at.tabs]
    textes = _textes(at) + " " + " ".join(libelles)
    for interdit in ("scrap", "li_at", "(s)", "(x)", "✅", "❌", "📥", "🏢", "⚙️", "🔗", "⚠️"):
        assert interdit not in textes, interdit


def test_la_cause_cookie_ne_nomme_pas_le_cookie_technique():
    from ui.page_veille import _CAUSES
    assert "li_at" not in _CAUSES["cookie"] and "session linkedin" in _CAUSES["cookie"].lower()
