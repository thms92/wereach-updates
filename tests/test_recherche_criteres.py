# -*- coding: utf-8 -*-
"""Onglet « Par critères » : chercher sans inviter, choisir, puis inviter."""

import pandas as pd
import pytest

from utils.verrou_linkedin import VerrouOccupe

import scraper_v2_sync
import ui.invitations
from tests.conftest import lancer_app, verifier_page_affichee
from utils.budget import Budget

PAGE = "🔍 Recherche"
TROUVES = pd.DataFrame([
    {"Nom": f"Exemple {i}", "Poste": "Product Manager", "Entreprise": "Société Démo",
     "URL du profil": f"https://www.linkedin.com/in/exemple-{i}/", "Invitation envoyée": "Non"}
    for i in range(3)
])


@pytest.fixture
def espion(monkeypatch):
    etat = {"recherches": [], "invitations": [], "df": TROUVES}
    monkeypatch.setattr(ui.invitations, "budget_du_jour", lambda _d: Budget(utilisees=5, plafond=20))

    class FauxScraper:
        def __init__(self, **kwargs):
            self.errors = []
            self.ecartes_reseau = etat.get("ecartes", 0)

        def run_scraper(self, **kwargs):
            etat["recherches"].append(kwargs)
            self.errors = list(etat.get("erreurs_recherche", []))
            return etat["df"]

        def run_url_scraper(self, **kwargs):
            etat["invitations"].append(kwargs)
            self.errors = list(etat.get("erreurs_invitation", []))
            return etat.get("df_invitation", pd.DataFrame())

    monkeypatch.setattr(scraper_v2_sync, "LinkedInScraperV2Sync", FauxScraper)
    return etat


def _rechercher(mots="Product Manager"):
    at = lancer_app(PAGE)
    verifier_page_affichee(at, PAGE)
    at.session_state["global_cookie"] = "COOKIE-DE-TEST"
    at.run()
    at.text_input(key="crit_mots").set_value(mots)
    at.button(key="btn_rechercher").click()
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


def test_la_recherche_n_invite_jamais(espion):
    at = _rechercher()
    assert len(espion["recherches"]) == 1
    assert espion["recherches"][0]["inviter"] is False
    assert len(at.session_state["crit_profils"]) == 3


def test_choisir_puis_inviter_les_seuls_profils_choisis(espion):
    at = _rechercher()
    assert at.button(key="crit_btn_recuperer").label == "Inviter 3 profils choisis"
    at.button(key="crit_rien").click().run()
    assert "Cochez au moins un profil" in " ".join(c.value for c in at.caption)
    at.button(key="crit_tout").click().run()
    at.button(key="crit_btn_recuperer").click().run()
    assert espion["invitations"] == [], "le premier clic montre le récapitulatif"
    at.button(key="confirmer_crit_ok").click().run()
    assert len(espion["invitations"]) == 1
    appel = espion["invitations"][0]
    assert appel["inviter"] is True and len(appel["urls"]) == 3


def test_une_recherche_vide_n_affiche_ni_tableau_ni_envoi(espion):
    espion["df"] = pd.DataFrame()
    at = _rechercher()
    assert any("Aucun nouveau profil" in i.value for i in at.info)
    assert not [b for b in at.button if b.key == "crit_btn_recuperer"]


def test_la_liste_survit_a_un_aller_retour(espion):
    at = _rechercher()
    at.session_state["page"] = "💾 Historique"
    at.run()
    at.session_state["page"] = PAGE
    at.run()
    assert len(at.session_state["crit_profils"]) == 3
    assert at.button(key="crit_btn_recuperer").label == "Inviter 3 profils choisis"


def test_sans_critere_rien_ne_part(espion):
    at = _rechercher(mots="")
    assert espion["recherches"] == []
    assert any("au moins un filtre" in e.value for e in at.error)


def test_les_profils_deja_en_relation_ou_invites_sont_comptes(espion):
    espion["ecartes"] = 4
    at = _rechercher()
    assert any("4 profils déjà dans votre réseau ou déjà invités ont été écartés" in c.value
               for c in at.caption)


# ── Refus de séance (pause, séances du jour) : dit en clair ──
PAUSE = "Pause entre deux séances : prochaine action possible à 10:51."


def test_une_recherche_refusee_dit_le_refus_et_pas_aucun_profil(espion):
    espion["df"] = pd.DataFrame()
    espion["erreurs_recherche"] = [PAUSE]
    at = _rechercher()
    assert any(PAUSE in w.value for w in at.warning)
    assert not any("Aucun nouveau profil" in i.value for i in at.info)
    assert at.session_state["crit_profils"] is None


def test_une_invitation_refusee_dit_le_refus_et_pas_aucun_profil(espion):
    espion["erreurs_invitation"] = [PAUSE]
    at = _rechercher()
    at.button(key="crit_btn_recuperer").click().run()
    at.button(key="confirmer_crit_ok").click().run()
    assert not at.exception
    assert any(PAUSE in e.value for e in at.error)
    assert not any("Aucun profil récupéré" in w.value for w in at.warning)


# ── Arrêt sans résultat (session occupée, limite du jour) : la cause en clair ──

LIMITE_PAGES = ("Limite du jour atteinte : 60 pages LinkedIn consultées. "
                "Vous pourrez reprendre demain.")


