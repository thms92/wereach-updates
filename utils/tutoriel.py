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

_TDB, _RECH, _VEILLE, _MSG, _HIST, _JOURNAL = (
    "📊 Dashboard", "🔍 Recherche", "🏢 Veille", "✉️ Messages", "💾 Historique", "📜 Logs")


def _etape(titre, texte, page=None, cible=None, contient=None, onglet=None):
    return {"page": page, "cible": cible, "contient": contient, "onglet": onglet,
            "titre": titre, "texte": texte}


ETAPES = [
    _etape("Bienvenue sur We.Reach",
           "We.Reach vous aide à trouver les bonnes personnes sur LinkedIn, à les inviter "
           "sans risque pour votre compte, et à savoir qui a accepté. Deux minutes pour "
           "faire le tour ?"),
    _etape("Le menu",
           "Six pages, dans l'ordre où vous vous en servirez : votre journée commence au "
           "Tableau de bord.",
           cible=".st-key-nav_menu"),
    _etape("Votre budget du jour",
           "20 invitations par jour, pas plus : c'est ce qui protège votre compte LinkedIn. "
           "La jauge montre ce qu'il vous reste, partout dans l'outil.",
           cible='section[data-testid="stSidebar"] .wf-jauge'),
    _etape("Ce qui vous attend",
           "Chaque matin, ouvrez le Tableau de bord : il vous dit qui a accepté, ce qui "
           "attend une réponse et ce que la veille a trouvé.",
           page=_TDB, cible='[class*="st-key-wf_carte_"], .wf-action, .wf-vide'),
    _etape("Votre parcours",
           "Trouvés, invités, acceptés, contactés : vous voyez où en sont vos prospects, "
           "et votre taux d'acceptation.",
           page=_TDB, cible="ol.wf-entonnoir, .wf-vide"),
    _etape("Votre session LinkedIn",
           "À faire une seule fois : connectez votre session LinkedIn ici. Sans elle, "
           "aucune recherche ne peut partir.",
           page=_RECH, cible=".st-key-session_ligne, .st-key-premiere_connexion, .st-key-session_edition"),
    _etape("Trois façons de chercher",
           "Candidats par école, entreprise ou secteur ; contacts chez des clients ; ou "
           "profils proches d'un profil qui vous a plu.",
           page=_RECH, cible='.stTabs [data-baseweb="tab-list"]'),
    _etape("Inviter en toute sécurité",
           "Activez les invitations si vous voulez inviter les profils trouvés. Avant "
           "tout envoi, un récapitulatif vous demande de confirmer.",
           page=_RECH, onglet="Candidats", cible=".st-key-bloc_inviter_candidat"),
    _etape("La veille de vos entreprises cibles",
           "Suivez vos entreprises cibles : à chaque passage, We.Reach y repère les "
           "personnes Product, Data et IA.",
           page=_VEILLE, cible='.stTabs [data-baseweb="tab-list"]'),
    _etape("Ajouter une entreprise",
           "Ajoutez une entreprise depuis votre fichier ou par le lien de sa page "
           "LinkedIn. Un clic sur une ligne ouvre sa fiche.",
           page=_VEILLE, onglet="Mes entreprises",
           cible='.st-key-veille_ajouter_fichier, .st-key-veille_depuis_fichier, [data-testid="stDataFrame"]'),
    _etape("Lancer un passage",
           "Lancez la veille : une fenêtre Chrome s'ouvre quelques minutes. Les nouveaux "
           "contacts apparaissent dans Nouveautés.",
           page=_VEILLE, onglet="Nouveautés", cible=".st-key-veille_lancer"),
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
