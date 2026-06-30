import os

from utils.proxy_store import save_proxy, load_proxy
from utils.crypto_key import get_or_create_fernet_key


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


def test_key_file_permissions_are_0600(tmp_path):
    pf = tmp_path / "proxy.enc"
    kf = tmp_path / "secret.key"
    proxy = {"server": "http://1.2.3.4:8000", "username": "u", "password": "p"}

    save_proxy(str(pf), str(kf), proxy)

    assert oct(os.stat(kf).st_mode & 0o777) == '0o600'
    assert oct(os.stat(pf).st_mode & 0o777) == '0o600'


def test_load_proxy_with_wrong_key_returns_none(tmp_path):
    pf = tmp_path / "proxy.enc"
    kf = tmp_path / "secret.key"
    other_kf = tmp_path / "other_secret.key"
    proxy = {"server": "http://1.2.3.4:8000", "username": "u", "password": "p"}

    save_proxy(str(pf), str(kf), proxy)

    # Create a different key up front so load_proxy doesn't just reuse the original.
    get_or_create_fernet_key(str(other_kf))

    assert load_proxy(str(pf), str(other_kf)) is None