def test_une_invitation_refusee_faute_de_pages_le_dit_en_clair(espion):
    # Pages du jour épuisées : refus avant Chrome, dit comme les autres refus.
    espion["erreurs_invitation"] = [LIMITE_PAGES]
    at = _rechercher()
    at.button(key="crit_btn_recuperer").click().run()
    at.button(key="confirmer_crit_ok").click().run()
    assert not at.exception
    assert [e.value for e in at.error] == [LIMITE_PAGES]
    assert not any("Aucun profil récupéré" in w.value for w in at.warning)


def test_une_recherche_arretee_par_la_limite_garde_ses_profils(espion):
    # Limite atteinte en cours de recherche : les profils déjà lus restent,
    # la limite est dite au-dessus.
    espion["erreurs_recherche"] = [LIMITE_PAGES]
    at = _rechercher()
    assert len(at.session_state["crit_profils"]) == 3
    assert any(LIMITE_PAGES in w.value for w in at.warning)


@pytest.mark.parametrize("erreur", [str(VerrouOccupe("veille"))])
def test_une_invitation_arretee_sans_resultat_dit_pourquoi(espion, erreur):
    espion["erreurs_invitation"] = [erreur]
    at = _rechercher()
    at.button(key="crit_btn_recuperer").click().run()
    at.button(key="confirmer_crit_ok").click().run()
    assert not at.exception
    assert any(erreur in w.value for w in at.warning)
    assert not any("Aucun profil récupéré" in w.value for w in at.warning)
    assert not any(e.label.startswith("Incidents") for e in at.expander)


# ── Arrêt en cours de passage : dit au-dessus des résultats ──

SEANCE_FINIE = "Séance terminée : 25 pages consultées. Prochaine séance possible dans 20 minutes."


def _dans_l_ordre(at):
    def parcourir(noeud):
        yield noeud
        for enfant in getattr(noeud, "children", {}).values():
            yield from parcourir(enfant)
    return list(parcourir(at.main))


@pytest.mark.parametrize("arret", [
    SEANCE_FINIE,
    LIMITE_PAGES,
    "Limite du jour atteinte : 20 invitations envoyées. Vous pourrez reprendre demain.",
    "Session LinkedIn expirée : mettez-la à jour dans la page Recherche.",
])
def test_un_arret_en_cours_d_invitation_se_voit_au_dessus_des_resultats(espion, arret):
    espion["df_invitation"] = TROUVES.head(2)
    espion["erreurs_invitation"] = [arret, "Profil illisible : exemple-9"]
    at = _rechercher()
    at.button(key="crit_btn_recuperer").click().run()
    at.button(key="confirmer_crit_ok").click().run()
    assert not at.exception
    ordre = _dans_l_ordre(at)
    alerte = next(i for i, n in enumerate(ordre) if getattr(n, "type", None) == "warning"
                  and getattr(n, "value", "") == arret)
    # Le bilan des résultats commence par ses boutons de suite.
    bilan = next(i for i, n in enumerate(ordre) if getattr(n, "type", None) == "button"
                 and getattr(n, "key", None) == "crit_vers_historique")
    assert alerte < bilan
    # Les autres incidents restent dans l'encadré, l'arrêt n'y est pas répété.
    incidents = [e for e in at.expander if e.label.startswith("Incidents")]
    assert incidents and incidents[0].label.endswith("(1)")


# ── Pages restantes de la séance, avant d'inviter ──

def _seance_restante(monkeypatch, restantes):
    monkeypatch.setattr(ui.invitations, "debut_action", lambda _d, _t: (None, restantes))


def test_le_recapitulatif_dit_les_pages_restantes_de_la_seance(espion, monkeypatch):
    _seance_restante(monkeypatch, 10)
    at = _rechercher()
    at.button(key="crit_btn_recuperer").click().run()
    recap = [m.value for m in at.markdown if m.value.startswith("Jusqu'à")]
    assert recap and "Il reste 9 pages dans cette séance." in recap[0]


@pytest.mark.parametrize("restantes,attendu", [
    (3, "Il reste 2 pages dans cette séance : sélectionnez-en 2 au plus, "
        "ou attendez la prochaine séance."),
    (2, "Il reste 1 page dans cette séance : sélectionnez-en 1 au plus, "
        "ou attendez la prochaine séance."),
])
def test_une_selection_plus_grande_que_la_seance_est_refusee(espion, monkeypatch,
                                                             restantes, attendu):
    _seance_restante(monkeypatch, restantes)
    at = _rechercher()
    assert [e.value for e in at.error] == [attendu]
    assert at.button(key="crit_btn_recuperer").disabled
    at.button(key="crit_btn_recuperer").click().run()
    assert espion["invitations"] == []


# ── Recherche arrêtée (budget, alerte) sans profil : pas « élargir les critères » ──

@pytest.mark.parametrize("arret", [
    SEANCE_FINIE,
    "Session LinkedIn expirée : mettez-la à jour dans la page Recherche.",
])
def test_une_recherche_arretee_ne_dit_pas_aucun_nouveau_profil(espion, arret):
    espion["df"] = pd.DataFrame()
    espion["erreurs_recherche"] = [arret]
    at = _rechercher()
    assert any(arret == w.value for w in at.warning)
    assert not any("Aucun nouveau profil" in i.value for i in at.info)
