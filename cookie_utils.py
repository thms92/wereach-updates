# -*- coding: utf-8 -*-
import base64
import os
from cryptography.fernet import Fernet
from typing import Optional
from logger import logger
from config import ScraperConfig


class CookieManager:
    """Gestion sécurisée des cookies LinkedIn"""

    def __init__(self, config_dir: str = None):
        cfg_dir = config_dir or ScraperConfig.CONFIG_DIR
        os.makedirs(cfg_dir, exist_ok=True)
        self.key_file = os.path.join(cfg_dir, "secret.key")
        self.cookie_file = os.path.join(cfg_dir, "cookie.txt")
        self.key = self._get_or_create_key()

    def _get_or_create_key(self) -> bytes:
        """Récupère ou crée une clé de chiffrement"""
        if os.path.exists(self.key_file):
            with open(self.key_file, 'rb') as f:
                return f.read()
        else:
            key = Fernet.generate_key()
            with open(self.key_file, 'wb') as f:
                f.write(key)
            return key

    def encrypt_cookie(self, cookie: str) -> str:
        """Chiffre un cookie"""
        try:
            f = Fernet(self.key)
            encrypted = f.encrypt(cookie.encode())
            return base64.urlsafe_b64encode(encrypted).decode()
        except Exception as e:
            logger.error(f"Erreur chiffrement cookie: {e}")
            return ""

    def decrypt_cookie(self, encrypted_cookie: str) -> str:
        """Déchiffre un cookie"""
        try:
            f = Fernet(self.key)
            decoded = base64.urlsafe_b64decode(encrypted_cookie.encode())
            decrypted = f.decrypt(decoded)
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Erreur déchiffrement cookie: {e}")
            return ""

    def save_cookie(self, cookie: str) -> bool:
        """Sauvegarde un cookie chiffré"""
        try:
            encrypted = self.encrypt_cookie(cookie)
            with open(self.cookie_file, 'w') as f:
                f.write(encrypted)
            logger.info("Cookie sauvegardé avec succès")
            return True
        except Exception as e:
            logger.error(f"Erreur sauvegarde cookie: {e}")
            return False

    def load_cookie(self) -> Optional[str]:
        """Charge un cookie chiffré"""
        try:
            if not os.path.exists(self.cookie_file):
                return None

            with open(self.cookie_file, 'r') as f:
                encrypted = f.read().strip()

            if not encrypted:
                return None

            return self.decrypt_cookie(encrypted)
        except Exception as e:
            logger.error(f"Erreur chargement cookie: {e}")
            return None

    def validate_cookie_format(self, cookie: str) -> bool:
        """Valide le format d'un cookie li_at"""
        if not cookie:
            return False

        # Le cookie li_at de LinkedIn a généralement 152 caractères
        if len(cookie) < 100 or len(cookie) > 200:
            logger.warning(f"Longueur cookie suspecte: {len(cookie)}")
            return False

        # Vérifier que le cookie contient uniquement des caractères alphanumériques et certains caractères spéciaux
        import re
        if not re.match(r'^[A-Za-z0-9_\-=]+$', cookie):
            logger.warning("Format cookie invalide")
            return False

        return True
