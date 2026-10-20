# -*- coding: utf-8 -*-
"""Invitations du jour, telles que le moteur les compte.

La limite de 20 par jour est CONSEILLÉE, pas bloquante (décision du
2026-10-20) : l'outil prévient quand un envoi la dépasse, il ne refuse
jamais d'inviter.

Le moteur compte les invitations avec `DailyLimitsTracker`, dans
`<config_dir>/daily_limits.json` (un par personne). La base de données les
compte aussi, mais c'est le compteur du moteur que l'interface lit, pour
que la jauge affichée et le compte réel ne divergent jamais.
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


def budget_du_jour(config_dir: str) -> Budget:
    """Invitations envoyées aujourd'hui et plafond, pour cette personne."""
    suivi = DailyLimitsTracker(
        max_invitations=ScraperConfig.MAX_INVITATIONS_PER_DAY,
        limits_file=os.path.join(str(config_dir), "daily_limits.json"),
    )
    return Budget(utilisees=suivi.invitations_today,
                  plafond=ScraperConfig.MAX_INVITATIONS_PER_DAY)


def message_depassement(n_prevues: int, utilisees: int, plafond: int):
    """Avertissement si `n_prevues` invitations font dépasser la limite
    conseillée, sinon None. Le texte dit que rien n'est bloqué."""
    total = max(int(utilisees), 0) + max(int(n_prevues), 0)
    if plafond <= 0 or n_prevues <= 0 or total <= plafond:
        return None
    return (f"Avec cet envoi, vous en serez à {total} invitations aujourd'hui, "
            f"au-delà de la limite conseillée de {plafond}. Rien n'est bloqué, "
            "mais le risque de restriction de votre compte LinkedIn augmente.")

