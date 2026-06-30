"""
update_cookie.py
----------------
Met à jour le cookie LinkedIn li_at encrypté dans config/cookie.txt.

Usage:
    python3 update_cookie.py

Le script te demande de coller ton nouveau li_at, puis :
  1. Encrypte le token avec la clé Fernet de config/secret.key
  2. Écrit le résultat dans config/cookie.txt
  3. Génère aussi un linkedin_cookies.json (format Playwright) pour enrich_linkedin.py

Comment récupérer un li_at frais :
  1. Ouvre linkedin.com/feed/ dans Chrome (connecté à ton compte "alain.")
  2. DevTools (⌘+⌥+I) → Application → Cookies → https://www.linkedin.com
  3. Trouve "li_at", copie la Value (~100-150 caractères, commence par AQE...)
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    from cryptography.fernet import Fernet
except ImportError:
    print("❌ Module 'cryptography' manquant. Installe-le avec :")
    print("   pip install cryptography")
    sys.exit(1)


CONFIG_DIR      = Path("config")
SECRET_KEY_PATH = CONFIG_DIR / "secret.key"
COOKIE_PATH     = CONFIG_DIR / "cookie.txt"
PLAYWRIGHT_PATH = Path("linkedin_cookies.json")


def ensure_config_dir():
    """Crée config/ si inexistant, et secret.key si inexistante."""
    CONFIG_DIR.mkdir(exist_ok=True)

    if not SECRET_KEY_PATH.exists():
        print(f"⚠️  {SECRET_KEY_PATH} introuvable — génération d'une nouvelle clé…")
        key = Fernet.generate_key()
        SECRET_KEY_PATH.write_bytes(key)
        print(f"✅ Nouvelle clé Fernet créée : {SECRET_KEY_PATH}")


def encrypt_and_save(token: str):
    """Encrypte le token avec Fernet et le sauvegarde dans cookie.txt."""
    key = SECRET_KEY_PATH.read_bytes()
    fernet = Fernet(key)
    encrypted = fernet.encrypt(token.encode())
    COOKIE_PATH.write_bytes(encrypted)
    print(f"✅ Cookie encrypté écrit dans : {COOKIE_PATH}")


def save_playwright_format(token: str):
    """
    Génère aussi un linkedin_cookies.json au format Playwright,
    utilisé par enrich_linkedin.py.
    """
    # Expiration à +30 jours (LinkedIn fait ~1 an mais on est prudent)
    expires = int((datetime.now() + timedelta(days=30)).timestamp())

    cookies = [
        {
            "name":     "li_at",
            "value":    token,
            "domain":   ".linkedin.com",
            "path":     "/",
            "expires":  expires,
            "httpOnly": True,
            "secure":   True,
            "sameSite": "None",
        }
    ]

    PLAYWRIGHT_PATH.write_text(
        json.dumps(cookies, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"✅ Format Playwright écrit dans : {PLAYWRIGHT_PATH}")


def main():
    print("=" * 60)
    print("  🔑 Mise à jour du cookie LinkedIn (li_at)")
    print("=" * 60)
    print()
    print("📋 Instructions :")
    print("   1. Ouvre linkedin.com/feed/ dans Chrome (compte 'alain.')")
    print("   2. DevTools (⌘+⌥+I) → Application → Cookies")
    print("      → https://www.linkedin.com")
    print("   3. Trouve 'li_at' et copie sa Value")
    print()

    ensure_config_dir()

    # Lire le token (support multi-ligne au cas où)
    print("👉 Colle ton nouveau li_at puis appuie sur Entrée :")
    token = input("   li_at = ").strip()

    # Nettoyage basique
    if token.startswith('"') and token.endswith('"'):
        token = token[1:-1]
    if token.startswith("'") and token.endswith("'"):
        token = token[1:-1]

    if not token:
        print("❌ Aucun token fourni. Abandon.")
        sys.exit(1)

    if len(token) < 50:
        print(f"⚠️  Le token semble anormalement court ({len(token)} caractères).")
        print("   Un li_at normal fait ~100-150 caractères.")
        confirm = input("   Continuer quand même ? (o/N) : ").strip().lower()
        if confirm != "o":
            print("Abandon.")
            sys.exit(1)

    print()
    encrypt_and_save(token)
    save_playwright_format(token)

    print()
    print("=" * 60)
    print("  ✅ Terminé !")
    print("=" * 60)
    print()
    print("⏳ IMPORTANT — attends 1-2h avant de relancer le scraper.")
    print("   LinkedIn vient de te rate-limit, relancer immédiatement")
    print("   risque de faire révoquer le cookie direct.")
    print()
    print("🧪 Puis teste d'abord sur 1 profil en mode visible :")
    print("   python3 enrich_linkedin.py --visible -i test_1.csv -o test_out.csv")
    print()


if __name__ == "__main__":
    main()
