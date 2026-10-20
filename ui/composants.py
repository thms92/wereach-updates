# -*- coding: utf-8 -*-
"""Composants visuels We.Reach (DESIGN.md, refonte du 2026-10-18).

Chaque composant est une fonction pure qui retourne du HTML (testable sans
Streamlit), plus un `afficher_*` qui l'écrit dans la page. Les classes
`wf-*` sont stylées dans `wefiit_theme.py`. Tout texte reçu est échappé.

Le HTML tient sur une seule ligne : st.markdown traite le Markdown, et une
ligne vide ou une indentation de quatre espaces y casserait le bloc HTML.
"""
from html import escape
from typing import Iterable, Optional, Sequence, Tuple

TONS = ("ok", "attention", "danger", "neutre", "accent")

# Espace fine insécable : séparateur de milliers et avant « % » en français.
_ESPACE_FINE = " "

# Icônes dessinées (trait 1.75, 24×24, couleur héritée). Jamais d'émoji.
_TRAIT = ('xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
          'stroke="currentColor" stroke-width="1.75" stroke-linecap="round" '
          'stroke-linejoin="round" aria-hidden="true" focusable="false"')
ICONES = {
    "invitation": f'<svg {_TRAIT}><circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M19 8v6M16 11h6"/></svg>',
    "relance": f'<svg {_TRAIT}><path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/></svg>',
    "message": f'<svg {_TRAIT}><rect x="3" y="5" width="18" height="14" rx="2.5"/><path d="m4 7 8 6 8-6"/></svg>',
    "alerte": f'<svg {_TRAIT}><path d="M12 4 2.8 19.5h18.4Z"/><path d="M12 10v4.5M12 17.2v.1"/></svg>',
    "ok": f'<svg {_TRAIT}><circle cx="12" cy="12" r="9"/><path d="m8 12.5 2.7 2.7L16.5 9.5"/></svg>',
    "info": f'<svg {_TRAIT}><circle cx="12" cy="12" r="9"/><path d="M12 11v5.5M12 7.8v.1"/></svg>',
    "recherche": f'<svg {_TRAIT}><circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.4-4.4"/></svg>',
    "veille": f'<svg {_TRAIT}><path d="M4 20V6.5L12 3l8 3.5V20"/><path d="M9 20v-5h6v5M8 9h.01M12 9h.01M16 9h.01"/></svg>',
    "vide": f'<svg {_TRAIT}><path d="M3 13.5 5.5 5h13l2.5 8.5V19H3Z"/><path d="M3 13.5h5l1.5 2.5h5l1.5-2.5h5"/></svg>',
    # Une personne et une coche : quelqu'un a dit oui (le pic de réussite).
    "accepte": f'<svg {_TRAIT}><circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="m15.5 11.5 2.2 2.2 4.3-4.4"/></svg>',
}
_ICONE_PAR_TON = {"ok": "ok", "attention": "alerte", "danger": "alerte",
                  "accent": "info", "neutre": "info"}


def _verifier_ton(ton: str) -> str:
    if ton not in TONS:
        raise ValueError(f"Ton inconnu : {ton!r} (attendu : {', '.join(TONS)})")
    return ton


def _nombre(n: int) -> str:
    """1200 → « 1 200 » (espace fine insécable)."""
    return f"{n:,}".replace(",", _ESPACE_FINE)


def pluriel(n: int, singulier: str, pluriel: Optional[str] = None) -> str:
    """« 0 entreprise », « 1 entreprise », « 3 entreprises ».

    En français, 0 et 1 prennent le singulier. Sans `pluriel`, on ajoute
    un « s » au singulier.
    """
    mot = singulier if abs(n) < 2 else (pluriel or singulier + "s")
    return f"{_nombre(n)} {mot}"


# ---------------------------------------------------------------- puces

def point_direct(libelle: str = "") -> str:
    """Point pulsé « en direct » (statique si mouvement réduit).

    Sans libellé, le point est décoratif (masqué aux lecteurs d'écran).
    """
    if not libelle:
        return '<span class="wf-direct" aria-hidden="true"></span>'
    return ('<span class="wf-puce wf-puce--ok"><span class="wf-direct" aria-hidden="true"></span>'
            f'{escape(libelle)}</span>')


def puce(texte: str, ton: str = "neutre", en_direct: bool = False) -> str:
    """Pilule d'état. `en_direct=True` remplace le point fixe par un point pulsé."""
    _verifier_ton(ton)
    point = ('<span class="wf-direct" aria-hidden="true"></span>' if en_direct
             else '<span class="wf-puce__point" aria-hidden="true"></span>')
    return f'<span class="wf-puce wf-puce--{ton}">{point}{escape(texte)}</span>'


