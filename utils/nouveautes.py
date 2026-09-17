# -*- coding: utf-8 -*-
"""Annonce des nouveautés au lancement, une seule fois par version et par personne.

Le texte vit dans `NOUVEAUTES.md` à la racine, une section `## <version>` par
publication. Ce fichier part avec l'application (contrairement à `docs/`, que
`make_package.sh` retire du package).

La dernière version vue est mémorisée dans le dossier de config de chaque
utilisateur, à côté de son cookie : `config/` est exclu du rsync de mise à
jour, donc la mémoire survit aux publications.
"""

from pathlib import Path

FICHIER_NOTES = "NOUVEAUTES.md"
_FICHIER_VU = "derniere_version_vue.txt"


def _cle(version: str) -> tuple:
    """Version en tuple d'entiers, pour comparer 1.10.0 > 1.9.0 correctement."""
    morceaux = []
    for part in (version or "").strip().split("."):
        if not part.isdigit():
            break
        morceaux.append(int(part))
    return tuple(morceaux)


def lire_sections(texte: str) -> dict:
    """Index `version -> corps` des sections `## <version>` du fichier."""
    sections: dict = {}
    version_courante = None
    lignes_courantes: list = []

    for ligne in (texte or "").splitlines():
        if ligne.startswith("## "):
            if version_courante is not None:
                sections[version_courante] = "\n".join(lignes_courantes).strip()
            titre = ligne[3:].strip()
            version_courante = titre if _cle(titre) else None
            lignes_courantes = []
        elif version_courante is not None:
            lignes_courantes.append(ligne)

    if version_courante is not None:
        sections[version_courante] = "\n".join(lignes_courantes).strip()
    return sections


def notes_depuis(texte: str, version_actuelle: str, derniere_vue: str) -> str:
    """Notes cumulées de `derniere_vue` (exclue) à `version_actuelle` (incluse).

    Cumulatif à dessein : quelqu'un qui n'ouvre pas l'application pendant
    quelques semaines peut sauter une version, et ne doit rien rater.
    """
    plancher, plafond = _cle(derniere_vue), _cle(version_actuelle)
    retenues = [
        (_cle(v), v, corps)
        for v, corps in lire_sections(texte).items()
        if plancher < _cle(v) <= plafond
    ]
    retenues.sort(reverse=True)  # la plus récente en premier
    return "\n\n".join(f"## {v}\n{corps}" for _, v, corps in retenues)


# Traces d'un usage antérieur dans le dossier de config. Servent à
# reconnaître quelqu'un qui utilisait déjà l'application avant que la mémoire
# des versions n'existe : sans ça, tous les utilisateurs en place seraient
# pris pour des nouveaux venus et rateraient l'annonce de cette version-là.
_MARQUEURS_USAGE = ("cookie.txt", "queue.json")


def usage_anterieur(config_dir) -> bool:
    """True si cette personne se servait déjà de l'application."""
    dossier = Path(config_dir)
    return any((dossier / nom).exists() for nom in _MARQUEURS_USAGE)


def version_vue(config_dir) -> str:
    """Dernière version annoncée à cette personne, ou None si jamais."""
    chemin = Path(config_dir) / _FICHIER_VU
    try:
        return chemin.read_text(encoding="utf-8").strip() or None
    except Exception:
        return None


def marquer_vue(config_dir, version: str) -> None:
    """Mémorise la version comme déjà annoncée."""
    try:
        dossier = Path(config_dir)
        dossier.mkdir(parents=True, exist_ok=True)
        (dossier / _FICHIER_VU).write_text(f"{version}\n", encoding="utf-8")
    except Exception:
        pass  # l'annonce reparaîtra au prochain lancement : sans gravité


def doit_annoncer(config_dir, version_actuelle: str, texte: str) -> str:
    """Notes à afficher maintenant, ou None s'il n'y a rien à annoncer.

    Rend None dans trois cas : arrivée d'un vrai nouveau venu (dossier de
    config vierge — les « nouveautés » d'une version qu'il n'a jamais connue
    ne lui apprendraient rien), version déjà vue, ou version publiée sans
    notes — pour ne jamais ouvrir une fenêtre vide.

    Mémorise systématiquement la version courante : l'annonce ne se répète
    pas, même si la personne ferme l'application sans la lire.
    """
    deja_vue = version_vue(config_dir)
    marquer_vue(config_dir, version_actuelle)

    if deja_vue is None:
        if not usage_anterieur(config_dir):
            return None
        # Utilisateur déjà installé, arrivé avant que la mémoire n'existe :
        # son passé est inconnu, on lui montre la version qu'il découvre.
        corps = lire_sections(texte).get(version_actuelle)
        return f"## {version_actuelle}\n{corps}" if corps else None
    return notes_depuis(texte, version_actuelle, deja_vue) or None


def charger_notes(racine=None) -> str:
    """Contenu de NOUVEAUTES.md, ou chaîne vide s'il est absent."""
    base = Path(racine) if racine else Path(__file__).resolve().parent.parent
    try:
        return (base / FICHIER_NOTES).read_text(encoding="utf-8")
    except Exception:
        return ""
