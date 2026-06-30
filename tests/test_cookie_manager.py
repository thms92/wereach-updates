from cookie_utils import CookieManager


def test_cookies_isolated_per_directory(tmp_path):
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    cm_a = CookieManager(config_dir=str(dir_a))
    cm_b = CookieManager(config_dir=str(dir_b))

    cm_a.save_cookie("AQEDcookieA")
    cm_b.save_cookie("AQEDcookieB")

    assert cm_a.load_cookie() == "AQEDcookieA"
    assert cm_b.load_cookie() == "AQEDcookieB"
    assert (dir_a / "cookie.txt").exists()
    assert (dir_b / "cookie.txt").exists()


def test_default_dir_is_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cm = CookieManager()
    cm.save_cookie("AQEDdefault")
    assert (tmp_path / "config" / "cookie.txt").exists()
