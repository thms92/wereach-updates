# -*- coding: utf-8 -*-
"""Le nom de la personne, demandé une fois, et le signal de connexion.

Demande de Thomas (2026-10-22) : savoir qui utilise quelle version, et
quand. À chaque ouverture, l'outil envoie au webhook n8n de Thomas trois
choses et rien d'autre : le nom saisi, la version, la date et l'heure.
Ni contacts, ni recherches, ni session LinkedIn.

L'envoi part dans un fil à part, avec un délai court, et toute erreur est
avalée : sans réseau ou si n8n ne répond pas, l'outil s'ouvre normalement.
"""

import json
import os
import pwd
import threading
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

FICHIER_NOM = "nom_utilisateur.txt"


def lire_nom(config_dir) -> str:
    try:
        return (Path(config_dir) / FICHIER_NOM).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def enregistrer_nom(config_dir, nom: str) -> None:
    dossier = Path(config_dir)
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / FICHIER_NOM).write_text(nom.strip(), encoding="utf-8")


def nom_par_defaut() -> str:
    """Le nom complet de la session Mac, pour pré-remplir le champ."""
    try:
        return pwd.getpwuid(os.getuid()).pw_gecos.split(",")[0].strip()
    except (KeyError, OSError):
        return ""


def message_connexion(nom: str, version: str, maintenant: datetime = None) -> dict:
    maintenant = maintenant or datetime.now(ZoneInfo("Europe/Paris"))
    return {"nom": nom, "version": version, "date": maintenant.strftime("%d/%m/%Y %H:%M")}


def _envoyer(url: str, message: dict) -> None:
    try:
        requete = urllib.request.Request(
            url, data=json.dumps(message).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        urllib.request.urlopen(requete, timeout=5).close()
    except Exception:
        pass


def signaler_connexion(url: str, nom: str, version: str) -> bool:
    """Envoie le signal sans attendre la réponse. Faux s'il n'y a rien à faire."""
    if not (url and nom):
        return False
    threading.Thread(target=_envoyer, args=(url, message_connexion(nom, version)),
                     daemon=True).start()
    return True
