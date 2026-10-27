# -*- coding: utf-8 -*-
import pytest

from utils.alerte_linkedin import nature_page


@pytest.mark.parametrize("url,texte,statut,attendu", [
    ("https://www.linkedin.com/checkpoint/challenge/AgGun67__rMi0g", "", 200, "alerte"),
    ("https://www.linkedin.com/authwall?trk=x", "", 200, "session"),
    ("https://www.linkedin.com/uas/login?session_redirect=x", "", 200, "session"),
    ("https://www.linkedin.com/in/ana-test/", "Compte restreint aux membres", 200, None),
    ("https://www.linkedin.com/feed/", "", 429, "alerte"),
    ("https://www.linkedin.com/in/ana-test/", "", 999, "alerte"),
    ("https://www.linkedin.com/some/other/",
     "Nous avons remarqué une activité inhabituelle sur votre compte", 200, "alerte"),
    ("https://www.linkedin.com/search/results/people/?keywords=x", "", 200, None),
    ("https://www.linkedin.com/login", "", 200, "session"),
    ("https://www.linkedin.com/login/fr", "", 200, "session"),
    # Une requête ou un nom proche ne suffit pas
    ("https://www.linkedin.com/feed/?session_redirect=/login", "", 200, None),
    ("https://www.linkedin.com/in/loginov/", "", 200, None),
    # L'alerte passe avant la session
    ("https://www.linkedin.com/login", "", 429, "alerte"),
    ("https://www.linkedin.com/some/other/", "Let's do a quick security check", 200, "alerte"),
    ("https://www.linkedin.com/some/other/", "", None, None),
])
def test_nature_page(url, texte, statut, attendu):
    assert nature_page(url, texte, statut) == attendu


def test_mot_restreint_sur_un_profil_n_est_pas_une_alerte():
    assert nature_page("https://www.linkedin.com/in/ana-test/",
                       "Votre compte a été restreint", 200) is None
    # Hors profil, la même phrase est bien une alerte
    assert nature_page("https://www.linkedin.com/hp/",
                       "Votre compte a été restreint", 200) == "alerte"
