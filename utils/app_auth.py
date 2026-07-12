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


# ---------------------------------------------------------------------------
# Accès partagé : un domaine email autorisé (@wefiit.com) + UN mot de passe
# générique commun à tout le groupe. L'email saisi fixe l'identité (isolation
# par utilisateur), le mot de passe est le même pour tout le monde.
# ---------------------------------------------------------------------------
def set_access_password(password: str, path: str = ACCESS_FILE) -> None:
    """Définit (ou remplace) le mot de passe d'accès partagé."""
    salt = secrets.token_hex(16)
    _save({"salt": salt, "hash": _hash(password, salt)}, path)


def access_configured(path: str = ACCESS_FILE) -> bool:
    """True si un mot de passe d'accès partagé est défini → connexion exigée."""
    rec = _load(path)
    return bool(rec.get("salt") and rec.get("hash"))


def email_domain_ok(email: str) -> bool:
    """True si l'email appartient au domaine autorisé (ou si aucun filtre)."""
    if not ALLOWED_DOMAIN:
        return True
    return (email or "").strip().lower().endswith("@" + ALLOWED_DOMAIN)


def verify_access(email: str, password: str, path: str = ACCESS_FILE) -> bool:
    """Vérifie : email du bon domaine ET mot de passe d'accès partagé correct."""
    if not email_domain_ok(email):
        return False
    rec = _load(path)
    if not rec.get("salt") or not rec.get("hash"):
        return False
    return secrets.compare_digest(rec["hash"], _hash(password, rec["salt"]))
