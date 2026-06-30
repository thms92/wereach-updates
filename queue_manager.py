# -*- coding: utf-8 -*-
"""
QueueManager - Gestionnaire de file d'attente de scraping
Permet d'enchaîner automatiquement plusieurs scrapings (un par entreprise)
avec des paramètres partagés (keyword, école, cookie, etc.)
"""

import json
import os
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Callable, Dict
from enum import Enum
import pandas as pd

from scraper_v2_sync import LinkedInScraperV2Sync
from logger import logger


class JobStatus(str, Enum):
    EN_ATTENTE = "en_attente"
    EN_COURS = "en_cours"
    TERMINE = "termine"
    ERREUR = "erreur"
    ANNULE = "annule"


@dataclass
class ScrapingJob:
    """Un job de scraping pour une entreprise."""
    entreprise: str
    status: str = JobStatus.EN_ATTENTE
    nb_profils_trouves: int = 0
    nb_invitations_envoyees: int = 0
    erreurs: List[str] = field(default_factory=list)
    debut: Optional[str] = None
    fin: Optional[str] = None
    duree_secondes: int = 0


@dataclass
class QueueConfig:
    """Configuration partagée par tous les jobs de la file."""
    cookie: str = ""
    keyword: str = ""
    nb_profils_par_entreprise: int = 10
    ecoles_ids: List[str] = field(default_factory=list)
    inviter: bool = False
    message_invitation: str = ""
    reinviter_profils_scrapes: bool = False
    ile_de_france: bool = False
    # Pause entre les jobs (en secondes) pour éviter la détection
    pause_entre_jobs_min: int = 30
    pause_entre_jobs_max: int = 90


