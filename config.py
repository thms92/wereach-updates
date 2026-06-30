# -*- coding: utf-8 -*-
from dataclasses import dataclass
import os
import random

@dataclass
class ScraperConfig:
    PROFIL_FILE: str = "profils_scrapes.csv"
    DATABASE_FILE: str = "profiles.db"
    LOG_FILE: str = "scraper.log"
    CONFIG_DIR: str = "config"
    SCHEDULE_FILE: str = "config/schedules.json"
    COOKIE_FILE: str = "config/cookie.txt"
    TEMPLATES_FILE: str = "config/search_templates.json"

    TIMEOUT_PAGE: int = 60000
    TIMEOUT_ELEMENT: int = 3000

    # -----------------------------------------------------------------------
    # Délais (en ms) — utilisés comme moyenne pour distribution gaussienne
    # Les valeurs MIN/MAX définissent la plage naturelle du comportement humain
    # -----------------------------------------------------------------------

    # Entre chaque profil traité (scroll, lecture, décision)
    DELAY_BETWEEN_PROFILES_MIN: int = 2500
    DELAY_BETWEEN_PROFILES_MAX: int = 5500

    # Après envoi d'invitation (attendre que la modal se ferme)
    DELAY_AFTER_INVITATION_MIN: int = 1800
    DELAY_AFTER_INVITATION_MAX: int = 3500

    # Après le clic sur "Se connecter" (attendre l'ouverture de la modal)
    DELAY_AFTER_CONNECT_CLICK_MIN: int = 1200
    DELAY_AFTER_CONNECT_CLICK_MAX: int = 2800

    # Après le chargement d'une page (temps de "lecture" initiale)
    DELAY_PAGE_LOAD_MIN: int = 1500
    DELAY_PAGE_LOAD_MAX: int = 4500

    MAX_PROFILES_PER_RUN: int = 200
    MAX_INVITATIONS_PER_DAY: int = 50
    MAX_RETRY_ATTEMPTS: int = 3
    HEADLESS: bool = True

    SMTP_SERVER: str = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    EMAIL_FROM: str = os.getenv("EMAIL_FROM", "")
    EMAIL_PASSWORD: str = os.getenv("EMAIL_PASSWORD", "")

    SCHEDULER_CHECK_INTERVAL: int = 60

    @staticmethod
    def random_delay(min_ms: int, max_ms: int) -> int:
        """Génère un délai aléatoire entre min et max millisecondes"""
        return random.randint(min_ms, max_ms)

ECOLES = {
    "Dauphine": "15092700",
    "Arts et Métiers": "1280025",
    "GEM": "18927",
    "HEC": "235785",
    "ESSEC": "11415",
    "ESCP": "308907",
    "EM Lyon": "18361",
    "Edhec": "16001",
    "SKEMA": "2413397",
    "Kedge": "2757210",
}

os.makedirs(ScraperConfig.CONFIG_DIR, exist_ok=True)
