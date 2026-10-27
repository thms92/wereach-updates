"""Rythme humain : constantes et compteur de pages LinkedIn par jour."""
import json
from datetime import date, timedelta

from config import ScraperConfig
from utils.human_behavior import DailyLimitsTracker


def test_compteur_de_pages_par_jour(tmp_path):
    t = DailyLimitsTracker(max_pages=3, limits_file=str(tmp_path / "l.json"))
    assert t.can_navigate() and t.remaining_pages() == 3
    t.increment_pages()
    t.increment_pages(2)
    assert t.pages_today == 3 and t.remaining_pages() == 0 and not t.can_navigate()


def test_compteur_de_pages_relu_et_remis_a_zero_le_lendemain(tmp_path):
    f = tmp_path / "l.json"
    t = DailyLimitsTracker(limits_file=str(f))
    t.increment_pages(4)
    assert DailyLimitsTracker(limits_file=str(f)).pages_today == 4
    hier = (date.today() - timedelta(days=1)).isoformat()
    f.write_text(json.dumps({"date": hier, "pages_linkedin": 50}))
    assert DailyLimitsTracker(limits_file=str(f)).pages_today == 0


def test_constantes_du_rythme():
    assert (ScraperConfig.MAX_PAGES_PER_DAY, ScraperConfig.MAX_PROFILES_PER_RUN,
            ScraperConfig.MAX_PAGES_PER_SEANCE, ScraperConfig.PAUSE_ENTRE_SEANCES_MIN) == (60, 25, 25, 20)
    assert ScraperConfig.PAUSE_LECTURE_PROBA == 1 / 6
    assert ScraperConfig.MAX_INVITATIONS_PER_DAY == 20
