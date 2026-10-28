# -*- coding: utf-8 -*-
"""Séances courtes et pauses entre séances (tâche 4 du rythme humain).

L'horloge est passée en paramètre : aucun test n'attend, aucun ne lance de
navigateur ni ne touche LinkedIn.
"""

from datetime import datetime

import pandas as pd
import pytest

import scraper_v2
from scraper_v2_sync import LinkedInScraperV2Sync
from utils.seances import (debut_action, fin_action, message_refus, numero_seance,
                           noter_verification, verification_permise)
from utils.verrou_linkedin import MESSAGE_OCCUPE, session_linkedin


def h(heure: str, jour: int = 28) -> datetime:
    hh, mm = heure.split(":")
    return datetime(2026, 10, jour, int(hh), int(mm))


PAUSE_10_51 = "Pause entre deux séances : prochaine action possible à 10:51."
QUATRE_SEANCES = "Vous avez fait 4 séances aujourd'hui. Vous pourrez reprendre demain."
VERIF_FAITE = "Vérification déjà faite aujourd'hui. Vous pourrez la refaire demain."


def _seance(dossier, debut: str, fin: str, pages: int, jour: int = 28):
    """Une action permise de `debut` à `fin`, qui a lu `pages` pages."""
    refus, _ = debut_action(dossier, h(debut, jour))
    assert refus is None
    fin_action(dossier, h(fin, jour), pages, debut=h(debut, jour))


# ── Règles de séance ─────────────────────────────────────────────────────

def test_premiere_action_ouvre_une_seance(tmp_path):
    d = str(tmp_path)
    assert debut_action(d, h("10:00")) == (None, 25)
    fin_action(d, h("10:05"), 8, debut=h("10:00"))
    # La séance est ouverte : elle compte pour le jour.
    assert (tmp_path / "seances.json").exists()


def test_deuxieme_appel_dans_la_fenetre_continue_la_seance(tmp_path):
    d = str(tmp_path)
    _seance(d, "10:00", "10:05", 8)
    # Chercher puis inviter : une seule séance, plafond partagé.
    assert debut_action(d, h("10:12")) == (None, 17)


def test_un_appel_commence_dans_la_fenetre_reste_dans_la_seance(tmp_path):
    d = str(tmp_path)
    _seance(d, "10:00", "10:05", 8)
    # Commencé à 10:25, fini à 10:31 : même séance, la pause part de 10:31.
    _seance(d, "10:25", "10:31", 4)
    assert debut_action(d, h("10:40"))[0] == PAUSE_10_51
    assert debut_action(d, h("10:51")) == (None, 25)


def test_refus_de_pause_dit_l_heure(tmp_path):
    d = str(tmp_path)
    _seance(d, "10:00", "10:31", 10)
    # Fenêtre de 30 minutes dépassée à 10:40 : nouvelle séance, pause de 20 min.
    assert debut_action(d, h("10:40")) == (PAUSE_10_51, 0)


def test_l_heure_de_reprise_est_arrondie_a_la_minute_superieure(tmp_path):
    d = str(tmp_path)
    debut_action(d, h("10:00"))
    fin_action(d, datetime(2026, 10, 28, 10, 31, 20), 3, debut=h("10:00"))
    refus, _ = debut_action(d, h("10:51"))
    assert refus == "Pause entre deux séances : prochaine action possible à 10:52."


def test_cinquieme_seance_refusee(tmp_path):
    d = str(tmp_path)
    for debut, fin in (("08:00", "08:10"), ("09:00", "09:10"),
                       ("10:00", "10:10"), ("11:00", "11:10")):
        _seance(d, debut, fin, 5)
    assert debut_action(d, h("12:00")) == (QUATRE_SEANCES, 0)
    # Le lendemain, on reprend.
    assert debut_action(d, h("08:00", jour=29)) == (None, 25)


