# -*- coding: utf-8 -*-
"""Une seule instance de We.Reach à la fois.

Double-cliquer le lanceur alors que l'outil tourne déjà remplaçait les
fichiers sous le processus en cours : celui-ci rechargeait le nouveau
`app_advanced.py` avec l'ancien `config` encore en mémoire, d'où un
`ImportError` incompréhensible. Et la nouvelle instance, ne pouvant prendre
le port déjà occupé, se rabattait ailleurs — l'utilisateur continuait donc
de voir l'ancienne version dans son navigateur.
"""

import re
import subprocess
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
LANCEUR = RACINE / "LinkedIn Scraper Pro Advanced.command"
BOOTSTRAP_SOURCE = RACINE / "make_package.sh"

MOTIF_TEST = "wereach-sentinelle-de-test"


def _fonction(nom: str, source: Path = LANCEUR) -> str:
    bloc = re.search(rf"^{nom}\(\) \{{.*?^\}}", source.read_text(encoding="utf-8"), re.S | re.M)
    assert bloc, f"fonction {nom} introuvable dans {source.name}"
    return bloc.group(0)


def test_une_instance_en_cours_est_arretee():
    sentinelle = subprocess.Popen(["/bin/sh", "-c", f"exec -a {MOTIF_TEST} sleep 60"])
    time.sleep(0.4)
    try:
        script = _fonction("arreter_instance_existante") + f'\narreter_instance_existante "{MOTIF_TEST}"\n'
        subprocess.run(["bash", "-c", script], capture_output=True, timeout=30)
        assert sentinelle.poll() is not None or sentinelle.wait(timeout=10) is not None
    finally:
        sentinelle.kill()


def test_sans_instance_en_cours_rien_ne_casse():
    script = _fonction("arreter_instance_existante") + '\narreter_instance_existante "motif-qui-n-existe-pas"; echo OK\n'
    r = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=30)
    assert "OK" in r.stdout


def test_le_garde_fou_est_pose_aux_deux_endroits():
    """Le runner interne atteint les installations déjà en place par la mise à
    jour ; le bootstrap du zip, lui, n'est jamais mis à jour — il doit donc
    naître avec le garde-fou, et l'appliquer AVANT de remplacer les fichiers."""
    assert "arreter_instance_existante" in LANCEUR.read_text(encoding="utf-8")
    bootstrap = BOOTSTRAP_SOURCE.read_text(encoding="utf-8")
    assert "arreter_instance_existante" in bootstrap
