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
# (retirer_entreprise supprime aussi fiche et contacts)


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


def _textes(at):
    return " ".join(e.value for e in list(at.markdown) + list(at.warning) + list(at.info)
                    + list(at.success) + list(at.caption) + list(at.error))


def test_le_dernier_passage_est_resume_en_entier(store):
    store.enregistrer_passage("2026-10-15T08:00:00", "2026-10-15T08:12:00", ["Orbique", "Zéphyr Conseil"], 7,
                              "budget", ["Zéphyr Conseil : annuaire officiel injoignable"])
    textes = _textes(_page())
    assert "15/10/2026 08:12" in textes
    assert "Budget de pages du jour atteint" in textes
    assert "2 entreprise(s) : Orbique, Zéphyr Conseil" in textes
    assert "7 page(s)" in textes
    assert "Zéphyr Conseil : annuaire officiel injoignable" in textes


def test_apres_la_veille_le_recap_montre_ce_qu_elle_a_trouve(store, monkeypatch):
    i = store.ajouter_entreprise("Orbique", "2026-10-14")

    def faux(chemins, cookie, proxy=None, status=None):
        s = VeilleStore(str(chemins.db_file))
        s.relier_contact(i, {"nom": "Paul Exemple", "poste": "Head of Data",
                             "url": "https://www.linkedin.com/in/paul-exemple/", "connexions": "3e"},
                         "Data", "2999-01-01T08:00:00", set())
        s.enregistrer_passage("2026-10-15T08:00:00", "2026-10-15T08:05:00", ["Orbique"], 2, "termine", [])
        return RapportPassage(debut="2026-10-15T08:00:00", fin="2026-10-15T08:05:00", entreprises=["Orbique"],
                              pages=2, cause="termine", nouveaux_contacts=1)

    monkeypatch.setattr(veille, "lancer_passage", faux)
    at = _page()
    at.session_state["global_cookie"] = "COOKIE-DE-TEST"
    _bouton(at, "🏢 Lancer la veille").click()
    at.run()
    assert not at.exception
    recap = [d.value for d in at.dataframe if "Inviter" in d.value.columns]
    assert recap and "Paul Exemple" in recap[0].to_string()
    assert "1 nouveau(x) contact(s)" in _textes(at)
    # Montré une fois : au rechargement suivant, seul le résumé enregistré reste.
    at.run()
    assert "1 nouveau(x) contact(s)" not in _textes(at)
    assert "Passage terminé" in _textes(at)


def test_la_date_de_visite_est_reecrite_a_chaque_affichage(store):
    from pathlib import Path
    fichier = Path(chemins_de_test().config_dir) / "derniere_visite_veille.txt"
    at = _page()
    precedente = at.session_state["veille_visite_precedente"]
    fichier.write_text("2000-01-01T00:00:00", encoding="utf-8")
    at.run()
    assert fichier.read_text(encoding="utf-8") != "2000-01-01T00:00:00"
    assert at.session_state["veille_visite_precedente"] == precedente


def test_une_cause_d_arret_n_est_pas_dite_deux_fois(store, monkeypatch):
    def faux(chemins, cookie, proxy=None, status=None):
        return RapportPassage(debut="2026-10-15T08:00:00", fin="2026-10-15T08:01:00", entreprises=[], pages=1,
                              cause="securite", erreurs=[veille.MESSAGES_ARRET["securite"], "Orbique : autre souci"])

    monkeypatch.setattr(veille, "lancer_passage", faux)
    store.ajouter_entreprise("Orbique", "2026-10-14")
    at = _page()
    at.session_state["global_cookie"] = "COOKIE-DE-TEST"
    _bouton(at, "🏢 Lancer la veille").click()
    at.run()
    assert sum("activité inhabituelle" in w.value for w in at.warning) == 1
    assert any("Orbique : autre souci" in w.value for w in at.warning)


