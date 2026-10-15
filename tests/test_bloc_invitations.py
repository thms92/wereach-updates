# -*- coding: utf-8 -*-
"""Le bloc « récupérer et inviter » partagé par Profils similaires et Veille.

Les garde-fous sont les mêmes partout : case décochée par défaut, plafond du
jour vérifié avant l'envoi. Ce test les fige au niveau du bloc ; les tests
de l'onglet Profils similaires, inchangés, prouvent le branchement.
"""

import ast
from pathlib import Path


def test_profils_similaires_utilise_le_bloc_partage():
    source = Path("app_advanced.py").read_text(encoding="utf-8")
    appels = [n for n in ast.walk(ast.parse(source))
              if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "bloc_recuperer_inviter"]
    assert appels, "l'onglet Profils similaires doit appeler bloc_recuperer_inviter"
    assert "remaining_invitations" not in source, "le plafond ne doit plus être recodé dans app_advanced.py"


def test_le_bloc_porte_les_garde_fous():
    source = Path("ui/invitations.py").read_text(encoding="utf-8")
    assert "remaining_invitations" in source
    assert 'setdefault(f"{prefixe}_inviter", False)' in source


def test_le_nom_d_export_est_un_parametre():
    source = Path("ui/invitations.py").read_text(encoding="utf-8")
    assert 'nom_export: str = "profils_similaires"' in source
    assert 'f"{nom_export}_{datetime' in source
    assert "profils_similaires_{" not in source
