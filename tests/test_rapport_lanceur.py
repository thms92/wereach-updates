# -*- coding: utf-8 -*-
"""Le rapport de problème côté lanceur, en shell pur.

Il doit tenir sans Python : la panne la plus fréquente est précisément
« python: command not found ».
"""

import re
import subprocess
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
LANCEUR = RACINE / "LinkedIn Scraper Pro Advanced.command"


def _fonction(nom: str) -> str:
    source = LANCEUR.read_text(encoding="utf-8")
    bloc = re.search(rf"^{nom}\(\) \{{.*?^\}}", source, re.S | re.M)
    assert bloc, f"fonction {nom} introuvable dans le lanceur"
    return bloc.group(0)


def _executer(script: str, *args, cwd=None) -> str:
    return subprocess.run(
        ["bash", "-c", script, "--", *args], cwd=cwd or RACINE,
        capture_output=True, text=True,
    ).stdout


# --- L'adresse ne doit pas diverger ---------------------------------------


def test_l_adresse_de_support_est_la_meme_des_deux_cotes():
    """Le lanceur duplique l'adresse (il ne peut pas lire du Python quand
    Python manque). Les deux copies doivent rester synchronisées."""
    from config import EMAIL_SUPPORT

    trouvee = re.search(r'^EMAIL_SUPPORT="([^"]+)"', LANCEUR.read_text(encoding="utf-8"), re.M)
    assert trouvee, "EMAIL_SUPPORT introuvable dans le lanceur"
    assert trouvee.group(1) == EMAIL_SUPPORT


# --- Encodage sans Python --------------------------------------------------


def test_l_encodage_survit_aux_accents_et_aux_esperluettes():
    # Une esperluette non encodée couperait le corps du mail ; un accent mal
    # encodé le rendrait illisible.
    script = _fonction("urlencode") + '\nurlencode "$1"\n'
    assert _executer(script, "été & là") == "%C3%A9t%C3%A9%20%26%20l%C3%A0"


def test_l_encodage_n_utilise_pas_python():
    corps = _fonction("urlencode")
    assert "python" not in corps.lower()


# --- Contenu du diagnostic -------------------------------------------------


def test_le_diagnostic_porte_de_quoi_comprendre():
    script = _fonction("diagnostic") + '\ndiagnostic "$1"\n'
    sortie = _executer(script, "python: command not found")
    for attendu in ("Version", "macOS", "Mac", "Dossier", "Date",
                    "python: command not found", "journal"):
        assert attendu in sortie, f"« {attendu} » manque au diagnostic"


def test_le_diagnostic_tient_sans_journal(tmp_path):
    script = _fonction("diagnostic") + '\ndiagnostic "une erreur"\n'
    sortie = _executer(script, cwd=tmp_path)
    assert "journal introuvable" in sortie
    assert "une erreur" in sortie


def test_python_sans_droits_administrateur():
    """L'installeur .pkg exigeait un administrateur : échec réel le 2026-10-22."""
    texte = LANCEUR.read_text(encoding="utf-8")
    assert "with administrator privileges" not in texte
    assert "python-build-standalone" in texte and "install_only.tar.gz" in texte
