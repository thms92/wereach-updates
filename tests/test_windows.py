# -*- coding: utf-8 -*-
"""Version Windows : ce qui se vérifie depuis un Mac.

Le lanceur PowerShell ne peut pas s'exécuter ici ; on vérifie ce qui le lie
au reste (adresse de rapport, chemins, texte en ASCII) et le paquet produit.
"""

import importlib
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
LANCEUR = RACINE / "windows" / "demarrer.ps1"


def test_lanceur_meme_adresse_de_rapport_que_l_app():
    from config import EMAIL_SUPPORT
    trouvee = re.search(r'^\$EMAIL_SUPPORT = "([^"]+)"', LANCEUR.read_text(encoding="utf-8"), re.M)
    assert trouvee and trouvee.group(1) == EMAIL_SUPPORT


def test_lanceur_en_ascii():
    """Windows PowerShell 5.1 lit un .ps1 sans BOM dans l'encodage local."""
    assert LANCEUR.read_bytes().isascii()


def test_lanceur_garde_les_reglages_du_mac():
    texte = LANCEUR.read_text(encoding="utf-8")
    for attendu in ('SCRAPER_HEADLESS = "false"', 'SCRAPER_STEALTH = "false"',
                    "playwright install chromium", "LOCALAPPDATA", "WEREACH_MAJ_FAITE"):
        assert attendu in texte, attendu


def test_donnees_dans_localappdata(monkeypatch, tmp_path):
    import utils.user_context as uc
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("WEREACH_DATA_DIR", raising=False)
    assert uc.racine_donnees() == tmp_path / "We.Reach" / "data" / "users"


def test_raccourcis_windows_dans_les_etapes_de_session(monkeypatch):
    import ui.page_recherche as pr
    monkeypatch.setattr(sys, "platform", "win32")
    try:
        importlib.reload(pr)
        assert "Ctrl + Maj + I" in pr.ETAPES_SESSION and "Ctrl + C" in pr.ETAPES_SESSION
        assert "Cmd" not in pr.ETAPES_SESSION
    finally:
        monkeypatch.setattr(sys, "platform", "darwin")
        importlib.reload(pr)


def test_nom_par_defaut_sans_pwd(monkeypatch):
    import builtins
    import utils.identite as identite
    vrai_import = builtins.__import__

    def sans_pwd(nom, *a, **k):
        if nom == "pwd":
            raise ImportError
        return vrai_import(nom, *a, **k)

    monkeypatch.setattr(builtins, "__import__", sans_pwd)
    assert identite.nom_par_defaut() == ""


def test_paquet_windows(tmp_path):
    sortie = tmp_path / "We.Reach-Windows.zip"
    subprocess.run(["bash", str(RACINE / "make_package_windows.sh"), str(sortie)],
                   check=True, capture_output=True, cwd=RACINE)
    with zipfile.ZipFile(sortie) as z:
        noms = z.namelist()
        assert "We.Reach/1 - Lancer We.Reach.bat" in noms
        assert "We.Reach/0 - LIRE-MOI.txt" in noms
        assert "We.Reach/app/app_advanced.py" in noms
        assert not [n for n in noms if n.startswith("We.Reach/app/tests/")]
        bat = z.read("We.Reach/1 - Lancer We.Reach.bat")
        assert b"\r\n" in bat and b"\n" not in bat.replace(b"\r\n", b"")
        assert b"app\\windows\\demarrer.ps1" in bat
