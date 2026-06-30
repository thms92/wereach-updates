from scraper_v2_sync import LinkedInScraperV2Sync


def test_sync_wrapper_threads_proxy_to_scraper():
    proxy = {"server": "http://1.2.3.4:8000", "username": "u", "password": "p"}
    s = LinkedInScraperV2Sync(use_database=False, proxy=proxy)
    assert s.scraper._proxy == proxy


def test_sync_wrapper_proxy_defaults_none():
    s = LinkedInScraperV2Sync(use_database=False)
    assert s.scraper._proxy is None
