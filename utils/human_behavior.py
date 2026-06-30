# -*- coding: utf-8 -*-
"""
HumanBehavior - Module de simulation de comportement humain
Rend le scraper indiscernable d'un vrai utilisateur LinkedIn

Techniques implémentées :
- Délais gaussiens (plus réalistes qu'un random uniforme)
- Mouvements de souris naturels (courbe de Bézier)
- Scroll progressif et naturel
- Frappe caractère par caractère avec variations
- Pauses aléatoires de "lecture"
- Micro-mouvements de souris simulant l'hésitation
- Gestion de la fatigue (ralentissement progressif)
- Warm-up session (visite du feed avant le scraping)
- Referrer chain (navigation naturelle entre les pages)
- Monitoring des réponses HTTP (détection 429, authwall)
- Compteur quotidien persistant (limite de sécurité)
"""

import asyncio
import json
import os
import random
import math
from datetime import datetime, date
from typing import Optional, Dict
from playwright.async_api import Page, Locator, BrowserContext, Response
from logger import logger


class DailyLimitsTracker:
    """
    Suivi persistant des limites quotidiennes.
    Écrit un fichier JSON mis à jour à chaque action.
    """

    LIMITS_FILE = "config/daily_limits.json"

    def __init__(self, max_profiles: int = 200, max_invitations: int = 50):
        self.max_profiles = max_profiles
        self.max_invitations = max_invitations
        self._data = self._load()

    def _load(self) -> Dict:
        today = date.today().isoformat()
        try:
            if os.path.exists(self.LIMITS_FILE):
                with open(self.LIMITS_FILE, "r") as f:
                    data = json.load(f)
                if data.get("date") == today:
                    return data
        except Exception:
            pass
        return {"date": today, "profiles_scraped": 0, "invitations_sent": 0, "sessions": 0}

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.LIMITS_FILE), exist_ok=True)
            with open(self.LIMITS_FILE, "w") as f:
                json.dump(self._data, f, indent=2)
        except Exception:
            pass

    def increment_profiles(self, n: int = 1):
        self._data["profiles_scraped"] = self._data.get("profiles_scraped", 0) + n
        self._save()

    def increment_invitations(self, n: int = 1):
        self._data["invitations_sent"] = self._data.get("invitations_sent", 0) + n
        self._save()

    def increment_sessions(self):
        self._data["sessions"] = self._data.get("sessions", 0) + 1
        self._save()

    @property
    def profiles_today(self) -> int:
        return self._data.get("profiles_scraped", 0)

    @property
    def invitations_today(self) -> int:
        return self._data.get("invitations_sent", 0)

    @property
    def sessions_today(self) -> int:
        return self._data.get("sessions", 0)

    def can_scrape(self) -> bool:
        return self.profiles_today < self.max_profiles

    def can_invite(self) -> bool:
        return self.invitations_today < self.max_invitations

    def remaining_profiles(self) -> int:
        return max(0, self.max_profiles - self.profiles_today)

    def remaining_invitations(self) -> int:
        return max(0, self.max_invitations - self.invitations_today)


class ResponseMonitor:
    """
    Monitore les réponses HTTP de LinkedIn pour détecter les problèmes.
    Attaché à la page via page.on("response", ...).
    """

    def __init__(self):
        self.rate_limited = False
        self.auth_wall = False
        self.challenge_detected = False
        self._429_count = 0
        self._last_status_codes = []

    async def on_response(self, response: Response):
        """Callback appelé sur chaque réponse HTTP."""
        url = response.url
        status = response.status

        # Ignorer les ressources statiques
        if any(ext in url for ext in ['.png', '.jpg', '.gif', '.css', '.woff', '.ico']):
            return

        # Tracker les status codes récents (LinkedIn API)
        if 'linkedin.com' in url:
            self._last_status_codes.append(status)
            if len(self._last_status_codes) > 50:
                self._last_status_codes = self._last_status_codes[-50:]

        # Détection 429 (rate limited)
        if status == 429:
            self._429_count += 1
            self.rate_limited = True
            logger.warning(f"⚠️ HTTP 429 détecté ! (count: {self._429_count}) URL: {url[:80]}")

        # Détection redirection auth/challenge
        if status in (401, 403):
            if 'challenge' in url or 'checkpoint' in url:
                self.challenge_detected = True
                logger.error(f"🚨 Challenge/Checkpoint LinkedIn détecté ! URL: {url[:80]}")

        if 'authwall' in url or 'login' in url:
            self.auth_wall = True

    @property
    def is_safe(self) -> bool:
        """True si aucun signal de danger détecté."""
        return not self.rate_limited and not self.auth_wall and not self.challenge_detected

    @property
    def danger_level(self) -> str:
        """Retourne le niveau de danger actuel."""
        if self.challenge_detected:
            return "CRITICAL"
        if self.rate_limited:
            return "HIGH"
        if self.auth_wall:
            return "HIGH"
        # Vérifier la fréquence d'erreurs récentes
        recent = self._last_status_codes[-20:]
        error_rate = sum(1 for s in recent if s >= 400) / max(len(recent), 1)
        if error_rate > 0.3:
            return "MEDIUM"
        return "LOW"

    def reset(self):
        self.rate_limited = False
        self.auth_wall = False
        self.challenge_detected = False


