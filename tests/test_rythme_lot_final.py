"""Rythme humain, lot de correction final : chaque requête vers LinkedIn est
comptée et contrôlée, chaque refus est dit. Aucun navigateur : Playwright se
simule."""
import asyncio

import pytest

from scraper_v2 import ArretLinkedIn, LinkedInScraperV2

PROFIL_A = "https://www.linkedin.com/in/alice/"
CHECKPOINT = "https://www.linkedin.com/checkpoint/challenge/AgEx123?ut=1"


async def _rien(*a, **k):
    return None


class _Corps:
    async def inner_text(self, timeout=None):
        return ""


class _PageGoto:
    """Page dont goto suit un scénario : chaque entrée est une URL
    d'arrivée, ou une exception à lever."""

    def __init__(self, scenario):
        self.url = "about:blank"
        self.scenario = list(scenario)
        self.appels = []

    def locator(self, selecteur):
        return _Corps()

    async def goto(self, url, **k):
        self.appels.append(url)
        issue = self.scenario.pop(0)
        if isinstance(issue, Exception):
            raise issue
        self.url = issue
        return type("Reponse", (), {"status": 200})()


def _scraper_reseau_reel(tmp_path, monkeypatch):
    """Scraper au vrai NetworkManager (tentatives comprises), sans attente."""
    s = LinkedInScraperV2(use_database=False, config_dir=str(tmp_path))
    monkeypatch.setattr(s.human, "pause_entre_pages", _rien)
    monkeypatch.setattr("utils.network_manager.asyncio.sleep", _rien)
    return s


# --- 1. Une navigation = une requête, une page comptée, un contrôle --------

def test_goto_rate_n_est_pas_retente(tmp_path, monkeypatch):
    s = _scraper_reseau_reel(tmp_path, monkeypatch)
    page = _PageGoto([Exception("net::ERR_CONNECTION_RESET"), PROFIL_A])
    assert asyncio.run(s._naviguer(page, PROFIL_A)) is False
    assert page.appels == [PROFIL_A]
    assert s.human.daily_limits.pages_today == 1


def test_goto_vers_checkpoint_arrete_apres_un_seul_appel(tmp_path, monkeypatch):
    s = _scraper_reseau_reel(tmp_path, monkeypatch)
    page = _PageGoto([CHECKPOINT, PROFIL_A])
    with pytest.raises(ArretLinkedIn) as arret:
        asyncio.run(s._naviguer(page, PROFIL_A))
    assert arret.value.motif == "alerte"
    assert page.appels == [PROFIL_A]
    assert s.human.daily_limits.pages_today == 1


def test_goto_qui_echoue_sur_checkpoint_arrete_sans_nouvel_essai(tmp_path, monkeypatch):
    s = _scraper_reseau_reel(tmp_path, monkeypatch)
    page = _PageGoto([])

    async def goto(url, **k):
        page.appels.append(url)
        page.url = CHECKPOINT
        raise Exception("net::ERR_TOO_MANY_REDIRECTS")

    page.goto = goto
    with pytest.raises(ArretLinkedIn) as arret:
        asyncio.run(s._naviguer(page, PROFIL_A))
    assert arret.value.motif == "alerte"
    assert page.appels == [PROFIL_A]


# --- 6. Typeahead entreprise : 429 ou 999 = page d'alerte ------------------

class _Contexte:
    async def cookies(self, url):
        return [{"name": "JSESSIONID", "value": '"ajax:123"'}]


class _PageTypeahead:
    url = "https://www.linkedin.com/search/results/people/"

    def __init__(self, reponse):
        self.context = _Contexte()
        self.reponse = reponse

    async def evaluate(self, script, arg):
        return self.reponse


@pytest.mark.parametrize("statut", [429, 999])
def test_typeahead_en_alerte_arrete_tout(tmp_path, monkeypatch, statut):
    s = LinkedInScraperV2(use_database=False, config_dir=str(tmp_path))
    monkeypatch.setattr(LinkedInScraperV2, "_resoudre_company_urn", staticmethod(lambda e: None))
    page = _PageTypeahead({"ok": False, "status": statut})
    with pytest.raises(ArretLinkedIn) as arret:
        asyncio.run(s._resoudre_company_urn_via_typeahead("Société Démo", page))
    assert arret.value.motif == "alerte"


def test_typeahead_autre_echec_reste_un_echec_simple(tmp_path, monkeypatch):
    s = LinkedInScraperV2(use_database=False, config_dir=str(tmp_path))
    monkeypatch.setattr(LinkedInScraperV2, "_resoudre_company_urn", staticmethod(lambda e: None))
    echecs = []
    page = _PageTypeahead({"ok": False, "status": 500})
    assert asyncio.run(s._resoudre_company_urn_via_typeahead("Société Démo", page, echecs)) is None
    assert echecs == ["réponse HTTP 500"]