def bandeau_contexte(sous_titre: str,
                     puces: Iterable[Sequence] = ()) -> str:
    """Phrase de contexte sous le titre de page, et 1 à 3 puces d'état.

    Le titre reste un `st.title` (vrai h1). Chaque puce est (texte, ton) ou
    (texte, ton, en_direct).
    """
    rendues = "".join(puce(*p) for p in puces)
    texte = f'<p class="wf-bandeau__texte">{escape(sous_titre)}</p>' if sous_titre else "<span></span>"
    bloc_puces = f'<div class="wf-bandeau__puces">{rendues}</div>' if rendues else ""
    return f'<div class="wf-bandeau">{texte}{bloc_puces}</div>'


# ---------------------------------------------- jauge des invitations du jour

def ton_budget(utilisees: int, plafond: int) -> str:
    """« ok » sous 80 %, « attention » de 80 % à la limite, « danger » au-delà.

    La limite est conseillée, pas bloquante : « danger » signale un risque
    pour le compte LinkedIn, jamais un arrêt.
    """
    if plafond <= 0 or utilisees > plafond:
        return "danger"
    if utilisees * 100 >= plafond * 80:
        return "attention"
    return "ok"


def texte_budget(utilisees: int, plafond: int) -> str:
    """Formulation courte (puces) : « 3 invitations restantes sur 20 »,
    ou « 23 invitations (20 conseillées) » au-delà de la limite."""
    plafond = max(int(plafond), 0)
    utilisees = max(int(utilisees), 0)
    if utilisees > plafond:
        return f"{pluriel(utilisees, 'invitation')} ({plafond} conseillées)"
    restantes = plafond - utilisees
    return f"{pluriel(restantes, 'invitation restante', 'invitations restantes')} sur {plafond}"


def jauge_budget(utilisees: int, plafond: int, sur_fond_sombre: bool = False) -> str:
    """Les invitations du jour, dessinées en `plafond` crans.

    La limite (20) est CONSEILLÉE, pas bloquante. Crans consommés en orange,
    restants en accent ; à 80 % le chiffre passe en attention ; à la limite,
    une note dit qu'on peut continuer ; au-delà (danger), le chiffre montre
    le dépassement. Exposé comme `role="meter"` (valeur : restantes).
    """
    plafond = max(int(plafond), 0)
    brut = max(int(utilisees), 0)
    depasse = max(brut - plafond, 0)
    utilisees = min(brut, plafond)
    restantes = plafond - utilisees
    ton = ton_budget(brut, plafond)

    classes = f"wf-jauge wf-jauge--{ton}"
    if sur_fond_sombre:
        classes += " wf-jauge--sombre wf-sur-sombre"

    crans = "".join(
        f'<span class="wf-cran{" wf-cran--utilise" if i < utilisees else ""}" style="--i:{i}"></span>'
        for i in range(plafond)
    )
    if depasse:
        valeur = (f'<span class="wf-jauge__nombre">+{depasse}</span> au-delà'
                  f' <span class="wf-jauge__compte">des {plafond} conseillées</span>')
        note = ('<div class="wf-jauge__note">Rien n\'est bloqué, mais le risque '
                'de restriction augmente</div>')
        texte_aria = f"{pluriel(brut, 'invitation envoyée', 'invitations envoyées')}, {plafond} conseillées"
    else:
        mot = "restante" if restantes < 2 else "restantes"
        valeur = (f'<span class="wf-jauge__nombre">{restantes}</span> {mot}'
                  f' <span class="wf-jauge__compte">sur {plafond} conseillées</span>')
        note = ('<div class="wf-jauge__note">Limite conseillée atteinte : vous pouvez continuer</div>'
                if restantes == 0 and plafond > 0 else "")
        texte_aria = f"{pluriel(restantes, 'invitation restante', 'invitations restantes')} sur {plafond} conseillées"
    aria = (f'role="meter" aria-label="Invitations du jour" '
            f'aria-valuemin="0" aria-valuemax="{plafond}" aria-valuenow="{restantes}" '
            f'aria-valuetext="{escape(texte_aria)}"')
    return (
        f'<div class="{classes}" {aria}>'
        '<div class="wf-jauge__tete"><span class="wf-jauge__libelle">Invitations du jour</span></div>'
        f'<div class="wf-jauge__valeur">{valeur}</div>'
        f'<div class="wf-jauge__crans" style="--wf-crans:{max(plafond, 1)}" aria-hidden="true">{crans}</div>'
        f'{note}</div>'
    )


# ------------------------------------------------------------ entonnoir

def taux_passage(precedent: int, courant: int) -> str:
    """« 42 % » ; « — » quand l'étape précédente est vide."""
    if precedent <= 0:
        return "—"
    return f"{round(courant * 100 / precedent)}{_ESPACE_FINE}%"


