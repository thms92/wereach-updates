# -*- coding: utf-8 -*-
"""Rapport de problème pré-rempli, à envoyer en un clic.

Jusqu'ici, un utilisateur bloqué devait photographier son écran et espérer
que la fenêtre noire soit lisible. Le rapport rassemble tout seul ce qui sert
réellement au diagnostic — version, macOS, emplacement du dossier, état de
l'environnement, dernières lignes du journal — et ouvre un mail déjà rédigé.

Tout ce qui sort d'ici part dans un mail : le contenu est expurgé des
secrets, car le cookie LinkedIn vaut un accès au compte de la personne.
"""

import json
import os
import platform
import re
import subprocess
import sys
import urllib.parse
from datetime import datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


def chemin_journal() -> Path:
    """Le fichier journal, en chemin absolu : celui que montre la page Journal.

    `ScraperConfig.LOG_FILE` est relatif (« scraper.log ») : on le rattache
    au dossier de l'application plutôt qu'au dossier courant, qui dépend de
    la façon dont l'application a été lancée.
    """
    from config import ScraperConfig

    chemin = Path(ScraperConfig.LOG_FILE).expanduser()
    return chemin if chemin.is_absolute() else RACINE / chemin


FICHIER_JOURNAL = chemin_journal()
LIGNES_JOURNAL = 12

# Émojis et pictogrammes en tête de message (« 🚀 Lancement… ») : du bruit
# dans un mail. Seuls les pictogrammes sont retirés, pas la ponctuation.
_PICTOGRAMMES = "\U0001F000-\U0001FAFF←-⇿⌀-⏿①-⓿■-➿⬀-⯿️‍"
_EN_TETE = re.compile(r"^(?P<tete>.*? - (?:DEBUG|INFO|WARNING|ERROR|CRITICAL) - )?"
                      rf"[{_PICTOGRAMMES}]+\s*")


def sans_emoji_de_tete(ligne: str) -> str:
    """« … - INFO - 🚀 Lancement » → « … - INFO - Lancement » (ligne sans en-tête aussi)."""
    return _EN_TETE.sub(lambda m: m.group("tete") or "", ligne, count=1)

# Le cookie li_at, les clés Fernet et tout jeton de la même famille. On masque
# par la forme plutôt que par la provenance : un futur message de log pourrait
# en recracher un sans qu'on y pense.
_SECRETS = (
    re.compile(r"(li_at\s*[=:]\s*)\S+", re.I),
    re.compile(r"\bAQED[A-Za-z0-9_\-]{10,}=*"),
    re.compile(r"\b[A-Za-z0-9_\-]{40,}=*\b"),
)


def expurger(texte: str) -> str:
    """Remplace les secrets reconnaissables par une marque visible."""
    sortie = texte or ""
    sortie = _SECRETS[0].sub(r"\1[masqué]", sortie)
    for motif in _SECRETS[1:]:
        sortie = motif.sub("[masqué]", sortie)
    return sortie


def _commande(args) -> str:
    try:
        return subprocess.run(
            args, capture_output=True, text=True, timeout=5
        ).stdout.strip() or "inconnu"
    except Exception:
        return "inconnu"


def _fin_du_journal() -> str:
    try:
        lignes = FICHIER_JOURNAL.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(sans_emoji_de_tete(l) for l in lignes[-LIGNES_JOURNAL:]) or "(journal vide)"
    except Exception:
        return "(journal introuvable)"


def rapport(erreur: str = None) -> str:
    """Le texte du rapport, prêt à être envoyé — expurgé."""
    from version import get_version

    lignes = [
        "We.Reach — rapport de problème",
        "",
        f"Version      : {get_version()}",
        f"macOS        : {_commande(['sw_vers', '-productVersion'])}",
        f"Mac          : {_commande(['sysctl', '-n', 'hw.model'])}",
        f"Python       : {platform.python_version()}",
        f"Dossier      : {RACINE}",
        f"Date         : {datetime.now():%Y-%m-%d %H:%M}",
        "",
        "Problème signalé :",
        erreur or "(aucun message, signalement manuel)",
        "",
        f"Dernières lignes du journal ({LIGNES_JOURNAL}) :",
        _fin_du_journal(),
    ]
    return expurger("\n".join(lignes))


def lien_mailto(destinataire: str, corps: str, sujet: str = None) -> str:
    """URL mailto ouvrant un message pré-rempli dans le client par défaut."""
    from version import get_version

    params = urllib.parse.urlencode(
        {
            "subject": sujet or f"We.Reach {get_version()} — problème",
            "body": corps,
        },
        quote_via=urllib.parse.quote,
    )
    return f"mailto:{destinataire}?{params}"


# Navigateurs susceptibles de s'etre empares des liens mailto. Chrome le fait
# volontiers a l'installation, et avale ensuite le lien sans rien afficher :
# `open` reussit, et rien ne s'ouvre.
_NAVIGATEURS = ("chrome", "safari", "firefox", "arc", "edge", "opera", "brave")


def _gestionnaire_mailto() -> str:
    """Identifiant du logiciel que macOS a désigné pour les liens mailto.

    Lu en JSON via plutil plutôt qu'en analysant la sortie texte de
    `defaults` : l'entrée qui porte `mailto` contient elle-même un
    sous-dictionnaire, ce qu'une expression régulière lit de travers.
    """
    try:
        sortie = subprocess.run(
            ["sh", "-c",
             "defaults export com.apple.LaunchServices/"
             "com.apple.launchservices.secure - | plutil -convert json -o - -"],
            capture_output=True, text=True, timeout=5,
        ).stdout
        for entree in json.loads(sortie).get("LSHandlers", []):
            if entree.get("LSHandlerURLScheme") == "mailto":
                return str(entree.get("LSHandlerRoleAll", "")).lower()
    except Exception:
        pass
    return ""


def ouvrir_mail(lien: str) -> bool:
    """Ouvre un lien mailto dans un vrai logiciel de messagerie.

    `st.link_button` laissait le navigateur décider, et Chrome détourne
    volontiers les mailto vers un webmail. Mais passer par `open` ne suffit
    pas non plus : macOS peut avoir désigné un navigateur comme gestionnaire
    des mailto — c'était le cas ici — et le lien disparaissait en silence,
    `open` renvoyant pourtant 0.

    On ne force Mail que dans ce cas. Quelqu'un ayant choisi Outlook garde
    Outlook : on contourne un navigateur, pas le choix de la personne.

    Retourne False sans rien faire hors macOS : sur un déploiement serveur,
    `open` s'exécuterait sur le serveur et non chez la personne.
    """
    if sys.platform == "win32":
        try:
            os.startfile(lien)  # messagerie par défaut de Windows
            return True
        except Exception:
            return False
    if sys.platform != "darwin":
        return False

    gestionnaire = _gestionnaire_mailto()
    detourne = any(nom in gestionnaire for nom in _NAVIGATEURS)
    commande = ["open", "-a", "Mail", lien] if detourne else ["open", lien]

    try:
        return subprocess.run(
            commande, capture_output=True, timeout=15
        ).returncode == 0
    except Exception:
        return False
