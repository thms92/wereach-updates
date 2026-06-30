# -*- coding: utf-8 -*-
"""Identité et chemins isolés par utilisateur (multi-locataire)."""
import hashlib
from dataclasses import dataclass
from pathlib import Path

CF_HEADER = "cf-access-authenticated-user-email"
DEFAULT_DEV_EMAIL = "local@dev"


def user_id_from_email(email: str) -> str:
    norm = (email or "").strip().lower().encode("utf-8")
    return hashlib.sha256(norm).hexdigest()[:16]


def resolve_user_email(headers: dict, dev_fallback: str | None) -> str:
    for k, v in (headers or {}).items():
        if k.lower() == CF_HEADER and v:
            return v.strip()
    return (dev_fallback or DEFAULT_DEV_EMAIL).strip()


@dataclass
class UserPaths:
    base: Path
    config_dir: Path
    cookie_file: Path
    key_file: Path
    db_file: Path
    queue_file: Path
    profiles_csv: Path
    proxy_file: Path


def user_paths_for(email: str, root: str = "data/users") -> UserPaths:
    uid = user_id_from_email(email)
    base = Path(root) / uid
    config_dir = base / "config"
    base.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    return UserPaths(
        base=base,
        config_dir=config_dir,
        cookie_file=config_dir / "cookie.txt",
        key_file=config_dir / "secret.key",
        db_file=base / "profiles.db",
        queue_file=config_dir / "queue.json",
        profiles_csv=base / "profils_scrapes.csv",
        proxy_file=config_dir / "proxy.enc",
    )