def entonnoir(etapes: Sequence[Tuple[str, int]],
              titre_accessible: str = "Parcours des prospects") -> str:
    """Parcours horizontal (3 à 5 étapes) : effectif, barre proportionnelle
    au plus grand effectif, et taux de passage depuis l'étape précédente."""
    etapes = list(etapes)
    if not etapes:
        return ""
    plus_grand = max((max(int(n), 0) for _, n in etapes), default=0)
    items = []
    for i, (libelle, n) in enumerate(etapes):
        n = max(int(n), 0)
        largeur = 0 if plus_grand == 0 else max(round(n * 100 / plus_grand, 1), 2 if n else 0)
        if i == 0:
            taux = ""
        else:
            valeur = taux_passage(max(int(etapes[i - 1][1]), 0), n)
            vide = " wf-entonnoir__taux--vide" if valeur == "—" else ""
            explication = ("étape précédente vide" if valeur == "—"
                           else "de l'étape précédente")
            taux = (f'<span class="wf-entonnoir__taux{vide}">{valeur}'
                    f'<span class="wf-sr"> {explication}</span></span>')
        items.append(
            f'<li class="wf-entonnoir__etape" style="--i:{i}">'
            f'<div class="wf-entonnoir__tete"><span class="wf-entonnoir__libelle">{escape(libelle)}</span>{taux}</div>'
            f'<div class="wf-entonnoir__nombre">{_nombre(n)}</div>'
            f'<div class="wf-entonnoir__barre" aria-hidden="true"><span style="width:{largeur:g}%;--i:{i}"></span></div>'
            '</li>'
        )
    return (f'<ol class="wf-entonnoir" style="--wf-etapes:{len(etapes)}" '
            f'aria-label="{escape(titre_accessible)}">{"".join(items)}</ol>')


# --------------------------------------------------- cartes et état vide

def carte_action(titre: str, detail: str, ton: str = "neutre",
                 icone: Optional[str] = None, vedette: bool = False) -> str:
    """Ligne « À faire » : icône dessinée (selon le ton par défaut), titre, détail.

    `vedette=True` : la carte la plus forte de la liste (une réussite à
    exploiter), teintée de son ton. Une seule par liste.
    """
    _verifier_ton(ton)
    nom = icone or _ICONE_PAR_TON[ton]
    if nom not in ICONES:
        raise ValueError(f"Icône inconnue : {nom!r} (attendu : {', '.join(ICONES)})")
    detail_html = f'<div class="wf-action__detail">{escape(detail)}</div>' if detail else ""
    classes = f"wf-action wf-action--{ton}" + (" wf-action--vedette" if vedette else "")
    return (
        f'<div class="{classes}">'
        f'<span class="wf-action__icone">{ICONES[nom]}</span>'
        f'<div class="wf-action__corps"><div class="wf-action__titre">{escape(titre)}</div>{detail_html}</div>'
        '</div>'
    )


def etat_vide(titre: str, explication: str, etapes: Sequence[str] = ()) -> str:
    """État vide qui apprend : ce qui manque et comment le remplir.

    `etapes` : quelques gestes courts, numérotés, pour en sortir.
    """
    liste = ("".join(f"<li>{escape(e)}</li>" for e in etapes))
    bloc_etapes = f'<ol class="wf-vide__etapes">{liste}</ol>' if liste else ""
    return (
        f'<div class="wf-vide"><span class="wf-vide__icone">{ICONES["vide"]}</span>'
        f'<div><div class="wf-vide__titre">{escape(titre)}</div>'
        f'<p class="wf-vide__texte">{escape(explication)}</p>{bloc_etapes}</div></div>'
    )


# --------------------------------------------------- écriture dans la page

def _ecrire(html: str, conteneur=None) -> None:
    import streamlit as st
    (conteneur or st).markdown(html, unsafe_allow_html=True)


def afficher_bandeau_contexte(sous_titre: str, puces: Iterable[Sequence] = (),
                              conteneur=None) -> None:
    _ecrire(bandeau_contexte(sous_titre, puces), conteneur)


def afficher_jauge_budget(utilisees: int, plafond: int,
                          sur_fond_sombre: bool = False, conteneur=None) -> None:
    _ecrire(jauge_budget(utilisees, plafond, sur_fond_sombre), conteneur)


def afficher_entonnoir(etapes: Sequence[Tuple[str, int]], conteneur=None) -> None:
    _ecrire(entonnoir(etapes), conteneur)


def afficher_carte_action(titre: str, detail: str, ton: str = "neutre",
                          icone: Optional[str] = None, conteneur=None,
                          vedette: bool = False) -> None:
    _ecrire(carte_action(titre, detail, ton, icone, vedette), conteneur)


def afficher_etat_vide(titre: str, explication: str, conteneur=None,
                       etapes: Sequence[str] = ()) -> None:
    _ecrire(etat_vide(titre, explication, etapes), conteneur)


def afficher_puce(texte: str, ton: str = "neutre", en_direct: bool = False,
                  conteneur=None) -> None:
    _ecrire(puce(texte, ton, en_direct), conteneur)
