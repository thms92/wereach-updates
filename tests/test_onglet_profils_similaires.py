# -*- coding: utf-8 -*-
"""Onglet « Profils similaires » : du lien de référence à la liste filtrée.

L'onglet ne scrape pas et n'invite pas : il récolte le panneau de LinkedIn,
filtre, et confie les URLs retenues à la chaîne run_url_scraper. Ces
tests vérifient ce câblage — ce qui part dans la récolte, ce que le filtre
reçoit, ce qui reste à l'écran.
"""

import logging
from types import SimpleNamespace

import pandas as pd
import pytest

import scraper_v2_sync
from tests.conftest import lancer_app, verifier_page_affichee

URL_REFERENCE = "https://www.linkedin.com/in/jean-dupont-12345/"
BOUTON_TROUVER = "Rechercher des profils similaires"


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
    etat = {"reponse": ([], None), "appels": [], "recoltes": 0,
            "invitations_restantes": 1000, "erreurs": [], "etapes": []}

    class FauxLimites:
        """Le plafond du jour, dictée par le test."""
        def remaining_invitations(self):
            return etat["invitations_restantes"]

    class FauxScraper:
        def __init__(self, **kwargs):
            self.errors = []
            self.use_database = False
            # Même chemin que le vrai : scraper.scraper.human.daily_limits.
            self.scraper = SimpleNamespace(
                human=SimpleNamespace(daily_limits=FauxLimites())
            )

        def recolter_browsemap(self, **kwargs):
            etat["appels"].append(kwargs)
            etat["recoltes"] += 1
            # Les étapes annoncées par la vraie récolte passent par ce rappel.
            for etape in etat["etapes"]:
                kwargs["status_callback"](etape)
            self.errors = list(etat["erreurs"])
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
    assert any("/in/" in e.value for e in at.error), [e.value for e in at.error]


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
    # « ailleurs » : celui qui est encore chez Thiga n'est pas la cible, une
    # fois l'entreprise écartée d'un clic.
    recolte_espionne["reponse"] = (
        [voisin("Marie Martin", "marie-martin", intitule="Lead Dev, Thiga")], "Thiga"
    )
    at = _trouver(_page_recherche())
    _bouton(at, "Écarter Thiga").click()
    at.run()

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

    expanders = [e for e in at.expander if "1 profil écarté" in e.label]
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
    assert any("Session LinkedIn manquante" in e.value for e in at.error), [e.value for e in at.error]


# --- Étape 2 : récupérer et inviter --------------------------------------

BOUTON_RECUPERER = "Récupérer les infos"


def test_l_etape_2_n_apparait_pas_avant_d_avoir_trouve():
    at = _page_recherche()
    assert not [b for b in at.button if b.key == "sim_btn_recuperer" or b.label.startswith(BOUTON_RECUPERER)], (
        "le bouton de récupération s'affiche alors qu'aucune liste n'existe"
    )


def test_les_urls_retenues_partent_dans_la_chaine_existante(recolte_espionne):
    recolte_espionne["reponse"] = (
        [voisin("Marie Martin", "marie-martin"), voisin("Paul Durand", "paul-durand")],
        None,
    )
    at = _trouver(_page_recherche())
    recolte_espionne["appels"].clear()

    at.button(key="sim_btn_recuperer").click()
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]

    assert recolte_espionne["appels"][0]["urls"] == [
        "https://www.linkedin.com/in/marie-martin/",
        "https://www.linkedin.com/in/paul-durand/",
    ]


def test_les_invitations_ne_partent_pas_sans_l_avoir_demande(recolte_espionne):
    # Le quota d'invitations est rare et l'envoi irréversible : la case doit
    # être décochée par défaut.
    recolte_espionne["reponse"] = ([voisin("Marie Martin", "marie-martin")], None)
    at = _trouver(_page_recherche())
    recolte_espionne["appels"].clear()

    at.button(key="sim_btn_recuperer").click()
    at.run()

    assert recolte_espionne["appels"][0]["inviter"] is False


def test_la_case_cochee_fait_partir_les_invitations(recolte_espionne):
    recolte_espionne["reponse"] = ([voisin("Marie Martin", "marie-martin")], None)
    at = _trouver(_page_recherche())
    at.checkbox(key="sim_inviter").set_value(True)
    at.run()
    recolte_espionne["appels"].clear()

    at.button(key="sim_btn_recuperer").click()
    at.run()

    assert recolte_espionne["appels"][0]["inviter"] is True


