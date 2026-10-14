# -*- coding: utf-8 -*-
"""Onglet « Profils similaires » : du lien de référence à la liste filtrée.

L'onglet ne scrape pas et n'invite pas : il récolte le panneau de LinkedIn,
filtre, et confie les URLs retenues à la chaîne de l'onglet Par URLs. Ces
tests vérifient ce câblage — ce qui part dans la récolte, ce que le filtre
reçoit, ce qui reste à l'écran.
"""

import pandas as pd
import pytest

import scraper_v2_sync
from tests.conftest import lancer_app, verifier_page_affichee

URL_REFERENCE = "https://www.linkedin.com/in/jean-dupont-12345/"
BOUTON_TROUVER = "👥 Trouver des profils similaires"


def voisin(nom, vanity, degre="2e", intitule="Product Manager, Kering", invitable=True):
    return {
        "nom": nom,
        "url": f"https://www.linkedin.com/in/{vanity}/",
        "degre": degre,
        "intitule": intitule,
        "invitable": invitable,
    }


@pytest.fixture
def recolte_espionne(monkeypatch):
    """Remplace le scraper : rien n'est lancé, la récolte est dictée.

    `reponse` est modifiable par le test ; `appels` capture ce qui a été
    demandé.
    """
    etat = {"reponse": ([], None), "appels": []}

    class FauxScraper:
        def __init__(self, **kwargs):
            self.errors = []
            self.use_database = False

        def recolter_browsemap(self, **kwargs):
            etat["appels"].append(kwargs)
            return etat["reponse"]

        def run_url_scraper(self, **kwargs):
            etat["appels"].append(kwargs)
            return pd.DataFrame()

    monkeypatch.setattr(scraper_v2_sync, "LinkedInScraperV2Sync", FauxScraper)
    return etat


def _page_recherche():
    at = lancer_app("🔍 Recherche")
    verifier_page_affichee(at, "🔍 Recherche")
    at.session_state["global_cookie"] = "COOKIE-DE-TEST"
    return at


def _bouton(at, libelle):
    return [b for b in at.button if b.label == libelle][0]


def _trouver(at, url=URL_REFERENCE):
    at.text_input(key="sim_url").set_value(url)
    _bouton(at, BOUTON_TROUVER).click()
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


def test_l_onglet_existe_dans_la_page_recherche():
    at = _page_recherche()
    assert at.text_input(key="sim_url") is not None


def test_le_lien_de_reference_part_dans_la_recolte(recolte_espionne):
    at = _trouver(_page_recherche())

    assert recolte_espionne["appels"][0]["url_reference"] == URL_REFERENCE
    assert recolte_espionne["appels"][0]["cookie"] == "COOKIE-DE-TEST"


def test_un_lien_qui_n_est_pas_un_profil_est_refuse_sans_rien_lancer(recolte_espionne):
    at = _trouver(_page_recherche(), "https://www.linkedin.com/company/thiga/")

    assert recolte_espionne["appels"] == []
    assert at.error, "aucun message d'erreur affiché"


def test_les_profils_retenus_sont_mis_en_session(recolte_espionne):
    recolte_espionne["reponse"] = (
        [voisin("Marie Martin", "marie-martin"), voisin("Paul Durand", "paul-durand")],
        "Thiga",
    )
    at = _trouver(_page_recherche())

    assert [p["nom"] for p in at.session_state["sim_retenues"]] == [
        "Marie Martin", "Paul Durand"
    ]
    assert at.session_state["sim_entreprise"] == "Thiga"


def test_le_premier_degre_est_ecarte_a_l_ecran(recolte_espionne):
    recolte_espionne["reponse"] = (
        [voisin("Marie Martin", "marie-martin", degre="1er")], None
    )
    at = _trouver(_page_recherche())

    assert at.session_state["sim_retenues"] == []
    assert len(at.session_state["sim_ecartees"]) == 1


def test_l_entreprise_de_reference_est_transmise_au_filtre(recolte_espionne):
    # « ailleurs » : celui qui est encore chez Thiga n'est pas la cible.
    recolte_espionne["reponse"] = (
        [voisin("Marie Martin", "marie-martin", intitule="Lead Dev, Thiga")], "Thiga"
    )
    at = _trouver(_page_recherche())

    assert at.session_state["sim_retenues"] == []
    assert "Thiga" in at.session_state["sim_ecartees"][0]["motif"]


def test_une_liste_entierement_ecartee_affiche_ses_motifs(recolte_espionne):
    # Le défaut de la 1.4.7 sous une autre forme : une liste vide sans
    # explication passerait pour un profil sans voisins. On cible l'expander
    # lui-même : le texte d'introduction de l'onglet dit déjà « votre réseau »,
    # une recherche dans tout l'écran réussirait même sans expander.
    recolte_espionne["reponse"] = (
        [voisin("Marie Martin", "marie-martin", degre="1er")], None
    )
    at = _trouver(_page_recherche())

    expanders = [e for e in at.expander if "1 profil(s) écarté(s)" in e.label]
    assert expanders, f"pas d'expander des écartés : {[e.label for e in at.expander]}"
    textes = [m.value for m in expanders[0].markdown]
    assert any("déjà dans ton réseau (1er degré)" in t for t in textes), textes


def test_aucun_voisin_propose_n_est_pas_presente_comme_un_tri(recolte_espionne):
    # Rien récolté, rien écarté : dire « tout a été écarté » renverrait vers
    # un détail qui n'existe pas.
    recolte_espionne["reponse"] = ([], None)
    at = _trouver(_page_recherche())

    infos = [i.value for i in at.info]
    assert any("aucun profil voisin" in t for t in infos), infos
    assert not any("tout a été écarté" in t for t in infos), infos


def test_un_refus_efface_les_resultats_de_la_reference_precedente(recolte_espionne):
    recolte_espionne["reponse"] = ([voisin("Marie Martin", "marie-martin")], "Thiga")
    at = _trouver(_page_recherche())
    assert "sim_retenues" in at.session_state

    at = _trouver(at, "https://www.linkedin.com/company/thiga/")

    assert "sim_retenues" not in at.session_state


def test_le_mot_attendu_resserre_la_liste(recolte_espionne):
    recolte_espionne["reponse"] = (
        [
            voisin("Marie Martin", "marie-martin", intitule="Product Manager, Kering"),
            voisin("Paul Durand", "paul-durand", intitule="Data Engineer, Kering"),
        ],
        None,
    )
    at = _page_recherche()
    at.text_input(key="sim_mot").set_value("Product")
    at = _trouver(at)

    assert [p["nom"] for p in at.session_state["sim_retenues"]] == ["Marie Martin"]


def test_un_cookie_absent_est_signale(recolte_espionne):
    at = lancer_app("🔍 Recherche")
    at.session_state["global_cookie"] = ""
    at = _trouver(at)

    assert recolte_espionne["appels"] == []
    assert at.error
