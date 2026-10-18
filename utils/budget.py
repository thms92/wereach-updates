# -*- coding: utf-8 -*-
"""Budget d'invitations du jour, tel que le moteur le compte.

Le moteur plafonne les invitations avec `DailyLimitsTracker`, dont le
compteur vit dans `<config_dir>/daily_limits.json` (un par personne). La
base de données compte aussi les invitations du jour, mais c'est le fichier
du moteur qui bloque réellement : l'interface lit donc celui-là, pour que
la jauge affichée et l'arrêt effectif ne divergent jamais.
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
