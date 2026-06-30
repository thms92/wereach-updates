# -*- coding: utf-8 -*-
"""Stockage chiffré (Fernet) des identifiants de proxy par utilisateur."""
import json
import os
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken

from utils.crypto_key import get_or_create_fernet_key


def save_proxy(proxy_file: str, key_file: str, proxy: dict) -> None:
    f = Fernet(get_or_create_fernet_key(key_file))
    token = f.encrypt(json.dumps(proxy).encode("utf-8"))
    Path(proxy_file).parent.mkdir(parents=True, exist_ok=True)
    Path(proxy_file).write_bytes(token)
    try:
        os.chmod(proxy_file, 0o600)
    except OSError:
        pass


def load_proxy(proxy_file: str, key_file: str) -> dict | None:
    if not os.path.exists(proxy_file):
        return None
    f = Fernet(get_or_create_fernet_key(key_file))
    try:
        data = f.decrypt(Path(proxy_file).read_bytes())
    except InvalidToken:
        return None
    return json.loads(data.decode("utf-8"))
