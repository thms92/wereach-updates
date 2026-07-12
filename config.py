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
    # Valeurs volontairement longues (mode "sécurité max", sans proxy)
    DELAY_BETWEEN_PROFILES_MIN: int = 4000
    DELAY_BETWEEN_PROFILES_MAX: int = 9000

    # Après envoi d'invitation (attendre que la modal se ferme)
    DELAY_AFTER_INVITATION_MIN: int = 3000
    DELAY_AFTER_INVITATION_MAX: int = 6000

    # Après le clic sur "Se connecter" (attendre l'ouverture de la modal)
    DELAY_AFTER_CONNECT_CLICK_MIN: int = 1800
    DELAY_AFTER_CONNECT_CLICK_MAX: int = 4000

    # Après le chargement d'une page (temps de "lecture" initiale)
    DELAY_PAGE_LOAD_MIN: int = 2500
    DELAY_PAGE_LOAD_MAX: int = 6000

    # Plafonds PAR UTILISATEUR et PAR JOUR (source de vérité — appliqués dans
    # le scraper via DailyLimitsTracker). Conservateurs pour limiter le risque
    # LinkedIn quand plusieurs comptes partagent l'IP du serveur (sans proxy).
    MAX_PROFILES_PER_RUN: int = 80
    MAX_INVITATIONS_PER_DAY: int = 20
    MAX_RETRY_ATTEMPTS: int = 3
    # Headless pilotable par variable d'env : SCRAPER_HEADLESS=false lance un
    # navigateur VISIBLE (headed). LinkedIn masque certains boutons d'action
    # (ex. "Se connecter") aux sessions headless détectées.
    HEADLESS: bool = os.getenv("SCRAPER_HEADLESS", "true").strip().lower() not in ("false", "0", "no")

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
