# -*- coding: utf-8 -*-
import json
import os
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, asdict
import threading
import time as time_module
from config import ScraperConfig
from logger import logger

@dataclass
class ScheduledTask:
    id: str
    name: str
    enabled: bool
    cookie: str
    keyword: str
    entreprise: str
    nb_profils: int
    ecoles: List[str]
    inviter: bool
    notify_email: str
    frequency: str
    schedule_time: str
    weekdays: List[int]
    schedule_date: Optional[str] = None
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    total_runs: int = 0
    last_result: Optional[Dict] = None

class TaskScheduler:
    def __init__(self, schedule_file: str = ScraperConfig.SCHEDULE_FILE):
        self.schedule_file = schedule_file
        self.tasks: Dict[str, ScheduledTask] = {}
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.callback: Optional[Callable] = None
        os.makedirs(os.path.dirname(schedule_file), exist_ok=True)
        self.load_tasks()
    
    def load_tasks(self):
        try:
            if os.path.exists(self.schedule_file):
                with open(self.schedule_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.tasks = {
                        task_id: ScheduledTask(**task_data)
                        for task_id, task_data in data.items()
                    }
                logger.info(f"Chargé {len(self.tasks)} tâche(s)")
        except Exception as e:
            logger.error(f"Erreur chargement tâches: {e}")
            self.tasks = {}
    
    def save_tasks(self):
        try:
            data = {task_id: asdict(task) for task_id, task in self.tasks.items()}
            with open(self.schedule_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"Sauvegardé {len(self.tasks)} tâche(s)")
        except Exception as e:
            logger.error(f"Erreur sauvegarde tâches: {e}")
    
    def add_task(self, task: ScheduledTask) -> bool:
        try:
            task.next_run = self._calculate_next_run(task)
            self.tasks[task.id] = task
            self.save_tasks()
            logger.info(f"Tâche ajoutée: {task.name}")
            return True
        except Exception as e:
            logger.error(f"Erreur ajout tâche: {e}")
            return False
    
    def remove_task(self, task_id: str) -> bool:
        if task_id in self.tasks:
            del self.tasks[task_id]
            self.save_tasks()
            return True
        return False
    
    def enable_task(self, task_id: str, enabled: bool = True):
        if task_id in self.tasks:
            self.tasks[task_id].enabled = enabled
            if enabled:
                self.tasks[task_id].next_run = self._calculate_next_run(self.tasks[task_id])
            self.save_tasks()
    
    def get_all_tasks(self) -> List[ScheduledTask]:
        return list(self.tasks.values())
    
    def set_callback(self, callback: Callable):
        self.callback = callback
    
    def start(self):
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._run_scheduler, daemon=True)
            self.thread.start()
            logger.info("Planificateur démarré")
    
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("Planificateur arrêté")
    
    def _run_scheduler(self):
        while self.running:
            try:
                self._check_and_run_tasks()
                time_module.sleep(ScraperConfig.SCHEDULER_CHECK_INTERVAL)
            except Exception as e:
                logger.error(f"Erreur planificateur: {e}")
    
    def _check_and_run_tasks(self):
        now = datetime.now()
        for task_id, task in list(self.tasks.items()):
            if not task.enabled or not task.next_run:
                continue
            next_run_dt = datetime.fromisoformat(task.next_run)
            if now >= next_run_dt:
                logger.info(f"Exécution tâche: {task.name}")
                if self.callback:
                    try:
                        result = self.callback(task)
                        task.last_result = result
                    except Exception as e:
                        logger.error(f"Erreur exécution: {e}")
                        task.last_result = {"error": str(e)}
                task.last_run = now.isoformat()
                task.total_runs += 1
                if task.frequency == 'once':
                    task.enabled = False
                    task.next_run = None
                else:
                    task.next_run = self._calculate_next_run(task)
                self.save_tasks()
    
    def _calculate_next_run(self, task: ScheduledTask) -> Optional[str]:
        now = datetime.now()
        try:
            hour, minute = map(int, task.schedule_time.split(':'))
            schedule_time_obj = time(hour, minute)
            
            if task.frequency == 'once':
                if task.schedule_date:
                    schedule_date = datetime.strptime(task.schedule_date, '%Y-%m-%d').date()
                    next_run = datetime.combine(schedule_date, schedule_time_obj)
                    if next_run <= now:
                        return None
                    return next_run.isoformat()
            elif task.frequency == 'daily':
                next_run = datetime.combine(now.date(), schedule_time_obj)
                if next_run <= now:
                    next_run += timedelta(days=1)
                return next_run.isoformat()
            elif task.frequency == 'weekly':
                next_run = datetime.combine(now.date(), schedule_time_obj)
                for _ in range(8):
                    if next_run.weekday() in task.weekdays and next_run > now:
                        return next_run.isoformat()
                    next_run += timedelta(days=1)
            return None
        except Exception as e:
            logger.error(f"Erreur calcul next_run: {e}")
            return None
    
    def get_next_scheduled_tasks(self, limit: int = 5) -> List[ScheduledTask]:
        enabled_tasks = [t for t in self.tasks.values() if t.enabled and t.next_run]
        return sorted(enabled_tasks, key=lambda t: t.next_run)[:limit]
