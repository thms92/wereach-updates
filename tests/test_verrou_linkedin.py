# -*- coding: utf-8 -*-
"""Une seule session LinkedIn à la fois par utilisateur.

Deux fenêtres Chrome sur le même compte — la veille et une recherche manuelle
— c'est exactement le comportement qui fait repérer un compte.
"""

import json
import os
import time

import pandas as pd
import pytest

from scraper_v2_sync import LinkedInScraperV2Sync
from utils.human_behavior import DailyLimitsTracker
from utils.verrou_linkedin import MESSAGE_OCCUPE, VerrouOccupe, session_linkedin


def test_le_verrou_est_pris_puis_rendu(tmp_path):
    with session_linkedin(tmp_path, "veille"):
        assert (tmp_path / "session_linkedin.lock").exists()
    assert not (tmp_path / "session_linkedin.lock").exists()


def test_une_seconde_session_est_refusee(tmp_path):
    with session_linkedin(tmp_path, "veille"):
        with pytest.raises(VerrouOccupe) as e:
            with session_linkedin(tmp_path, "recherche"):
                pass
    assert e.value.activite == "veille"


def test_le_verrou_est_rendu_meme_sur_exception(tmp_path):
    with pytest.raises(RuntimeError):
        with session_linkedin(tmp_path, "veille"):
            raise RuntimeError("boum")
    with session_linkedin(tmp_path, "recherche"):
        pass


def test_le_verrou_d_un_processus_mort_est_libre(tmp_path):
    (tmp_path / "session_linkedin.lock").write_text(
        json.dumps({"pid": 999999, "activite": "veille", "debut": time.time()}))
    with session_linkedin(tmp_path, "recherche"):
        pass


def test_un_verrou_trop_ancien_est_libre(tmp_path):
    (tmp_path / "session_linkedin.lock").write_text(
        json.dumps({"pid": os.getpid(), "activite": "veille", "debut": time.time() - 4 * 3600}))
    with session_linkedin(tmp_path, "recherche"):
        pass


def test_un_verrou_illisible_est_libre(tmp_path):
    (tmp_path / "session_linkedin.lock").write_text("{cassé")
    with session_linkedin(tmp_path, "recherche"):
        pass


def test_sans_dossier_pas_de_verrou():
    with session_linkedin(None, "veille"):
        with session_linkedin(None, "recherche"):
            pass


def test_une_recherche_manuelle_pendant_la_veille_est_refusee_proprement(tmp_path, monkeypatch):
    wrapper = LinkedInScraperV2Sync(use_database=False, config_dir=str(tmp_path))

    async def ne_doit_pas_tourner(**kwargs):
        raise AssertionError("la recherche a tourné malgré le verrou")

    monkeypatch.setattr(wrapper.scraper, "run_scraper_async", ne_doit_pas_tourner)
    with session_linkedin(tmp_path, "veille"):
        df = wrapper.run_scraper(cookie="c", keyword="pm", entreprises=[], nb_profils=10, ecoles_ids=[])
    assert isinstance(df, pd.DataFrame) and df.empty
    assert wrapper.errors == [MESSAGE_OCCUPE.format(activite="veille")]


@pytest.mark.parametrize("methode,kwargs,vide", [
    ("run_url_scraper", {"cookie": "c", "urls": ["https://www.linkedin.com/in/a/"]}, "df"),
    ("recolter_browsemap", {"cookie": "c", "url_reference": "https://www.linkedin.com/in/a/"}, ([], None)),
    ("verifier_acceptations", {"cookie": "c", "profils": []}, []),
    ("envoyer_messages", {"cookie": "c", "cibles": [], "message": "m"}, []),
])
def test_toutes_les_sessions_respectent_le_verrou(tmp_path, methode, kwargs, vide):
    wrapper = LinkedInScraperV2Sync(use_database=False, config_dir=str(tmp_path))
    with session_linkedin(tmp_path, "veille"):
        resultat = getattr(wrapper, methode)(**kwargs)
    if vide == "df":
        assert resultat.empty
    else:
        assert resultat == vide
    assert wrapper.errors == [MESSAGE_OCCUPE.format(activite="veille")]


def test_le_compteur_de_pages_veille(tmp_path):
    fichier = str(tmp_path / "daily_limits.json")
    t = DailyLimitsTracker(limits_file=fichier)
    assert t.pages_veille_today == 0
    t.increment_pages_veille(3)
    assert DailyLimitsTracker(limits_file=fichier).pages_veille_today == 3
    assert t.profiles_today == 0  # les pages de veille ne mangent pas le quota de profils
