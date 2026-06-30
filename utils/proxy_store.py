# -*- coding: utf-8 -*-
"""Stockage chiffré (Fernet) des identifiants de proxy par utilisateur."""
import json
import os
from pathlib import Path
from cryptography.fernet import Fernet


def _get_or_create_key(key_file: str) -> bytes:
    if os.path.exists(key_file):
        return Path(key_file).read_bytes()
    key = Fernet.generate_key()
    Path(key_file).parent.mkdir(parents=True, exist_ok=True)
    Path(key_file).write_bytes(key)
    return key


def save_proxy(proxy_file: str, key_file: str, proxy: dict) -> None:
    f = Fernet(_get_or_create_key(key_file))
    token = f.encrypt(json.dumps(proxy).encode("utf-8"))
    Path(proxy_file).parent.mkdir(parents=True, exist_ok=True)
    Path(proxy_file).write_bytes(token)


def load_proxy(proxy_file: str, key_file: str):
    if not os.path.exists(proxy_file):
        return None
    f = Fernet(_get_or_create_key(key_file))
    data = f.decrypt(Path(proxy_file).read_bytes())
    return json.loads(data.decode("utf-8"))