@pytest.mark.parametrize("headless, attendu", [(True, "arrière-plan"), (False, "fenêtre Chrome")])
def test_la_legende_du_lancement_suit_le_mode_du_navigateur(store, monkeypatch, headless, attendu):
    from config import ScraperConfig
    monkeypatch.setattr(ScraperConfig, "HEADLESS", headless)
    at = _page()
    assert any(attendu in c.value for c in at.caption)


def test_retirer_previent_de_ce_qui_est_supprime(store):
    store.ajouter_entreprise("Orbique", "2026-10-14")
    at = _page()
    at.selectbox(key="veille_retirer").set_value("Orbique")
    at.run()
    assert any("les profils restent dans l'Historique" in c.value for c in list(at.caption) + list(at.warning))


# ── Correctifs de la revue finale ────────────────────────────────────────

@pytest.mark.parametrize("headless", [True, False])
def test_la_legende_dit_de_garder_la_page_ouverte(store, monkeypatch, headless):
    from config import ScraperConfig
    monkeypatch.setattr(ScraperConfig, "HEADLESS", headless)
    at = _page()
    assert any("cette page ouverte jusqu'au rapport" in c.value for c in at.caption)


def test_coller_son_lien_sur_la_fiche_ne_cree_pas_de_doublon(store):
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    store.maj_identification(i, "non_identifiee")
    at = _page()
    assert any("collez ci-dessous le lien" in w.value for w in at.warning)
    at.text_input(key=f"veille_lien_fiche_{i}").set_value(
        "https://www.linkedin.com/company/orbique-conseil/about/?trk=x")
    _bouton(at, "Enregistrer ce lien").click()
    at.run()
    assert not at.exception
    [e] = store.entreprises()
    assert (e["nom"], e["url_linkedin"], e["etat"]) == \
        ("Orbique", "https://www.linkedin.com/company/orbique-conseil/", "a_identifier")


def test_coller_un_lien_qui_n_en_est_pas_un_sur_la_fiche_est_refuse(store):
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    store.maj_identification(i, "non_identifiee")
    at = _page()
    at.text_input(key=f"veille_lien_fiche_{i}").set_value("https://www.linkedin.com/in/jeanne/")
    _bouton(at, "Enregistrer ce lien").click()
    at.run()
    assert store.entreprises()[0]["etat"] == "non_identifiee"
    assert any("/company/" in e.value for e in at.error)


def test_les_postes_hors_familles_sont_a_part_et_pas_proposes_a_l_invitation(store):
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    store.relier_contact(i, {"nom": "Jeanne Exemple", "poste": "Product Manager",
                             "url": "https://www.linkedin.com/in/jeanne-exemple/"}, "Product", "2999-01-01T08:00:00",
                         set())
    store.relier_contact(i, {"nom": "Paul Comptable", "poste": "Comptable",
                             "url": "https://www.linkedin.com/in/paul-comptable/"}, "Autre", "2999-01-01T08:00:00",
                         set())
    at = _page()
    [recap] = [d.value for d in at.dataframe if "Inviter" in d.value.columns]
    assert "Jeanne Exemple" in recap.to_string() and "Paul Comptable" not in recap.to_string()
    assert any(x.label.startswith("Autres postes trouvés (1)") for x in at.expander)
    assert any("Paul Comptable" in d.value.to_string() for d in at.dataframe if "Inviter" not in d.value.columns)


def test_les_champs_de_l_annuaire_ont_des_libelles_lisibles(store):
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    store.enregistrer_fiche(i, {"siren": "333333333", "activite": "70.22Z", "commune": "PARIS",
                                "effectif": "100 à 199 salariés", "rapprochement": "rapprochée"},
                            "annuaire", "2026-10-14")
    at = _page()
    fiche = [d.value for d in at.dataframe if "Source" in d.value.columns][0]
    assert {"SIREN", "Activité (NAF)", "Commune du siège", "Effectif (INSEE)"} <= set(fiche["Information"])


