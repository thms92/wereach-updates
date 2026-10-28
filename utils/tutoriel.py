# -*- coding: utf-8 -*-
"""Tutoriel guidé : quoi montrer, dans quel ordre, et s'il a déjà été vu.

Module pur (aucun Streamlit). Les textes viennent mot pour mot de
docs/superpowers/specs/2026-10-20-tutoriel-design.md. Chaque étape vise un
élément par un sélecteur CSS (`cible`, plusieurs séparés par des virgules :
le premier présent gagne), éventuellement restreint à celui dont le texte
contient `contient` ; `page` est la clé interne de la page (PAGES de
app_advanced.py) à ouvrir avant, `onglet` le libellé d'onglet à ouvrir.
Sans cible, ou cible introuvable, la bulle s'affiche au centre.
"""

from datetime import date
from pathlib import Path

FICHIER_VU = "tutoriel_vu.txt"

_TDB, _RECH, _MSG, _HIST, _JOURNAL = (
    "📊 Dashboard", "🔍 Recherche", "✉️ Messages", "💾 Historique", "📜 Logs")


def _etape(titre, texte, page=None, cible=None, contient=None, onglet=None):
    return {"page": page, "cible": cible, "contient": contient, "onglet": onglet,
            "titre": titre, "texte": texte}


ETAPES = [
    _etape("Bienvenue sur We.Reach",
           "We.Reach vous aide à trouver les bonnes personnes sur LinkedIn, à les inviter "
           "sans risque pour votre compte, et à savoir qui a accepté. Deux minutes pour "
           "faire le tour ?"),
    _etape("Le menu",
           "Cinq pages, dans l'ordre où vous vous en servirez : votre journée commence au "
           "Tableau de bord.",
           cible=".st-key-nav_menu"),
    _etape("Vos invitations du jour",
           "20 invitations par jour au plus, pour protéger votre compte LinkedIn : une fois "
           "atteintes, l'outil n'invite plus et vous pourrez reprendre demain. Juste dessous, "
           "les pages LinkedIn du jour (60 au plus).",
           cible='section[data-testid="stSidebar"] .wf-jauge--invitations'),
    _etape("Ce qui vous attend",
           "Chaque matin, ouvrez le Tableau de bord : il vous dit qui a accepté et ce qui "
           "attend une réponse.",
           page=_TDB, cible='[class*="st-key-wf_carte_"], .wf-action, .wf-vide'),
    _etape("Vos chiffres",
           "Invitations, acceptations, messages : vos chiffres sur la période choisie, "
           "filtrables par école, entreprise et poste.",
           page=_TDB, cible=".st-key-tdb_chiffres, .wf-vide"),
    _etape("Votre session LinkedIn",
           "À faire une seule fois : connectez votre session LinkedIn ici. Sans elle, "
           "aucune recherche ne peut partir.",
           page=_RECH, cible=".st-key-session_ligne, .st-key-premiere_connexion, .st-key-session_edition"),
    _etape("Deux façons de chercher",
           "Par critères (mots-clés, entreprises, écoles, secteurs), ou à partir d'un "
           "profil qui vous a plu : LinkedIn propose ses profils similaires.",
           page=_RECH, cible='.stTabs [data-baseweb="tab-list"]'),
    _etape("Chercher, choisir, puis inviter",
           "La recherche n'envoie rien : vous choisissez ensuite les profils à inviter, "
           "et un récapitulatif vous demande de confirmer avant tout envoi.",
           page=_RECH, onglet="Par critères", cible=".st-key-btn_rechercher"),
    _etape("Relancer ceux qui ont accepté",
           "Vérifiez qui a accepté vos invitations, puis écrivez-leur en une fois : "
           "sélectionnez, rédigez, confirmez.",
           page=_MSG, cible='[data-testid="stMain"] h2', contient="Vérifier qui a accepté"),
    _etape("Tout retrouver",
           "Tous les profils trouvés sont ici : cherchez, filtrez par école ou par "
           "période, exportez en Excel.",
           page=_HIST, cible=".st-key-hist_recherche"),
    _etape("Ce que l'outil a fait",
           "Le Journal raconte ce que We.Reach a fait. En cas de souci, « Signaler un "
           "problème » prépare un mail avec tout le nécessaire.",
           page=_JOURNAL, cible='[data-testid="stMain"] h1'),
    _etape("C'est parti",
           "Vous pouvez revoir ce tutoriel à tout moment ici. Bonne prospection !",
           cible=".st-key-btn_tutoriel"),
]

TEXTE_BIENVENUE_MAJ = (
    "We.Reach a été mis à jour : nouvelle apparence, nouvelles pages. Deux minutes "
    "pour faire le tour ?")


def tutoriel_a_afficher(config_dir) -> bool:
    """Vrai tant que la personne n'a ni terminé ni passé le tutoriel."""
    return not (Path(config_dir) / FICHIER_VU).exists()


def marquer_vu(config_dir) -> None:
    """Mémorise que le tutoriel a été vu (terminé ou passé)."""
    dossier = Path(config_dir)
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / FICHIER_VU).write_text(date.today().isoformat(), encoding="utf-8")


def etapes_pour(mise_a_jour: bool) -> list:
    """Les étapes à jouer ; l'accueil change pour qui utilisait déjà l'outil."""
    etapes = [dict(e) for e in ETAPES]
    if mise_a_jour:
        etapes[0]["texte"] = TEXTE_BIENVENUE_MAJ
    return etapes
