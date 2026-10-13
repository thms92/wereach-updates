# -*- coding: utf-8 -*-
"""Le lanceur doit reconstruire un environnement Python cassé.

Une montée de version de macOS laisse le dossier `.venv` en place mais rend
son interpréteur introuvable. Le lanceur ne testait que l'existence du
dossier : il sautait donc la reconstruction, sautait l'installation des
dépendances (le marqueur .setup_done étant là lui aussi), et échouait sur
`python: command not found`. L'utilisatrice n'avait d'autre issue que de
tout réinstaller — huit fois, dans un cas réel.
"""

import re
import subprocess
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
LANCEUR = RACINE / "LinkedIn Scraper Pro Advanced.command"


def _venv_ok(cible: str, cwd: Path) -> bool:
    """Exécute la fonction venv_ok du lanceur, telle qu'elle est livrée."""
    source = LANCEUR.read_text(encoding="utf-8")
    bloc = re.search(r"^venv_ok\(\) \{.*?^\}", source, re.S | re.M)
    assert bloc, "fonction venv_ok introuvable dans le lanceur"
    script = f'{bloc.group(0)}\nvenv_ok "{cible}"\n'
    return subprocess.run(
        ["bash", "-c", script], cwd=cwd, capture_output=True
    ).returncode == 0


def test_un_environnement_sain_est_reconnu():
    # Le venv de developpement du depot : interpreteur vivant, paquets presents.
    # Si ce test echoue, le lanceur reconstruirait a CHAQUE demarrage.
    assert _venv_ok("venv", RACINE)


def test_un_environnement_absent_est_detecte(tmp_path):
    assert not _venv_ok(".venv", tmp_path)


def test_un_interpreteur_mort_est_detecte(tmp_path):
    # Reproduit l'etat laisse par une mise a jour de macOS : le dossier est
    # la, le lien vers Python ne pointe plus sur rien.
    subprocess.run(["python3", "-m", "venv", ".venv"], cwd=tmp_path, check=True)
    for nom in Path(tmp_path / ".venv" / "bin").glob("python*"):
        nom.unlink()
    (tmp_path / ".venv" / "bin" / "python").symlink_to("/introuvable/python3")

    assert not _venv_ok(".venv", tmp_path)


def test_un_environnement_incomplet_est_detecte(tmp_path):
    # Installation interrompue : l'interpreteur tourne mais les paquets
    # manquent. Le marqueur .setup_done empechait aussi de le rattraper.
    subprocess.run(["python3", "-m", "venv", ".venv"], cwd=tmp_path, check=True)

    assert not _venv_ok(".venv", tmp_path)
