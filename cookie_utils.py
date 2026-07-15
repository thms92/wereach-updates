# -*- coding: utf-8 -*-
import base64
import os
from cryptography.fernet import Fernet
from typing import Optional
from logger import logger
from config import ScraperConfig
from utils.crypto_key import get_or_create_fernet_key


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
        return get_or_create_fernet_key(self.key_file)

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
            try:
                os.chmod(self.cookie_file, 0o600)
            except OSError:
                pass
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
        """Valide (souplement) le format d'un cookie li_at.

        On reste permissif : les cookies li_at de LinkedIn ont grossi (200-300+
        caractères) et le jeu de caractères varie (base64 + url-safe). Le vrai
        test de validité, c'est le warm-up. On ne rejette donc que l'évident :
        vide, trop court, ou contenant des espaces (copié de travers).
        """
        if not cookie:
            return False
        cookie = cookie.strip()
        if len(cookie) < 30:
            logger.warning(f"Cookie trop court: {len(cookie)}")
            return False
        import re
        # Charset large : lettres, chiffres, base64 (+/=), url-safe (-_), et
        # quelques signes possibles du jeton.
        if not re.match(r'^[A-Za-z0-9_\-=:./+%~]+$', cookie):
            logger.warning("Format cookie invalide (caractères inattendus)")
            return False
        return True