def test_la_liste_trouvee_survit_au_rerun_de_l_etape_2(recolte_espionne):
    # Elle vit dans session_state justement pour ça : un clic sur l'étape 2
    # relance le script, et la liste ne doit pas disparaître de l'écran.
    recolte_espionne["reponse"] = ([voisin("Marie Martin", "marie-martin")], None)
    at = _trouver(_page_recherche())

    at.button(key="sim_btn_recuperer").click()
    at.run()

    assert [p["nom"] for p in at.session_state["sim_retenues"]] == ["Marie Martin"]


# --- Entreprise à écarter : saisie manuelle quand elle n'a pas été lue ----


def test_entreprise_non_lue_le_champ_est_vide_puis_la_saisie_ecarte(recolte_espionne):
    recolte_espionne["reponse"] = (
        [voisin("Marie Martin", "marie-martin", intitule="Lead Dev, Kering")], None
    )
    at = _trouver(_page_recherche())

    assert at.text_input(key="sim_entreprise_exclue").value == ""
    assert [p["nom"] for p in at.session_state["sim_retenues"]] == ["Marie Martin"]

    at.text_input(key="sim_entreprise_exclue").set_value("Kering")
    at.run()

    assert at.session_state["sim_retenues"] == []
    assert at.session_state["sim_ecartees"][0]["motif"] == "encore chez Kering"
    assert recolte_espionne["recoltes"] == 1


def test_entreprise_lue_le_champ_reste_vide_et_elle_est_proposee(recolte_espionne):
    # Par défaut rien n'est écarté hors fichier et 1er degré : l'entreprise
    # lue n'est que proposée, jamais appliquée d'office.
    recolte_espionne["reponse"] = (
        [voisin("Marie Martin", "marie-martin", intitule="Lead Dev, Thiga")], "Thiga"
    )
    at = _trouver(_page_recherche())

    assert at.text_input(key="sim_entreprise_exclue").value == ""
    assert [p["nom"] for p in at.session_state["sim_retenues"]] == ["Marie Martin"]
    assert any("Thiga" in c.value for c in at.caption), [c.value for c in at.caption]
    assert [b for b in at.button if b.label == "Écarter Thiga"]


def test_ecarter_l_entreprise_proposee_remplit_le_champ_et_ecarte(recolte_espionne):
    recolte_espionne["reponse"] = (
        [voisin("Marie Martin", "marie-martin", intitule="Lead Dev, Thiga"),
         voisin("Paul Durand", "paul-durand", intitule="Lead Dev, Kering")],
        "Thiga",
    )
    at = _trouver(_page_recherche())

    _bouton(at, "Écarter Thiga").click()
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]

    assert at.text_input(key="sim_entreprise_exclue").value == "Thiga"
    assert [p["nom"] for p in at.session_state["sim_retenues"]] == ["Paul Durand"]
    assert at.session_state["sim_ecartees"][0]["motif"] == "encore chez Thiga"
    assert recolte_espionne["recoltes"] == 1


def test_entreprise_non_lue_aucune_proposition(recolte_espionne):
    recolte_espionne["reponse"] = ([voisin("Marie Martin", "marie-martin")], None)
    at = _trouver(_page_recherche())

    assert not [b for b in at.button if b.label.startswith("Écarter ")]
    assert any("n'a pas pu être lue" in c.value for c in at.caption)


def test_un_profil_suivre_seulement_est_retenu_par_defaut(recolte_espionne):
    recolte_espionne["reponse"] = (
        [voisin("Marie Martin", "marie-martin", invitable=False)], None
    )
    at = _trouver(_page_recherche())

    assert at.checkbox(key="sim_invitables").value is False
    assert [p["nom"] for p in at.session_state["sim_retenues"]] == ["Marie Martin"]


def test_cocher_invitables_ecarte_le_profil_suivre_seulement(recolte_espionne):
    recolte_espionne["reponse"] = (
        [voisin("Marie Martin", "marie-martin", invitable=False)], None
    )
    at = _trouver(_page_recherche())

    at.checkbox(key="sim_invitables").set_value(True)
    at.run()

    assert at.session_state["sim_retenues"] == []
    assert len(at.session_state["sim_ecartees"]) == 1


def test_changer_le_mot_apres_trouver_refiltre_sans_nouvelle_recolte(recolte_espionne):
    recolte_espionne["reponse"] = (
        [
            voisin("Marie Martin", "marie-martin", intitule="Product Manager, Kering"),
            voisin("Paul Durand", "paul-durand", intitule="Data Engineer, Kering"),
        ],
        None,
    )
    at = _trouver(_page_recherche())
    assert len(at.session_state["sim_retenues"]) == 2

    at.text_input(key="sim_mot").set_value("Product")
    at.run()

    assert [p["nom"] for p in at.session_state["sim_retenues"]] == ["Marie Martin"]
    assert recolte_espionne["recoltes"] == 1


