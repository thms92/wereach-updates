# -*- coding: utf-8 -*-
"""Outillage commun aux tests qui exécutent réellement l'application.

Pourquoi : `app_advanced.py` commence par une porte d'authentification. Dès que
`config/access.json` existe — donc sur toute installation déployée — l'app
affiche son écran de connexion puis appelle `st.stop()`. Tout ce qui suit
(navigation, pages) n'est jamais exécuté, et un test qui se contente de
`assert not at.exception` passe sans avoir rien chargé.

`lancer_app()` franchit la porte en fournissant une identité déjà connectée, et
`verifier_page_affichee()` refuse explicitement un rendu resté sur l'écran de
connexion.
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from utils.app_auth import ACCESS_FILE, set_access_password
from utils.user_context import user_paths_for

APP = Path(__file__).resolve().parents[1] / "app_advanced.py"

# Identité dédiée aux tests : ses données vivent sous data/users/<hash> et ne
# touchent donc jamais au cookie ni à la base de l'utilisateur réel.
EMAIL_DE_TEST = "tests@wefiit.com"

TITRE_ECRAN_CONNEXION = "🔒 Connexion"


def chemins_de_test():
    """Chemins isolés (base, cookie, file) de l'utilisateur de test."""
    return user_paths_for(EMAIL_DE_TEST)


def lancer_app(page: str, authentifier: bool = True, timeout: int = 120) -> AppTest:
    """Exécute l'app sur la page demandée.

    authentifier=False reproduit un visiteur non connecté : sur une
    installation où un mot de passe d'accès est configuré, l'app s'arrête
    alors sur l'écran de connexion.
    """
    at = AppTest.from_file(str(APP), default_timeout=timeout)
    if authentifier:
        at.session_state["auth_email"] = EMAIL_DE_TEST
    at.session_state["page"] = page
    at.run()
    return at


def verifier_page_affichee(at: AppTest, page: str) -> None:
    """Échoue si l'app n'a pas rendu la page demandée.

    Trois garanties, dans l'ordre où l'app les franchit :
    1. aucune exception,
    2. l'écran de connexion n'a pas pris la place de l'application,
    3. la navigation *et* le corps de la page ont bien été rendus.
    """
    assert not at.exception, [str(e.value) for e in at.exception]

    sous_titres = [s.value for s in at.subheader]
    assert TITRE_ECRAN_CONNEXION not in sous_titres, (
        "l'app s'est arrêtée sur l'écran de connexion : la page n'a pas été chargée"
    )

    cles_nav = [b.key for b in at.sidebar.button]
    assert f"nav_{page}" in cles_nav, (
        f"la navigation n'a pas été rendue (boutons trouvés : {cles_nav})"
    )

    assert at.header, "aucun en-tête : le corps de la page n'a pas été rendu"
    assert at.session_state["page"] == page


@pytest.fixture
def acces_configure():
    """Simule une installation déployée : config/access.json existe.

    Le fichier éventuellement présent est restauré à l'identique en sortie.
    """
    chemin = Path(ACCESS_FILE)
    sauvegarde = chemin.read_bytes() if chemin.exists() else None
    set_access_password("mot-de-passe-de-test")
    try:
        yield chemin
    finally:
        if sauvegarde is None:
            chemin.unlink(missing_ok=True)
        else:
            chemin.write_bytes(sauvegarde)
