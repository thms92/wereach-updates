from scraper_v2_sync import LinkedInScraperV2Sync


def test_sync_wrapper_threads_proxy_to_scraper():
    proxy = {"server": "http://1.2.3.4:8000", "username": "u", "password": "p"}
    s = LinkedInScraperV2Sync(use_database=False, proxy=proxy)
    assert s.scraper._proxy == proxy


def test_sync_wrapper_proxy_defaults_none():
    s = LinkedInScraperV2Sync(use_database=False)
    assert s.scraper._proxy is None


def test_sync_wrapper_threads_db_and_csv():
    s = LinkedInScraperV2Sync(use_database=True, db_file="/tmp/u/profiles.db",
                              profiles_csv="/tmp/u/profils.csv")
    assert s.scraper.db.db_file == "/tmp/u/profiles.db"
    assert s.scraper.profil_file == "/tmp/u/profils.csv"


def test_sync_wrapper_db_csv_default_global():
    s = LinkedInScraperV2Sync(use_database=True)
    # defaults preserved (backward compatible)
    assert s.scraper.profil_file == s.scraper.config.PROFIL_FILE
