# -*- coding: utf-8 -*-
"""
Wrapper synchrone pour LinkedInScraperV2
Permet d'utiliser le scraper async depuis du code synchrone (Streamlit)
"""

import asyncio
from typing import List, Optional, Callable
import pandas as pd

from scraper_v2 import LinkedInScraperV2
from logger import logger


class LinkedInScraperV2Sync:
    """
    Wrapper synchrone pour LinkedInScraperV2
    Utilise asyncio.run() pour exécuter les méthodes async de manière synchrone
    """

    def __init__(self, use_database: bool = True, proxy: dict = None,
                 db_file: str = None, profiles_csv: str = None,
                 config_dir: str = None):
        self.scraper = LinkedInScraperV2(use_database=use_database, proxy=proxy,
                                          db_file=db_file, profiles_csv=profiles_csv,
                                          config_dir=config_dir)
        self.errors = []

    def run_scraper(
        self,
        cookie: str,
        keyword: str,
        entreprise: str,
        nb_profils: int,
        ecoles_ids: List[str],
        inviter: bool = False,
        email_notif: Optional[str] = None,
        message_invitation: str = "",
        reinviter_profils_scrapes: bool = False,
        ile_de_france: bool = False,
        progress_callback: Optional[Callable] = None,
        status_callback: Optional[Callable] = None
    ) -> pd.DataFrame:
        """
        Version synchrone de run_scraper_async

        Cette méthode peut être appelée depuis du code synchrone (comme Streamlit)
        Elle exécute la version async en interne

        Args:
            cookie: Cookie li_at LinkedIn
            keyword: Mots-clés de recherche
            entreprise: Entreprise cible (optionnel)
            nb_profils: Nombre de profils à scraper
            ecoles_ids: IDs des écoles
            inviter: Si True, envoie des invitations
            email_notif: Email pour notifications (optionnel)
            message_invitation: Message personnalisé pour invitations
            reinviter_profils_scrapes: Si True, réinvite les profils déjà scrapés
            progress_callback: Callback pour mise à jour progression
            status_callback: Callback pour mise à jour statut

        Returns:
            DataFrame avec les profils scrapés
        """
        try:
            logger.info("🚀 Lancement du scraper V2 (mode synchrone)")

            # Exécuter la méthode async de manière synchrone
            # asyncio.run() crée un nouvel event loop et exécute la coroutine
            result = asyncio.run(
                self.scraper.run_scraper_async(
                    cookie=cookie,
                    keyword=keyword,
                    entreprise=entreprise,
                    nb_profils=nb_profils,
                    ecoles_ids=ecoles_ids,
                    inviter=inviter,
                    email_notif=email_notif,
                    message_invitation=message_invitation,
                    reinviter_profils_scrapes=reinviter_profils_scrapes,
                    ile_de_france=ile_de_france,
                    progress_callback=progress_callback,
                    status_callback=status_callback
                )
            )

            # Copier les erreurs
            self.errors = self.scraper.errors.copy()

            return result

        except Exception as e:
            logger.error(f"❌ Erreur dans le wrapper synchrone: {e}", exc_info=True)
            self.errors.append(f"Erreur wrapper: {e}")
            return pd.DataFrame()

    def run_url_scraper(
        self,
        cookie: str,
        urls: List[str],
        inviter: bool = False,
        message_invitation: str = "",
        message_direct: str = "",
        progress_callback: Optional[Callable] = None,
        status_callback: Optional[Callable] = None
    ) -> pd.DataFrame:
        """
        Scrape des profils LinkedIn à partir d'une liste d'URLs (mode synchrone).
        Peut aussi inviter (inviter=True) et/ou envoyer un message (message_direct).
        """
        try:
            logger.info(f"🔗 Lancement scraping URLs ({len(urls)} profils)")

            result = asyncio.run(
                self.scraper.run_url_scraper_async(
                    cookie=cookie,
                    urls=urls,
                    inviter=inviter,
                    message_invitation=message_invitation,
                    message_direct=message_direct,
                    progress_callback=progress_callback,
                    status_callback=status_callback
                )
            )

            self.errors = self.scraper.errors.copy()
            return result

        except Exception as e:
            logger.error(f"❌ Erreur wrapper URL scraper: {e}", exc_info=True)
            self.errors.append(f"Erreur: {e}")
            return pd.DataFrame()

    def verifier_acceptations(self, cookie, profils, max_check=30,
                              progress_callback=None, status_callback=None):
        """Version synchrone : détecte les invitations acceptées (1er degré)."""
        try:
            result = asyncio.run(
                self.scraper.verifier_acceptations_async(
                    cookie=cookie, profils=profils, max_check=max_check,
                    progress_callback=progress_callback, status_callback=status_callback,
                )
            )
            self.errors = self.scraper.errors.copy()
            return result
        except Exception as e:
            logger.error(f"❌ Erreur vérification acceptations: {e}", exc_info=True)
            self.errors.append(f"Erreur: {e}")
            return []

    def envoyer_messages(self, cookie, cibles, message, max_msg=20,
                         progress_callback=None, status_callback=None):
        """Version synchrone : envoie un message aux relations sélectionnées."""
        try:
            result = asyncio.run(
                self.scraper.envoyer_messages_async(
                    cookie=cookie, cibles=cibles, message=message, max_msg=max_msg,
                    progress_callback=progress_callback, status_callback=status_callback,
                )
            )
            self.errors = self.scraper.errors.copy()
            return result
        except Exception as e:
            logger.error(f"❌ Erreur envoi messages: {e}", exc_info=True)
            self.errors.append(f"Erreur: {e}")
            return []

    @property
    def db(self):
        """Accès à la base de données via le scraper interne"""
        return self.scraper.db

    @property
    def use_database(self):
        """Accès au flag use_database"""
        return self.scraper.use_database
