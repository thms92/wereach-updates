# -*- coding: utf-8 -*-
import logging
import os
from logging.handlers import RotatingFileHandler
from config import ScraperConfig


def _fichier_journal() -> str:
    # Rattaché au dossier de l'application, comme le lisent la page Journal
    # et le diagnostic (utils/diagnostic.py::chemin_journal) : lancé depuis
    # un autre dossier, le logger écrivait ailleurs que ce qu'ils montraient.
    chemin = os.path.expanduser(ScraperConfig.LOG_FILE)
    if os.path.isabs(chemin):
        return chemin
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), chemin)

def setup_logger(name="linkedin_scraper"):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    if logger.handlers:
        return logger
    
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    file_handler = RotatingFileHandler(
        _fichier_journal(),
        maxBytes=10*1024*1024,
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger

logger = setup_logger()