def test_releve_le_donne_la_derniere_lecture(store):
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    store.enregistrer_fiche(i, {"taille": "201-500 employés"}, "linkedin", "2026-09-01T08:00:00")
    store.enregistrer_fiche(i, {"recherche": "aucun profil trouvé"}, "linkedin", "2026-09-01T08:00:00")
    store.marquer_lecture(i, "linkedin", "2026-10-14T08:00:00")
    at = _page()
    fiche = [d.value for d in at.dataframe if "Source" in d.value.columns][0]
    dates = dict(zip(fiche["Information"], fiche["Relevé le"]))
    assert dates["Taille"] == "2026-10-14"
    assert dates["Recherche des employés"] == "2026-09-01"


def test_un_refus_est_dit_une_fois_sans_cacher_le_dernier_passage(store, monkeypatch):
    store.enregistrer_passage("2026-10-15T08:00:00", "2026-10-15T08:12:00", ["Orbique"], 7, "budget", [])

    def occupe(chemins, cookie, proxy=None, status=None):
        s = VeilleStore(str(chemins.db_file))
        s.enregistrer_passage("2026-10-15T09:00:00", "2026-10-15T09:00:00", [], 0, "occupe",
                              ["Une autre session LinkedIn de We.Reach est en cours (recherche)"])
        return RapportPassage(debut="2026-10-15T09:00:00", fin="2026-10-15T09:00:00", cause="occupe",
                              erreurs=["Une autre session LinkedIn de We.Reach est en cours (recherche)"])

    monkeypatch.setattr(veille, "lancer_passage", occupe)
    store.ajouter_entreprise("Orbique", "2026-10-14")
    at = _page()
    at.session_state["global_cookie"] = "COOKIE-DE-TEST"
    _bouton(at, "🏢 Lancer la veille").click()
    at.run()
    assert any("en cours (recherche)" in w.value for w in at.warning)
    assert "15/10/2026 08:12" in _textes(at) and "7 page(s)" in _textes(at)
    at.run()
    assert not any("en cours (recherche)" in w.value for w in at.warning)
    assert "7 page(s)" in _textes(at)


# ── Coordonnées et export ────────────────────────────────────────────────

def _orbique_avec_contacts(store):
    """Une entreprise, ses coordonnées générales, et un contact de chaque cas."""
    i = store.ajouter_entreprise("Orbique Conseil", "2026-10-14")
    store.enregistrer_fiche(i, {"telephone": "+33 1 23 45 67 89", "site": "https://orbique.example"},
                            "linkedin", "2026-10-14T08:00:00")
    store.marquer_lecture(i, "linkedin", "2026-10-14T08:00:00")
    store.enregistrer_fiche(i, {"lecture": "site lu", "email": "contact@orbique.example"}, "site",
                            "2026-10-14T08:05:00")
    store.marquer_lecture(i, "site", "2026-10-14T08:05:00")
    cas = [("jeanne-exemple", "Jeanne Exemple", "1er"), ("paul-exemple", "Paul Exemple", "1er"),
           ("lea-exemple", "Léa Exemple", "1er"), ("max-exemple", "Max Exemple", "2e"),
           ("zoe-exemple", "Zoé Exemple", "1er")]
    for vanity, nom, degre in cas:
        store.relier_contact(i, {"nom": nom, "poste": "Product Manager",
                                 "url": f"https://www.linkedin.com/in/{vanity}/", "connexions": degre},
                             "Product", "2026-10-14T08:00:00", set())
    store.enregistrer_coordonnees("https://www.linkedin.com/in/jeanne-exemple/", "jeanne@orbique.example", "",
                                  "2999-01-01T08:00:00")
    store.enregistrer_coordonnees("https://www.linkedin.com/in/paul-exemple/", "", "", "2026-10-14T09:00:00")
    store.noter_echec_coordonnees("https://www.linkedin.com/in/lea-exemple/", "2026-10-14T09:00:00")
    return i


def _tableau_contacts(at):
    return [d.value for d in at.dataframe if "Email" in d.value.columns and "Inviter" not in d.value.columns][0]


