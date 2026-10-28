# -*- coding: utf-8 -*-
"""
Wrapper synchrone pour LinkedInScraperV2
Permet d'utiliser le scraper async depuis du code synchrone (Streamlit)
"""

import asyncio
from contextlib import contextmanager
from datetime import datetime
from typing import List, Optional, Callable, Union
import pandas as pd

from config import ScraperConfig
from scraper_v2 import LinkedInScraperV2
from utils.budget import LIMITE_PAGES_ATTEINTE
from logger import logger
from utils.seances import (debut_action, fin_action, noter_verification, numero_seance,
                           verification_permise)
from utils.verrou_linkedin import VerrouOccupe, session_linkedin


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
        self.config_dir = config_dir
        # Heure locale du Mac ; remplaçable dans les tests.
        self._horloge = datetime.now
        self._debut_seance = None

    def _refus_seance(self, verification: bool = False) -> Optional[str]:
        """Le refus de séance pour l'action qui commence, ou None.

        Appelé avant le verrou et avant Chrome. Pages LinkedIn du jour
        épuisées : refus, comme la pause ou les séances du jour. Permise : le
        scraper reçoit les pages qui restent dans la séance et repart de 0
        page.
        """
        self._debut_seance = self._horloge()
        refus = None
        limites = self.scraper.human.daily_limits
        if not limites.can_navigate():
            refus = LIMITE_PAGES_ATTEINTE.format(n=limites.pages_today)
        if refus is None and verification:
            refus = verification_permise(self.config_dir, self._debut_seance)
        if refus is None:
            refus, restantes = debut_action(self.config_dir, self._debut_seance)
        if refus:
            logger.warning(f"🚫 {refus}")
            self.errors = [refus]
            return refus
        self.scraper.limite_pages_seance = restantes
        self.scraper.pages_cette_seance = 0
        # Dernière séance du jour : sa fin dira « demain », pas « dans 20 minutes ».
        self.scraper.derniere_seance_du_jour = (
            numero_seance(self.config_dir, self._debut_seance)
            >= ScraperConfig.MAX_SEANCES_PER_DAY)
        return None

    @contextmanager
    def _session(self, activite: str, verification: bool = False):
        """Verrou LinkedIn, puis pages de l'action ajoutées à la séance, même
        sur échec. Session occupée (VerrouOccupe) : l'état n'est pas touché."""
        with session_linkedin(self.config_dir, activite):
            try:
                yield
            finally:
                fin_action(self.config_dir, self._horloge(),
                           self.scraper.pages_cette_seance, debut=self._debut_seance)
                if verification and getattr(self.scraper, "verifiees", None):
                    noter_verification(self.config_dir, self._horloge())

    def run_scraper(
        self,
        cookie: str,
        keyword: str,
        entreprises: Union[str, List[str], None],
        nb_profils: int,
        ecoles_ids: List[str],
        secteurs_ids: Optional[List[str]] = None,
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
            entreprises: Entreprise(s) cible(s) — chaîne ou liste (optionnel)
            nb_profils: Nombre de profils à scraper
            ecoles_ids: IDs des écoles
            secteurs_ids: IDs de secteurs LinkedIn (facette industry, optionnel)
            inviter: Si True, envoie des invitations
            email_notif: Email pour notifications (optionnel)
            message_invitation: Message personnalisé pour invitations
            reinviter_profils_scrapes: Si True, réinvite les profils déjà scrapés
            progress_callback: Callback pour mise à jour progression
            status_callback: Callback pour mise à jour statut

        Returns:
            DataFrame avec les profils scrapés
        """
        if self._refus_seance():
            return pd.DataFrame()
        try:
            logger.info("🚀 Lancement du scraper V2 (mode synchrone)")

            # Exécuter la méthode async de manière synchrone
            # asyncio.run() crée un nouvel event loop et exécute la coroutine
            with self._session("recherche"):
                result = asyncio.run(
                    self.scraper.run_scraper_async(
                        cookie=cookie,
                        keyword=keyword,
                        entreprises=entreprises,
                        nb_profils=nb_profils,
                        ecoles_ids=ecoles_ids,
                        secteurs_ids=secteurs_ids,
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

        except VerrouOccupe as occupe:
            self.errors = [str(occupe)]
            return pd.DataFrame()
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
        if self._refus_seance():
            return pd.DataFrame()
        try:
            logger.info(f"🔗 Lancement scraping URLs ({len(urls)} profils)")

            with self._session("récupération par URLs"):
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

        except VerrouOccupe as occupe:
            self.errors = [str(occupe)]
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"❌ Erreur wrapper URL scraper: {e}", exc_info=True)
            self.errors.append(f"Erreur: {e}")
            return pd.DataFrame()

    def recolter_browsemap(self, cookie, url_reference, status_callback=None):
        """Version synchrone : profils voisins d'un profil de référence.

        Rend `([], None)` sur échec plutôt que de lever : Streamlit
        afficherait une trace à l'écran, là où l'utilisateur attend une
        phrase.
        """
        if self._refus_seance():
            return [], None
        try:
            logger.info(f"👥 Récolte des profils voisins de {url_reference}")

            with self._session("profils similaires"):
                result = asyncio.run(
                    self.scraper.recolter_browsemap_async(
                        cookie=cookie,
                        url_reference=url_reference,
                        status_callback=status_callback,
                    )
                )

            self.errors = self.scraper.errors.copy()
            return result

        except VerrouOccupe as occupe:
            self.errors = [str(occupe)]
            return [], None
        except Exception as e:
            logger.error(f"❌ Erreur récolte profils voisins: {e}", exc_info=True)
            self.errors.append(f"Erreur: {e}")
            return [], None

    def verifier_acceptations(self, cookie, profils,
                              max_check=ScraperConfig.MAX_VERIFICATIONS_PAR_PASSAGE,
                              progress_callback=None, status_callback=None):
        """Version synchrone : détecte les invitations acceptées (1er degré).

        `self.verifiees` : URL dont le statut a été établi ([] si session occupée ou erreur)."""
        self.verifiees = []
        if self._refus_seance(verification=True):
            return []
        # Une liste d'un appel précédent ne doit pas noter la vérification.
        self.scraper.verifiees = []
        try:
            with self._session("vérification des acceptations", verification=True):
                result = asyncio.run(
                    self.scraper.verifier_acceptations_async(
                        cookie=cookie, profils=profils, max_check=max_check,
                        progress_callback=progress_callback, status_callback=status_callback,
                    )
                )
            self.errors = self.scraper.errors.copy()
            self.verifiees = list(self.scraper.verifiees)
            return result
        except VerrouOccupe as occupe:
            self.errors = [str(occupe)]
            return []
        except Exception as e:
            logger.error(f"❌ Erreur vérification acceptations: {e}", exc_info=True)
            self.errors.append(f"Erreur: {e}")
            return []

    def envoyer_messages(self, cookie, cibles, message,
                         max_msg=ScraperConfig.MAX_MESSAGES_PAR_SEANCE,
                         progress_callback=None, status_callback=None):
        """Version synchrone : envoie un message aux relations sélectionnées."""
        if self._refus_seance():
            return []
        try:
            with self._session("envoi de messages"):
                result = asyncio.run(
                    self.scraper.envoyer_messages_async(
                        cookie=cookie, cibles=cibles, message=message, max_msg=max_msg,
                        progress_callback=progress_callback, status_callback=status_callback,
                    )
                )
            self.errors = self.scraper.errors.copy()
            return result
        except VerrouOccupe as occupe:
            self.errors = [str(occupe)]
            return []
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
