# -*- coding: utf-8 -*-
"""Helper partagé pour la gestion des clés Fernet (chiffrement des secrets)."""
import os
from pathlib import Path
from cryptography.fernet import Fernet


def get_or_create_fernet_key(key_file: str) -> bytes:
    """Récupère la clé Fernet existante ou en crée une nouvelle.

    Si `key_file` existe déjà, son contenu est lu et renvoyé tel quel.
    Sinon, une nouvelle clé est générée, le dossier parent est créé si
    nécessaire, la clé est écrite sur disque avec des permissions
    restreintes (0o600) puis renvoyée.
    """
    if os.path.exists(key_file):
        return Path(key_file).read_bytes()

    key = Fernet.generate_key()
    Path(key_file).parent.mkdir(parents=True, exist_ok=True)
    Path(key_file).write_bytes(key)
    try:
        os.chmod(key_file, 0o600)
    except OSError:
        pass
    return key
