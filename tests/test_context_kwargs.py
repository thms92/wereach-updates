from types import SimpleNamespace
from scraper_v2 import LinkedInScraperV2


def _fake_profile():
    return SimpleNamespace(
        user_agent="UA", locale="fr-FR", timezone="Europe/Paris",
    )


def test_context_kwargs_without_proxy():
    s = LinkedInScraperV2(use_database=False)
    kw = s._context_kwargs(_fake_profile(), {"width": 1280, "height": 800})
    assert "proxy" not in kw
    assert kw["user_agent"] == "UA"
    assert kw["locale"] == "fr-FR"


def test_context_kwargs_with_proxy():
    proxy = {"server": "http://1.2.3.4:8000", "username": "u", "password": "p"}
    s = LinkedInScraperV2(use_database=False, proxy=proxy)
    kw = s._context_kwargs(_fake_profile(), {"width": 1280, "height": 800})
    assert kw["proxy"] == proxy