# --- Invitations : jamais cochées d'office, jamais au-delà du plafond ------


def test_une_nouvelle_liste_decoche_les_invitations(recolte_espionne):
    recolte_espionne["reponse"] = ([voisin("Marie Martin", "marie-martin")], None)
    at = _trouver(_page_recherche())
    at.checkbox(key="sim_inviter").set_value(True)
    at.run()
    assert at.checkbox(key="sim_inviter").value is True

    at = _trouver(at)
    assert at.checkbox(key="sim_inviter").value is False

    recolte_espionne["appels"].clear()
    at.button(key="sim_btn_recuperer").click()
    at.run()
    assert recolte_espionne["appels"][0]["inviter"] is False


def test_au_dela_du_plafond_du_jour_rien_ne_part(recolte_espionne):
    recolte_espionne["reponse"] = (
        [voisin("Marie Martin", "marie-martin"), voisin("Paul Durand", "paul-durand"),
         voisin("Anne Petit", "anne-petit")],
        None,
    )
    at = _trouver(_page_recherche())
    at.checkbox(key="sim_inviter").set_value(True)
    at.run()
    recolte_espionne["invitations_restantes"] = 2
    recolte_espionne["appels"].clear()

    at.button(key="sim_btn_recuperer").click()
    at.run()

    assert recolte_espionne["appels"] == []
    messages = [e.value for e in at.error]
    assert any("2 invitations" in m and "3 profils retenus" in m for m in messages), messages


def test_dans_le_plafond_ou_sans_invitation_la_chaine_part(recolte_espionne):
    recolte_espionne["reponse"] = (
        [voisin("Marie Martin", "marie-martin"), voisin("Paul Durand", "paul-durand")],
        None,
    )
    at = _trouver(_page_recherche())
    recolte_espionne["invitations_restantes"] = 0
    recolte_espionne["appels"].clear()

    # Plafond atteint mais pas d'invitation demandée : le scrape part.
    at.button(key="sim_btn_recuperer").click()
    at.run()
    assert len(recolte_espionne["appels"]) == 1

    recolte_espionne["invitations_restantes"] = 2
    at.checkbox(key="sim_inviter").set_value(True)
    at.run()
    recolte_espionne["appels"].clear()
    at.button(key="sim_btn_recuperer").click()
    at.run()
    assert recolte_espionne["appels"][0]["inviter"] is True


# --- Les filtres survivent à un changement de page -------------------------


def test_les_filtres_survivent_a_un_aller_retour_par_une_autre_page(recolte_espionne):
    # Streamlit abandonne l'état d'un widget dès qu'un rerun ne le dessine pas,
    # et les pages sont des branches d'un même script : sans parade, revenir
    # sur Recherche vide « Entreprise à écarter » alors que la liste, elle,
    # survit — et on y revoit en silence ceux qui sont encore chez Thiga.
    recolte_espionne["reponse"] = (
        [
            voisin("Marie Martin", "marie-martin", intitule="Product Manager, Thiga"),
            voisin("Paul Durand", "paul-durand", intitule="Product Manager, Kering"),
        ],
        "Thiga",
    )
    at = _page_recherche()
    at.text_input(key="sim_mot").set_value("Product")
    at = _trouver(at)
    assert at.text_input(key="sim_entreprise_exclue").value == ""
    _bouton(at, "Écarter Thiga").click()
    at.run()
    assert at.text_input(key="sim_entreprise_exclue").value == "Thiga"
    assert [p["nom"] for p in at.session_state["sim_retenues"]] == ["Paul Durand"]

    at.session_state["page"] = "💾 Historique"
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    at.session_state["page"] = "🔍 Recherche"
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]

    assert at.text_input(key="sim_entreprise_exclue").value == "Thiga"
    assert at.text_input(key="sim_mot").value == "Product"
    assert at.checkbox(key="sim_invitables").value is False
    assert [p["nom"] for p in at.session_state["sim_retenues"]] == ["Paul Durand"]
    assert recolte_espionne["recoltes"] == 1


def test_la_case_invitables_cochee_survit_a_un_changement_de_page(recolte_espionne):
    recolte_espionne["reponse"] = ([voisin("Marie Martin", "marie-martin")], None)
    at = _page_recherche()
    at.checkbox(key="sim_invitables").set_value(True)
    at = _trouver(at)

    at.session_state["page"] = "💾 Historique"
    at.run()
    at.session_state["page"] = "🔍 Recherche"
    at.run()

    assert at.checkbox(key="sim_invitables").value is True


