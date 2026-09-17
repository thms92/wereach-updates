# -*- coding: utf-8 -*-
"""Chaque page du menu doit se charger sans lever d'exception.

Ce test est le filet qui protège les déplacements de blocs entre pages. Pour
qu'il protège quelque chose, il doit exécuter la page : `verifier_page_affichee`
refuse un rendu resté sur l'écran de connexion (cas de toute installation où
`config/access.json` existe), et `lancer_app` franchit cette porte.
"""

import pytest

from tests.conftest import lancer_app, verifier_page_affichee
from tests.test_navigation import arbre_app, pages_du_menu

PAGES = pages_du_menu(arbre_app())


@pytest.mark.parametrize("page", PAGES)
def test_la_page_se_charge_sans_exception(page):
    verifier_page_affichee(lancer_app(page), page)


@pytest.mark.parametrize("page", PAGES)
def test_la_page_se_charge_aussi_sur_une_installation_deployee(page, acces_configure):
    """Un mot de passe d'accès configuré ne doit pas vider le test de fumée."""
    verifier_page_affichee(lancer_app(page), page)


def test_le_test_de_fumee_vire_au_rouge_devant_l_ecran_de_connexion(acces_configure):
    """La propriété non négociable : l'écran de connexion fait échouer le test.

    Sans cette garantie, les tests ci-dessus repasseraient au vert sur un poste
    déployé sans avoir chargé la moindre page (`at.exception` vide parce que
    l'app s'est arrêtée avant la navigation).
    """
    at = lancer_app("📊 Dashboard", authentifier=False)

    # L'app s'est bien arrêtée sur l'écran de connexion…
    assert [s.value for s in at.subheader] == ["🔒 Connexion"]
    assert not at.exception

    # … et la vérification du test de fumée le refuse.
    with pytest.raises(AssertionError):
        verifier_page_affichee(at, "📊 Dashboard")
