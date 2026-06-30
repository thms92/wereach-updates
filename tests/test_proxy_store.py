from utils.proxy_store import save_proxy, load_proxy


def test_roundtrip_encrypted(tmp_path):
    pf = tmp_path / "proxy.enc"
    kf = tmp_path / "secret.key"
    proxy = {"server": "http://1.2.3.4:8000", "username": "u", "password": "p"}

    save_proxy(str(pf), str(kf), proxy)

    assert pf.exists()
    raw = pf.read_bytes()
    assert b"1.2.3.4" not in raw           # chiffré, pas en clair
    assert load_proxy(str(pf), str(kf)) == proxy


def test_load_missing_returns_none(tmp_path):
    assert load_proxy(str(tmp_path / "none.enc"), str(tmp_path / "k.key")) is None
