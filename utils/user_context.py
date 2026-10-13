# -*- coding: utf-8 -*-
"""Identité et chemins isolés par utilisateur (multi-locataire)."""
import hashlib
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

CF_HEADER = "cf-access-authenticated-user-email"
DEFAULT_DEV_EMAIL = "local@dev"


def user_id_from_email(email: str) -> str:
    norm = (email or "").strip().lower().encode("utf-8")
    return hashlib.sha256(norm).hexdigest()[:16]


def resolve_user_email(headers: dict, dev_fallback: str | None) -> str:
    for k, v in (headers or {}).items():
        if k.lower() == CF_HEADER and v:
            return v.strip()
    return (dev_fallback or DEFAULT_DEV_EMAIL).strip()


@dataclass
class UserPaths:
    base: Path
    config_dir: Path
    cookie_file: Path
    key_file: Path
    db_file: Path
    queue_file: Path
    profiles_csv: Path
    proxy_file: Path


# Emplacement historique : à l'intérieur du dossier de l'application.
ANCIENNE_RACINE = Path("data/users")


def racine_donnees() -> Path:
    """Où vivent les données utilisateur, hors du dossier de l'application.

    Ce dossier peut être posé sur le Bureau, que macOS synchronise sur iCloud
    par défaut. iCloud décharge alors des fichiers pour gagner de la place :
    l'environnement Python casse et la base SQLite devient instable. Seul
    Téléchargements y échappait, d'où un outil qui ne marchait qu'à cet
    endroit. Application Support n'est jamais synchronisé, n'exige aucune
    autorisation de confidentialité, et survit au remplacement du dossier —
    donc retélécharger le zip ne fait plus rien perdre.
    """
    forcee = os.environ.get("WEREACH_DATA_DIR", "").strip()
    if forcee:
        return Path(forcee)
    if sys.platform == "darwin":
        return (Path.home() / "Library" / "Application Support" / "We.Reach"
                / "data" / "users")
    # Serveur (déploiement Linux) : on garde le comportement historique.
    return ANCIENNE_RACINE


def migrer_donnees_locales(uid: str, racine) -> bool:
    """Récupère les données laissées dans l'ancien emplacement.

    Ne déplace que si la destination n'existe pas : on n'écrase jamais des
    données plus récentes, et en cas de doute on ne supprime rien.
    """
    ancien = ANCIENNE_RACINE / uid
    nouveau = Path(racine) / uid
    if not ancien.is_dir() or nouveau.exists():
        return False
    try:
        nouveau.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(ancien), str(nouveau))
        return True
    except Exception:
        return False


def user_paths_for(email: str, root: str = None) -> UserPaths:
    uid = user_id_from_email(email)
    if root is None:
        racine = racine_donnees()
        migrer_donnees_locales(uid, racine)
    else:
        racine = Path(root)
    base = racine / uid
    config_dir = base / "config"
    base.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    return UserPaths(
        base=base,
        config_dir=config_dir,
        cookie_file=config_dir / "cookie.txt",
        key_file=config_dir / "secret.key",
        db_file=base / "profiles.db",
        queue_file=config_dir / "queue.json",
        profiles_csv=base / "profils_scrapes.csv",
        proxy_file=config_dir / "proxy.enc",
    )


def racine_application() -> Path:
    """Dossier stable de l'application, hors du code et hors des données.

    Y vivent les marqueurs et réglages qui doivent survivre au remplacement
    du dossier de l'application — donc aux mises à jour et aux
    retéléchargements.
    """
    forcee = os.environ.get("WEREACH_DATA_DIR", "").strip()
    if forcee:
        return Path(forcee)
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "We.Reach"
    return Path(".")


def mode_admin() -> bool:
    """Faut-il montrer les réglages techniques ?

    Le proxy n'a aucun sens dans l'usage actuel — chacun scrape depuis son
    propre Mac, donc sa propre adresse IP — et le volet Réglages contient un
    bouton qui efface toute la base de profils. Ni l'un ni l'autre n'a sa
    place sous la main de l'équipe.

    L'administrateur les retrouve en déposant un fichier `admin` dans le
    dossier de l'application ; la variable WEREACH_ADMIN tranche dans les deux
    sens si besoin (déploiement serveur, dépannage).
    """
    drapeau = os.environ.get("WEREACH_ADMIN", "").strip().lower()
    if drapeau in ("1", "true", "oui"):
        return True
    if drapeau in ("0", "false", "non"):
        return False
    return (racine_application() / "admin").exists()