def test_seance_close_a_25_pages(tmp_path):
    d = str(tmp_path)
    _seance(d, "10:00", "10:08", 25)
    # Encore dans la fenêtre, mais plus de pages : la séance est close.
    refus, _ = debut_action(d, h("10:10"))
    assert refus == "Pause entre deux séances : prochaine action possible à 10:28."


def test_une_action_sans_page_ne_change_rien(tmp_path):
    d = str(tmp_path)
    debut_action(d, h("10:00"))
    fin_action(d, h("10:01"), 0, debut=h("10:00"))
    assert not (tmp_path / "seances.json").exists()


def test_une_verification_par_jour(tmp_path):
    d = str(tmp_path)
    assert verification_permise(d, h("09:00")) is None
    noter_verification(d, h("09:00"))
    assert verification_permise(d, h("17:00")) == VERIF_FAITE
    assert verification_permise(d, h("09:00", jour=29)) is None


def test_etat_illisible_repart_de_zero(tmp_path):
    (tmp_path / "seances.json").write_text("{cassé", encoding="utf-8")
    assert debut_action(str(tmp_path), h("10:00")) == (None, 25)
    assert verification_permise(str(tmp_path), h("10:00")) is None
    (tmp_path / "seances.json").write_text('{"seances": [{"debut": 3}]}', encoding="utf-8")
    assert debut_action(str(tmp_path), h("10:00")) == (None, 25)


def test_message_refus_reconnait_les_refus():
    assert message_refus(["autre", PAUSE_10_51]) == PAUSE_10_51
    assert message_refus([QUATRE_SEANCES]) == QUATRE_SEANCES
    assert message_refus([VERIF_FAITE]) == VERIF_FAITE
    assert message_refus(["Séance terminée : 25 pages consultées."]) is None
    assert message_refus(None) is None


# ── Câblage dans le wrapper synchrone ────────────────────────────────────

ACTIONS = [
    ("run_scraper", "run_scraper_async",
     {"cookie": "c", "keyword": "pm", "entreprises": [], "nb_profils": 5, "ecoles_ids": []}, "df"),
    ("run_url_scraper", "run_url_scraper_async",
     {"cookie": "c", "urls": ["https://www.linkedin.com/in/a/"]}, "df"),
    ("recolter_browsemap", "recolter_browsemap_async",
     {"cookie": "c", "url_reference": "https://www.linkedin.com/in/a/"}, ([], None)),
    ("verifier_acceptations", "verifier_acceptations_async",
     {"cookie": "c", "profils": [{"url": "https://www.linkedin.com/in/a/"}]}, []),
    ("envoyer_messages", "envoyer_messages_async",
     {"cookie": "c", "cibles": [{"url": "https://www.linkedin.com/in/a/"}], "message": "m"}, []),
]


def _vide(resultat, vide):
    if vide == "df":
        return isinstance(resultat, pd.DataFrame) and resultat.empty
    return resultat == vide


@pytest.fixture
def chrome_espion(monkeypatch):
    """Remplace async_playwright : tout appel serait une ouverture de Chrome."""
    appels = []

    def espion(*a, **k):
        appels.append(1)
        raise AssertionError("Chrome ouvert malgré le refus")

    monkeypatch.setattr(scraper_v2, "async_playwright", espion)
    return appels


@pytest.mark.parametrize("methode,_async,kwargs,vide", ACTIONS)
def test_refus_de_pause_n_ouvre_pas_chrome(tmp_path, chrome_espion, methode, _async, kwargs, vide):
    _seance(str(tmp_path), "10:00", "10:31", 10)
    wrapper = LinkedInScraperV2Sync(use_database=False, config_dir=str(tmp_path))
    wrapper._horloge = lambda: h("10:40")

    resultat = getattr(wrapper, methode)(**kwargs)

    assert chrome_espion == []
    assert _vide(resultat, vide)
    assert wrapper.errors == [PAUSE_10_51]
    # Le refus n'a pris aucun verrou.
    assert not (tmp_path / "session_linkedin.lock").exists()


