from pathlib import Path
from utils.user_context import (
    user_id_from_email, resolve_user_email, user_paths_for, UserPaths,
)


def test_user_id_is_stable_and_safe():
    a = user_id_from_email("Alice@Example.com")
    b = user_id_from_email("alice@example.com")
    assert a == b                      # insensible à la casse
    assert len(a) == 16
    assert a.isalnum()                 # sûr comme nom de dossier


def test_user_id_differs_per_user():
    assert user_id_from_email("a@x.com") != user_id_from_email("b@x.com")


def test_resolve_email_from_cloudflare_header():
    headers = {"Cf-Access-Authenticated-User-Email": "bob@corp.com"}
    assert resolve_user_email(headers, None) == "bob@corp.com"


def test_resolve_email_header_case_insensitive():
    headers = {"cf-access-authenticated-user-email": "bob@corp.com"}
    assert resolve_user_email(headers, None) == "bob@corp.com"


def test_resolve_email_falls_back_to_dev():
    assert resolve_user_email({}, "dev@me.com") == "dev@me.com"
    assert resolve_user_email({}, None) == "local@dev"


def test_user_paths_isolated_and_created(tmp_path):
    p1 = user_paths_for("a@x.com", root=str(tmp_path))
    p2 = user_paths_for("b@x.com", root=str(tmp_path))
    assert p1.base != p2.base
    assert p1.base.is_dir()
    assert p1.config_dir.is_dir()
    assert p1.cookie_file.parent == p1.config_dir
    assert isinstance(p1, UserPaths)
