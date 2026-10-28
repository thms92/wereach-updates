# -*- coding: utf-8 -*-
"""Invitations et pages LinkedIn du jour, telles que le moteur les compte.

Les 20 invitations par jour sont BLOQUANTES (de nouveau depuis le
2026-10-27) : la confirmation refuse une sélection plus grande que le
reste, et le moteur n'invite plus une fois le plafond atteint. Les 60 pages
LinkedIn par jour le sont aussi (porte de navigation du moteur).

Le moteur compte avec `DailyLimitsTracker`, dans
`<config_dir>/daily_limits.json` (un par personne). La base de données
compte aussi les invitations, mais c'est le compteur du moteur que
l'interface lit, pour que la jauge affichée et le compte réel ne divergent
jamais.
"""

import os
from dataclasses import dataclass

from config import ScraperConfig
from utils.human_behavior import DailyLimitsTracker


@dataclass(frozen=True)
class Budget:
    utilisees: int
    plafond: int

    @property
    def restantes(self) -> int:
        return max(0, self.plafond - self.utilisees)

    @property
    def epuise(self) -> bool:
        return self.restantes == 0


LIMITE_INVITATIONS_ATTEINTE = ("Limite du jour atteinte : {plafond} invitations "
                               "envoyées. Vous pourrez reprendre demain.")


def _suivi(config_dir: str) -> DailyLimitsTracker:
    return DailyLimitsTracker(
        max_invitations=ScraperConfig.MAX_INVITATIONS_PER_DAY,
        max_pages=ScraperConfig.MAX_PAGES_PER_DAY,
        limits_file=os.path.join(str(config_dir), "daily_limits.json"),
    )


def budget_du_jour(config_dir: str) -> Budget:
    """Invitations envoyées aujourd'hui et plafond, pour cette personne."""
    return Budget(utilisees=_suivi(config_dir).invitations_today,
                  plafond=ScraperConfig.MAX_INVITATIONS_PER_DAY)


def budget_pages_du_jour(config_dir: str) -> Budget:
    """Pages LinkedIn consultées aujourd'hui et plafond, pour cette personne."""
    return Budget(utilisees=_suivi(config_dir).pages_today,
                  plafond=ScraperConfig.MAX_PAGES_PER_DAY)


def refus_invitations(n_prevues: int, utilisees: int, plafond: int):
    """Refus si `n_prevues` invitations dépassent le reste du jour, sinon
    None. Le texte dit combien en choisir, ou quand reprendre."""
    n_prevues = max(int(n_prevues), 0)
    restantes = max(int(plafond) - max(int(utilisees), 0), 0)
    if n_prevues <= restantes:
        return None
    if restantes == 0:
        return LIMITE_INVITATIONS_ATTEINTE.format(plafond=plafond)
    mot = "invitation" if restantes < 2 else "invitations"
    return (f"Il vous reste {restantes} {mot} aujourd'hui : "
            f"sélectionnez-en {restantes} au plus.")