def _fausse_action(wrapper, nom_async, pages, verifiees=()):
    """Remplace l'action async : lit `pages` pages et vérifie la limite reçue."""
    vu = {}

    async def action(**kwargs):
        vu["limite"] = wrapper.scraper.limite_pages_seance
        vu["depart"] = wrapper.scraper.pages_cette_seance
        wrapper.scraper.pages_cette_seance += pages
        wrapper.scraper.verifiees = list(verifiees)
        if nom_async in ("run_scraper_async", "run_url_scraper_async"):
            return pd.DataFrame()
        if nom_async == "recolter_browsemap_async":
            return [], None
        return []

    return action, vu


@pytest.mark.parametrize("methode,nom_async,kwargs,vide", ACTIONS)
def test_une_action_permise_compte_ses_pages_dans_la_seance(tmp_path, monkeypatch,
                                                           methode, nom_async, kwargs, vide):
    d = str(tmp_path)
    _seance(d, "10:00", "10:05", 8)
    wrapper = LinkedInScraperV2Sync(use_database=False, config_dir=d)
    wrapper.scraper.pages_cette_seance = 99  # reste d'un appel précédent
    wrapper._horloge = lambda: h("10:12")
    action, vu = _fausse_action(wrapper, nom_async, 6, verifiees=["u"])
    monkeypatch.setattr(wrapper.scraper, nom_async, action)

    getattr(wrapper, methode)(**kwargs)

    assert vu == {"limite": 17, "depart": 0}
    # 8 + 6 pages : il en reste 11 dans la même séance.
    assert debut_action(d, h("10:15")) == (None, 11)


def test_la_verification_est_notee_seulement_si_une_page_a_ete_lue(tmp_path, monkeypatch):
    d = str(tmp_path)
    wrapper = LinkedInScraperV2Sync(use_database=False, config_dir=d)
    wrapper._horloge = lambda: h("10:00")
    action, _ = _fausse_action(wrapper, "verifier_acceptations_async", 0, verifiees=[])
    monkeypatch.setattr(wrapper.scraper, "verifier_acceptations_async", action)
    wrapper.verifier_acceptations(cookie="c", profils=[])
    assert verification_permise(d, h("11:00")) is None

    action, _ = _fausse_action(wrapper, "verifier_acceptations_async", 2, verifiees=["u"])
    monkeypatch.setattr(wrapper.scraper, "verifier_acceptations_async", action)
    wrapper.verifier_acceptations(cookie="c", profils=[])
    assert verification_permise(d, h("11:00")) == VERIF_FAITE


def test_une_deuxieme_verification_est_refusee_sans_chrome(tmp_path, chrome_espion):
    d = str(tmp_path)
    noter_verification(d, h("09:00"))
    wrapper = LinkedInScraperV2Sync(use_database=False, config_dir=d)
    wrapper._horloge = lambda: h("15:00")

    assert wrapper.verifier_acceptations(cookie="c", profils=[{"url": "u"}]) == []
    assert wrapper.errors == [VERIF_FAITE]
    assert chrome_espion == []
    # Refusée avant tout : aucune séance ouverte.
    assert debut_action(d, h("15:01")) == (None, 25)


def test_session_occupee_n_ouvre_ni_ne_consomme_de_seance(tmp_path, monkeypatch):
    d = str(tmp_path)
    _seance(d, "10:00", "10:05", 8)
    avant = (tmp_path / "seances.json").read_text(encoding="utf-8")
    wrapper = LinkedInScraperV2Sync(use_database=False, config_dir=d)
    wrapper._horloge = lambda: h("10:12")
    action, _ = _fausse_action(wrapper, "run_url_scraper_async", 6)
    monkeypatch.setattr(wrapper.scraper, "run_url_scraper_async", action)

    with session_linkedin(d, "veille"):
        wrapper.run_url_scraper(cookie="c", urls=["https://www.linkedin.com/in/a/"])

    assert wrapper.errors == [MESSAGE_OCCUPE.format(activite="veille")]
    assert (tmp_path / "seances.json").read_text(encoding="utf-8") == avant


