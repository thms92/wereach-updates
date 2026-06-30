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
_ITERATIONS = 200_000


def _load(path: str = USERS_FILE) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(data: dict, path: str = USERS_FILE) -> None:
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


def add_user(email: str, password: str, path: str = USERS_FILE) -> None:
    """Ajoute (ou met à jour) un utilisateur."""
    data = _load(path)
    salt = secrets.token_hex(16)
    data[(email or "").strip().lower()] = {"salt": salt, "hash": _hash(password, salt)}
    _save(data, path)


def verify_user(email: str, password: str, path: str = USERS_FILE) -> bool:
    """Vérifie email + mot de passe (comparaison à temps constant)."""
    rec = _load(path).get((email or "").strip().lower())
    if not rec or "salt" not in rec or "hash" not in rec:
        return False
    return secrets.compare_digest(rec["hash"], _hash(password, rec["salt"]))


def remove_user(email: str, path: str = USERS_FILE) -> bool:
    data = _load(path)
    key = (email or "").strip().lower()
    if key in data:
        del data[key]
        _save(data, path)
        return True
    return False


def list_users(path: str = USERS_FILE) -> list:
    return sorted(_load(path).keys())


def auth_configured(path: str = USERS_FILE) -> bool:
    """True si au moins un utilisateur existe → l'app exige une connexion."""
    return len(_load(path)) > 0