class QueueManager:
    """
    Gère une file d'attente de jobs de scraping.
    Chaque job correspond à une entreprise différente,
    tous partagent la même configuration (keyword, école, etc.)
    """

    QUEUE_FILE = "config/queue.json"

    def __init__(self, queue_file: str = None):
        self.queue_file = queue_file or self.QUEUE_FILE
        self.config = QueueConfig()
        self.jobs: List[ScrapingJob] = []
        self.is_running = False
        self.current_job_index = -1
        self.all_results: List[pd.DataFrame] = []

    # =========================================================================
    # GESTION DE LA FILE
    # =========================================================================

    def ajouter_entreprise(self, entreprise: str) -> bool:
        """Ajoute une entreprise à la file d'attente."""
        # Éviter les doublons
        noms_existants = [j.entreprise.lower().strip() for j in self.jobs]
        if entreprise.lower().strip() in noms_existants:
            logger.warning(f"⚠️ '{entreprise}' est déjà dans la file")
            return False

        self.jobs.append(ScrapingJob(entreprise=entreprise.strip()))
        logger.info(f"➕ '{entreprise}' ajouté à la file ({len(self.jobs)} jobs)")
        return True

    def ajouter_entreprises(self, entreprises: List[str]) -> int:
        """Ajoute plusieurs entreprises d'un coup. Retourne le nombre ajouté."""
        count = 0
        for e in entreprises:
            e = e.strip()
            if e and self.ajouter_entreprise(e):
                count += 1
        return count

    def supprimer_entreprise(self, index: int) -> bool:
        """Supprime un job par son index."""
        if 0 <= index < len(self.jobs):
            removed = self.jobs.pop(index)
            logger.info(f"🗑️ '{removed.entreprise}' retiré de la file")
            return True
        return False

    def monter_job(self, index: int):
        """Monte un job d'une position dans la file."""
        if 1 <= index < len(self.jobs):
            self.jobs[index], self.jobs[index - 1] = self.jobs[index - 1], self.jobs[index]

    def descendre_job(self, index: int):
        """Descend un job d'une position dans la file."""
        if 0 <= index < len(self.jobs) - 1:
            self.jobs[index], self.jobs[index + 1] = self.jobs[index + 1], self.jobs[index]

    def vider_file(self):
        """Vide toute la file d'attente."""
        self.jobs.clear()
        self.all_results.clear()
        self.current_job_index = -1
        self.is_running = False

    def reset_statuts(self):
        """Remet tous les jobs en attente (pour relancer)."""
        for job in self.jobs:
            job.status = JobStatus.EN_ATTENTE
            job.nb_profils_trouves = 0
            job.nb_invitations_envoyees = 0
            job.erreurs = []
            job.debut = None
            job.fin = None
            job.duree_secondes = 0

    # =========================================================================
    # EXÉCUTION DE LA FILE
    # =========================================================================

    def lancer_file(
        self,
        progress_callback: Optional[Callable] = None,
        status_callback: Optional[Callable] = None,
        job_callback: Optional[Callable] = None,
        proxy: dict = None
    ) -> pd.DataFrame:
        """
        Lance l'exécution séquentielle de tous les jobs en attente.

        Args:
            progress_callback: Appelé avec (progression_globale: float) entre 0 et 1
            status_callback: Appelé avec (texte_statut: str)
            job_callback: Appelé avec (index_job: int, job: ScrapingJob) à chaque changement

        Returns:
            DataFrame consolidé de tous les profils scrapés
        """
        import time
        import random

        if not self.jobs:
            logger.warning("⚠️ File d'attente vide, rien à lancer")
            return pd.DataFrame()

        if not self.config.cookie:
            logger.error("❌ Cookie non configuré")
            return pd.DataFrame()

        self.is_running = True
        self.all_results = []

        # Compter les jobs en attente
        jobs_a_faire = [j for j in self.jobs if j.status == JobStatus.EN_ATTENTE]
        total_jobs = len(jobs_a_faire)

        if total_jobs == 0:
            logger.warning("⚠️ Aucun job en attente")
            self.is_running = False
            return pd.DataFrame()

        logger.info(f"{'═'*60}")
        logger.info(f"🚀 LANCEMENT DE LA FILE D'ATTENTE ({total_jobs} entreprises)")
        logger.info(f"   Keyword: {self.config.keyword}")
        logger.info(f"   Profils/entreprise: {self.config.nb_profils_par_entreprise}")
        logger.info(f"   Invitations: {'Oui' if self.config.inviter else 'Non'}")
        logger.info(f"{'═'*60}")

        jobs_traites = 0
        start_total = datetime.now()

        for i, job in enumerate(self.jobs):
            if job.status != JobStatus.EN_ATTENTE:
                continue

            if not self.is_running:
                job.status = JobStatus.ANNULE
                logger.info(f"⏹️ File annulée, '{job.entreprise}' non traité")
                continue

            self.current_job_index = i
            job.status = JobStatus.EN_COURS
            job.debut = datetime.now().strftime("%H:%M:%S")

            if job_callback:
                job_callback(i, job)

            logger.info(f"\n{'─'*40}")
            logger.info(f"📋 Job {jobs_traites + 1}/{total_jobs}: {job.entreprise}")
            logger.info(f"{'─'*40}")

            if status_callback:
                status_callback(f"🏢 {job.entreprise} ({jobs_traites + 1}/{total_jobs})")

            # Créer un nouveau scraper pour chaque job
            scraper = LinkedInScraperV2Sync(use_database=True, proxy=proxy)
            job_start = datetime.now()

            try:
                def _progress(p):
                    # Progression globale = (jobs terminés + progression du job actuel) / total
                    global_progress = (jobs_traites + p) / total_jobs
                    if progress_callback:
                        progress_callback(min(global_progress, 1.0))

                df = scraper.run_scraper(
                    cookie=self.config.cookie,
                    keyword=self.config.keyword,
                    entreprise=job.entreprise,
                    nb_profils=self.config.nb_profils_par_entreprise,
                    ecoles_ids=self.config.ecoles_ids,
                    inviter=self.config.inviter,
                    message_invitation=self.config.message_invitation,
                    reinviter_profils_scrapes=self.config.reinviter_profils_scrapes,
                    ile_de_france=self.config.ile_de_france,
                    progress_callback=_progress,
                    status_callback=status_callback
                )

                job.duree_secondes = int((datetime.now() - job_start).total_seconds())
                job.fin = datetime.now().strftime("%H:%M:%S")

                if not df.empty:
                    # Ajouter la colonne entreprise cible pour identifier le job
                    df['entreprise_cible'] = job.entreprise
                    self.all_results.append(df)
                    job.nb_profils_trouves = len(df)

                    # Compter les invitations
                    if 'Invitation' in df.columns:
                        job.nb_invitations_envoyees = len(df[df['Invitation'] == 'Oui'])

                    job.status = JobStatus.TERMINE
                    logger.info(f"✅ '{job.entreprise}' terminé: {job.nb_profils_trouves} profils, "
                                f"{job.nb_invitations_envoyees} invitations ({job.duree_secondes}s)")
                else:
                    job.status = JobStatus.TERMINE
                    job.nb_profils_trouves = 0
                    logger.info(f"✅ '{job.entreprise}' terminé: 0 profils ({job.duree_secondes}s)")

                # Copier les erreurs du scraper
                if scraper.errors:
                    job.erreurs = scraper.errors.copy()

            except Exception as e:
                job.status = JobStatus.ERREUR
                job.erreurs.append(str(e))
                job.duree_secondes = int((datetime.now() - job_start).total_seconds())
                job.fin = datetime.now().strftime("%H:%M:%S")
                logger.error(f"❌ Erreur pour '{job.entreprise}': {e}")

            if job_callback:
                job_callback(i, job)

            jobs_traites += 1

            # Pause naturelle entre les jobs (sauf pour le dernier)
            remaining = [j for j in self.jobs[i+1:] if j.status == JobStatus.EN_ATTENTE]
            if remaining and self.is_running:
                pause = random.randint(
                    self.config.pause_entre_jobs_min,
                    self.config.pause_entre_jobs_max
                )
                logger.info(f"⏳ Pause de {pause}s avant le prochain job...")
                if status_callback:
                    status_callback(f"⏳ Pause {pause}s avant {remaining[0].entreprise}...")
                time.sleep(pause)

        # Résultats finaux
        self.is_running = False
        self.current_job_index = -1
        duration_total = int((datetime.now() - start_total).total_seconds())

        logger.info(f"\n{'═'*60}")
        logger.info(f"✅ FILE D'ATTENTE TERMINÉE")
        logger.info(f"   Jobs traités: {jobs_traites}/{total_jobs}")
        logger.info(f"   Durée totale: {duration_total}s")
        logger.info(f"{'═'*60}")

        if self.all_results:
            return pd.concat(self.all_results, ignore_index=True)
        return pd.DataFrame()

    def arreter(self):
        """Arrête l'exécution de la file après le job en cours."""
        self.is_running = False
        logger.info("⏹️ Arrêt demandé (finira le job en cours)")

    # =========================================================================
    # RÉSUMÉ & STATISTIQUES
    # =========================================================================

    def get_resume(self) -> Dict:
        """Retourne un résumé de l'état de la file."""
        total = len(self.jobs)
        en_attente = sum(1 for j in self.jobs if j.status == JobStatus.EN_ATTENTE)
        en_cours = sum(1 for j in self.jobs if j.status == JobStatus.EN_COURS)
        termines = sum(1 for j in self.jobs if j.status == JobStatus.TERMINE)
        erreurs = sum(1 for j in self.jobs if j.status == JobStatus.ERREUR)
        annules = sum(1 for j in self.jobs if j.status == JobStatus.ANNULE)

        total_profils = sum(j.nb_profils_trouves for j in self.jobs)
        total_invitations = sum(j.nb_invitations_envoyees for j in self.jobs)
        total_duree = sum(j.duree_secondes for j in self.jobs)

        return {
            "total_jobs": total,
            "en_attente": en_attente,
            "en_cours": en_cours,
            "termines": termines,
            "erreurs": erreurs,
            "annules": annules,
            "total_profils": total_profils,
            "total_invitations": total_invitations,
            "total_duree_secondes": total_duree,
        }

    # =========================================================================
    # SAUVEGARDE / CHARGEMENT (persistance entre sessions)
    # =========================================================================

    def sauvegarder(self):
        """Sauvegarde la file d'attente dans un fichier JSON."""
        data = {
            "config": {
                "keyword": self.config.keyword,
                "nb_profils_par_entreprise": self.config.nb_profils_par_entreprise,
                "ecoles_ids": self.config.ecoles_ids,
                "inviter": self.config.inviter,
                "message_invitation": self.config.message_invitation,
                "reinviter_profils_scrapes": self.config.reinviter_profils_scrapes,
                "ile_de_france": self.config.ile_de_france,
                "pause_entre_jobs_min": self.config.pause_entre_jobs_min,
                "pause_entre_jobs_max": self.config.pause_entre_jobs_max,
            },
            "jobs": [
                {
                    "entreprise": j.entreprise,
                    "status": j.status,
                    "nb_profils_trouves": j.nb_profils_trouves,
                    "nb_invitations_envoyees": j.nb_invitations_envoyees,
                }
                for j in self.jobs
            ]
        }

        os.makedirs(os.path.dirname(self.queue_file), exist_ok=True)
        with open(self.queue_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"💾 File d'attente sauvegardée ({len(self.jobs)} jobs)")

    def charger(self):
        """Charge la file d'attente depuis le fichier JSON."""
        if not os.path.exists(self.queue_file):
            return

        try:
            with open(self.queue_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            cfg = data.get("config", {})
            self.config.keyword = cfg.get("keyword", "")
            self.config.nb_profils_par_entreprise = cfg.get("nb_profils_par_entreprise", 10)
            self.config.ecoles_ids = cfg.get("ecoles_ids", [])
            self.config.inviter = cfg.get("inviter", False)
            self.config.message_invitation = cfg.get("message_invitation", "")
            self.config.reinviter_profils_scrapes = cfg.get("reinviter_profils_scrapes", False)
            self.config.ile_de_france = cfg.get("ile_de_france", False)
            self.config.pause_entre_jobs_min = cfg.get("pause_entre_jobs_min", 30)
            self.config.pause_entre_jobs_max = cfg.get("pause_entre_jobs_max", 90)

            self.jobs = []
            for j_data in data.get("jobs", []):
                self.jobs.append(ScrapingJob(
                    entreprise=j_data["entreprise"],
                    status=j_data.get("status", JobStatus.EN_ATTENTE),
                    nb_profils_trouves=j_data.get("nb_profils_trouves", 0),
                    nb_invitations_envoyees=j_data.get("nb_invitations_envoyees", 0),
                ))

            logger.info(f"📂 File d'attente chargée ({len(self.jobs)} jobs)")

        except Exception as e:
            logger.warning(f"⚠️ Erreur chargement file: {e}")
