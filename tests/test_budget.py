# -*- coding: utf-8 -*-
import json
from datetime import date

from config import ScraperConfig
from utils.budget import Budget, budget_du_jour


def test_sans_fichier_le_budget_est_entier(tmp_path):
    b = budget_du_jour(str(tmp_path))
    assert b.utilisees == 0
    assert b.restantes == ScraperConfig.MAX_INVITATIONS_PER_DAY


def test_lit_le_compteur_du_moteur_du_jour(tmp_path):
    (tmp_path / "daily_limits.json").write_text(json.dumps(
        {"date": date.today().isoformat(), "invitations_sent": 7}))
    assert budget_du_jour(str(tmp_path)).utilisees == 7


def test_un_compteur_d_hier_ne_compte_plus(tmp_path):
    (tmp_path / "daily_limits.json").write_text(json.dumps(
        {"date": "2000-01-01", "invitations_sent": 19}))
    assert budget_du_jour(str(tmp_path)).utilisees == 0


def test_restantes_jamais_negatives():
    assert Budget(utilisees=25, plafond=20).restantes == 0
    assert Budget(utilisees=25, plafond=20).epuise


def test_une_nouvelle_session_garde_le_compteur_de_la_personne(tmp_path):
    from scraper_v2 import LinkedInScraperV2
    from utils.human_behavior import HumanBehavior
    s = object.__new__(LinkedInScraperV2)
    fichier = str(tmp_path / "daily_limits.json")
    s.human = HumanBehavior(fatigue_factor=0.5, limits_file=fichier)
    neuf = s._nouvelle_session_humaine()
    assert neuf.daily_limits.limits_file == fichier
    assert neuf.fatigue_factor == 0.0
