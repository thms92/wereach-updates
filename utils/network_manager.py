# -*- coding: utf-8 -*-
"""
Module de gestion réseau avec retry intelligent et gestion d'erreurs
Gère les timeouts, rate limiting, erreurs temporaires vs permanentes
"""

import asyncio
from typing import Callable, Any, Optional, TypeVar, Dict
from dataclasses import dataclass
from datetime import datetime, timedelta
from logger import logger

T = TypeVar('T')


@dataclass
class RetryConfig:
    """Configuration pour les tentatives de retry"""
    max_attempts: int = 3
    base_delay: float = 1.0  # Délai de base en secondes
    max_delay: float = 30.0  # Délai maximum en secondes
    exponential_base: float = 2.0  # Base pour backoff exponentiel
    timeout: int = 60000  # Timeout par défaut en ms


class NetworkError(Exception):
    """Erreur réseau de base"""
    pass


class TemporaryNetworkError(NetworkError):
    """Erreur réseau temporaire (peut être retentée)"""
    pass


class PermanentNetworkError(NetworkError):
    """Erreur réseau permanente (ne pas retenter)"""
    pass


class RateLimitError(TemporaryNetworkError):
    """Erreur de rate limiting"""
    pass


class NetworkManager:
    """
    Gestionnaire réseau avec retry intelligent
    Gère les erreurs temporaires, rate limiting, timeouts
    """

    def __init__(self, config: Optional[RetryConfig] = None):
        self.config = config or RetryConfig()
        self.rate_limit_reset_time: Optional[datetime] = None
        self.error_counts: Dict[str, int] = {}
        # Dernière erreur rencontrée par safe_page_goto (utile pour
        # diagnostiquer un cookie expiré vs une vraie panne réseau).
        self.last_error: Optional[Exception] = None

    async def retry_async(
        self,
        func: Callable,
        *args,
        operation_name: str = "operation",
        **kwargs
    ) -> Any:
        """
        Exécute une fonction async avec retry intelligent

        Args:
            func: Fonction async à exécuter
            operation_name: Nom de l'opération pour les logs
            *args, **kwargs: Arguments pour la fonction

        Returns:
            Résultat de la fonction

        Raises:
            NetworkError: Si toutes les tentatives échouent
        """
        last_error = None

        for attempt in range(1, self.config.max_attempts + 1):
            try:
                # Vérifier le rate limiting
                if self.rate_limit_reset_time:
                    wait_time = (self.rate_limit_reset_time - datetime.now()).total_seconds()
                    if wait_time > 0:
                        logger.warning(f"⏳ Rate limit actif, attente de {wait_time:.1f}s")
                        await asyncio.sleep(wait_time)
                        self.rate_limit_reset_time = None

                # Exécuter la fonction
                logger.debug(f"🔄 {operation_name} - Tentative {attempt}/{self.config.max_attempts}")
                result = await func(*args, **kwargs)

                # Succès : réinitialiser les compteurs d'erreurs
                if operation_name in self.error_counts:
                    del self.error_counts[operation_name]

                return result

            except PermanentNetworkError as e:
                # Erreur permanente : ne pas retenter
                logger.error(f"❌ {operation_name} - Erreur permanente : {e}")
                raise

            except RateLimitError as e:
                # Rate limiting : attendre avant de retenter
                logger.warning(f"⏸️ {operation_name} - Rate limit détecté")
                self.rate_limit_reset_time = datetime.now() + timedelta(seconds=60)
                last_error = e

                if attempt < self.config.max_attempts:
                    await asyncio.sleep(60)  # Attendre 1 minute
                    continue
                else:
                    raise

            except TemporaryNetworkError as e:
                # Erreur temporaire : retry avec backoff exponentiel
                last_error = e
                self.error_counts[operation_name] = self.error_counts.get(operation_name, 0) + 1

                if attempt < self.config.max_attempts:
                    delay = self._calculate_backoff_delay(attempt)
                    logger.warning(
                        f"⚠️ {operation_name} - Erreur temporaire (tentative {attempt}/{self.config.max_attempts}): {e}"
                    )
                    logger.info(f"⏱️ Nouvelle tentative dans {delay:.1f}s")
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(f"❌ {operation_name} - Échec après {self.config.max_attempts} tentatives")
                    raise

            except Exception as e:
                # Erreur inconnue : considérer comme temporaire
                logger.error(f"⚠️ {operation_name} - Erreur inattendue : {type(e).__name__}: {e}")
                last_error = TemporaryNetworkError(f"Erreur inattendue: {e}")

                if attempt < self.config.max_attempts:
                    delay = self._calculate_backoff_delay(attempt)
                    logger.info(f"⏱️ Nouvelle tentative dans {delay:.1f}s")
                    await asyncio.sleep(delay)
                    continue
                else:
                    raise last_error

        # Ne devrait jamais arriver ici
        raise last_error or NetworkError(f"{operation_name} a échoué")

    def retry_sync(
        self,
        func: Callable,
        *args,
        operation_name: str = "operation",
        **kwargs
    ) -> Any:
        """
        Version synchrone de retry_async pour compatibilité

        Args:
            func: Fonction synchrone à exécuter
            operation_name: Nom de l'opération pour les logs
            *args, **kwargs: Arguments pour la fonction

        Returns:
            Résultat de la fonction
        """
        import time

        last_error = None

        for attempt in range(1, self.config.max_attempts + 1):
            try:
                # Vérifier le rate limiting
                if self.rate_limit_reset_time:
                    wait_time = (self.rate_limit_reset_time - datetime.now()).total_seconds()
                    if wait_time > 0:
                        logger.warning(f"⏳ Rate limit actif, attente de {wait_time:.1f}s")
                        time.sleep(wait_time)
                        self.rate_limit_reset_time = None

                # Exécuter la fonction
                logger.debug(f"🔄 {operation_name} - Tentative {attempt}/{self.config.max_attempts}")
                result = func(*args, **kwargs)

                # Succès : réinitialiser les compteurs d'erreurs
                if operation_name in self.error_counts:
                    del self.error_counts[operation_name]

                return result

            except PermanentNetworkError as e:
                logger.error(f"❌ {operation_name} - Erreur permanente : {e}")
                raise

            except RateLimitError as e:
                logger.warning(f"⏸️ {operation_name} - Rate limit détecté")
                self.rate_limit_reset_time = datetime.now() + timedelta(seconds=60)
                last_error = e

                if attempt < self.config.max_attempts:
                    time.sleep(60)
                    continue
                else:
                    raise

            except (TemporaryNetworkError, Exception) as e:
                last_error = e
                self.error_counts[operation_name] = self.error_counts.get(operation_name, 0) + 1

                if attempt < self.config.max_attempts:
                    delay = self._calculate_backoff_delay(attempt)
                    logger.warning(
                        f"⚠️ {operation_name} - Erreur (tentative {attempt}/{self.config.max_attempts}): {e}"
                    )
                    logger.info(f"⏱️ Nouvelle tentative dans {delay:.1f}s")
                    time.sleep(delay)
                    continue
                else:
                    logger.error(f"❌ {operation_name} - Échec après {self.config.max_attempts} tentatives")
                    raise

        raise last_error or NetworkError(f"{operation_name} a échoué")

    def _calculate_backoff_delay(self, attempt: int) -> float:
        """
        Calcule le délai d'attente avec backoff exponentiel

        Args:
            attempt: Numéro de la tentative (1, 2, 3, ...)

        Returns:
            Délai en secondes
        """
        # Backoff exponentiel : base_delay * (exponential_base ^ (attempt - 1))
        # Exemple avec base=1.0 et exp=2.0 : 1s, 2s, 4s, 8s, 16s...
        delay = self.config.base_delay * (self.config.exponential_base ** (attempt - 1))

        # Appliquer le délai maximum
        delay = min(delay, self.config.max_delay)

        # Ajouter un peu de jitter pour éviter les thundering herd
        import random
        jitter = random.uniform(0, 0.1 * delay)
        delay += jitter

        return delay

    @staticmethod
    def classify_playwright_error(error: Exception) -> NetworkError:
        """
        Classifie une erreur Playwright en erreur réseau appropriée

        Args:
            error: Exception Playwright

        Returns:
            NetworkError appropriée (Temporary, Permanent, RateLimit)
        """
        error_message = str(error).lower()

        # Erreurs de rate limiting
        if any(keyword in error_message for keyword in ['rate limit', 'too many requests', '429']):
            return RateLimitError("Rate limit LinkedIn détecté")

        # Erreurs temporaires (réseau, timeout)
        if any(keyword in error_message for keyword in [
            'timeout', 'timed out', 'connection', 'network',
            'dns', 'socket', 'econnreset', 'enotfound'
        ]):
            return TemporaryNetworkError(f"Erreur réseau temporaire: {error}")

        # Erreurs permanentes (authentification, page non trouvée)
        if any(keyword in error_message for keyword in [
            'login', 'authentication', 'unauthorized', '401', '403',
            'not found', '404', 'forbidden'
        ]):
            return PermanentNetworkError(f"Erreur permanente: {error}")

        # Par défaut : erreur temporaire
        return TemporaryNetworkError(f"Erreur inconnue: {error}")

    async def safe_page_goto(self, page, url: str, timeout: Optional[int] = None) -> bool:
        """
        Navigate vers une URL avec gestion d'erreurs

        Args:
            page: Page Playwright
            url: URL cible
            timeout: Timeout en ms (optionnel)

        Returns:
            True si succès, False sinon
        """
        timeout = timeout or self.config.timeout

        async def _goto():
            try:
                await page.goto(url, timeout=timeout, wait_until="domcontentloaded")
                return True
            except Exception as e:
                raise self.classify_playwright_error(e)

        try:
            self.last_error = None
            return await self.retry_async(_goto, operation_name=f"goto {url[:50]}")
        except NetworkError as e:
            self.last_error = e
            logger.error(f"❌ Impossible de charger {url}: {e}")
            return False

    async def safe_wait_for_selector(
        self,
        page,
        selector: str,
        timeout: Optional[int] = None,
        state: str = "visible"
    ) -> bool:
        """
        Attend un sélecteur avec gestion d'erreurs

        Args:
            page: Page Playwright
            selector: Sélecteur CSS
            timeout: Timeout en ms
            state: État attendu (visible, attached, etc.)

        Returns:
            True si trouvé, False sinon
        """
        timeout = timeout or self.config.timeout

        async def _wait():
            try:
                await page.wait_for_selector(selector, timeout=timeout, state=state)
                return True
            except Exception as e:
                # Timeout n'est pas une erreur réseau
                if 'timeout' in str(e).lower():
                    logger.debug(f"Sélecteur non trouvé : {selector}")
                    return False
                raise self.classify_playwright_error(e)

        try:
            return await self.retry_async(_wait, operation_name=f"wait selector {selector[:30]}")
        except NetworkError:
            return False

    def get_error_summary(self) -> Dict[str, int]:
        """
        Retourne un résumé des erreurs rencontrées

        Returns:
            Dictionnaire {operation: nombre_erreurs}
        """
        return self.error_counts.copy()

    def reset_error_counts(self):
        """Réinitialise les compteurs d'erreurs"""
        self.error_counts.clear()
        self.rate_limit_reset_time = None
        logger.info("♻️ Compteurs d'erreurs réinitialisés")