def test_la_fiche_montre_les_coordonnees_de_l_entreprise_avec_leur_source(store):
    _orbique_avec_contacts(store)
    at = _page()
    assert any("Coordonnées de l'entreprise" in m.value for m in list(at.markdown) + list(at.subheader))
    [coord] = [d.value for d in at.dataframe if "Source" in d.value.columns
               and "Email (site)" in set(d.value["Information"])]
    lignes = {r["Information"]: r for _, r in coord.iterrows()}
    assert lignes["Téléphone (LinkedIn)"]["Valeur"] == "+33 1 23 45 67 89"
    assert lignes["Téléphone (LinkedIn)"]["Source"].startswith("LinkedIn")
    assert lignes["Email (site)"]["Valeur"] == "contact@orbique.example"
    assert lignes["Email (site)"]["Source"].startswith("Site de l'entreprise")
    assert lignes["Email (site)"]["Relevé le"] == "2026-10-14"
    # Site lu sans téléphone : dit, pas laissé vide.
    assert lignes["Téléphone (site)"]["Valeur"] == "non publié"


def test_un_site_non_lisible_est_dit(store):
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    store.enregistrer_fiche(i, {"lecture": "site non lisible (réseau social)"}, "site", "2026-10-14T08:00:00")
    store.marquer_lecture(i, "site", "2026-10-14T08:00:00")
    at = _page()
    tableaux = " ".join(d.value.to_string() for d in at.dataframe)
    assert "site non lisible (réseau social)" in tableaux


def test_le_tableau_des_contacts_dit_l_etat_de_chaque_coordonnee(store):
    _orbique_avec_contacts(store)
    at = _page()
    t = _tableau_contacts(at)
    assert {"Degré", "Email", "Téléphone"} <= set(t.columns)
    par_nom = {r["Nom"]: r for _, r in t.iterrows()}
    assert par_nom["Jeanne Exemple"]["Email"] == "jeanne@orbique.example"
    assert par_nom["Jeanne Exemple"]["Degré"] == "1er"
    assert par_nom["Paul Exemple"]["Email"] == "rien de partagé"
    assert par_nom["Léa Exemple"]["Email"].startswith("lecture impossible")
    assert par_nom["Max Exemple"]["Email"] == "après acceptation de l'invitation"
    assert par_nom["Max Exemple"]["Téléphone"] == "après acceptation de l'invitation"
    assert par_nom["Zoé Exemple"]["Email"] == "à lire au prochain passage"


def test_l_export_des_contacts_a_les_bonnes_colonnes(store):
    from ui.page_veille import _contacts_a_exporter
    i = _orbique_avec_contacts(store)
    at = _page()
    # L'identifiant d'un widget à clé se termine par sa clé.
    ids = [b.proto.id for b in at.get("download_button")]
    assert any(x.endswith(f"veille_dl_xlsx_{i}") for x in ids) and any(x.endswith(f"veille_dl_csv_{i}") for x in ids)
    df = _contacts_a_exporter(store.contacts_et_coordonnees(i))
    assert list(df.columns) == ["Nom", "Intitulé", "Famille", "Degré", "Email", "Téléphone", "Lien", "Trouvé le"]
    assert "jeanne@orbique.example" in set(df["Email"])
    assert "max@" not in df.to_csv()


def test_une_entreprise_sans_contact_n_a_pas_d_export(store):
    store.ajouter_entreprise("Orbique", "2026-10-14")
    at = _page()
    assert not [b for b in at.get("download_button") if "veille_dl_" in b.proto.id]
    assert any("rien à exporter" in c.value.lower() for c in at.caption)


def test_le_nom_du_fichier_exporte(store):
    from ui.page_veille import _nom_export
    assert _nom_export("Zéphyr & Fils SA", "2026-10-15") == "contacts_zephyr-fils-sa_20261015"


def test_le_recap_montre_une_coordonnee_nouvellement_partagee(store):
    _orbique_avec_contacts(store)
    at = _page()
    assert any("Jeanne Exemple" in m.value and "a partagé son email" in m.value for m in at.markdown)
    assert not any("Paul Exemple a partagé" in m.value for m in at.markdown)
    assert not any("Rien de nouveau" in x.value for x in at.info)