# --- Les avertissements se voient, l'avancement aussi ----------------------


def _dans_l_ordre(at):
    """Les éléments de l'écran dans l'ordre d'affichage (parcours en profondeur)."""
    def parcourir(noeud):
        yield noeud
        for enfant in getattr(noeud, "children", {}).values():
            yield from parcourir(enfant)
    return list(parcourir(at.main))


def test_les_avertissements_s_affichent_juste_sous_le_bouton_trouver(recolte_espionne):
    # Au premier essai réel, l'avertissement était rendu sous le champ
    # entreprise et le tableau : la personne ne l'a pas vu.
    recolte_espionne["reponse"] = ([voisin("Marie Martin", "marie-martin")], "Thiga")
    recolte_espionne["erreurs"] = ["Liste partielle (test) : seuls les 1 profils visibles"]
    at = _trouver(_page_recherche())

    ordre = _dans_l_ordre(at)

    def position(predicat, quoi):
        for i, n in enumerate(ordre):
            if predicat(n):
                return i
        raise AssertionError(f"introuvable à l'écran : {quoi}")

    bouton = position(lambda n: getattr(n, "type", None) == "button"
                      and getattr(n, "label", None) == BOUTON_TROUVER, "bouton Trouver")
    alerte = position(lambda n: getattr(n, "type", None) == "warning"
                      and "Liste partielle" in str(getattr(n, "value", "")), "avertissement")
    champ = position(lambda n: getattr(n, "type", None) == "text_input"
                     and getattr(n, "key", None) == "sim_entreprise_exclue", "champ entreprise")
    succes = position(lambda n: getattr(n, "type", None) == "success"
                      and "retenu" in str(getattr(n, "value", "")), "compte des retenus")

    assert bouton < alerte < champ < succes


def test_l_avancement_de_la_recolte_reste_affiche(recolte_espionne):
    # Le rappel d'étape écrit dans un bloc d'état qui reste à l'écran, et
    # qui dit à la fin combien de profils ont été lus.
    recolte_espionne["reponse"] = (
        [voisin("Marie Martin", "marie-martin"), voisin("Paul Durand", "paul-durand")], None
    )
    recolte_espionne["etapes"] = ["👤 Ouverture du profil de référence..."]
    at = _trouver(_page_recherche())

    etats = [n for n in _dans_l_ordre(at) if getattr(n, "type", None) == "status"
             and "voisin" in str(getattr(n, "label", ""))]
    assert etats, "aucun bloc d'avancement à l'écran"
    assert "2 profils voisins lus" in etats[0].label


@pytest.fixture
def avertissements_streamlit(monkeypatch):
    """Capte les avertissements que Streamlit écrit dans son journal.

    Ce ne sont pas des warnings Python : `-W error` ne les voit pas, et le
    journal de Streamlit ne remonte pas jusqu'à caplog (propagate=False).
    On s'y branche donc directement. Streamlit n'émet celui-ci qu'une fois
    par processus : on remet son drapeau à zéro, sinon un test précédent
    le masquerait.
    """
    from streamlit.elements.lib import policies

    monkeypatch.setattr(policies, "_shown_default_value_warning", False)
    messages = []

    class Collecteur(logging.Handler):
        def emit(self, record):
            messages.append(record.getMessage())

    journal = logging.getLogger("streamlit.elements.lib.policies")
    collecteur = Collecteur(level=logging.WARNING)
    journal.addHandler(collecteur)
    yield messages
    journal.removeHandler(collecteur)


def test_aucun_widget_n_a_a_la_fois_une_valeur_par_defaut_et_une_valeur_en_session(
        recolte_espionne, avertissements_streamlit):
    # Vu au premier essai réel : « The widget with key "sim_invitables" was
    # created with a default value but also had its value set via the
    # Session State API. » — value=True plus la réaffectation qui retient
    # les filtres d'une page à l'autre.
    recolte_espionne["reponse"] = ([voisin("Marie Martin", "marie-martin")], None)
    at = _trouver(_page_recherche())
    at.text_input(key="sim_mot").set_value("Product")
    at.run()
    at.session_state["page"] = "💾 Historique"
    at.run()
    at.session_state["page"] = "🔍 Recherche"
    at.run()

    assert not any("default value" in m for m in avertissements_streamlit), (
        avertissements_streamlit
    )
    assert at.checkbox(key="sim_invitables").value is False
