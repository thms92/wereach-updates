# -*- coding: utf-8 -*-
"""Authentification applicative par utilisateur (login email + mot de passe).

Sert à la fois à :
1. Restreindre l'accès à l'app (groupe choisi),
2. Fixer l'identité de l'utilisateur connecté → l'isolation par utilisateur
   (cookie/base/file/proxy sous data/users/<hash>/) s'appuie dessus quand on
   n'a pas l'en-tête Cloudflare Access.

Stockage : config/users.json (git-ignoré), {email: {salt, hash}}.
Hash : PBKDF2-HMAC-SHA256 (stdlib, pas de dépendance) avec sel aléatoire.
"""
import json
import os
import hashlib
import secrets
from pathlib import Path

from config import ScraperConfig

USERS_FILE = os.path.join(ScraperConfig.CONFIG_DIR, "users.json")
ACCESS_FILE = os.path.join(ScraperConfig.CONFIG_DIR, "access.json")
# Domaine email autorisé pour se connecter (ex. wefiit.com).
ALLOWED_DOMAIN = os.getenv("WEFIIT_ALLOWED_DOMAIN", "wefiit.com").strip().lower().lstrip("@")
_ITERATIONS = 200_000

# Les fonctions ci-dessous prennent `path: str | None = None` plutôt que
# `path: str = USERS_FILE` (ou ACCESS_FILE) : un défaut de fonction Python est
# figé à la définition du module, une fois pour toutes. Avec `= USERS_FILE`,
# un test qui redirige `utils.app_auth.USERS_FILE` (monkeypatch) vers un
# répertoire jetable n'aurait aucun effet sur les appels sans argument — qui
# sont la norme partout ailleurs dans le code (app_advanced.py, manage_*.py) —
# puisque ces appels resteraient liés à la chaîne résolue à l'import. En
# résolvant `USERS_FILE`/`ACCESS_FILE` à l'intérieur du corps de la fonction,
# la valeur courante du module est relue à chaque appel : la redirection de
# test s'applique partout, sans toucher un seul site d'appel.


def _load(path: str | None = None) -> dict:
    path = USERS_FILE if path is None else path
    if not os.path.exists(path):
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(data: dict, path: str | None = None) -> None:
    path = USERS_FILE if path is None else path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", (password or "").encode("utf-8"), bytes.fromhex(salt), _ITERATIONS
    ).hex()


def add_user(email: str, password: str, path: str | None = None) -> None:
    """Ajoute (ou met à jour) un utilisateur."""
    path = USERS_FILE if path is None else path
    data = _load(path)
    salt = secrets.token_hex(16)
    data[(email or "").strip().lower()] = {"salt": salt, "hash": _hash(password, salt)}
    _save(data, path)


def verify_user(email: str, password: str, path: str | None = None) -> bool:
    """Vérifie email + mot de passe (comparaison à temps constant)."""
    path = USERS_FILE if path is None else path
    rec = _load(path).get((email or "").strip().lower())
    if not rec or "salt" not in rec or "hash" not in rec:
        return False
    return secrets.compare_digest(rec["hash"], _hash(password, rec["salt"]))


def remove_user(email: str, path: str | None = None) -> bool:
    path = USERS_FILE if path is None else path
    data = _load(path)
    key = (email or "").strip().lower()
    if key in data:
        del data[key]
        _save(data, path)
        return True
    return False


def list_users(path: str | None = None) -> list:
    path = USERS_FILE if path is None else path
    return sorted(_load(path).keys())


def auth_configured(path: str | None = None) -> bool:
    """True si au moins un utilisateur existe → l'app exige une connexion."""
    path = USERS_FILE if path is None else path
    return len(_load(path)) > 0


# ---------------------------------------------------------------------------
# Accès partagé : un domaine email autorisé (@wefiit.com) + UN mot de passe
# générique commun à tout le groupe. L'email saisi fixe l'identité (isolation
# par utilisateur), le mot de passe est le même pour tout le monde.
# ---------------------------------------------------------------------------
def set_access_password(password: str, path: str | None = None) -> None:
    """Définit (ou remplace) le mot de passe d'accès partagé."""
    path = ACCESS_FILE if path is None else path
    salt = secrets.token_hex(16)
    _save({"salt": salt, "hash": _hash(password, salt)}, path)


def access_configured(path: str | None = None) -> bool:
    """True si un mot de passe d'accès partagé est défini → connexion exigée."""
    path = ACCESS_FILE if path is None else path
    rec = _load(path)
    return bool(rec.get("salt") and rec.get("hash"))


def email_domain_ok(email: str) -> bool:
    """True si l'email appartient au domaine autorisé (ou si aucun filtre)."""
    if not ALLOWED_DOMAIN:
        return True
    return (email or "").strip().lower().endswith("@" + ALLOWED_DOMAIN)


def verify_access(email: str, password: str, path: str | None = None) -> bool:
    """Vérifie : email du bon domaine ET mot de passe d'accès partagé correct."""
    path = ACCESS_FILE if path is None else path
    if not email_domain_ok(email):
        return False
    rec = _load(path)
    if not rec.get("salt") or not rec.get("hash"):
        return False
    return secrets.compare_digest(rec["hash"], _hash(password, rec["salt"]))
