from utils.app_auth import (
    add_user, verify_user, remove_user, list_users, auth_configured,
)


def test_add_and_verify(tmp_path):
    f = str(tmp_path / "users.json")
    assert auth_configured(f) is False
    add_user("Alice@Example.com", "s3cret", path=f)
    assert auth_configured(f) is True
    # email insensible à la casse, bon mot de passe
    assert verify_user("alice@example.com", "s3cret", path=f) is True
    # mauvais mot de passe
    assert verify_user("alice@example.com", "wrong", path=f) is False
    # utilisateur inconnu
    assert verify_user("bob@example.com", "s3cret", path=f) is False


def test_password_not_stored_in_clear(tmp_path):
    f = tmp_path / "users.json"
    add_user("a@x.com", "monMotDePasse", path=str(f))
    raw = f.read_text(encoding="utf-8")
    assert "monMotDePasse" not in raw  # haché, jamais en clair


def test_salts_differ_between_users(tmp_path):
    import json
    f = str(tmp_path / "users.json")
    add_user("a@x.com", "same", path=f)
    add_user("b@x.com", "same", path=f)
    data = json.loads(open(f, encoding="utf-8").read())
    assert data["a@x.com"]["salt"] != data["b@x.com"]["salt"]
    assert data["a@x.com"]["hash"] != data["b@x.com"]["hash"]


def test_remove_and_list(tmp_path):
    f = str(tmp_path / "users.json")
    add_user("a@x.com", "p", path=f)
    add_user("b@x.com", "p", path=f)
    assert list_users(f) == ["a@x.com", "b@x.com"]
    assert remove_user("a@x.com", path=f) is True
    assert list_users(f) == ["b@x.com"]
    assert remove_user("nope@x.com", path=f) is False
