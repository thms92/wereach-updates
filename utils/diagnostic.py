# -*- coding: utf-8 -*-
"""Rapport de problème pré-rempli, à envoyer en un clic.

Jusqu'ici, un utilisateur bloqué devait photographier son écran et espérer
que la fenêtre noire soit lisible. Le rapport rassemble tout seul ce qui sert
réellement au diagnostic — version, macOS, emplacement du dossier, état de
l'environnement, dernières lignes du journal — et ouvre un mail déjà rédigé.

Tout ce qui sort d'ici part dans un mail : le contenu est expurgé des
secrets, car le cookie LinkedIn vaut un accès au compte de la personne.
"""

import platform
import re
import subprocess
import sys
import urllib.parse
from datetime import datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
FICHIER_JOURNAL = RACINE / "scraper.log"
LIGNES_JOURNAL = 12

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
        return "\n".join(lignes[-LIGNES_JOURNAL:]) or "(journal vide)"
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


def ouvrir_mail(lien: str) -> bool:
    """Ouvre le client de messagerie par défaut du Mac sur un lien mailto.

    Un lien HTML laisserait le NAVIGATEUR décider du sort d'un `mailto:` —
    Chrome et Arc le détournent volontiers vers un webmail. L'application
    tournant sur le Mac de la personne, on passe par `open`, qui respecte le
    client par défaut du système : Mail, Outlook, peu importe lequel.

    Retourne False sans rien faire hors macOS : sur un déploiement serveur,
    `open` s'exécuterait sur le serveur et non chez la personne.
    """
    if sys.platform != "darwin":
        return False
    try:
        subprocess.run(["open", lien], check=False, timeout=10)
        return True
    except Exception:
        return False