class HumanBehavior:
    """
    Simule un comportement humain naturel dans le navigateur.
    Toutes les méthodes sont async et utilisent Playwright.
    """

    def __init__(self, fatigue_factor: float = 0.0):
        """
        Args:
            fatigue_factor: Entre 0 et 1. Plus il est élevé, plus les délais augmentent
                            (simule la fatigue d'un utilisateur après une longue session).
        """
        self.fatigue_factor = fatigue_factor  # entre 0.0 et 1.0
        self.response_monitor = ResponseMonitor()
        self.daily_limits = DailyLimitsTracker()

    # =========================================================================
    # DÉLAIS NATURELS
    # =========================================================================

    def gaussian_delay(self, mean_ms: int, std_ms: Optional[int] = None) -> int:
        """
        Génère un délai selon une distribution gaussienne.
        Beaucoup plus réaliste qu'un random.randint() uniforme.

        Args:
            mean_ms: Délai moyen en millisecondes
            std_ms: Écart-type (par défaut: 20% de la moyenne)

        Returns:
            Délai en millisecondes (toujours positif)
        """
        if std_ms is None:
            std_ms = int(mean_ms * 0.25)

        # Appliquer le facteur de fatigue (ralentissement progressif)
        fatigue_boost = int(mean_ms * self.fatigue_factor * 0.5)

        delay = random.gauss(mean_ms + fatigue_boost, std_ms)
        return max(200, int(delay))  # jamais moins de 200ms

    async def human_delay(self, mean_ms: int, std_ms: Optional[int] = None):
        """Attend un délai gaussien réaliste."""
        delay = self.gaussian_delay(mean_ms, std_ms)
        await asyncio.sleep(delay / 1000)

    async def reading_pause(self, text_length: int = 100):
        """
        Simule une pause de lecture proportionnelle à la longueur du texte.
        Un humain lit ~200 mots/min, soit ~1000 caractères/min.
        """
        # ~1000 chars/min = ~60ms par caractère, avec variation
        base_ms = int(text_length * random.uniform(40, 80))
        base_ms = max(500, min(base_ms, 4000))  # entre 500ms et 4s
        await self.human_delay(base_ms, base_ms // 4)

    async def random_long_pause(self, probability: float = 0.1):
        """
        Avec une certaine probabilité, fait une pause plus longue
        (simule l'utilisateur qui se lève, répond à un message, etc.)
        """
        if random.random() < probability:
            # Pause entre 3 et 15 secondes
            pause = random.uniform(3000, 15000)
            await asyncio.sleep(pause / 1000)

    def increase_fatigue(self, increment: float = 0.05):
        """Augmente le facteur de fatigue progressivement."""
        self.fatigue_factor = min(1.0, self.fatigue_factor + increment)

    # =========================================================================
    # MOUVEMENTS DE SOURIS NATURELS
    # =========================================================================

    async def human_mouse_move(self, page: Page, target_x: int, target_y: int,
                                steps: int = 10):
        """
        Déplace la souris de manière naturelle vers une cible.
        Utilise une courbe légèrement courbée (pas une ligne droite).

        Args:
            page: Page Playwright
            target_x, target_y: Coordonnées de destination
            steps: Nombre d'étapes intermédiaires
        """
        try:
            # Récupérer la position actuelle de la souris (centre par défaut)
            viewport = page.viewport_size
            if not viewport:
                return

            # Position de départ aléatoire dans le viewport
            start_x = random.randint(100, viewport['width'] - 100)
            start_y = random.randint(100, viewport['height'] // 2)

            # Point de contrôle pour la courbe de Bézier (légère déviation)
            ctrl_x = (start_x + target_x) / 2 + random.randint(-80, 80)
            ctrl_y = (start_y + target_y) / 2 + random.randint(-60, 60)

            for i in range(steps + 1):
                t = i / steps
                # Courbe de Bézier quadratique
                x = int((1-t)**2 * start_x + 2*(1-t)*t * ctrl_x + t**2 * target_x)
                y = int((1-t)**2 * start_y + 2*(1-t)*t * ctrl_y + t**2 * target_y)

                await page.mouse.move(x, y)

                # Délai variable entre chaque micro-mouvement
                step_delay = random.uniform(10, 40)
                await asyncio.sleep(step_delay / 1000)

        except Exception:
            pass  # Mouvement souris non bloquant

    async def human_hover_and_click(self, page: Page, locator: Locator):
        """
        Survole un élément puis clique dessus, comme un vrai utilisateur.
        """
        try:
            # Récupérer les coordonnées de l'élément
            box = await locator.bounding_box()
            if box:
                # Cible: au hasard dans l'élément (pas toujours le centre)
                target_x = box['x'] + random.uniform(box['width'] * 0.2, box['width'] * 0.8)
                target_y = box['y'] + random.uniform(box['height'] * 0.2, box['height'] * 0.8)

                # Déplacer la souris vers l'élément
                await self.human_mouse_move(page, int(target_x), int(target_y))

                # Micro-pause avant le clic (temps de décision)
                await self.human_delay(120, 60)

                # Cliquer
                await locator.click()
            else:
                # Fallback: clic simple si bounding box non disponible
                await locator.click()

        except Exception:
            # Fallback en cas d'erreur
            await locator.click()

    # =========================================================================
    # SCROLL NATUREL
    # =========================================================================

    async def human_scroll_down(self, page: Page, total_px: int = 400,
                                 scroll_steps: int = 5):
        """
        Fait défiler la page vers le bas de manière naturelle.

        Args:
            page: Page Playwright
            total_px: Nombre total de pixels à scroller
            scroll_steps: Nombre d'étapes de scroll
        """
        try:
            px_per_step = total_px // scroll_steps

            for i in range(scroll_steps):
                # Varier la quantité scrollée à chaque étape
                step_px = px_per_step + random.randint(-30, 30)
                await page.mouse.wheel(0, step_px)

                # Pause variable entre chaque scroll (simule lecture)
                step_delay = random.uniform(80, 250)
                await asyncio.sleep(step_delay / 1000)

            # Pause finale après avoir scrollé
            await self.human_delay(400, 150)

        except Exception:
            pass

    async def scroll_to_element_naturally(self, page: Page, locator: Locator):
        """
        Scroll progressivement jusqu'à ce qu'un élément soit visible.
        Plus naturel que scroll_into_view_if_needed() seul.
        """
        try:
            # D'abord, scroll progressivement
            for _ in range(3):
                await self.human_scroll_down(page, total_px=200, scroll_steps=3)
                is_visible = await locator.is_visible()
                if is_visible:
                    break

            # Scroll précis vers l'élément
            await locator.scroll_into_view_if_needed()
            await self.human_delay(300, 100)

        except Exception:
            try:
                await locator.scroll_into_view_if_needed()
            except Exception:
                pass

    async def browse_page_naturally(self, page: Page):
        """
        Simule un utilisateur qui parcourt la page de résultats:
        scroll progressif du haut vers le bas avant de commencer l'extraction.
        """
        try:
            # Scroll vers le bas pour "voir" la page
            total_scroll = random.randint(300, 700)
            await self.human_scroll_down(page, total_px=total_scroll, scroll_steps=random.randint(3, 7))

            # Petite pause de "lecture" des résultats
            await self.human_delay(random.randint(800, 1800), 300)

            # Parfois, scroll un peu vers le haut (comportement naturel)
            if random.random() < 0.3:
                scroll_up = random.randint(50, 150)
                await page.mouse.wheel(0, -scroll_up)
                await self.human_delay(400, 150)

        except Exception:
            pass

    # =========================================================================
    # FRAPPE HUMAINE
    # =========================================================================

    async def human_type(self, page: Page, locator: Locator, text: str):
        """
        Tape du texte caractère par caractère avec des délais variables,
        comme un vrai utilisateur.

        Args:
            page: Page Playwright
            locator: Champ de texte
            text: Texte à taper
        """
        try:
            await locator.click()
            await self.human_delay(300, 100)

            for char in text:
                await locator.type(char)

                # Délai entre chaque caractère: distribution gaussienne
                # Un humain tape environ 60-80 mots/min = 5-7 chars/sec = 140-200ms/char
                char_delay = random.gauss(150, 40)
                char_delay = max(50, min(char_delay, 400))

                # Parfois, petite hésitation (cherche le caractère suivant)
                if random.random() < 0.05:
                    char_delay += random.uniform(300, 800)

                await asyncio.sleep(char_delay / 1000)

            # Pause finale après avoir tout tapé
            await self.human_delay(300, 100)

        except Exception:
            # Fallback: remplir le texte d'un coup
            await locator.fill(text)

    # =========================================================================
    # COMPORTEMENTS AVANCÉS
    # =========================================================================

    async def page_entry_behavior(self, page: Page):
        """
        Comportement naturel à l'entrée sur une nouvelle page.
        Simule le temps de chargement + la lecture initiale.
        """
        # Attendre que la page soit stable
        try:
            await page.wait_for_load_state('domcontentloaded', timeout=10000)
        except Exception:
            pass

        # Pause initiale de "découverte" de la page
        await self.human_delay(random.randint(600, 1500), 300)

        # Scroll léger initial (regarder ce qu'il y a)
        if random.random() < 0.7:
            await self.human_scroll_down(page, total_px=random.randint(100, 300),
                                          scroll_steps=random.randint(2, 4))

    async def simulate_distraction(self, probability: float = 0.05):
        """
        Simule une distraction de l'utilisateur (pause plus longue qu'habituel).
        """
        if random.random() < probability:
            # Distraction: 5 à 30 secondes
            distraction_time = random.uniform(5, 30)
            await asyncio.sleep(distraction_time)

    # =========================================================================
    # CONFIGURATION DU NAVIGATEUR
    # =========================================================================

    # =========================================================================
    # MONITORING & SÉCURITÉ
    # =========================================================================

    def attach_monitor(self, page: Page):
        """
        Attache le moniteur de réponses HTTP à une page.
        Doit être appelé après la création de chaque page.
        """
        page.on("response", self.response_monitor.on_response)
        logger.info("🛡️ Moniteur HTTP attaché à la page")

    async def check_safety(self, page: Page) -> bool:
        """
        Vérifie si la session est toujours safe.
        Retourne False si on doit s'arrêter.
        """
        danger = self.response_monitor.danger_level

        if danger == "CRITICAL":
            logger.error("🚨 ARRÊT DE SÉCURITÉ — Challenge/Checkpoint LinkedIn détecté !")
            logger.error("🚨 Le compte pourrait être temporairement restreint.")
            return False

        if danger == "HIGH":
            if self.response_monitor.rate_limited:
                logger.warning("⏸️ Rate limit détecté — pause longue de 2-5 minutes...")
                pause = random.uniform(120, 300)
                await asyncio.sleep(pause)
                self.response_monitor.reset()
                return True  # On réessaie après la pause

            if self.response_monitor.auth_wall:
                logger.error("🔐 Redirigé vers authwall — cookie expiré ?")
                return False

        if danger == "MEDIUM":
            logger.warning("⚠️ Taux d'erreurs élevé — ralentissement préventif...")
            await asyncio.sleep(random.uniform(30, 60))

        return True

    # =========================================================================
    # WARM-UP SESSION
    # =========================================================================

    async def warmup_session(self, page: Page):
        """
        Simule le comportement d'un utilisateur qui ouvre LinkedIn :
        1. Visite le feed
        2. Scrolle un peu
        3. Peut-être clique sur une notification
        4. Puis va vers la recherche

        Cela crée un historique de navigation naturel dans la session.
        Un bot va directement sur /search/results/people — un humain, jamais.
        """
        logger.info("🌡️ Warm-up session — visite du feed LinkedIn...")

        try:
            # Aller sur le feed
            await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(random.uniform(2, 4))

            # Vérifier qu'on est bien connecté
            if any(x in page.url for x in ["login", "authwall", "checkpoint"]):
                logger.error("❌ Warm-up: pas connecté, cookie invalide")
                return False

            logger.info("✅ Warm-up: connecté au feed LinkedIn")

            # Simuler la lecture du feed (scroll naturel)
            await self.browse_page_naturally(page)

            # Pause de "lecture" du feed (3-8 secondes)
            await asyncio.sleep(random.uniform(3, 8))

            # Parfois, visiter les notifications (30% de chance)
            if random.random() < 0.30:
                logger.info("🔔 Warm-up: visite des notifications...")
                try:
                    await page.goto("https://www.linkedin.com/notifications/",
                                    wait_until="domcontentloaded", timeout=15000)
                    await asyncio.sleep(random.uniform(2, 5))
                    await self.human_scroll_down(page, total_px=random.randint(100, 300))
                except Exception:
                    pass

            # Parfois, visiter la messagerie (20% de chance)
            if random.random() < 0.20:
                logger.info("💬 Warm-up: visite de la messagerie...")
                try:
                    await page.goto("https://www.linkedin.com/messaging/",
                                    wait_until="domcontentloaded", timeout=15000)
                    await asyncio.sleep(random.uniform(1.5, 4))
                except Exception:
                    pass

            # Pause finale avant de passer à la recherche
            await asyncio.sleep(random.uniform(1, 3))

            logger.info("✅ Warm-up terminé — session naturelle établie")
            return True

        except Exception as e:
            err_str = str(e)
            # Erreurs qui indiquent clairement un cookie expiré / session invalide.
            # Dans ce cas, inutile de continuer — la recherche échouera de la même façon.
            auth_failure_markers = [
                "ERR_TOO_MANY_REDIRECTS",
                "net::ERR_TOO_MANY_REDIRECTS",
            ]
            if any(m in err_str for m in auth_failure_markers):
                # NE PAS annuler le scrape ici : une boucle de redirections sur
                # /feed/ peut survenir même avec un cookie li_at parfaitement
                # valide (cookies compagnons absents, redirection régionale
                # passagère, etc.). On laisse la PAGE DE RECHERCHE — qui possède
                # sa propre détection fiable d'expiration — trancher.
                logger.warning(
                    "⚠️ Warm-up: boucle de redirections sur /feed/ (non bloquant) — "
                    "le cookie peut être valide malgré tout, on passe directement "
                    "à la recherche."
                )
                return True
            logger.warning(f"⚠️ Erreur warm-up (non bloquant): {e}")
            return True  # On continue même si le warm-up échoue (erreur transitoire)

    # =========================================================================
    # CONFIGURATION DU NAVIGATEUR (LEGACY — rétrocompatibilité)
    # =========================================================================
    # Note: préférer StealthProfileManager pour les nouveaux usages.
    # Ces méthodes restent pour ne pas casser le code existant.

    @staticmethod
    async def apply_stealth_headers(context):
        """
        Applique des en-têtes HTTP supplémentaires pour paraître plus humain.
        LEGACY: utiliser StealthProfileManager.get_stealth_headers() de préférence.
        """
        await context.set_extra_http_headers({
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                      "image/avif,image/webp,image/apng,*/*;q=0.8",
            "DNT": "1",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Sec-CH-UA": '"Chromium";v="134", "Google Chrome";v="134", "Not-A.Brand";v="99"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"macOS"',
        })

    @staticmethod
    def get_realistic_viewport():
        """
        LEGACY: utiliser StealthProfileManager.generate_profile().viewport
        """
        viewports = [
            {"width": 1920, "height": 1080},
            {"width": 1440, "height": 900},
            {"width": 1536, "height": 864},
            {"width": 1280, "height": 800},
            {"width": 1366, "height": 768},
            {"width": 1600, "height": 900},
            {"width": 2560, "height": 1440},
        ]
        vp = random.choice(viewports)
        vp['width'] += random.randint(-20, 20)
        vp['height'] += random.randint(-10, 10)
        return vp

    @staticmethod
    async def init_stealth_scripts(page: Page):
        """
        LEGACY: utiliser StealthProfileManager.get_stealth_init_script()
        Cette version reste fonctionnelle mais le StealthProfile est plus complet.
        """
        from utils.stealth_profile import StealthProfileManager
        # Générer un profil par défaut pour le script
        profile = StealthProfileManager.generate_profile()
        await page.add_init_script(StealthProfileManager.get_stealth_init_script(profile))