def test_une_action_qui_echoue_compte_quand_meme_ses_pages(tmp_path, monkeypatch):
    d = str(tmp_path)
    wrapper = LinkedInScraperV2Sync(use_database=False, config_dir=d)
    wrapper._horloge = lambda: h("10:00")

    async def plante(**kwargs):
        wrapper.scraper.pages_cette_seance += 3
        raise RuntimeError("Chrome introuvable")

    monkeypatch.setattr(wrapper.scraper, "envoyer_messages_async", plante)
    assert wrapper.envoyer_messages(cookie="c", cibles=[], message="m") == []
    assert debut_action(d, h("10:05")) == (None, 22)


# ── Pages du jour épuisées : refus avant le verrou et avant Chrome ───────

LIMITE_60_PAGES = ("Limite du jour atteinte : 60 pages LinkedIn consultées. "
                   "Vous pourrez reprendre demain.")


@pytest.mark.parametrize("methode,_async,kwargs,vide", ACTIONS)
def test_pages_du_jour_epuisees_refus_sans_chrome(tmp_path, chrome_espion, methode, _async,
                                                  kwargs, vide):
    d = str(tmp_path)
    wrapper = LinkedInScraperV2Sync(use_database=False, config_dir=d)
    wrapper.scraper.human.daily_limits.increment_pages(60)
    wrapper._horloge = lambda: h("10:00")

    resultat = getattr(wrapper, methode)(**kwargs)

    assert chrome_espion == []
    assert _vide(resultat, vide)
    assert wrapper.errors == [LIMITE_60_PAGES]
    assert not (tmp_path / "session_linkedin.lock").exists()
    # État de séance inchangé : rien d'écrit.
    assert not (tmp_path / "seances.json").exists()


def test_message_refus_reconnait_la_limite_de_pages():
    assert message_refus(["autre", LIMITE_60_PAGES]) == LIMITE_60_PAGES


# ── Numéro de la séance : la 4e du jour dit « demain » à sa fin ──────────

def test_numero_de_la_seance_de_l_action(tmp_path):
    d = str(tmp_path)
    assert numero_seance(d, h("09:00")) == 1
    _seance(d, "09:00", "09:10", 25)
    _seance(d, "09:40", "09:50", 25)
    _seance(d, "10:20", "10:30", 5)
    # Dans la 3e séance, encore ouverte.
    assert numero_seance(d, h("10:35")) == 3
    # Après la pause : la 4e.
    assert numero_seance(d, h("11:10")) == 4


def test_l_enveloppe_signale_la_derniere_seance_du_jour(tmp_path, monkeypatch):
    d = str(tmp_path)
    for debut, fin in (("08:00", "08:10"), ("08:40", "08:50"), ("09:20", "09:30")):
        _seance(d, debut, fin, 25)
    wrapper = LinkedInScraperV2Sync(use_database=False, config_dir=d)
    action, _ = _fausse_action(wrapper, "run_url_scraper_async", 1)
    monkeypatch.setattr(wrapper.scraper, "run_url_scraper_async", action)

    wrapper._horloge = lambda: h("10:00")
    wrapper.run_url_scraper(cookie="c", urls=["https://www.linkedin.com/in/a/"])
    assert wrapper.scraper.derniere_seance_du_jour is True


def test_une_seance_qui_n_est_pas_la_derniere(tmp_path, monkeypatch):
    wrapper = LinkedInScraperV2Sync(use_database=False, config_dir=str(tmp_path))
    action, _ = _fausse_action(wrapper, "run_url_scraper_async", 1)
    monkeypatch.setattr(wrapper.scraper, "run_url_scraper_async", action)
    wrapper._horloge = lambda: h("10:00")
    wrapper.run_url_scraper(cookie="c", urls=["https://www.linkedin.com/in/a/"])
    assert wrapper.scraper.derniere_seance_du_jour is False
